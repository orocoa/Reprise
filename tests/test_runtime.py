import json
import http.client
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from reprise.git import Repository
from reprise.runtime import RuntimeManager, process_identity
from reprise.processes import ProcessCleanupError
from reprise.static_server import LoopbackHTTPServer, PreviewHandler


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


def http_server_command():
    # This command fixture tests execution/cleanup, not external reverse DNS.
    code = ('import runpy,socket; socket.getfqdn=lambda host: "localhost"; '
            'runpy.run_module("http.server",run_name="__main__")')
    return [sys.executable, '-c', code, '{port}', '--bind', '{host}']


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('runtime')
        self.repo = commit_repo(self.root / 'repo')
        self.manager = RuntimeManager(self.root / 'state')
        self.opened = []

    def tearDown(self):
        for runtime in self.opened:
            self.manager.stop(runtime['id'])

    def test_loopback_http_works_when_reverse_dns_is_unavailable(self):
        with patch('socket.getfqdn', side_effect=AssertionError('DNS must not be queried')):
            server = LoopbackHTTPServer(('127.0.0.1', 0), PreviewHandler)
            server.root = self.repo.work_tree
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=2)
            try:
                connection.request('GET', '/')
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertIn(b'<h1>first</h1>', response.read())
            finally:
                connection.close()
                server.shutdown()
                server.server_close()
                thread.join(2)

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
        recipe = {'adapter': 'command-web', 'commands': {'start': http_server_command()}}
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
            'start': http_server_command()}}
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
        with self.assertRaisesRegex(ProcessCleanupError, 'no process was signalled'):
            self.manager.stop(runtime['id'])
        self.assertEqual(json.loads(path.read_text())['status'], 'cleanup_failed')
        self.assertIsNotNone(process_identity(runtime['pid']))
        path.write_text(json.dumps(runtime))

    def test_stop_waits_for_children_after_parent_exits_and_manager_reloads(self):
        source = self.root / 'repo'
        (source / 'child.py').write_text('import os, signal, time\nfrom pathlib import Path\n'
            'signal.signal(signal.SIGTERM, signal.SIG_IGN)\n'
            'Path("child.pid").write_text(str(os.getpid()))\ntime.sleep(60)\n')
        (source / 'parent.py').write_text('import os, socket, subprocess, sys, time\nfrom pathlib import Path\n'
            'from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler\n'
            'socket.getfqdn=lambda host: "localhost"\n'
            'subprocess.Popen([sys.executable, "child.py"])\n'
            'while not Path("child.pid").exists(): time.sleep(.01)\n'
            'ThreadingHTTPServer(("127.0.0.1", int(os.environ["PORT"])), SimpleHTTPRequestHandler).serve_forever()\n')
        subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(source), 'commit', '-qm', 'child outlives terminating parent'], check=True)
        runtime = self.manager.start(self.repo, 'HEAD', {'adapter': 'command-web',
            'commands': {'start': [sys.executable, 'parent.py']}}, approved=True)
        self.opened.append(runtime)
        child = int((Path(runtime['path']) / 'child.pid').read_text())
        self.assertIsNotNone(process_identity(child))
        stopped = RuntimeManager(self.root / 'state').stop(runtime['id'])
        self.assertEqual(stopped['status'], 'stopped')
        self.assertFalse(stopped['running'])
        self.assertIsNone(process_identity(runtime['pid']))
        self.assertIsNone(process_identity(child))

    def test_build_descendants_are_cleaned_before_starting_preview(self):
        source = self.root / 'repo'
        (source / 'build.py').write_text('import subprocess, sys, time\nfrom pathlib import Path\n'
            'code = "import os,signal,time; from pathlib import Path; signal.signal(signal.SIGTERM,signal.SIG_IGN); Path(\'build-child.pid\').write_text(str(os.getpid())); time.sleep(60)"\n'
            'subprocess.Popen([sys.executable, "-c", code])\n'
            'while not Path("build-child.pid").exists(): time.sleep(.01)\n')
        subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(source), 'commit', '-qm', 'background process from build'], check=True)
        runtime = self.manager.start(self.repo, 'HEAD', {'adapter': 'command-web', 'commands': {
            'build': [[sys.executable, 'build.py']],
            'start': http_server_command()}}, approved=True)
        self.opened.append(runtime)
        child = int((Path(runtime['path']) / 'build-child.pid').read_text())
        self.assertIsNone(process_identity(child))
        self.assertEqual(len(runtime['process_trees']), 2)
        self.assertTrue(self.manager.list()[0]['running'])

    def test_cleanup_failure_is_retained_and_never_reported_as_stopped(self):
        runtime = self.manager.start(self.repo, 'HEAD', {'adapter': 'static-web'})
        self.opened.append(runtime)
        with patch('reprise.runtime.OwnedProcessTree.terminate', side_effect=ProcessCleanupError('injected cleanup failure')):
            with self.assertRaisesRegex(ProcessCleanupError, 'injected cleanup failure'):
                self.manager.stop(runtime['id'])
        state = self.manager.list()[0]
        self.assertEqual(state['status'], 'cleanup_failed')
        self.assertTrue(state['running'])
        self.assertIn('injected cleanup failure', state['cleanup_error'])

    def test_legacy_live_runtime_is_safely_adopted_before_stop(self):
        runtime = self.manager.start(self.repo, 'HEAD', {'adapter': 'static-web'})
        self.opened.append(runtime)
        for tree in self.manager._trees.values():
            tree.close()
        path = self.root / 'state' / 'runtimes' / runtime['id'] / 'runtime.json'
        legacy = {key: value for key, value in runtime.items() if key not in ('process_tree', 'process_trees')}
        path.write_text(json.dumps(legacy))
        stopped = RuntimeManager(self.root / 'state').stop(runtime['id'])
        self.assertEqual(stopped['status'], 'stopped')
        self.assertTrue(stopped['process_trees'])
        self.assertIsNone(process_identity(runtime['pid']))

    def test_static_symlinks_do_not_expose_external_files(self):
        runtime = self.manager.start(self.repo, 'HEAD', {'adapter': 'static-web'})
        self.opened.append(runtime)
        secret = self.root / 'secret.txt'
        secret.write_text('outside preview')
        (Path(runtime['path']) / 'leak').symlink_to(secret)
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(runtime['url'] + 'leak')
        self.assertEqual(raised.exception.code, 403)

    def test_static_server_ignores_repository_packages_and_python_startup_hooks(self):
        source = self.root / 'repo'
        marker = self.root / 'unapproved-python-code.txt'
        poison = 'open(%r, "a").write("executed\\n")\nraise RuntimeError("untrusted Python imported")\n' % str(marker)
        for name in ('reprise/__init__.py', 'http/__init__.py', 'sitecustomize.py', 'usercustomize.py', 'json.py'):
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(poison)
        subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(source), 'commit', '-qm', 'untrusted Python names in static content'], check=True)
        # Inherited Python search settings must not affect the trusted server.
        with patch.dict(os.environ, {'PYTHONPATH': str(source), 'PYTHONHOME': str(source)}):
            runtime = self.manager.start(self.repo, 'HEAD', {'adapter': 'static-web'}, approved=False)
        self.opened.append(runtime)
        with urllib.request.urlopen(runtime['url']) as response:
            self.assertIn(b'<h1>first</h1>', response.read())
        self.assertFalse(marker.exists())
        self.assertTrue((Path(runtime['path']) / 'reprise/__init__.py').exists())

    def test_static_preview_rejects_foreign_missing_and_duplicate_host(self):
        runtime = self.manager.start(self.repo, 'HEAD', {'adapter': 'static-web'})
        self.opened.append(runtime)
        port = runtime['port']
        for method in ('GET', 'HEAD'):
            for hosts, status in ((['localhost:%s' % port], 200),
                                  (['untrusted.example:%s' % port], 403),
                                  (['127.0.0.1:%s' % (port + 1)], 403),
                                  ([], 403),
                                  (['127.0.0.1:%s' % port, 'untrusted.example'], 403)):
                with self.subTest(method=method, hosts=hosts):
                    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
                    try:
                        connection.putrequest(method, '/', skip_host=True)
                        for host in hosts:
                            connection.putheader('Host', host)
                        connection.endheaders()
                        response = connection.getresponse()
                        self.assertEqual(response.status, status)
                        response.read()
                    finally:
                        connection.close()


if __name__ == '__main__':
    unittest.main()
