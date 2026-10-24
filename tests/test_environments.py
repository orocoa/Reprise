"""Synthetic, retained fixtures for explicitly released generated environments."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from unittest.mock import patch

from reprise.cancellation import Cancellation, Cancelled
from reprise.environments import _scan
from reprise.git import Repository
from reprise.recipes import validate_recipe
from reprise.runtime import RuntimeManager


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parents[1] / 'work/test-artifacts/reprise-environments'
        parent.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix=self._testMethodName + '-', dir=str(parent)))
        self.source = self.root / 'original'
        self.source.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.source)], check=True)
        subprocess.run(['git', '-C', str(self.source), 'config', 'user.name', 'Reprise fixture'], check=True)
        subprocess.run(['git', '-C', str(self.source), 'config', 'user.email', 'fixture@example.invalid'], check=True)
        (self.source / 'index.html').write_text('<h1>retained historical source</h1>')
        (self.source / 'requirements.txt').write_text('# local stdlib-only fixture; no network\n')
        (self.source / 'server.py').write_text(
            'import os,socket\nfrom http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler\n'
            'socket.getfqdn=lambda host:"localhost"\n'
            'ThreadingHTTPServer(("127.0.0.1",int(os.environ["PORT"])),SimpleHTTPRequestHandler).serve_forever()\n')
        self.commit()
        self.repository = Repository(self.source)
        self.manager = RuntimeManager(self.root / 'state')
        self.recipe = {'adapter': 'command-web', 'commands': {
            'install': [[sys.executable, '-c', 'from pathlib import Path; p=Path("node_modules/demo"); p.mkdir(parents=True); (p/"index.js").write_text("module.exports=42\\n")']],
            'start': [sys.executable, 'server.py']},
            'environment': {'outputs': ['node_modules'], 'inputs': ['requirements.txt'], 'tools': [sys.executable]}}
        self.opened = []

    def tearDown(self):
        for runtime in self.opened:
            self.manager.stop(runtime['id'])

    def commit(self):
        subprocess.run(['git', '-C', str(self.source), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.source), 'commit', '-qm', 'fixture'], check=True)

    def start(self, recipe=None, project_id='fixture-project'):
        value = self.manager.start(self.repository, 'HEAD', recipe or self.recipe,
                                   approved=True, project_id=project_id)
        self.opened.append(value)
        return value

    def stopped(self, recipe=None):
        runtime = self.start(recipe)
        self.manager.stop(runtime['id'])
        return runtime, runtime['environment_id'], Path(runtime['path'])

    def test_real_venv_reuses_releases_and_rebuilds_without_touching_source_or_evidence(self):
        recipe = copy.deepcopy(self.recipe)
        recipe['commands']['install'] = [[sys.executable, '-m', 'venv', '--without-pip', '.venv']]
        recipe['commands']['start'] = ['.venv/bin/python', 'server.py']
        recipe['environment']['outputs'] = ['.venv']
        runtime = self.start(recipe)
        identifier, workspace = runtime['environment_id'], Path(runtime['path'])
        with urllib.request.urlopen(runtime['url']) as response:
            self.assertIn(b'retained historical source', response.read())
        self.assertTrue((workspace / '.venv/pyvenv.cfg').is_file())
        interpreter = (workspace / '.venv/bin/python').resolve()
        interpreter_bytes = interpreter.stat().st_size
        self.assertEqual(self.start(recipe)['id'], runtime['id'])
        self.assertFalse(self.manager.environment_check(identifier)['releasable'])
        self.manager.stop(runtime['id'])
        reused = self.start(recipe)
        self.assertTrue(reused['environment_reused'])
        self.assertEqual(reused['path'], runtime['path'])
        self.assertEqual(len(reused['process_trees']), 1, 'reuse must not reinstall')
        self.manager.stop(reused['id'])
        evidence = self.root / 'state/evidence/fixture.png'
        evidence.parent.mkdir()
        evidence.write_bytes(b'retained screenshot sentinel')
        check = self.manager.environment_check(identifier)
        self.assertTrue(check['releasable'], check)
        receipt = self.manager.release_environment(identifier)
        self.assertEqual(receipt['status'], 'released')
        self.assertGreater(receipt['removed_logical_bytes'], 0)
        self.assertFalse(receipt['source_files_removed'])
        self.assertFalse((workspace / '.venv').exists())
        self.assertTrue((workspace / 'server.py').is_file())
        self.assertEqual(interpreter.stat().st_size, interpreter_bytes)
        self.assertEqual(evidence.read_bytes(), b'retained screenshot sentinel')
        self.assertTrue(Path(runtime['log_path']).is_file())
        self.assertTrue(Path(receipt['receipt']).is_file())
        self.assertTrue(self.manager.release_environment(identifier)['already_released'])
        rebuilt = self.start(recipe)
        self.assertEqual(rebuilt['environment_id'], identifier)
        self.assertFalse(rebuilt['environment_reused'])
        self.assertNotEqual(rebuilt['path'], runtime['path'])
        self.assertTrue((Path(rebuilt['path']) / '.venv/pyvenv.cfg').is_file())
        self.assertTrue((workspace / 'server.py').is_file(), 'old source attempt is retained')
        self.assertFalse((self.source / '.venv').exists())
        self.assertEqual(subprocess.check_output(['git', '-C', str(self.source), 'status', '--porcelain']), b'')
        record = self.manager.environments.get(identifier)
        self.assertTrue(record['rebuild_verified'])
        self.assertEqual(len(record['attempts']), 1)
        (self.root / 'lifecycle-evidence.json').write_text(json.dumps({'first': runtime, 'release': receipt, 'rebuilt': rebuilt}, indent=2))

    def test_release_refuses_changed_output_and_retains_modified_attempt_on_retry(self):
        runtime, identifier, workspace = self.stopped()
        changed = workspace / 'node_modules/demo/user-notes.txt'
        changed.write_text('user data must be retained')
        check = self.manager.environment_check(identifier)
        self.assertFalse(check['releasable'])
        self.assertIn('changed', ' '.join(check['blockers']))
        with self.assertRaisesRegex(ValueError, 'release refused'):
            self.manager.release_environment(identifier)
        retry = self.start()
        self.assertNotEqual(retry['path'], str(workspace))
        self.assertEqual(changed.read_text(), 'user data must be retained')
        self.assertEqual(self.manager.environments.get(identifier)['attempts'][0]['status'], 'failed')

    def test_release_refuses_additional_database_and_missing_activity_probe(self):
        _, identifier, workspace = self.stopped()
        database = workspace / 'local.sqlite'
        database.write_bytes(b'local state')
        check = self.manager.environment_check(identifier)
        self.assertFalse(check['releasable'])
        self.assertIn('additional data', ' '.join(check['blockers']))
        self.assertTrue(database.exists())
        # A second untouched environment reaches the inactivity guard.
        runtime = self.start(project_id='second-project')
        self.manager.stop(runtime['id'])
        with patch('reprise.environments._activity', side_effect=ValueError('lsof is unavailable')):
            self.assertFalse(self.manager.environment_check(runtime['environment_id'])['releasable'])

    def test_release_detects_external_process_cwd(self):
        _, identifier, workspace = self.stopped()
        with subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], cwd=workspace) as process:
            try:
                check = self.manager.environment_check(identifier)
                self.assertFalse(check['releasable'])
                self.assertIn(process.pid, check['active_process_ids'])
            finally:
                process.terminate()
                process.wait(timeout=10)

    def test_identity_binds_project_sha_recipe_and_tools(self):
        store = self.manager.environments
        first = store.identity(self.repository, 'HEAD', self.recipe, 'a')
        second = store.identity(self.repository, 'HEAD', self.recipe, 'b')
        self.assertNotEqual(store.key(first), store.key(second))
        changed = copy.deepcopy(self.recipe)
        changed['readiness'] = {'timeout_ms': 20000}
        self.assertNotEqual(store.key(first), store.key(store.identity(self.repository, 'HEAD', changed, 'a')))
        (self.source / 'requirements.txt').write_text('# changed saved dependency input\n')
        self.commit()
        self.assertNotEqual(store.key(first), store.key(store.identity(self.repository, 'HEAD', self.recipe, 'a')))
        with patch('reprise.environments._toolchains', return_value=[{'version': 'changed'}]):
            self.assertNotEqual(store.key(first), store.key(store.identity(self.repository, first['sha'], self.recipe, 'a')))
        self.assertNotIn('environment', validate_recipe({'adapter': 'static-web'}))

    def test_configuration_rejects_source_outputs_and_bad_paths(self):
        for output in ['../original', '/tmp/data', '.git', '.GIT/data', '.', 'C:/data']:
            value = copy.deepcopy(self.recipe)
            value['environment']['outputs'] = [output]
            with self.subTest(output=output), self.assertRaises(ValueError):
                validate_recipe(value)
        value = copy.deepcopy(self.recipe)
        value['environment']['outputs'] = ['server.py']
        with self.assertRaisesRegex(ValueError, 'overlaps retained'):
            self.start(value)
        with self.assertRaisesRegex(ValueError, 'project_id'):
            self.start(project_id=None)
        with self.assertRaisesRegex(ValueError, 'approve'):
            self.manager.start(self.repository, 'HEAD', self.recipe, project_id='a')
        self.assertEqual(self.manager.environments.list(), [])

    def test_missing_output_or_install_writes_source_cannot_be_released(self):
        for commands, expected in [([], OSError),
                ([[sys.executable, '-c', 'from pathlib import Path; Path("node_modules").mkdir(); Path("index.html").write_text("changed")']], ValueError)]:
            value = copy.deepcopy(self.recipe)
            value['commands']['install'] = commands
            with self.subTest(commands=commands), self.assertRaises(expected):
                self.start(value)
        records = self.manager.environments.list()
        self.assertEqual(len(records), 2)
        for record in records:
            self.assertEqual(record['status'], 'failed')
            self.assertFalse(record['rebuild_verified'])
            self.assertFalse(self.manager.environment_check(record['environment_id'])['releasable'])

    def test_modified_metadata_and_symlink_paths_fail_closed(self):
        _, identifier, workspace = self.stopped()
        file = self.root / 'state/environments' / identifier / 'environment.json'
        record = json.loads(file.read_text())
        record['outputs'] = ['server.py']
        file.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'registered identity'):
            self.manager.release_environment(identifier)
        self.assertTrue((workspace / 'server.py').exists())
        # Another independent environment has an output replaced by a link.
        runtime = self.start(project_id='symlink-fixture')
        self.manager.stop(runtime['id'])
        path = Path(runtime['path']) / 'node_modules'
        preserved = path.with_name('preserved-node-modules')
        path.rename(preserved)
        path.symlink_to(self.source, target_is_directory=True)
        self.assertFalse(self.manager.environment_check(runtime['environment_id'])['releasable'])
        self.assertTrue(preserved.is_dir())
        self.assertTrue((self.source / 'server.py').is_file())

    def test_changed_toolchain_prevents_release_and_incomplete_release_retains_receipt(self):
        _, identifier, workspace = self.stopped()
        with patch('reprise.environments._toolchains', return_value=[{'version': 'different'}]):
            self.assertFalse(self.manager.environment_check(identifier)['releasable'])
        with patch('reprise.environments._delete_output', side_effect=ValueError('concurrent change')):
            with self.assertRaisesRegex(ValueError, 'concurrent change'):
                self.manager.release_environment(identifier)
        record = self.manager.environments.get(identifier)
        self.assertEqual(record['status'], 'failed')
        self.assertEqual(record['last_release']['status'], 'partial')
        self.assertEqual(record['last_release']['removed_logical_bytes'], 0)
        self.assertTrue(Path(record['last_release']['receipt']).is_file())
        self.assertTrue((workspace / 'node_modules').is_dir())

    def test_hardlinks_and_ancestor_links_are_uncertain(self):
        generated = self.root / 'generated'
        generated.mkdir()
        (generated / 'file').write_bytes(b'generated')
        os.link(generated / 'file', generated / 'second')
        with self.assertRaisesRegex(ValueError, 'shared ownership'):
            _scan(generated, identities=True)
        redirect = self.root / 'redirect'
        redirect.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            _scan(redirect / 'original')

    def test_cancelled_release_keeps_outputs_and_environment_lock_is_cancellable(self):
        _, identifier, workspace = self.stopped()
        request = self.root / 'cancel.request'
        request.touch()
        cancel = Cancellation(request)
        with self.assertRaises(Cancelled):
            self.manager.release_environment(identifier, cancel)
        self.assertTrue((workspace / 'node_modules/demo/index.js').is_file())
        self.assertEqual(self.manager.environments.get(identifier)['status'], 'ready')
        # Cancellation is observed before waiting for another process's lease.
        with self.manager.environments.lease(identifier):
            with self.assertRaises(Cancelled):
                with self.manager.environments.lease(identifier, cancel=cancel):
                    self.fail('cancelled lease must not enter')


if __name__ == '__main__':
    unittest.main()
