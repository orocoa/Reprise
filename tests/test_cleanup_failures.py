"""Storage failures after launch must not lose owned process handles."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from reprise.capture import CaptureService, stop_browser_from_record
from reprise.processes import ProcessCleanupError, launch_owned, process_identity
from reprise.runtime import RuntimeManager, read_json, write_json
from test_runtime import commit_repo, fixture


class CleanupFailureTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('cleanup-failures')
        self.repo = commit_repo(self.root / 'repo')
        self.manager = RuntimeManager(self.root / 'state')

    def test_runtime_metadata_read_failure_still_stops_the_launched_process(self):
        def unreadable(path):
            if Path(path).name.startswith('process-'):
                raise OSError('injected ownership read failure')
            return read_json(path)
        with patch('reprise.runtime.read_json', side_effect=unreadable):
            with self.assertRaisesRegex(OSError, 'injected ownership read failure'):
                self.manager.start(self.repo, 'HEAD', {'adapter': 'static-web'})
        self.assertEqual(len(self.manager._trees), 1)
        tree = next(iter(self.manager._trees.values()))
        self.assertIsNotNone(tree.process.poll())
        self.assertIsNone(process_identity(tree.process.pid))
        self.assertEqual(self.manager.list()[0]['status'], 'failed')

    def test_capture_worker_metadata_write_failure_still_stops_worker_and_preview(self):
        trees = []
        def worker(argv, cwd, env, log, record_path):
            tree = launch_owned([sys.executable, '-c', 'import time; time.sleep(60)'],
                                cwd, env, log, record_path)
            trees.append(tree)
            return tree
        def cannot_save_worker(path, value):
            if Path(path).name.endswith('-worker.json'):
                raise OSError('injected worker write failure')
            return write_json(path, value)
        capture = CaptureService(self.root / 'state', self.manager)
        with patch.dict(os.environ, {'REPRISE_NODE': sys.executable}), \
                patch('reprise.capture.launch_owned', side_effect=worker), \
                patch('reprise.capture.write_json', side_effect=cannot_save_worker):
            result = capture.capture(self.repo, 'fixture', 'HEAD', {'adapter': 'static-web'})
        self.assertEqual(result['status'], 'failed')
        self.assertIn('injected worker write failure', result['errors'][0]['error'])
        self.assertEqual(len(trees), 1)
        self.assertIsNotNone(trees[0].process.poll())
        self.assertIsNone(process_identity(trees[0].process.pid))
        self.assertFalse(any(item['running'] for item in self.manager.list()))

    def test_corrupt_browser_record_is_a_cleanup_failure(self):
        path = self.root / 'browser-process.json'
        path.write_text('{invalid')
        with self.assertRaisesRegex(ProcessCleanupError, 'Browser cleanup could not be confirmed'):
            stop_browser_from_record(path)
        self.assertEqual(path.read_text(), '{invalid')


if __name__ == '__main__':
    unittest.main()
