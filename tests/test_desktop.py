"""Native-picker contracts only: never open a real system dialog in tests."""
import os
import subprocess
import unittest
from unittest.mock import patch

from reprise import desktop
from test_runtime import fixture


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('desktop-picker')
        self.selected = self.root / 'local project'
        self.selected.mkdir()
        self.platform = patch.object(desktop.sys, 'platform', 'darwin')
        self.which = patch.object(desktop.shutil, 'which', return_value='/usr/bin/osascript')
        self.run = patch.object(desktop.subprocess, 'run')
        self.platform.start()
        self.which_mock = self.which.start()
        self.run_mock = self.run.start()
        self.addCleanup(self.platform.stop)
        self.addCleanup(self.which.stop)
        self.addCleanup(self.run.stop)

    def completion(self, stdout=b'', returncode=0, stderr=b''):
        self.run_mock.return_value = subprocess.CompletedProcess([], returncode, stdout, stderr)

    def test_capabilities_do_not_open_picker(self):
        self.assertEqual(desktop.capabilities(), {'supported': True, 'backend': 'osascript', 'reason': None})
        self.run_mock.assert_not_called()
        self.which_mock.assert_called_once_with('/usr/bin/osascript')

    def test_mac_selection_uses_fixed_script_and_returns_existing_folder(self):
        self.completion(os.fsencode(self.selected) + b'/\n')
        result = desktop.choose_folder()
        self.assertEqual(result['status'], 'selected')
        self.assertEqual(result['path'], str(self.selected) + '/')
        args, kwargs = self.run_mock.call_args
        self.assertEqual(args[0], ['/usr/bin/osascript', '-e', desktop._MAC_SCRIPT])
        self.assertNotIn(str(self.selected), args[0][-1])
        self.assertNotIn('shell', kwargs)
        self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
        self.assertEqual(kwargs['timeout'], 120)

    def test_mac_cancel_is_explicit_and_does_not_choose_cwd(self):
        for output, code, error in ((b'\n', 0, b''), (b'', 1, b'User canceled. (-128)')):
            with self.subTest(code=code):
                self.completion(output, code, error)
                result = desktop.choose_folder()
                self.assertEqual(result['status'], 'cancelled')
                self.assertIsNone(result['path'])

    def test_timeout_and_failure_release_picker_lock(self):
        self.run_mock.side_effect = subprocess.TimeoutExpired('osascript', 2)
        self.assertEqual(desktop.choose_folder(timeout=2)['status'], 'timeout')
        self.run_mock.side_effect = OSError('Synthetic unavailable executable')
        self.assertEqual(desktop.choose_folder()['reason'], 'picker-start-failed')
        self.run_mock.side_effect = None
        self.completion(os.fsencode(self.selected) + b'\n')
        self.assertEqual(desktop.choose_folder()['status'], 'selected')

    def test_unexpected_process_error_is_not_cancellation(self):
        self.completion(b'', 1, b'Execution not permitted')
        result = desktop.choose_folder()
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['reason'], 'picker-failed')
        self.assertIsNone(result['path'])

    def test_invalid_or_missing_directory_is_rejected(self):
        for output in (b'relative/folder\n', os.fsencode(self.root / 'absent') + b'\n', b'/invalid\x00name\n'):
            with self.subTest(output=output):
                self.completion(output)
                result = desktop.choose_folder()
                self.assertEqual(result['reason'], 'selected-folder-unavailable')
                self.assertIsNone(result['path'])

    def test_spaces_and_newlines_in_actual_directory_name_are_preserved(self):
        selected = self.root / '  odd\nfolder  '
        selected.mkdir()
        self.completion(os.fsencode(selected) + b'\n')
        self.assertEqual(desktop.choose_folder()['path'], str(selected))

    def test_linux_zenity_uses_argument_array(self):
        with patch.object(desktop.sys, 'platform', 'linux'), patch.dict(os.environ, {'DISPLAY': ':1'}, clear=True):
            self.which_mock.return_value = '/usr/bin/zenity'
            self.completion(os.fsencode(self.selected) + b'\n')
            result = desktop.choose_folder()
            self.assertEqual(result['backend'], 'zenity')
            self.assertEqual(result['status'], 'selected')
            self.assertEqual(self.run_mock.call_args.args[0], ['/usr/bin/zenity', '--file-selection', '--directory',
                                                              '--title=Choose your local project folder'])

    def test_linux_kdialog_fallback_and_cancel(self):
        with patch.object(desktop.sys, 'platform', 'linux'), patch.dict(os.environ, {'WAYLAND_DISPLAY': 'wayland-0'}, clear=True):
            self.which_mock.side_effect = lambda name: '/usr/bin/kdialog' if name == 'kdialog' else None
            self.completion(b'', 1)
            result = desktop.choose_folder()
            self.assertEqual(result['backend'], 'kdialog')
            self.assertEqual(result['status'], 'cancelled')
            self.assertEqual(self.run_mock.call_args.args[0][1], '--getexistingdirectory')

    def test_headless_or_missing_picker_never_starts_a_process(self):
        with patch.object(desktop.sys, 'platform', 'linux'), patch.dict(os.environ, {}, clear=True):
            result = desktop.choose_folder()
            self.assertEqual(result['status'], 'unavailable')
            self.assertEqual(result['reason'], 'desktop-session-unavailable')
        self.which_mock.return_value = None
        self.assertEqual(desktop.choose_folder()['reason'], 'native-picker-unavailable')
        with patch.object(desktop.sys, 'platform', 'win32'):
            self.assertEqual(desktop.choose_folder()['reason'], 'unsupported-platform')
        self.run_mock.assert_not_called()

    def test_concurrent_picker_request_does_not_open_another_dialog(self):
        desktop._PICKER_LOCK.acquire()
        try:
            result = desktop.choose_folder()
            self.assertEqual(result['reason'], 'picker-busy')
            self.assertIsNone(result['path'])
            self.run_mock.assert_not_called()
        finally:
            desktop._PICKER_LOCK.release()

    def test_invalid_timeout_is_rejected_before_any_process(self):
        for value in (True, 0, 601, '120', float('nan')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                desktop.choose_folder(timeout=value)
        self.run_mock.assert_not_called()


if __name__ == '__main__':
    unittest.main()
