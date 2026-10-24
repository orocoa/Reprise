"""CLI entry points keep draft durability and explicit capture consent intact."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import patch

from reprise.cli import main
from reprise.projects import ProjectStore
from test_runtime import fixture


class DraftCLITests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('cli-draft')
        self.source = self.root / 'Website with spaces'
        self.source.mkdir()
        self.content = '<!doctype html><h1>A local draft</h1>'
        (self.source / 'index.html').write_text(self.content)
        self.data = self.root / 'state'

    def cli(self, *arguments):
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(['--data', str(self.data), *map(str, arguments)])
        self.assertEqual(code, 0, error.getvalue())
        return json.loads(output.getvalue())

    def test_save_waits_for_capture_of_the_persisted_exact_draft(self):
        def capture(repository, identifier, sha, recipe, **options):
            self.assertEqual(repository.blob(sha, 'index.html'), self.content.encode())
            self.assertIn(len(sha), (40, 64))
            saved = ProjectStore(self.data).record(identifier)['version_recipes'][sha]
            self.assertEqual(saved['recipe'], recipe)
            self.assertEqual(recipe['adapter'], 'static-web')
            self.assertEqual(recipe['commands'], {})
            self.assertTrue(options['approved'])
            return {'id': 'synthetic-capture', 'sha': sha, 'status': 'complete', 'items': []}

        with patch('reprise.capture.CaptureService.capture', side_effect=capture) as browser:
            job = self.cli('save', self.source, '--title', 'Before spacing changes', '--capture-static')
        browser.assert_called_once()
        self.assertEqual(job['status'], 'complete')
        result = job['result']
        self.assertTrue(result['saved'])
        self.assertEqual(result['preview']['status'], 'complete')
        self.assertEqual(result['preview']['evidence']['sha'], result['sha'])
        self.assertNotIn('preview_preferences', ProjectStore(self.data).record(job['project_id']))
        self.assertEqual((self.source / 'index.html').read_text(), self.content)
        self.assertFalse((self.source / '.git').exists())
        (self.root / 'save-result.json').write_text(json.dumps(job, indent=2))

    def test_snapshot_capture_failure_keeps_files_and_existing_preference(self):
        store = ProjectStore(self.data)
        project = store.add(str(self.source), kind='folder')['id']
        store.save_preview_preferences(project, 'none')
        with patch('reprise.capture.CaptureService.capture', side_effect=RuntimeError('Browser unavailable')):
            job = self.cli('snapshot', project, '--capture-static', '--title', 'Still saved')
        self.assertEqual(job['status'], 'complete')
        result = job['result']
        self.assertTrue(result['saved'])
        self.assertEqual(result['preview']['status'], 'failed')
        self.assertEqual(result['preview']['error'], 'Browser unavailable')
        store = ProjectStore(self.data)
        self.assertEqual(store.repository(project).blob(result['sha'], 'index.html'), self.content.encode())
        self.assertEqual(store.record(project)['preview_preferences']['mode'], 'none')
        (self.root / 'capture-failure-result.json').write_text(json.dumps(job, indent=2))

    def test_save_without_capture_flag_does_not_run_a_browser(self):
        with patch('reprise.capture.CaptureService.capture') as browser:
            job = self.cli('save', self.source)
        browser.assert_not_called()
        self.assertTrue(job['result']['saved'])
        self.assertEqual(job['result']['preview']['mode'], 'remind')
        self.assertEqual(job['result']['preview']['status'], 'optional')

    def test_remote_assets_need_configuration_without_losing_saved_files(self):
        (self.source / 'index.html').write_text('<img src="https://example.invalid/image.png">')
        with patch('reprise.capture.CaptureService.capture') as browser:
            job = self.cli('save', self.source, '--capture-static')
        browser.assert_not_called()
        self.assertTrue(job['result']['saved'])
        self.assertEqual(job['result']['preview']['status'], 'needs-configuration')
        self.assertEqual(job['result']['preview']['plan']['reason'], 'remote-assets')

    def test_capture_and_preview_conflicts_are_rejected_before_any_registration(self):
        for command, target in (('save', str(self.source)), ('snapshot', 'unregistered')):
            for preference in ('none', 'manual', 'remind', 'auto'):
                with self.subTest(command=command, preference=preference):
                    error = StringIO()
                    with patch('reprise.service.Reprise') as app, redirect_stderr(error), self.assertRaises(SystemExit) as failed:
                        main(['--data', str(self.data), command, target, '--capture-static', '--preview', preference])
                    self.assertEqual(failed.exception.code, 2)
                    self.assertIn('not allowed', error.getvalue())
                    app.assert_not_called()
        self.assertFalse(self.data.exists())

    def test_workbench_dispatch_preserves_language_and_does_not_import_cwd(self):
        expected = {'url': 'http://127.0.0.1:51582/?lang=en', 'project_id': None, 'path': None}
        with patch('reprise.launcher.open_workbench', return_value=expected) as open_workspace, \
                patch('reprise.launcher.open_repository') as open_repository:
            result = self.cli('open', '--workbench', '--lang', 'en', '--port', '51582', '--no-browser')
        self.assertEqual(result, expected)
        open_workspace.assert_called_once_with(str(self.data), 51582, False, 'en')
        open_repository.assert_not_called()
        self.assertFalse(self.data.exists())

    def test_workbench_conflicts_fail_before_compatibility_or_launcher_actions(self):
        conflicts = [['.'], [str(self.source)], ['--folder'], ['--history', str(self.source)],
                     ['--history-catalog', 'catalog.json'], ['--repo', str(self.source)],
                     ['--project', 'identifier'], ['--registry', 'registry.json'],
                     ['--repo=' + str(self.source)], ['--project=identifier'], ['--registry=registry.json']]
        for extra in conflicts:
            with self.subTest(extra=extra):
                error = StringIO()
                with patch('reprise.compat.main') as compat, patch('reprise.launcher.open_workbench') as opening, \
                        patch('reprise.projects.ProjectStore') as store, redirect_stderr(error), self.assertRaises(SystemExit) as failed:
                    main(['--data', str(self.data), 'open', '--workbench', *extra])
                self.assertEqual(failed.exception.code, 2)
                self.assertIn('--workbench cannot be combined', error.getvalue())
                compat.assert_not_called()
                opening.assert_not_called()
                store.assert_not_called()
        self.assertFalse(self.data.exists())

    def test_bare_and_pathless_open_do_not_import_current_folder(self):
        for arguments in ((), ('open', '--no-browser')):
            with self.subTest(arguments=arguments), \
                    patch('reprise.launcher.open_workbench', return_value={'project_id': None}) as opening, \
                    patch('reprise.launcher.open_repository') as importing:
                self.cli(*arguments)
                opening.assert_called_once_with(str(self.data), 0, not arguments, None)
                importing.assert_not_called()

    def test_project_options_without_a_path_are_rejected_before_opening(self):
        for arguments in (('--folder',), ('--history', 'source'), ('--history-catalog', 'catalog.json')):
            with self.subTest(arguments=arguments), redirect_stderr(StringIO()), \
                    patch('reprise.launcher.open_repository') as opening, self.assertRaises(SystemExit):
                self.cli('open', *arguments)
            opening.assert_not_called()


if __name__ == '__main__':
    unittest.main()
