"""Retained synthetic coverage for environments, backup, capture and accounting."""
import base64
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
import urllib.request
from unittest.mock import patch

from reprise.backup import BackupError, create_backup, restore_backup, verify_backup
from reprise.service import Reprise
from reprise.storage import write_json
from reprise.storage_report import storage_report
from test_runtime import fixture


class LifecycleIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('lifecycle-integration-' + self._testMethodName)
        self.source = self.root / 'original-project'
        self.source.mkdir()
        (self.source / 'index.html').write_text('<!doctype html><link rel="icon" href="data:,"><h1>Historical environment fixture</h1>')
        (self.source / 'requirements.txt').write_text('# offline stdlib-only virtual environment\n')
        (self.source / 'server.py').write_text(
            'import os,socket\nfrom http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler\n'
            'socket.getfqdn=lambda host:"localhost"\n'
            'ThreadingHTTPServer(("127.0.0.1",int(os.environ["PORT"])),SimpleHTTPRequestHandler).serve_forever()\n')
        self.data = self.root / 'data'
        self.app = Reprise(self.data)
        self.apps = [self.app]
        self.project = self.app.projects.add(str(self.source), kind='folder')
        self.sha = self.app.projects.snapshot(self.project['id'], 'Offline Python website')['sha']
        self.recipe = {'adapter': 'command-web', 'commands': {
            'install': [[sys.executable, '-m', 'venv', '--without-pip', '.venv']],
            'start': ['.venv/bin/python', 'server.py']},
            'environment': {'outputs': ['.venv'], 'inputs': ['requirements.txt'], 'tools': [sys.executable]},
            'captures': [{'id': 'main', 'viewport': {'width': 320, 'height': 240, 'scale': 1}}]}
        self.app.projects.save_recipe(self.project['id'], self.recipe, self.sha)

    def tearDown(self):
        for app in reversed(self.apps):
            for runtime in app.runtimes.list():
                if runtime.get('running'):
                    app.runtimes.stop(runtime['id'])
            app.close()

    def finished(self, app, operation, sha=None):
        job = app.execute(self.project['id'], operation, {'sha': sha or self.sha})
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            state = app.jobs.get(job['id'])
            if state['status'] in ('complete', 'failed', 'cancelled'):
                self.assertEqual(state['status'], 'complete', state)
                return state['result']
            time.sleep(.025)
        self.fail('Synthetic lifecycle task did not complete within 30 seconds')

    def assert_http(self, runtime):
        with urllib.request.urlopen(runtime['url'], timeout=5) as response:
            self.assertEqual(response.status, 200)
            self.assertIn(b'Historical environment', response.read())

    def test_released_venv_offline_backup_restore_rebuilds_same_sha_and_keeps_attempts(self):
        runtime = self.finished(self.app, 'run')
        self.assert_http(runtime)
        identifier, original_workspace = runtime['environment_id'], Path(runtime['path'])
        self.app.runtimes.stop(runtime['id'])
        check = self.app.runtimes.environment_check(identifier)
        self.assertTrue(check['releasable'], check)
        released = self.app.runtimes.release_environment(identifier)
        self.assertFalse((original_workspace / '.venv').exists())
        self.app.close()
        backup_path, restored_path = self.root / 'backup', self.root / 'restored-data'
        backup = create_backup(self.data, backup_path)
        self.assertEqual(backup['status'], 'complete')
        self.assertEqual(verify_backup(backup_path)['status'], 'verified')
        restored = restore_backup(backup_path, restored_path)
        self.assertEqual(restored['status'], 'complete')
        migrated = Reprise(restored_path)
        self.apps.append(migrated)
        before = migrated.runtimes.environments.get(identifier)
        self.assertEqual(before['status'], 'restored-rebuild-required')
        self.assertFalse(before['rebuild_verified'])
        restored_workspace = Path(before['workspace'])
        restored_workspace.relative_to(restored_path)
        self.assertNotEqual(restored_workspace, original_workspace)
        self.assertTrue((restored_workspace / 'server.py').is_file())
        self.assertFalse((restored_workspace / '.venv').exists())
        self.assertFalse(migrated.runtimes.environment_check(identifier)['releasable'])
        rebuilt = self.finished(migrated, 'run')
        self.assert_http(rebuilt)
        self.assertEqual(rebuilt['sha'], self.sha)
        self.assertEqual(rebuilt['environment_id'], identifier)
        self.assertFalse(rebuilt['environment_reused'])
        self.assertNotEqual(Path(rebuilt['path']), restored_workspace)
        self.assertTrue((Path(rebuilt['path']) / '.venv/pyvenv.cfg').is_file())
        self.assertTrue((original_workspace / 'server.py').is_file())
        self.assertTrue((restored_workspace / 'server.py').is_file())
        self.assertTrue(Path(runtime['log_path']).is_file())
        self.assertTrue(Path(released['receipt']).is_file())
        self.assertTrue(migrated.runtimes.environments.get(identifier)['rebuild_verified'])
        write_json(self.root / 'backup-rebuild-evidence.json',
                   {'backup': backup, 'restored': restored, 'environment_before': before, 'rebuilt': rebuilt})

    def test_unreleased_venv_external_links_block_backup_without_silent_omission(self):
        runtime = self.finished(self.app, 'run')
        workspace = Path(runtime['path'])
        links = [path for path in (workspace / '.venv').rglob('*') if path.is_symlink()]
        self.assertTrue(any(path.resolve() != workspace and workspace not in path.resolve().parents for path in links))
        self.app.runtimes.stop(runtime['id'])
        self.app.close()
        destination = self.root / 'must-not-claim-complete'
        with self.assertRaisesRegex(BackupError, '符号链接|链接') as caught:
            create_backup(self.data, destination)
        self.assertEqual(caught.exception.report['status'], 'failed')
        self.assertTrue((workspace / '.venv/pyvenv.cfg').is_file())
        self.assertTrue(all(path.is_symlink() for path in links))
        self.assertFalse((destination / 'receipt.json').exists(), 'unsafe links should fail before copy begins')
        write_json(self.root / 'unreleased-backup-refusal.json', caught.exception.report)

    def fake_worker(self, argv, cwd, env, log, ownership_path):
        """Only the browser worker is simulated; environment/runtime/HTTP stay real."""
        inputs = json.loads(Path(argv[-1]).read_text())
        with urllib.request.urlopen(inputs['url'], timeout=5) as response:
            self.assertIn(b'Historical environment', response.read())
        output = Path(inputs['output_dir']) / (inputs['side'] + '-mock-worker.png')
        output.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII='))
        write_json(inputs['result_path'], {'items': [{'path': str(output), 'media_type': 'image/png',
            'sha': inputs['sha'], 'side': inputs['side'], 'scenario': 'main', 'width': 1, 'height': 1,
            'verification': 'simulated-worker-test-only'}], 'errors': [], 'warnings': []})
        write_json(ownership_path, {'root_identity': 'synthetic worker; no process launched'})
        return SimpleNamespace(record_path=Path(ownership_path),
                               process=SimpleNamespace(pid=os.getpid(), returncode=0), terminate=lambda: None)

    def capture_with_mock_worker(self):
        with patch.dict(os.environ, {'REPRISE_NODE': sys.executable}), \
                patch('reprise.capture.launch_owned', side_effect=self.fake_worker), \
                patch('reprise.capture.wait_owned_process', return_value=0):
            return self.finished(self.app, 'capture')

    def test_capture_reuses_running_environment_and_does_not_stop_user_preview(self):
        running = self.finished(self.app, 'run')
        with patch.object(self.app.runtimes, 'stop', wraps=self.app.runtimes.stop) as stop:
            captured = self.capture_with_mock_worker()
            stop.assert_not_called()
        self.assertEqual(captured['status'], 'complete')
        self.assertEqual(captured['runtimes'][0]['id'], running['id'])
        self.assertTrue(next(row for row in self.app.runtimes.list() if row['id'] == running['id'])['running'])
        self.assert_http(running)
        write_json(self.root / 'mock-capture-reuse-evidence.json', captured)

    def test_capture_stops_runtime_that_it_started(self):
        with patch.object(self.app.runtimes, 'stop', wraps=self.app.runtimes.stop) as stop:
            captured = self.capture_with_mock_worker()
            stop.assert_called_once_with(captured['runtimes'][0]['id'])
        self.assertEqual(captured['status'], 'complete')
        self.assertFalse(any(row['running'] for row in self.app.runtimes.list()))
        self.assertTrue(self.app.runtimes.environments.list(self.project['id'])[0]['rebuild_verified'])

    def test_storage_report_has_distinct_environment_accounting_and_unknown_reclaimable(self):
        runtime = self.finished(self.app, 'run')
        self.app.runtimes.stop(runtime['id'])
        report = storage_report(self.data)
        categories = {row['key']: row for row in report['categories']}
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(categories['environments']['label'], '可重建环境')
        self.assertGreater(categories['environments']['logical_bytes'], 0)
        self.assertGreater(categories['environments']['symlinks'], 0)
        self.assertGreater(categories['runtimes']['logical_bytes'], 0)
        self.assertIsNone(report['reclaimable_bytes'])
        self.assertEqual(report['logical_bytes'], sum(row['logical_bytes'] for row in report['categories']))
        self.assertNotIn('reclaimable_bytes', categories['environments'])
        write_json(self.root / 'environment-storage-evidence.json', report)

    @unittest.skipUnless(os.environ.get('REPRISE_BROWSER_TESTS') == '1', 'set REPRISE_BROWSER_TESTS=1 for real Chromium capture')
    def test_real_browser_preserves_existing_runtime_then_stops_new_version_runtime(self):
        running = self.finished(self.app, 'run')
        captured = self.finished(self.app, 'capture')
        self.assertEqual(captured['status'], 'complete', captured)
        self.assertEqual(captured['runtimes'][0]['id'], running['id'])
        self.assert_http(running)
        self.assertTrue(next(row for row in self.app.runtimes.list() if row['id'] == running['id'])['running'])
        self.app.runtimes.stop(running['id'])
        (self.source / 'index.html').write_text('<!doctype html><link rel="icon" href="data:,"><h1>Historical environment second version</h1>')
        second = self.app.projects.snapshot(self.project['id'], 'Second capture version')['sha']
        self.app.projects.save_recipe(self.project['id'], self.recipe, second)
        own = self.finished(self.app, 'capture', second)
        self.assertEqual(own['status'], 'complete', own)
        self.assertEqual(own['sha'], second)
        self.assertNotEqual(own['runtimes'][0]['id'], running['id'])
        self.assertFalse(any(row['running'] for row in self.app.runtimes.list()))
        self.assertEqual({row['sha'] for row in self.app.runtimes.environments.list(self.project['id'])}, {self.sha, second})
        write_json(self.root / 'real-browser-capture-evidence.json', {'reused': captured, 'owned': own})


if __name__ == '__main__':
    unittest.main()
