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
        self.assertTrue(self.cli('shutdown')['stopped'])

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
