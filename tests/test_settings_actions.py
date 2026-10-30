import json
import os
import subprocess
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from reprise import desktop
from reprise.server import LocalServer
from reprise.service import Reprise
from test_runtime import fixture, commit_repo


class SettingsActionTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('settings-actions')
        self.app = Reprise(self.root / 'data')
        self.server = LocalServer(('127.0.0.1', 0), self.app)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:%s' % self.server.server_port
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.app.close()

    def call(self, path, body, *, token=True, method='POST'):
        request = urllib.request.Request(self.url + path, json.dumps(body).encode(), method=method,
            headers={'Content-Type': 'application/json', **({'X-Reprise-Token': self.server.token} if token else {})})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def test_author_display_persists_without_changing_git_identity(self):
        repository = commit_repo(self.root / 'original')
        project = self.app.projects.add(str(repository.work_tree))
        sha = repository.resolve('HEAD')
        original = repository.history(sha, limit=1)['commits'][0]['author']
        notes = {language: {'title': 'Title', 'summary': 'Summary', 'changes': ['Saved']} for language in ('zh', 'en')}
        endpoint = '/api/projects/%s/notes' % project['id']
        saved = self.call(endpoint, {'sha': sha, 'author': '显示作者', 'localizations': notes}, method='PUT')
        self.assertEqual(saved['author'], '显示作者')
        again = self.call(endpoint, {'sha': sha, 'localizations': notes}, method='PUT')
        self.assertEqual(again['author'], '显示作者')
        self.assertEqual(repository.history(sha, limit=1)['commits'][0]['author'], original)
        self.assertEqual(repository.resolve('HEAD'), sha)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.call(endpoint, {'sha': sha, 'author': 'bad\nauthor', 'localizations': notes}, method='PUT')
        self.assertEqual(error.exception.code, 400)

    def test_backup_picker_cancel_and_token_boundary(self):
        with patch.object(desktop, 'choose_backup', return_value={'status': 'cancelled', 'path': None}) as choose:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.call('/api/desktop/save-backup', {}, token=False)
            self.assertEqual(error.exception.code, 403)
            choose.assert_not_called()
            self.assertEqual(self.call('/api/desktop/save-backup', {})['status'], 'cancelled')
            choose.assert_called_once_with(save=True)

    def test_fixed_native_backup_script_and_single_file_validation(self):
        path = self.root / 'chosen.zip'
        path.write_bytes(b'backup')
        with patch.object(desktop, '_backend', return_value=('osascript', '/usr/bin/osascript', None)), \
             patch.object(desktop.subprocess, 'run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, os.fsencode(path) + b'\n', b'')
            self.assertEqual(desktop.choose_backup()['path'], str(path))
            self.assertIn('choose file with prompt', run.call_args.args[0][2])
            self.assertNotIn(str(path), run.call_args.args[0][2])
            self.assertEqual(desktop.choose_backup(save=True)['path'], str(path))
            self.assertIn('choose file name', run.call_args.args[0][2])
