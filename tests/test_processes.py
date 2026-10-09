"""Real retained fixtures for identity-checked process-tree cleanup."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from reprise.processes import (OwnedProcessTree, ProcessCleanupError,
                               launch_owned, owned_tree_running, process_identity, stop_owned_tree)


class OwnedProcessTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / 'work' / 'test-artifacts'
        root.mkdir(parents=True, exist_ok=True)
        self.folder = Path(tempfile.mkdtemp(prefix='process-ownership-', dir=str(root)))
        self.processes = []
        self.children = {}
        self.trees = []
        self.original_records = {}

    def tearDown(self):
        for tree in self.trees:
            tree.close()
        for path, value in self.original_records.items():
            path.write_text(json.dumps(value))
        for tree in self.trees:
            try:
                stop_owned_tree(tree.record_path, timeout=.1)
            except ProcessCleanupError:
                pass
        for process in self.processes:
            # Test fixture ownership is established before launch; this is only
            # emergency cleanup, never an application fallback by process name.
            if process.poll() is None:
                process.kill()
                process.wait(timeout=3)
        for pid, identity in self.children.items():
            if identity and process_identity(pid) == identity:
                os.kill(pid, signal.SIGKILL)

    def until(self, callback, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = callback()
            if result:
                return result
            time.sleep(.03)
        self.fail('Condition did not become true')

    def launch(self, detached=False):
        number = len(self.processes)
        child_file = self.folder / ('child-%s.pid' % number)
        release_file = self.folder / ('release-%s' % number)
        child = ('import os,signal,time; from pathlib import Path; '
                 'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                 'Path(%r).write_text(str(os.getpid())); time.sleep(60)' % str(child_file))
        parent = ('import subprocess,sys,time; from pathlib import Path\n'
                  'child=subprocess.Popen([sys.executable,"-c",%r],start_new_session=%r)\n'
                  'while not Path(%r).exists(): time.sleep(.01)\n' %
                  (child, detached, str(release_file)))
        log = (self.folder / ('parent-%s.log' % number)).open('wb')
        try:
            process = subprocess.Popen([sys.executable, '-c', parent], start_new_session=True,
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        finally:
            log.close()
        self.processes.append(process)
        tree = OwnedProcessTree(process, self.folder / ('owned-%s.json' % number), interval=.03)
        self.trees.append(tree)
        child_pid = self.until(lambda: int(child_file.read_text()) if child_file.exists() and child_file.read_text() else None)
        self.children[child_pid] = process_identity(child_pid)
        self.until(lambda: any(row['pid'] == child_pid for row in json.loads(tree.record_path.read_text())['members']))
        return process, tree, child_pid, release_file

    def test_parent_exits_on_term_but_ignoring_child_is_killed(self):
        process, tree, child, _ = self.launch()
        captured = []
        signal_group = tree._signal
        def signal_after_persistence(state, sig):
            persisted = json.loads(tree.record_path.read_text())
            captured.append(any(row['pid'] == child for row in persisted['members']))
            return signal_group(state, sig)
        with patch.object(tree, '_signal', side_effect=signal_after_persistence):
            self.assertTrue(tree.terminate(timeout=.15))
        self.assertTrue(all(captured))
        self.until(lambda: process_identity(child) is None)
        self.assertIsNotNone(process.poll())
        self.assertFalse(owned_tree_running(tree.record_path))
        self.assertEqual(json.loads(tree.record_path.read_text())['status'], 'stopped')

    def test_parent_already_exited_cleanup_works_after_reload(self):
        process, tree, child, release = self.launch()
        release.write_text('exit')
        process.wait(timeout=3)
        tree.close()
        self.assertIsNotNone(process_identity(child))
        self.assertTrue(owned_tree_running(tree.record_path))
        self.assertTrue(stop_owned_tree(tree.record_path, timeout=.1))
        self.until(lambda: process_identity(child) is None)

    def test_observed_detached_child_is_retained_after_parent_exit(self):
        process, tree, child, release = self.launch(detached=True)
        self.assertEqual(os.getsid(child), child)
        release.write_text('exit')
        process.wait(timeout=3)
        tree.close()
        self.assertTrue(stop_owned_tree(tree.record_path, timeout=.1))
        self.until(lambda: process_identity(child) is None)

    def test_identity_mismatch_never_signals_and_reports_uncertainty(self):
        process, tree, child, _ = self.launch()
        tree.close()
        original = json.loads(tree.record_path.read_text())
        self.original_records[tree.record_path] = original
        altered = json.loads(json.dumps(original))
        altered['root_identity'] = 'different-process'
        next(row for row in altered['members'] if row['pid'] == process.pid)['identity'] = 'different-process'
        tree.record_path.write_text(json.dumps(altered))
        with patch('reprise.processes.os.killpg') as send:
            with self.assertRaises(ProcessCleanupError):
                stop_owned_tree(tree.record_path, timeout=.1)
            send.assert_not_called()
        self.assertIsNone(process.poll())
        self.assertIsNotNone(process_identity(child))
        self.assertNotEqual(json.loads(tree.record_path.read_text())['status'], 'stopped')

    def test_signal_failure_never_claims_stopped(self):
        process, tree, child, _ = self.launch()
        with patch('reprise.processes.os.killpg', side_effect=PermissionError('fixture denied signal')):
            with self.assertRaisesRegex(ProcessCleanupError, 'denied signal'):
                tree.terminate(timeout=.1)
        value = json.loads(tree.record_path.read_text())
        self.assertEqual(value['status'], 'unconfirmed')
        self.assertIn('denied signal', value['cleanup_error'])
        self.assertIsNone(process.poll())
        self.assertIsNotNone(process_identity(child))

    def test_old_boot_record_never_signals_a_current_process(self):
        process, tree, _, _ = self.launch()
        tree.close()
        original = json.loads(tree.record_path.read_text())
        self.original_records[tree.record_path] = original
        altered = dict(original, boot_identity='different-boot')
        tree.record_path.write_text(json.dumps(altered))
        with patch('reprise.processes.os.killpg') as send:
            with self.assertRaises(ProcessCleanupError):
                stop_owned_tree(tree.record_path, timeout=.1)
            send.assert_not_called()
        self.assertIsNone(process.poll())

    def test_legacy_adoption_requires_live_verified_leader(self):
        process, tree, child, _ = self.launch()
        tree.close()
        path = self.folder / 'adopted.json'
        with patch('reprise.processes.os.killpg') as send:
            with self.assertRaises(ProcessCleanupError):
                OwnedProcessTree.adopt(process.pid, 'wrong identity', path)
            send.assert_not_called()
        self.assertFalse(path.exists())
        adopted = OwnedProcessTree.adopt(process.pid, process_identity(process.pid), path, interval=.03)
        self.trees.append(adopted)
        self.assertTrue(adopted.terminate(timeout=.1))
        self.until(lambda: process_identity(child) is None)

    def test_exited_members_are_retired_before_unrelated_pid_reuse(self):
        process, tree, child, release = self.launch(detached=True)
        release.write_text('exit')
        process.wait(timeout=3)
        tree.close()
        def retired():
            tree.refresh()
            return next(row for row in json.loads(tree.record_path.read_text())['members']
                        if row['pid'] == process.pid).get('exited')
        self.until(retired)
        state = json.loads(tree.record_path.read_text())
        self.assertTrue(next(row for row in state['members'] if row['pid'] == process.pid)['exited'])
        from reprise import processes
        table = processes._process_table()
        table[process.pid] = {'pid': process.pid, 'ppid': 1, 'pgid': process.pid,
                              'sid': process.pid, 'uid': os.getuid(),
                              'identity': 'unrelated-reused-pid', 'zombie': False}
        with patch('reprise.processes._process_table', return_value=table):
            self.assertTrue(tree.refresh())
        self.assertTrue(tree.terminate(timeout=.1))
        self.until(lambda: process_identity(child) is None)

    def test_group_without_identity_anchor_is_not_blindly_signalled(self):
        process, tree, child, release = self.launch()
        tree.close()
        original = json.loads(tree.record_path.read_text())
        self.original_records[tree.record_path] = original
        # Simulate an old record which never observed its surviving child.
        altered = dict(original, members=[row for row in original['members'] if row['pid'] == process.pid])
        tree.record_path.write_text(json.dumps(altered))
        release.write_text('exit')
        process.wait(timeout=3)
        with patch('reprise.processes.os.killpg') as send:
            with self.assertRaisesRegex(ProcessCleanupError, 'no surviving identity anchor'):
                stop_owned_tree(tree.record_path, timeout=.1)
            send.assert_not_called()
        self.assertIsNotNone(process_identity(child))

    def test_inspection_failure_can_recover_from_a_verified_live_anchor(self):
        process, tree, child, _ = self.launch()
        tree.close()
        self.original_records[tree.record_path] = json.loads(tree.record_path.read_text())
        with patch('reprise.processes._process_table', side_effect=PermissionError('inspection denied')):
            with self.assertRaisesRegex(ProcessCleanupError, 'inspection denied'):
                tree.refresh()
        self.assertEqual(json.loads(tree.record_path.read_text())['status'], 'unconfirmed')
        self.assertIsNone(process.poll())
        self.assertIsNotNone(process_identity(child))
        self.assertTrue(tree.terminate(timeout=.1))
        result = json.loads(tree.record_path.read_text())
        self.assertEqual(result['status'], 'stopped')
        self.assertIn('inspection denied', result['observation_errors'][0]['message'])
        self.assertNotIn('observation_error', result)

    def test_exec_gate_registers_even_a_short_successful_command(self):
        with (self.folder / 'true.log').open('wb') as log:
            tree = launch_owned(['/usr/bin/true'], self.folder, dict(os.environ), log,
                                self.folder / 'true-ownership.json')
        self.trees.append(tree)
        self.processes.append(tree.process)

        self.assertEqual(tree.wait(timeout=3), 0)
        tree.terminate(timeout=.1)
        self.assertEqual(json.loads(tree.record_path.read_text())['status'], 'stopped')

    def test_fast_double_fork_session_escape_is_found_after_parent_exit(self):
        pidfile = self.folder / 'fast-detached.pid'
        code = '''import os,signal,time
from pathlib import Path
child=os.fork()
if child==0:
    if os.fork(): os._exit(0)
    os.setsid()
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
    Path(%r).write_text(str(os.getpid()))
    time.sleep(30)
    os._exit(0)
os.waitpid(child,0)
''' % str(pidfile)
        with (self.folder / 'fast-detached.log').open('wb') as log:
            tree = launch_owned([sys.executable, '-c', code], self.folder, dict(os.environ), log,
                                self.folder / 'fast-detached.json', interval=1)
        self.trees.append(tree)
        self.processes.append(tree.process)
        child = self.until(lambda: int(pidfile.read_text()) if pidfile.exists() and pidfile.read_text() else None)
        self.children[child] = process_identity(child)
        tree.wait(timeout=5)
        tree.close()
        self.assertTrue(stop_owned_tree(tree.record_path, timeout=.1))
        self.until(lambda: process_identity(child) is None)
        state = json.loads(tree.record_path.read_text())
        self.assertEqual(state['status'], 'stopped')
        self.assertTrue(any(row['pid'] == child for row in state['members']))

    def test_exec_gate_observes_children_before_reaping_instant_parent(self):
        from reprise import processes
        child_file = self.folder / 'instant-child.pid'
        child_code = ('import os,signal,time; from pathlib import Path; '
                      'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                      'Path(%r).write_text(str(os.getpid())); time.sleep(60)' % str(child_file))
        parent_code = 'import subprocess,sys; subprocess.Popen([sys.executable,"-c",%r])' % child_code
        with (self.folder / 'instant.log').open('wb') as log:
            tree = launch_owned([sys.executable, '-c', parent_code], self.folder, dict(os.environ),
                                log, self.folder / 'instant-ownership.json', interval=1)
        self.trees.append(tree)
        self.processes.append(tree.process)
        tree.close()  # exercise poll's zombie anchor, independently of the observer.
        child = self.until(lambda: int(child_file.read_text()) if child_file.exists() and child_file.read_text() else None)
        self.children[child] = process_identity(child)
        self.until(lambda: (processes._process_info(tree.process.pid) or {}).get('zombie'))
        self.assertEqual(tree.poll(), 0)
        self.assertTrue(any(row['pid'] == child for row in json.loads(tree.record_path.read_text())['members']))
        self.assertTrue(tree.terminate(timeout=.1))
        self.until(lambda: process_identity(child) is None)

    def test_transient_missing_identity_is_rechecked_without_retiring_live_child(self):
        from reprise import processes
        _, tree, child, _ = self.launch()
        tree.close()
        table = processes._process_table()
        table.pop(child, None)
        inspect = processes._process_info
        missing_reads = []
        def transitioning(pid):
            if pid == child and len(missing_reads) < 2:
                missing_reads.append(pid)
                return None
            return inspect(pid)
        with patch('reprise.processes._process_table', return_value=table), \
                patch('reprise.processes._process_info', side_effect=transitioning):
            self.assertTrue(tree.refresh())
        value = json.loads(tree.record_path.read_text())
        self.assertEqual(len(missing_reads), 2)
        self.assertNotIn('observation_error', value)
        self.assertFalse(next(row for row in value['members'] if row['pid'] == child).get('exited'))
        self.assertTrue(tree.terminate(timeout=.1))

    def test_persistently_missing_identity_is_not_declared_dead(self):
        from reprise import processes
        _, tree, child, _ = self.launch()
        tree.close()
        table = processes._process_table()
        table.pop(child, None)
        inspect = processes._process_info
        def unavailable(pid):
            return None if pid == child else inspect(pid)
        with patch('reprise.processes._process_table', return_value=table), \
                patch('reprise.processes._process_info', side_effect=unavailable), \
                patch('reprise.processes.os.killpg') as send:
            with self.assertRaisesRegex(ProcessCleanupError, 'possibly living'):
                tree.terminate(timeout=.1)
            send.assert_not_called()
        value = json.loads(tree.record_path.read_text())
        self.assertEqual(value['status'], 'unconfirmed')
        self.assertIsNotNone(process_identity(child))
        self.assertTrue(tree.terminate(timeout=.1))


if __name__ == '__main__':
    unittest.main()
