"""Source windows reopen without the withdrawn desktop runtime or stale URLs."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

from reprise.window import open_window
from reprise.window_entry import main
from reprise.cli import main as cli
from test_runtime import fixture


class WindowTests(unittest.TestCase):
    def test_cli_window_opens_verified_service_without_browser_or_import(self):
        result = {'url': 'http://127.0.0.1:54321/?lang=zh#versions'}
        with patch('reprise.cli.sys.platform', 'darwin'), \
                patch('reprise.launcher.open_workbench', return_value=result) as opened, \
                patch('reprise.window.open_window', return_value={'status': 'ready'}) as shown, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            status = cli(['--data', '/unused/library', 'open', '--workbench', '--window', '--lang', 'zh'])
        self.assertEqual(status, 0)
        opened.assert_called_once_with('/unused/library', 0, False, 'zh')
        shown.assert_called_once_with('/unused/library', result['url'])
        self.assertEqual(json.loads(output.getvalue())['window']['status'], 'ready')

    def test_cli_rejects_native_window_on_other_platform_before_service_start(self):
        with patch('reprise.cli.sys.platform', 'linux'), \
                patch('reprise.launcher.open_workbench') as opened, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli(['--data', '/unused/library', 'open', '--window']), 1)
        opened.assert_not_called()

    def test_exact_ready_url_and_reopen_configuration(self):
        root = fixture('source-window')
        binary = root / 'Reprise.app/Contents/MacOS/Reprise'
        binary.parent.mkdir(parents=True)
        url = 'http://127.0.0.1:54321/?project=folder&lang=zh#versions'

        def start(arguments, **options):
            self.assertEqual(arguments[:3], [str(binary), '--url', url])
            receipt = Path(arguments[arguments.index('--ready-file') + 1])
            receipt.write_text(json.dumps({'status': 'ready', 'url': url}))
            return Mock(pid=12345)

        with patch('reprise.window.sys.platform', 'darwin'), \
                patch('reprise.window.window_binary', return_value=binary), \
                patch('reprise.window.subprocess.Popen', side_effect=start):
            result = open_window(root, url)
        self.assertEqual(result['status'], 'ready')
        config = json.loads((binary.parent.parent / 'Resources/source-launch.json').read_text())
        self.assertEqual(config['data'], str(root))
        self.assertEqual(config['language'], 'zh')
        self.assertEqual(config['project'], 'folder')
        self.assertTrue(Path(config['entry']).is_file())
        self.assertEqual(config['python'], str(Path(sys.executable).resolve()))
        self.assertNotIn('url', config)

    def test_unsafe_url_is_rejected_without_process_or_writes(self):
        root = fixture('source-window-invalid') / 'absent'
        for url in ('https://example.com/', 'http://localhost:51582/', 'http://127.0.0.1/',
                    'http://user@127.0.0.1:51582/', 'file:///tmp/page.html'):
            with self.subTest(url=url), patch('reprise.window.window_binary') as build, self.assertRaises(ValueError):
                open_window(root, url)
            build.assert_not_called()
        self.assertFalse(root.exists())

    def test_early_exit_keeps_log_and_reports_failure(self):
        root = fixture('source-window-exit')
        binary = root / 'Reprise.app/Contents/MacOS/Reprise'
        binary.parent.mkdir(parents=True)
        with patch('reprise.window.sys.platform', 'darwin'), \
                patch('reprise.window.window_binary', return_value=binary), \
                patch('reprise.window.subprocess.Popen', return_value=Mock(poll=Mock(return_value=1))), \
                self.assertRaisesRegex(ValueError, 'window exited'):
            open_window(root, 'http://127.0.0.1:54321/')
        self.assertEqual(len(list(root.glob('windows/sessions/session-*.log'))), 1)

    def test_bridge_opens_workbench_without_import_or_browser(self):
        with patch('reprise.window_entry.open_workbench', return_value={'url': 'local'}) as opened, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['open', '--data', '/unused/library', '--lang', 'zh']), 0)
        opened.assert_called_once_with('/unused/library', browser=False, language='zh')
        self.assertEqual(json.loads(output.getvalue())['url'], 'local')

    def test_bridge_reopens_exact_registered_project(self):
        with patch('reprise.window_entry.open_repository', return_value={'project_id': 'known'}) as opened, \
                patch('reprise.window_entry.open_workbench') as chooser, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['open', '--data', '/unused/library', '--project', 'known', '--lang', 'zh']), 0)
        opened.assert_called_once_with('/unused/library', 'known', browser=False, language='zh')
        chooser.assert_not_called()

    def test_bridge_shutdown_requires_and_preserves_instance_identity(self):
        with patch('reprise.window_entry.shutdown') as stopped, \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(['shutdown', '--data', '/unused/library'])
        stopped.assert_not_called()
        with patch('reprise.window_entry.shutdown', return_value={'stopped': True}) as stopped, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['shutdown', '--data', '/unused/library', '--instance-id', 'exact']), 0)
        stopped.assert_called_once_with('/unused/library', instance_id='exact')

    def test_native_cache_preserves_each_release_identity(self):
        import plistlib
        from reprise.window import window_binary
        root = fixture('native-release-identity')

        def compile_window(arguments, **options):
            Path(arguments[arguments.index('-o') + 1]).write_bytes(b'synthetic-window-binary')
            return Mock(returncode=0, stdout='', stderr='')

        with patch('reprise.window.shutil.which', return_value='/fixture/swiftc'), \
                patch('reprise.window.subprocess.run', side_effect=compile_window) as compile:
            with patch('reprise.window.__version__', '0.8.5'):
                first = window_binary(root)
                self.assertEqual(window_binary(root), first)
            with patch('reprise.window.__version__', '0.8.6'):
                second = window_binary(root)
        self.assertNotEqual(first, second)
        self.assertEqual(compile.call_count, 2)
        for path, version in ((first, '0.8.5'), (second, '0.8.6')):
            with (path.parent.parent / 'Info.plist').open('rb') as stream:
                self.assertEqual(plistlib.load(stream)['CFBundleShortVersionString'], version)
            self.assertTrue(path.is_file())
