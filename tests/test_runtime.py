import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

from reprise.git import Repository
from reprise.runtime import RuntimeManager, process_identity


def fixture(prefix):
    root = Path(__file__).resolve().parents[1] / 'work' / 'test-artifacts'
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix + '-', dir=str(root)))


def commit_repo(path):
    path.mkdir()
    subprocess.run(['git', 'init', '-q', str(path)], check=True)
    subprocess.run(['git', '-C', str(path), 'config', 'user.name', 'Reprise test'], check=True)
    subprocess.run(['git', '-C', str(path), 'config', 'user.email', 'test@example.invalid'], check=True)
    (path / 'index.html').write_text('<!doctype html><title>first</title><h1>first</h1>')
    (path / 'clip.bin').write_bytes(b'0123456789')
    subprocess.run(['git', '-C', str(path), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(path), 'commit', '-qm', 'first'], check=True)
    return Repository(path)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('runtime')
        self.repo = commit_repo(self.root / 'repo')
        self.manager = RuntimeManager(self.root / 'state')
        self.opened = []

    def tearDown(self):
        for runtime in self.opened:
            self.manager.stop(runtime['id'])

    def test_static_historical_snapshot_and_ranges(self):
        (self.root / 'repo' / 'index.html').write_text('<title>dirty working tree</title>')
        runtime = self.manager.start(self.repo, 'HEAD', {'adapter': 'static-web'})
        self.opened.append(runtime)
        with urllib.request.urlopen(runtime['url']) as response:
            self.assertIn(b'<h1>first</h1>', response.read())
        request = urllib.request.Request(runtime['url'] + 'clip.bin', headers={'Range': 'bytes=2-5'})
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read(), b'2345')
        self.assertIn('dirty working tree', (self.root / 'repo' / 'index.html').read_text())
        snapshot = Path(runtime['path'])
        self.assertTrue(snapshot.is_dir())
        self.assertTrue(self.manager.list()[0]['running'])
        stopped = RuntimeManager(self.root / 'state').stop(runtime['id'])
        self.assertFalse(stopped['running'])
        self.assertTrue(snapshot.is_dir())
        self.assertIsNone(process_identity(runtime['pid']))

    def test_commands_require_saved_approval(self):
        recipe = {'adapter': 'command-web', 'commands': {'start': [sys.executable, '-m', 'http.server', '{port}', '--bind', '{host}']}}
        with self.assertRaisesRegex(ValueError, 'approve'):
            self.manager.start(self.repo, 'HEAD', recipe)
        self.assertEqual(self.manager.list(), [])
        runtime = self.manager.start(self.repo, 'HEAD', recipe, approved=True)
        self.opened.append(runtime)
        with urllib.request.urlopen(runtime['url']) as response:
            self.assertEqual(response.status, 200)
        self.assertEqual(runtime['adapter'], 'command-web')

    def test_failure_retains_snapshot_and_logs(self):
        recipe = {'adapter': 'command-web', 'commands': {'build': [[sys.executable, '-c', 'import sys; print("meaningful build failure"); sys.exit(7)']],
            'start': [sys.executable, '-m', 'http.server', '{port}', '--bind', '{host}']}}
        with self.assertRaisesRegex(RuntimeError, 'build exited with code 7'):
            self.manager.start(self.repo, 'HEAD', recipe, approved=True)
        state = self.manager.list()[0]
        self.assertEqual(state['status'], 'failed')
        self.assertTrue(Path(state['path']).exists())
        self.assertIn('meaningful build failure', Path(state['log_path']).read_text())
        self.assertFalse(state['running'])

    def test_readiness_404_and_identity_guard(self):
        with self.assertRaisesRegex(RuntimeError, 'readiness failed'):
            self.manager.start(self.repo, 'HEAD', {'adapter': 'static-web', 'readiness': {'path': '/missing.html', 'timeout_ms': 200}})
        state = self.manager.list()[0]
        self.assertEqual(state['status'], 'failed')
        runtime = self.manager.start(self.repo, 'HEAD', {'adapter': 'static-web'})
        self.opened.append(runtime)
        path = self.root / 'state' / 'runtimes' / runtime['id'] / 'runtime.json'
        altered = json.loads(path.read_text())
        altered['process_identity'] = 'unrelated/reused process'
        path.write_text(json.dumps(altered))
        stopped = self.manager.stop(runtime['id'])
        self.assertIn('no process was signalled', stopped['stop_note'])
        self.assertIsNotNone(process_identity(runtime['pid']))
        path.write_text(json.dumps(runtime))

    def test_static_symlinks_do_not_expose_external_files(self):
        runtime = self.manager.start(self.repo, 'HEAD', {'adapter': 'static-web'})
        self.opened.append(runtime)
        secret = self.root / 'secret.txt'
        secret.write_text('outside preview')
        (Path(runtime['path']) / 'leak').symlink_to(secret)
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(runtime['url'] + 'leak')
        self.assertEqual(raised.exception.code, 403)


if __name__ == '__main__':
    unittest.main()
