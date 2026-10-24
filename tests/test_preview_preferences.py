"""Project opt-in, exact-version capture, and transfer without inherited execution."""
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from reprise.backup import create_backup, restore_backup, verify_backup
from reprise.cancellation import Cancelled
from reprise.projects import ProjectStore
from reprise.service import Reprise
from reprise.storage import read_json, write_json
from test_runtime import fixture


RECIPE = {'schema': 1, 'adapter': 'static-web', 'root': '.',
          'captures': [{'id': 'home', 'route': '/', 'viewport': {'width': 800, 'height': 600}}]}


class PreviewPreferencesTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('preview-preferences')
        self.source = self.root / 'working-folder'
        self.source.mkdir()
        (self.source / 'index.html').write_text('<h1>first</h1>')
        self.data = self.root / 'data'
        self.app = Reprise(self.data)
        self.identifier = self.app.projects.add(str(self.source), kind='folder')['id']

    def tearDown(self):
        self.app.close()

    def wait(self, job):
        deadline = time.monotonic() + 15
        while job['status'] in ('queued', 'running', 'cancelling') and time.monotonic() < deadline:
            time.sleep(.02)
            job = self.app.jobs.get(job['id'])
        self.assertEqual(job['status'], 'complete', job)
        return job['result']

    def snapshot(self, **body):
        return self.wait(self.app.execute(self.identifier, 'snapshot', body))

    def enable(self):
        first = self.snapshot()
        self.app.projects.save_recipe(self.identifier, RECIPE, first['sha'])
        self.app.projects.save_preview_preferences(self.identifier, 'auto', first['sha'])
        return first

    def test_default_and_nonautomatic_modes_save_without_running(self):
        with patch.object(self.app.captures, 'capture', side_effect=AssertionError('No capture consent')):
            first = self.snapshot()
            self.assertEqual(first['preview']['mode'], 'remind')
            for mode in ('none', 'manual', 'remind'):
                (self.source / 'index.html').write_text(mode)
                result = self.snapshot(preview_preferences={'mode': mode})
                self.assertEqual(result['preview']['mode'], mode)
                self.assertTrue(result['saved'])
                self.assertEqual(ProjectStore(self.data).record(self.identifier)['preview_preferences']['mode'], mode)

    def test_detection_and_unsaved_recipe_cannot_enable_auto(self):
        self.snapshot()
        before = (self.data / 'projects.json').read_bytes()
        with self.assertRaises(ValueError):
            self.app.projects.save_preview_preferences(self.identifier, 'auto', 'HEAD')
        with self.assertRaises(ValueError):
            self.app.projects.save_preview_preferences(self.identifier, 'auto')
        with self.assertRaises(ValueError):
            self.app.projects.save_preview_preferences(self.identifier, 'surprise')
        self.assertEqual((self.data / 'projects.json').read_bytes(), before)

    def test_auto_uses_explicit_template_and_new_exact_sha(self):
        first = self.enable()
        # A new repository recipe is untrusted and cannot replace the user's template.
        (self.source / '.reprise.json').write_text(json.dumps({'schema': 1, 'adapter': 'manual'}))
        (self.source / 'index.html').write_text('<h1>second</h1>')
        def capture(repository, project, sha, recipe, **kwargs):
            self.assertNotEqual(sha, first['sha'])
            self.assertEqual(project, self.identifier)
            self.assertEqual(repository.blob(sha, 'index.html'), b'<h1>second</h1>')
            self.assertEqual(recipe['adapter'], 'static-web')
            self.assertTrue(kwargs['approved'])
            return {'status': 'complete', 'sha': sha}
        with patch.object(self.app.captures, 'capture', side_effect=capture), patch.object(self.app.evidence, 'public', side_effect=lambda r:r):
            result = self.snapshot()
        self.assertEqual(result['preview']['status'], 'complete')
        self.assertEqual(result['preview']['evidence']['sha'], result['sha'])
        self.assertFalse((self.source / '.git').exists())

    def test_capture_failure_and_cancel_do_not_undo_committed_version(self):
        self.enable()
        for error in (RuntimeError('Synthetic browser failure'), Cancelled()):
            (self.source / 'index.html').write_text(str(error))
            def interrupted(*args, **kwargs):
                if isinstance(error, Cancelled):
                    kwargs['cancel'].request_path.touch()
                raise error
            with patch.object(self.app.captures, 'capture', side_effect=interrupted):
                result = self.snapshot()
            self.assertTrue(result['saved'])
            self.assertIn(result['preview']['status'], ('failed', 'cancelled'))
            self.assertEqual(self.app.projects.repository(self.identifier).blob(result['sha'], 'index.html'), str(error).encode())

    def test_transfer_preserves_versions_and_resets_auto_execution(self):
        first = self.enable()
        self.app.close()
        backup = self.root / 'portable-backup'
        create_backup(self.data, backup)
        self.assertEqual(verify_backup(backup)['status'], 'verified')
        restored = self.root / 'other-computer-data'
        restore_backup(backup, restored)
        store = ProjectStore(restored)
        record = store.record(self.identifier)
        self.assertEqual(record['preview_preferences']['mode'], 'remind')
        self.assertTrue(record['preview_preferences']['restored_auto_requires_confirmation'])
        # Simulate an unavailable source path on the destination without moving originals.
        document = read_json(restored / 'projects.json')
        document['projects'][0]['path'] = str(self.root / 'offline-original-path')
        write_json(restored / 'projects.json', document, private=True)
        repository = store.repository(self.identifier)
        destination = self.root / 'recovered-on-other-computer'
        repository.materialize(first['sha'], destination)
        self.assertEqual((destination / 'index.html').read_text(), '<h1>first</h1>')
        self.assertTrue(self.source.is_dir())
        self.assertTrue(self.data.is_dir())
        # The actual CLI opener must not require the old machine's folder.
        import os
        import subprocess
        import sys
        from reprise.launcher import shutdown
        try:
            process = subprocess.run([sys.executable, '-m', 'reprise', '--data', str(restored),
                'open', '--project', self.identifier, '--lang', 'en', '--no-browser'],
                env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src')),
                capture_output=True, text=True, timeout=25)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(json.loads(process.stdout)['project_id'], self.identifier)
        finally:
            shutdown(restored)
