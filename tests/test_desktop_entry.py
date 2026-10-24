"""The desktop bridge reports ownership without stopping unrelated services."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from reprise import __version__, desktop_entry
from reprise.launcher import _ensure_server, service_source_id, shutdown
from test_desktop_bundle import make_bundle
from test_runtime import fixture


class DesktopEntryTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('desktop-entry')
        self.resources, _ = make_bundle(self.root)
        self.data = self.root / 'state'

    def run_entry(self, command, *args, data=True):
        stdout, stderr = StringIO(), StringIO()
        argv = [command, '--resources', str(self.resources), *args]
        if data:
            argv.extend(['--data', str(self.data)])
        with patch.dict(os.environ, dict(os.environ), clear=True):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = desktop_entry.main(argv)
        return result, stdout.getvalue(), stderr.getvalue()

    def test_open_returns_confirmed_id_and_reused_without_browser(self):
        for reused in (False, True):
            with self.subTest(reused=reused):
                result = {'pid': 123, 'instance_id': 'owned-instance',
                          'reused': reused, 'url': 'http://127.0.0.1:1234/'}
                record = {'pid': 123, 'instance_id': 'owned-instance'}
                with patch.object(desktop_entry, 'open_workbench', return_value=result) as opened:
                    with patch.object(desktop_entry, 'verified_server', return_value=record):
                        code, stdout, stderr = self.run_entry('open')
                self.assertEqual(code, 0, stderr)
                opened.assert_called_once_with(str(self.data), browser=False)
                self.assertEqual(json.loads(stdout)['reused'], reused)
                self.assertEqual(json.loads(stdout)['instance_id'], 'owned-instance')
                self.assertEqual(len(stdout.splitlines()), 1)

    def test_service_changing_during_open_does_not_claim_new_ownership(self):
        result = {'pid': 123, 'instance_id': 'original', 'reused': False}
        record = {'pid': 456, 'instance_id': 'replacement'}
        with patch.object(desktop_entry, 'open_workbench', return_value=result):
            with patch.object(desktop_entry, 'verified_server', return_value=record):
                code, stdout, stderr = self.run_entry('open')
        self.assertEqual(code, 1)
        self.assertEqual(stdout, '')
        self.assertIn('changed before ownership was confirmed', stderr)
        self.assertNotIn('Traceback', stderr)

    def test_default_data_reuses_existing_cli_rule(self):
        record = {'pid': 123, 'instance_id': 'original', 'reused': True}
        expected = str(self.root / 'existing-data')
        with patch.object(desktop_entry, 'default_directory', return_value=expected):
            with patch.object(desktop_entry, 'open_workbench', return_value=record) as opened:
                with patch.object(desktop_entry, 'verified_server', return_value=record):
                    code, _, stderr = self.run_entry('open', data=False)
        self.assertEqual(code, 0, stderr)
        opened.assert_called_once_with(expected, browser=False)

    def test_shutdown_requires_owned_instance_and_passes_it_to_launcher(self):
        with patch.object(desktop_entry, 'shutdown') as stopped:
            code, stdout, stderr = self.run_entry('shutdown')
        self.assertEqual(code, 1)
        stopped.assert_not_called()
        self.assertEqual(stdout, '')
        self.assertIn('requires --instance-id', stderr)
        with patch.object(desktop_entry, 'shutdown', return_value={'stopped': True}) as stopped:
            code, stdout, stderr = self.run_entry('shutdown', '--instance-id', 'owned')
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout), {'stopped': True})
        stopped.assert_called_once_with(str(self.data), instance_id='owned')

    def test_doctor_prints_one_json_and_does_not_open_workbench(self):
        with patch.object(desktop_entry, 'open_workbench') as opened:
            code, stdout, stderr = self.run_entry('doctor')
        self.assertEqual(code, 0, stderr)
        self.assertTrue(json.loads(stdout)['ok'])
        self.assertEqual(len(stdout.splitlines()), 1)
        self.assertFalse(self.data.exists())
        opened.assert_not_called()

    def test_isolated_absolute_entry_imports_do_not_write_into_the_bundle(self):
        source = Path(__file__).resolve().parents[1] / 'src' / 'reprise'
        package = self.resources / 'app' / 'reprise'
        shutil.copytree(source, package, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        entry = package / 'desktop_entry.py'
        process = subprocess.run(
            [sys.executable, '-I', '-S', str(entry), 'doctor',
             '--resources', str(self.resources), '--data', str(self.data)],
            cwd=str(self.root), capture_output=True, text=True, timeout=15)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertTrue(json.loads(process.stdout)['ok'])
        self.assertEqual(list(package.rglob('__pycache__')), [])
        self.assertFalse(self.data.exists())

    def test_cli_forwards_arguments_output_and_exit_status_after_configuring_bundle(self):
        arguments = ['--data', str(self.data), 'save', '/draft with spaces',
                     '--title', '布局 "第二稿"', '--capture-static']
        stdout, stderr = StringIO(), StringIO()
        observed = {}

        def cli(values):
            observed['argv'] = values
            observed['node'] = os.environ['REPRISE_NODE']
            observed['pollution'] = os.environ.get('NODE_OPTIONS')
            print('{"saved":true,"capture":"failed"}')
            return 7

        with patch.dict(os.environ, {'NODE_OPTIONS': '--require=/outside'}, clear=True):
            with patch.object(desktop_entry, 'cli_main', side_effect=cli):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = desktop_entry.main(
                        ['cli', '--resources', str(self.resources), '--', *arguments])
        self.assertEqual(code, 7)
        self.assertEqual(observed['argv'], arguments)
        self.assertTrue(observed['node'].startswith(str(self.resources)))
        self.assertIsNone(observed['pollution'])
        self.assertEqual(stdout.getvalue(), '{"saved":true,"capture":"failed"}\n')
        self.assertEqual(stderr.getvalue(), '')

    def test_cli_reuses_actual_command_parser_and_does_not_wrap_its_json(self):
        stdout, stderr = StringIO(), StringIO()
        with patch.dict(os.environ, dict(os.environ), clear=True):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = desktop_entry.main([
                    'cli', '--resources', str(self.resources), '--',
                    '--data', str(self.data), 'projects'])
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(json.loads(stdout.getvalue()), [])


class DesktopShutdownTests(unittest.TestCase):
    def test_concurrent_opener_is_reused_instead_of_claimed_as_owned(self):
        directory = fixture('desktop-concurrent-open')
        process = Mock(pid=123)
        process.poll.return_value = None
        record = {'pid': 456, 'identity': 'identity', 'instance_id': 'other', 'version': __version__,
                  'source_id': service_source_id()}
        with patch('reprise.launcher.verified_server', side_effect=[None, record]), \
                patch('reprise.launcher.process_identity', return_value='verified-caller'):
            with patch('reprise.launcher.subprocess.Popen', return_value=process):
                found, reused = _ensure_server(directory, 0)
        self.assertEqual(found, record)
        self.assertTrue(reused)

    def test_concurrent_other_version_is_not_reused_or_stopped(self):
        directory = fixture('desktop-concurrent-version')
        process = Mock(pid=123)
        process.poll.return_value = None
        record = {'pid': 456, 'identity': 'identity', 'instance_id': 'other', 'version': '0.0.0'}
        with patch('reprise.launcher.verified_server', side_effect=[None, record]), \
                patch('reprise.launcher.process_identity', return_value='verified-caller'):
            with patch('reprise.launcher.subprocess.Popen', return_value=process):
                with self.assertRaisesRegex(ValueError, 'Another Reprise version is running'):
                    _ensure_server(directory, 0)
        process.terminate.assert_not_called()
        process.kill.assert_not_called()

    def test_only_our_running_process_grants_shutdown_ownership(self):
        directory = fixture('desktop-owned-open')
        process = Mock(pid=123)
        process.poll.return_value = None
        record = {'pid': 123, 'identity': 'identity', 'instance_id': 'owned', 'version': __version__,
                  'source_id': service_source_id()}
        with patch('reprise.launcher.verified_server', side_effect=[None, record]), \
                patch('reprise.launcher.process_identity', return_value='verified-caller'):
            with patch('reprise.launcher.subprocess.Popen', return_value=process):
                found, reused = _ensure_server(directory, 0)
        self.assertEqual(found, record)
        self.assertFalse(reused)

    def test_mismatched_instance_never_sends_a_shutdown_request(self):
        record = {'pid': 123, 'instance_id': 'replacement'}
        with patch('reprise.launcher.verified_server', return_value=record):
            with patch('reprise.launcher._request') as request:
                result = shutdown('/unused', instance_id='original')
        self.assertEqual(result, {'stopped': False, 'reason': 'different-instance'})
        request.assert_not_called()

    def test_matching_instance_is_sent_to_server_for_second_check(self):
        record = {'pid': 123, 'identity': 'identity', 'instance_id': 'owned'}
        with patch('reprise.launcher.verified_server', return_value=record):
            with patch('reprise.launcher._request', side_effect=[
                    {'token': 'token'}, {'stopped': True}]) as request:
                with patch('reprise.launcher.process_identity', return_value=None):
                    result = shutdown('/unused', instance_id='owned')
        self.assertTrue(result['stopped'])
        self.assertEqual(request.call_args.args,
                         (record, '/api/shutdown', {'instance_id': 'owned'}, 'token'))

    def test_changed_server_response_is_returned_without_waiting_or_killing(self):
        record = {'pid': 123, 'identity': 'identity', 'instance_id': 'owned'}
        response = {'stopped': False, 'reason': 'different-instance'}
        with patch('reprise.launcher.verified_server', return_value=record):
            with patch('reprise.launcher._request', side_effect=[{'token': 'token'}, response]):
                with patch('reprise.launcher.process_identity') as identity:
                    result = shutdown('/unused', instance_id='owned')
        self.assertEqual(result, response)
        identity.assert_not_called()
