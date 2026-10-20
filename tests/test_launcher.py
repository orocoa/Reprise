"""Real source-only open/reuse/shutdown with retained, isolated data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from reprise.launcher import shutdown
from test_runtime import fixture, commit_repo


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('cli-open')
        self.repo = commit_repo(self.root / 'source with spaces')
        self.data = self.root / 'state'
        self.env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))

    def tearDown(self):
        shutdown(self.data)

    def cli(self, *args):
        p = subprocess.run([sys.executable, '-m', 'reprise', '--data', str(self.data), *args],
                           cwd=str(self.repo.work_tree), env=self.env, capture_output=True, text=True, timeout=25)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_current_repository_open_reuse_and_shutdown(self):
        one = self.cli('.', '--no-browser', '--lang', 'en')
        self.assertIn('lang=en', one['url'])
        self.assertIn('project=', one['url'])
        self.assertFalse(one['reused'])
        two = self.cli('open', '.', '--no-browser')
        self.assertTrue(two['reused'])
        self.assertEqual(one['pid'], two['pid'])
        self.assertEqual(one['project_id'], two['project_id'])
        import shlex
        stopped = subprocess.run(shlex.split(one['stop_command']), cwd=str(self.root),
                                 capture_output=True, text=True, timeout=15)
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self.assertTrue(json.loads(stopped.stdout)['stopped'])
        self.assertTrue(self.cli('shutdown')['stopped'])

    def test_open_without_path_uses_current_repository(self):
        result = self.cli('open', '--no-browser')
        self.assertEqual(result['path'], str(self.repo.path))
        self.assertIsNotNone(result['project_id'])

    def test_explicit_related_history_is_saved_with_put(self):
        root = self.root / 'history.git'
        subprocess.run(['git', 'clone', '--bare', str(self.repo.path), str(root)], check=True, capture_output=True)
        result = self.cli('open', str(self.repo.path), '--no-browser', '--history', str(root))
        record = json.loads((self.data / 'projects.json').read_text())
        project = next(p for p in record['projects'] if p['id'] == result['project_id'])
        self.assertEqual(len(project['history_project_ids']), 1)

    def test_old_server_is_not_silently_reused_as_the_new_version(self):
        from unittest.mock import patch
        from reprise.launcher import open_repository
        with patch('reprise.launcher.verified_server', return_value={'version': '0.0.0'}):
            with self.assertRaisesRegex(ValueError, 'Another Reprise version'):
                open_repository(self.data, self.repo.path, browser=False)

    def test_busy_port_falls_back_without_touching_other_service(self):
        import socket
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0)); occupied.listen()
            port = occupied.getsockname()[1]
            result = self.cli('.', '--no-browser', '--port', str(port))
            self.assertNotIn(':%s/' % port, result['url'])

    def test_invalid_startup_arguments_report_usage_without_traceback(self):
        from contextlib import redirect_stderr
        from io import StringIO
        from reprise.cli import main
        for args in (['--data'], ['--database'], ['open', '.', '--port', '-1'], ['serve', '--port', '65536']):
            error = StringIO()
            with redirect_stderr(error), self.assertRaises(SystemExit) as failure: main(args)
            self.assertEqual(failure.exception.code, 2)
            self.assertNotIn('Traceback', error.getvalue())

    def test_malformed_saved_server_is_rejected(self):
        from reprise.launcher import verified_server
        self.data.mkdir()
        (self.data / 'server.json').write_text('{"url":"http://127.0.0.1:1/"}')
        with self.assertRaisesRegex(ValueError, 'Invalid'): verified_server(self.data)
        # Retain the bad record as diagnostic evidence; no service was launched.
        self.data = self.root / 'unused-state'

    def test_source_local_data_is_rejected_before_writes(self):
        from reprise.launcher import open_repository
        with self.assertRaisesRegex(ValueError, 'outside'):
            open_repository(Path(self.repo.work_tree) / 'state', self.repo.work_tree, browser=False)
        self.assertFalse((Path(self.repo.work_tree) / 'state').exists())
