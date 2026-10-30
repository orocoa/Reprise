"""Real source-only open/reuse/shutdown with retained, isolated data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from reprise.launcher import open_workbench, shutdown
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

    def test_restored_data_can_start_a_new_service_without_old_process_authority(self):
        one = self.cli('open', str(self.repo.path), '--no-browser')
        self.cli('shutdown')
        backup, restored = self.root / 'backup', self.root / 'restored-state'
        self.cli('backup', '--to', str(backup))
        self.cli('data-restore', str(backup), '--to', str(restored))
        self.data.rename(self.root / 'original-state-unavailable')
        self.data = restored
        marker = json.loads((self.data / 'server.json').read_text())
        self.assertTrue(marker['restored_process_authority_disabled'])
        self.assertIsNone(marker['pid'])
        two = self.cli('open', str(self.repo.path), '--no-browser')
        self.assertFalse(two['reused'])
        self.assertEqual(two['project_id'], one['project_id'])
        self.assertNotEqual(two['pid'], one['pid'])
        self.assertTrue(self.cli('shutdown')['stopped'])

    def test_open_without_path_opens_current_project_without_saving(self):
        result = self.cli('open', '--no-browser')
        self.assertEqual(result['path'], str(self.repo.work_tree))
        self.assertIsNotNone(result['project_id'])
        self.assertEqual(self.cli('projects')[0]['kind'], 'folder')
        self.assertEqual(self.cli('history', result['project_id'])['commits'], [])

    def test_current_project_reuses_folder_choice_from_a_nested_directory(self):
        from reprise.launcher import open_current_project
        from reprise.projects import ProjectStore
        store = ProjectStore(self.data)
        git = store.add(str(self.repo.work_tree))
        folder = store.add(str(self.repo.work_tree), kind='folder')
        store.save_preview_preferences(folder['id'], 'none')
        nested = self.repo.work_tree / 'nested'; nested.mkdir()
        result = open_current_project(self.data, nested, browser=False)
        self.assertEqual(result['project_id'], folder['id'])
        self.assertNotEqual(result['project_id'], git['id'])
        self.assertEqual(store.record(folder['id'])['preview_preferences']['mode'], 'none')

    def test_explicit_invoking_folder_wins_over_agent_process_directory(self):
        source = self.root / 'another website'; source.mkdir()
        (source / 'index.html').write_text('<h1>Current task</h1>')
        result = self.cli('open', '--cwd', str(source), '--no-browser')
        self.assertEqual(result['path'], str(source))
        self.assertEqual(self.cli('history', result['project_id'])['commits'], [])

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

    def test_empty_workbench_starts_reuses_and_never_imports_a_folder(self):
        from unittest.mock import patch
        from reprise.projects import ProjectStore
        with patch.object(ProjectStore, 'source', side_effect=AssertionError('No source was selected')):
            one = open_workbench(self.data, browser=False, language='en')
            two = open_workbench(self.data, browser=False)
        self.assertIsNone(one['project_id'])
        self.assertIsNone(one['path'])
        self.assertNotIn('project=', one['url'])
        self.assertIn('lang=en', one['url'])
        self.assertFalse(one['reused'])
        self.assertTrue(two['reused'])
        self.assertEqual(one['pid'], two['pid'])
        self.assertEqual(ProjectStore(self.data).records(), [])

    def test_source_workbench_entry_works_outside_checkout_without_cwd_import(self):
        from reprise.projects import ProjectStore
        entry = Path(__file__).resolve().parents[1] / 'scripts' / 'start_workbench.py'
        # A same-named module in the arbitrary current folder must not be loaded.
        (self.repo.work_tree / 'reprise.py').write_text('raise RuntimeError("wrong import")\n')
        process = subprocess.run([sys.executable, '-I', '-S', str(entry), '--data', str(self.data),
                                  '--no-browser', '--json'], cwd=str(self.repo.work_tree),
                                 capture_output=True, text=True, timeout=25)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertIsNone(result['project_id'])
        self.assertEqual(ProjectStore(self.data).records(), [])
        self.assertEqual((self.repo.work_tree / 'reprise.py').read_text(), 'raise RuntimeError("wrong import")\n')

    def test_double_click_entry_accepts_package_path_with_spaces(self):
        from reprise.projects import ProjectStore
        package = self.root / 'Reprise package with spaces'
        package.symlink_to(Path(__file__).resolve().parents[1], target_is_directory=True)
        process = subprocess.run(['/bin/sh', str(package / 'Reprise.command'), '--data', str(self.data),
                                  '--no-browser', '--json'], cwd=str(self.repo.work_tree),
                                 capture_output=True, text=True, timeout=25)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIsNone(json.loads(process.stdout)['project_id'])
        self.assertEqual(ProjectStore(self.data).records(), [])

    def test_workbench_does_not_reuse_incompatible_server(self):
        from unittest.mock import patch
        with patch('reprise.launcher.verified_server', return_value={'version': '0.0.0'}):
            with self.assertRaisesRegex(ValueError, 'Another Reprise version'):
                open_workbench(self.data, browser=False)
