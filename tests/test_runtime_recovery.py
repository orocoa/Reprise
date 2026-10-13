"""A dead startup owner can be stopped; a live or unknown owner cannot."""
import contextlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from reprise.processes import OwnedProcessTree, ProcessCleanupError, process_identity
from reprise.runtime import RuntimeManager, read_json, write_json
from reprise.service import Reprise
from reprise.storage import locked
from test_runtime import commit_repo, fixture


SUPERVISOR = '''import json, sys, time
from pathlib import Path
from reprise.git import Repository
from reprise.runtime import RuntimeManager
from reprise.service import Reprise
directory, repository, phase = sys.argv[1:]
marker = Path(directory) / "phase-ready"
app = Reprise(directory)
project = app.projects.add(repository)
command = [sys.executable, "-c", "import time; time.sleep(120)"]
commands = {"start": command}
if phase in ("install", "build"):
    commands[phase] = [command]
if phase == "preparing":
    def materialize(*args, **kwargs):
        marker.write_text("preparing")
        time.sleep(120)
    Repository.materialize = materialize
if phase == "unpublished":
    save = RuntimeManager._save
    def pause_before_publication(self, state):
        if state.get("process_trees"):
            marker.write_text(state["process_tree"])
            time.sleep(120)
        return save(self, state)
    RuntimeManager._save = pause_before_publication
app.projects.save_recipe(project["id"], {"adapter": "command-web", "commands": commands,
                                      "readiness": {"timeout_ms": 120000}})
job = app.execute(project["id"], "run", {})
print(json.dumps(job), flush=True)
time.sleep(120)
'''


class RuntimeRecoveryTests(unittest.TestCase):
    def test_crashed_service_is_recoverable_in_every_startup_phase(self):
        for phase in ('preparing', 'install', 'build', 'starting', 'unpublished', 'legacy'):
            with self.subTest(phase=phase):
                self._crash_and_stop(phase)

    def _crash_and_stop(self, phase):
        root = fixture('runtime-recovery-' + phase)
        repo = commit_repo(root / 'repo')
        directory = root / 'state'
        script = root / 'supervisor.py'
        script.write_text(SUPERVISOR)
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
        log = (root / 'supervisor.log').open('w')
        child = subprocess.Popen([sys.executable, str(script), str(directory), str(repo.work_tree), phase],
                                 stdout=subprocess.PIPE, stderr=log, text=True, env=env)
        app, state = None, None
        try:
            job = json.loads(child.stdout.readline())
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                states = [read_json(path) for path in (directory / 'runtimes').glob('*/runtime.json')]
                if states:
                    candidate = states[0]
                    ready = ((directory / 'phase-ready').exists() if phase in ('preparing', 'unpublished')
                             else candidate.get('pid') and candidate['status'] == ('starting' if phase == 'legacy' else phase))
                    if ready:
                        state = candidate
                        break
                self.assertIsNone(child.poll(), (root / 'supervisor.log').read_text())
                time.sleep(.03)
            self.assertIsNotNone(state, 'startup did not reach requested phase')
            if phase == 'legacy':
                for key in ('startup_lock', 'owner_pid', 'owner_identity', 'job_id'):
                    state.pop(key, None)
                write_json(directory / 'runtimes' / state['id'] / 'runtime.json', state)
            # Even a different manager may not race a still-running starter.
            other = RuntimeManager(directory)
            with self.assertRaisesRegex(ValueError, '取消任务'):
                other.stop(state['id'])
            self.assertIn(other.list()[0]['status'], ('preparing', 'install', 'build', 'starting'))
            os.kill(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
            app = Reprise(directory)
            self.assertEqual(app.jobs.get(job['id'])['status'], 'failed')
            recovered = app.runtimes.list()[0]
            self.assertEqual(recovered['status'], 'interrupted')
            self.assertEqual(recovered['running'], phase != 'preparing')
            stopped = app.runtimes.stop(state['id'])
            self.assertEqual(stopped['status'], 'stopped')
            self.assertFalse(stopped['running'])
            self.assertFalse(app.runtimes.list()[0]['running'])
            for path in (directory / 'runtimes' / state['id']).glob('process-*.json'):
                metadata = read_json(path)
                self.assertIsNone(process_identity(metadata['root_pid']))
                self.assertEqual(metadata['status'], 'stopped')
            self.assertTrue((directory / 'runtimes' / state['id'] / 'runtime.json').is_file())
            if phase != 'preparing':
                self.assertTrue(Path(state['log_path']).is_file())
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            child.stdout.close()
            log.close()
            for path in (directory / 'runtimes').glob('*/process-*.json'):
                OwnedProcessTree.from_record(path).terminate()
            if app:
                app.close()

    def test_unknown_legacy_owner_remains_unconfirmed_without_signals(self):
        root = fixture('runtime-unknown-owner')
        manager = RuntimeManager(root)
        state = {'id': 'a' * 32, 'status': 'starting', 'pid': None, 'created_at': '', 'sha': 'a' * 40}
        manager._save(state)
        with patch('reprise.runtime.os.kill') as signal_process:
            self.assertEqual(manager.list()[0]['status'], 'cleanup_failed')
            for _ in range(2):
                with self.assertRaisesRegex(ProcessCleanupError, '缺少可验证'):
                    manager.stop(state['id'])
            signal_process.assert_not_called()
        self.assertEqual(read_json(manager._path(state['id']))['status'], 'starting')

    def test_failed_owner_inspection_is_not_proof_of_exit(self):
        root = fixture('runtime-unobservable-owner')
        manager = RuntimeManager(root)
        state = {'id': 'b' * 32, 'status': 'preparing', 'pid': None, 'created_at': '',
                 'owner_pid': os.getpid(), 'owner_identity': 'unavailable identity'}
        manager._save(state)
        with patch('reprise.runtime.process_identity', return_value=None):
            with self.assertRaisesRegex(ProcessCleanupError, '无法核验'):
                manager.stop(state['id'])
            self.assertEqual(manager.list()[0]['status'], 'cleanup_failed')

    def test_start_finishing_during_lock_acquisition_is_not_interrupted(self):
        root = fixture('runtime-completing-owner')
        manager = RuntimeManager(root)
        state = {'id': 'c' * 32, 'status': 'starting', 'pid': None, 'startup_lock': True, 'created_at': ''}
        path = manager._path(state['id'])
        path.parent.mkdir()
        (path.parent / 'startup.lock').touch()

        @contextlib.contextmanager
        def finish_before_lock(lock_path, **options):
            write_json(path, dict(state, status='running', started_at='finished', url='http://127.0.0.1:1234/'))
            with locked(lock_path, **options):
                yield

        for operation in ('list', 'stop'):
            with self.subTest(operation=operation):
                manager._save(state)
                with patch('reprise.runtime.locked', side_effect=finish_before_lock):
                    result = manager.list()[0] if operation == 'list' else manager.stop(state['id'])
                self.assertEqual(result['status'], 'exited' if operation == 'list' else 'stopped')
                self.assertEqual(result['started_at'], 'finished')
                self.assertEqual(result['url'], 'http://127.0.0.1:1234/')
                self.assertNotIn('recovery_error', result)

    def test_missing_or_symlinked_startup_lock_is_not_assumed_inactive(self):
        for condition in ('missing', 'symlink'):
            with self.subTest(condition=condition):
                root = fixture('runtime-lock-' + condition)
                manager = RuntimeManager(root)
                state = {'id': 'd' * 32, 'status': 'preparing', 'pid': None, 'startup_lock': True, 'created_at': ''}
                manager._save(state)
                if condition == 'symlink':
                    target = root / 'unrelated.lock'
                    target.touch()
                    (manager._path(state['id']).parent / 'startup.lock').symlink_to(target)
                self.assertEqual(manager.list()[0]['status'], 'cleanup_failed')
                with self.assertRaises(ProcessCleanupError):
                    manager.stop(state['id'])
                self.assertEqual(read_json(manager._path(state['id']))['status'], 'preparing')


if __name__ == '__main__':
    unittest.main()
