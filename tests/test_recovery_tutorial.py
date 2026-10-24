"""The tutorial uses the public CLI and reports file saves separately from images."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from test_runtime import fixture


SPEC = importlib.util.spec_from_file_location('recovery_tutorial',
    Path(__file__).resolve().parents[1] / 'examples' / 'recovery-tutorial' / 'prepare.py')
tutorial = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tutorial)


class RecoveryTutorialTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('recovery-tutorial')
        self.destination = self.root / 'demo'
        self.entry = self.root / 'installed-reprise.py'
        self.entry.write_text('# Mock installed entry\n')
        self.calls = []
        self.saved = []
        self.capture_number = 0
        self.override = None

    def cli(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        operation = argv[argv.index('--data') + 2]
        if operation == 'save':
            sha = str(len(self.saved) + 1) * 40
            self.saved.append(sha)
            value = dict(project_id='demo-project', status='complete', result=dict(sha=sha))
        elif operation == 'recipe':
            value = dict(sha=argv[-1], status='saved')
        elif operation == 'capture':
            self.assertEqual(len(self.saved), 3, 'All file versions must be saved before capturing')
            self.capture_number += 1
            sha = argv[-1]
            picture = self.destination / ('picture-%s.png' % self.capture_number)
            picture.write_bytes(b'mock image bytes ' + sha.encode())
            value = dict(status='complete', result=dict(id='capture-%s' % self.capture_number,
                status='complete', source='automatic', sha=sha, errors=[], items=[dict(
                    sha=sha, side='after', media_type='image/png', capture_id='tutorial',
                    path=str(picture), content_sha256=tutorial.digest(picture))]))
        else:
            self.fail('Unexpected CLI operation ' + operation)
        if self.override:
            changed = self.override(operation, value)
            if changed is not None:
                return changed
        return subprocess.CompletedProcess(argv, 0, json.dumps(value), '')

    def prepare(self, **kwargs):
        with patch.object(tutorial.subprocess, 'run', side_effect=self.cli), contextlib.redirect_stdout(io.StringIO()):
            return tutorial.prepare(self.destination, entry=self.entry, **kwargs)

    def test_default_keeps_three_save_only_calls_and_old_summary_fields(self):
        summary = self.prepare()
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(summary['status'], 'prepared')
        self.assertEqual(summary['previews'], dict(requested=False, status='not_requested', results=[]))
        self.assertEqual(summary['file_versions'], dict(status='complete', saved=3))
        self.assertEqual(summary['versions'][0]['sha'], self.saved[0])
        self.assertIn(self.saved[0], summary['restore_command'])
        self.assertFalse((self.destination / 'preview.recipe.json').exists())
        self.assertFalse((self.destination / 'source' / '.git').exists())
        self.assertFalse((self.destination / 'restored-first-draft').exists())

    def test_preview_commands_pin_every_sha_and_preserve_installed_cli_mode(self):
        with patch.object(tutorial.subprocess, 'run', side_effect=self.cli), contextlib.redirect_stdout(io.StringIO()):
            summary = tutorial.prepare(self.destination, cli=self.entry, with_previews=True)
        self.assertEqual(len(self.calls), 9)
        self.assertEqual(summary['previews']['status'], 'complete')
        self.assertEqual(summary['previews']['complete'], 3)
        self.assertEqual([r['sha'] for r in summary['previews']['results']], self.saved)
        for number, sha in enumerate(self.saved):
            recipe, capture = self.calls[3 + 2 * number:5 + 2 * number]
            self.assertEqual(recipe[0][-2:], ['--sha', sha])
            self.assertEqual(capture[0][-2:], ['--sha', sha])
            self.assertEqual(capture[0][0], str(self.entry))
            self.assertIsNone(capture[1]['timeout'])
            self.assertNotIn('PYTHONPATH', capture[1]['env'])
        recipe = json.loads((self.destination / 'preview.recipe.json').read_text())
        self.assertEqual(recipe['adapter'], 'static-web')
        self.assertEqual(recipe['network'], 'local')
        self.assertNotIn('commands', recipe)
        self.assertEqual(len(list((self.destination / 'commands').glob('*.json'))), 9)
        self.assertEqual(json.loads((self.destination / 'summary.json').read_text()), summary)

    def test_partial_capture_failure_keeps_three_saves_and_later_capture(self):
        def fail_second(operation, value):
            if operation == 'capture' and self.capture_number == 2:
                value['result'].update(status='failed', items=[], errors=[dict(error='Browser unavailable')])
                # A completed job can wrap a failed capture; inspect both levels.
        self.override = fail_second
        summary = self.prepare(with_previews=True)
        self.assertEqual(summary['file_versions']['saved'], 3)
        self.assertEqual(summary['previews']['status'], 'partial')
        self.assertEqual(summary['previews']['complete'], 2)
        self.assertEqual(self.capture_number, 3)
        self.assertIn('Browser unavailable', str(summary['previews']['results'][1]['errors']))
        log = json.loads((self.destination / 'commands' / 'capture-2.json').read_text())
        self.assertIn('Browser unavailable', log['stdout'])

    def test_wrong_sha_diagnostic_and_modified_image_never_count_as_success(self):
        def invalid_image(operation, value):
            if operation == 'capture':
                image = value['result']['items'][0]
                if self.capture_number == 1:
                    image['sha'] = 'f' * 40
                elif self.capture_number == 2:
                    image['diagnostic'] = True
                else:
                    Path(image['path']).write_bytes(b'changed after recording')
        self.override = invalid_image
        summary = self.prepare(with_previews=True)
        self.assertEqual(summary['previews']['status'], 'failed')
        self.assertEqual(summary['previews']['complete'], 0)
        self.assertTrue(all(not result['images'] and result['errors'] for result in summary['previews']['results']))

    def test_recipe_timeout_keeps_output_and_continues_other_versions(self):
        def timeout(operation, value):
            if operation == 'recipe' and value['sha'] == self.saved[0]:
                raise subprocess.TimeoutExpired(['recipe'], 120, output=b'partial output', stderr=b'timed out')
        self.override = timeout
        summary = self.prepare(with_previews=True)
        self.assertEqual(summary['previews']['complete'], 2)
        self.assertEqual(self.capture_number, 2)
        log = json.loads((self.destination / 'commands' / 'recipe-1.json').read_text())
        self.assertIsNone(log['returncode'])
        self.assertEqual(log['stdout'], 'partial output')
        self.assertEqual(log['stderr'], 'timed out')
        self.assertTrue(log['error'])

    def test_invalid_json_capture_retained_without_losing_saved_versions(self):
        def malformed(operation, value):
            if operation == 'capture':
                return subprocess.CompletedProcess([], 1, 'not JSON', 'browser missing')
        self.override = malformed
        summary = self.prepare(with_previews=True)
        self.assertEqual(summary['file_versions']['status'], 'complete')
        self.assertEqual(summary['previews']['status'], 'failed')
        log = json.loads((self.destination / 'commands' / 'capture-1.json').read_text())
        self.assertEqual(log['stdout'], 'not JSON')
        self.assertEqual(log['stderr'], 'browser missing')

    def test_existing_destination_is_preserved(self):
        self.destination.mkdir()
        original = self.destination / 'original.txt'
        original.write_text('keep')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.prepare(with_previews=True)
        self.assertEqual(original.read_text(), 'keep')
        self.assertFalse(self.calls)

    def test_partial_preview_exits_one_after_reporting_saved_files(self):
        message = io.StringIO()
        with patch.object(tutorial.sys, 'argv', ['prepare.py', '--entry', str(self.entry),
                '--to', str(self.destination), '--with-previews']), \
                patch.object(tutorial, 'prepare', return_value=dict(previews=dict(status='partial'))), \
                contextlib.redirect_stderr(message), self.assertRaises(SystemExit) as error:
            tutorial.main()
        self.assertEqual(error.exception.code, 1)
        self.assertIn('All three file versions were saved', message.getvalue())


if __name__ == '__main__':
    unittest.main()
