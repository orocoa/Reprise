"""Retired boot records cannot be live previews or signal reused process IDs."""
import json
import os
import time
import unittest
from unittest.mock import patch

from reprise.processes import (OwnedProcessTree, ProcessCleanupError,
                               owned_tree_running, stop_owned_tree)
from reprise.runtime import RuntimeManager
from test_runtime import fixture


def darwin(seconds, label='display text'):
    return 'darwin:{ sec = %d, usec = 1 } %s' % (seconds, label)


def identity(seconds):
    return 'ps:' + time.strftime('%a %b %d %H:%M:%S %Y', time.localtime(seconds))


class BootLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('boot-lifecycle')

    def record(self, boot, process_identity=None, status='tracking'):
        row = {'pid': 4321, 'ppid': 1, 'pgid': 4321, 'sid': 4321,
               'uid': os.getuid(), 'identity': process_identity or identity(1010), 'zombie': False}
        return {'schema': 1, 'uid': os.getuid(), 'boot_identity': boot,
                'root_pid': row['pid'], 'root_identity': row['identity'],
                'members': [row], 'status': status, 'owner_marker': 'a' * 32}

    def retained(self, value):
        path = self.root / 'process.json'
        path.write_text(json.dumps(value))
        return path

    def test_previous_boot_records_are_exited_without_scanning_or_signalling(self):
        cases = [(darwin(1000), darwin(2000), identity(1010)),
                 ('linux:11111111-1111-4111-8111-111111111111',
                  'linux:22222222-2222-4222-8222-222222222222', 'linux:123')]
        for old, current, process in cases:
            with self.subTest(boot=old):
                value = self.record(old, process)
                value.update(observation_error='Historical inspection error',
                             observation_error_kind='inspection')
                path = self.retained(value)
                before = path.read_bytes()
                with patch('reprise.processes.boot_identity', return_value=current), \
                     patch('reprise.processes._process_table') as scan, \
                     patch('reprise.processes.os.killpg') as send:
                    self.assertFalse(owned_tree_running(path))
                    self.assertFalse(stop_owned_tree(path))
                    scan.assert_not_called()
                    send.assert_not_called()
                self.assertEqual(path.read_bytes(), before, 'Original ownership and diagnostics remain')

    def test_mac_display_text_change_is_the_same_boot_and_still_observes(self):
        value = self.record(darwin(1000, 'old time zone'))
        path = self.retained(value)
        with patch('reprise.processes.boot_identity', return_value=darwin(1000, 'new time zone')):
            tree = OwnedProcessTree.from_record(path)
            with patch.object(tree, '_advance', return_value=(value['members'], value)) as observe:
                self.assertTrue(tree.running())
                observe.assert_called_once()
            tree.close()

    def test_invalid_future_or_contradictory_boot_records_remain_unconfirmed(self):
        cases = [('different-boot', darwin(2000), identity(1010)),
                 (darwin(3000), darwin(2000), identity(1010)),
                 (darwin(1000), darwin(2000), identity(2010)),
                 ('linux:invalid', 'linux:22222222-2222-4222-8222-222222222222', 'linux:123'),
                 ('linux:11111111-1111-4111-8111-111111111111', darwin(2000), 'linux:123')]
        for old, current, process in cases:
            with self.subTest(boot=old, process=process):
                path = self.retained(self.record(old, process))
                before = path.read_bytes()
                with patch('reprise.processes.boot_identity', return_value=current), \
                     patch('reprise.processes.os.killpg') as send:
                    with self.assertRaises(ProcessCleanupError):
                        stop_owned_tree(path)
                    send.assert_not_called()
                self.assertEqual(path.read_bytes(), before)

    def test_foreign_uid_is_not_retired_or_signalled(self):
        value = self.record(darwin(1000));value['uid'] += 1
        path = self.retained(value)
        with patch('reprise.processes.boot_identity', return_value=darwin(2000)), \
             patch('reprise.processes.os.killpg') as send:
            with self.assertRaises(ProcessCleanupError):
                owned_tree_running(path)
            send.assert_not_called()

    def test_runtime_list_and_stop_keep_files_and_retired_process_records(self):
        manager = RuntimeManager(self.root / 'data')
        rid = 'a' * 32
        folder = manager.directory / rid;folder.mkdir()
        path = folder / 'process-old.json'
        value = self.record(darwin(1000));path.write_text(json.dumps(value))
        source = folder / 'source';source.mkdir();(source / 'index.html').write_text('saved copy')
        manager._save({'id': rid, 'pid': value['root_pid'], 'process_identity': value['root_identity'],
                       'process_tree': path.name, 'process_trees': [path.name],
                       'status': 'running', 'running': True, 'created_at': ''})
        before = path.read_bytes()
        with patch('reprise.processes.boot_identity', return_value=darwin(2000)), \
             patch('reprise.processes.os.killpg') as send:
            row = manager.list()[0]
            self.assertFalse(row['running'])
            self.assertEqual(row['process_state'], 'exited')
            self.assertEqual(row['status'], 'exited')
            stopped = manager.stop(rid)
            self.assertEqual(stopped['status'], 'stopped')
            self.assertFalse(stopped['running'])
            self.assertFalse(manager.stop(rid)['running'])
            send.assert_not_called()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual((source / 'index.html').read_text(), 'saved copy')

    def test_runtime_observation_failure_is_unknown_not_confirmed_alive(self):
        manager = RuntimeManager(self.root / 'data')
        manager._save({'id': 'b' * 32, 'status': 'running', 'running': True, 'created_at': ''})
        with patch.object(manager, '_alive', side_effect=ProcessCleanupError('Cannot inspect')):
            row = manager.list()[0]
        self.assertTrue(row['running'], 'Legacy safety checks remain conservative')
        self.assertEqual(row['process_state'], 'unknown')
        self.assertEqual(row['status'], 'cleanup_failed')


if __name__ == '__main__':
    unittest.main()
