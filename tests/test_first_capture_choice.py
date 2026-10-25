"""The first answer persists independently of capture readiness and chat state."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import time
import unittest
from unittest.mock import patch

from reprise.cli import main
from reprise.projects import ProjectStore
from reprise.service import Reprise
from test_runtime import fixture
from test_vite_preview import manifest, lock


class FirstCaptureChoiceTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('first-capture-choice')
        self.source = self.root / 'webpage'
        self.source.mkdir()
        (self.source / 'index.html').write_text('<h1>first</h1>')
        self.data = self.root / 'data'
        self.app = Reprise(self.data)
        self.project = self.app.projects.add(str(self.source), kind='folder')['id']

    def tearDown(self):
        self.app.close()

    def snapshot(self, **body):
        job = self.app.execute(self.project, 'snapshot', body)
        end = time.monotonic() + 15
        while job['status'] in ('queued', 'running', 'cancelling') and time.monotonic() < end:
            time.sleep(.01)
            job = self.app.jobs.get(job['id'])
        self.assertEqual(job['status'], 'complete', job)
        return job['result']

    def preference(self):
        return ProjectStore(self.data).record(self.project)['preview_preferences']

    def capture(self, repository, project, sha, recipe, **kwargs):
        self.assertEqual(project, self.project)
        self.assertEqual(recipe['adapter'], 'static-web')
        self.assertTrue(kwargs['approved'])
        return {'id': 'synthetic', 'sha': sha, 'status': 'complete', 'items': []}

    def test_yes_is_persisted_before_configuration_without_execution(self):
        with patch.object(self.app.captures, 'capture', side_effect=AssertionError('No save requested')):
            self.app.projects.save_preview_preferences(self.project, 'auto', pending_recipe=True)
        self.assertTrue(self.preference()['pending_recipe'])
        self.assertEqual(self.preference()['mode'], 'auto')
        self.assertEqual(self.app.projects.repository(self.project).history()['commits'], [])
        self.assertNotIn('version_recipes', self.app.projects.record(self.project))

    def test_first_static_save_completes_choice_then_future_save_reuses_it(self):
        with patch.object(self.app.captures, 'capture', side_effect=self.capture) as capture:
            first = self.snapshot(preview_preferences={'mode': 'auto', 'pending_recipe': True})
            self.assertNotIn('pending_recipe', self.preference())
            self.assertEqual(self.preference()['source_sha'], first['sha'])
            (self.source / 'index.html').write_text('<h1>second</h1>')
            second = self.snapshot()
        self.assertEqual(capture.call_count, 2)
        self.assertNotEqual(first['sha'], second['sha'])
        self.assertEqual(second['preview']['status'], 'complete')
        self.assertEqual(self.preference()['source_sha'], first['sha'])
        self.assertEqual((self.source / 'index.html').read_text(), '<h1>second</h1>')
        self.assertFalse((self.source / '.git').exists())

    def test_browser_failure_keeps_yes_and_files_for_an_ordinary_retry(self):
        with patch.object(self.app.captures, 'capture', side_effect=RuntimeError('Browser missing')):
            first = self.snapshot(preview_preferences={'mode': 'auto', 'pending_recipe': True})
        self.assertTrue(first['saved'])
        self.assertEqual(first['preview']['status'], 'failed')
        self.assertEqual(self.preference()['mode'], 'auto')
        self.assertEqual(self.preference()['source_sha'], first['sha'])
        with patch.object(self.app.captures, 'capture', side_effect=self.capture):
            retry = self.snapshot()
        self.assertTrue(retry['unchanged'])
        self.assertEqual(retry['sha'], first['sha'])
        self.assertEqual(retry['preview']['status'], 'complete')

    def test_missing_command_approval_keeps_choice_but_never_executes_it(self):
        package = manifest()
        (self.source / 'package.json').write_text(json.dumps(package))
        (self.source / 'package-lock.json').write_text(json.dumps(lock(package)))
        with patch.object(self.app.captures, 'capture', side_effect=AssertionError('Unapproved command')):
            first = self.snapshot(preview_preferences={'mode': 'auto', 'pending_recipe': True})
            second = self.snapshot()
        self.assertEqual(first['preview']['status'], 'needs-approval')
        self.assertEqual(second['preview']['status'], 'needs-approval')
        self.assertTrue(self.preference()['pending_recipe'])
        self.assertFalse(self.app.projects.record(self.project).get('version_recipes'))
        plan = first['preview']['plan']
        self.app.projects.save_recipe(self.project, plan['recipe'], first['sha'])
        self.assertNotIn('pending_recipe', self.preference())
        self.assertEqual(self.preference()['recipe']['adapter'], 'command-web')

    def test_no_is_remembered_on_later_saves(self):
        with patch.object(self.app.captures, 'capture', side_effect=AssertionError('User chose files only')):
            self.snapshot(preview_preferences={'mode': 'none'})
            (self.source / 'index.html').write_text('<h1>second</h1>')
            result = self.snapshot()
        self.assertEqual(self.preference()['mode'], 'none')
        self.assertEqual(result['preview']['status'], 'not-requested')

    def test_a_queued_yes_never_reenables_a_newer_no(self):
        choice = self.app.projects.save_preview_preferences(self.project, 'auto', pending_recipe=True)
        self.app.projects.save_preview_preferences(self.project, 'none')
        with patch.object(self.app.captures, 'capture', side_effect=self.capture):
            result = self.app.save_with_preview(self.project, 'Previously queued', choice, None)
        self.assertTrue(result['saved'])
        self.assertEqual(self.preference()['mode'], 'none')

    def test_invalid_pending_flags_cannot_create_execution_approval(self):
        for mode, sha, pending in [('none', None, True), ('auto', 'HEAD', True), ('auto', None, 'yes')]:
            with self.assertRaises(ValueError):
                self.app.projects.save_preview_preferences(self.project, mode, sha, pending_recipe=pending)
        self.assertNotIn('preview_preferences', self.app.projects.record(self.project))

    def test_documented_cli_can_remember_yes_before_first_capture(self):
        output, error = StringIO(), StringIO()
        self.app.close()
        with patch('reprise.capture.CaptureService.capture', side_effect=RuntimeError('Browser missing')), redirect_stdout(output), redirect_stderr(error):
            code = main(['--data', str(self.data), 'save', str(self.source), '--preview', 'auto', '--preview-pending'])
        self.assertEqual(code, 0, error.getvalue())
        result = json.loads(output.getvalue())['result']
        self.assertTrue(result['saved'])
        self.assertEqual(result['preview']['status'], 'failed')
        self.assertEqual(self.preference()['mode'], 'auto')
