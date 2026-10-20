import json
import os
from pathlib import Path
import subprocess
import threading
import unittest
import zipfile

from reprise.service import Reprise
from reprise.server import LocalServer
from test_runtime import fixture, commit_repo
from test_git import git


@unittest.skipUnless(os.environ.get('REPRISE_BROWSER_TESTS') == '1', 'browser tests opt in')
class WorkspaceFlowTests(unittest.TestCase):
    def test_agent_project_context_historical_preview_restore_and_download(self):
        root = fixture('portable-workspace-ui')
        repo = commit_repo(root / 'project 中文 with spaces')
        base = repo.resolve('HEAD')
        (repo.path / 'index.html').write_text('<h1>Second revision</h1>')
        git(repo.path, 'add', '.');git(repo.path, 'commit', '-m', 'Second revision')
        payload = {'root': str(root), 'source': str(repo.path), 'base': base}
        config = root / 'fixture.json';config.write_text(json.dumps(payload))
        app = Reprise(root / 'state')
        project = app.projects.add(str(repo.path))
        server = LocalServer(('127.0.0.1', 0), app)
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        try:
            result = subprocess.run([os.environ['REPRISE_NODE'], str(Path(__file__).with_name('workspace_flow_acceptance.mjs')),
                                    'http://127.0.0.1:%s/?project=%s' % (server.server_port, project['id']), str(config)], capture_output=True, text=True, timeout=150)
            (root / 'browser.log').write_text(result.stdout + '\n' + result.stderr)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with zipfile.ZipFile(root / 'browser-version.zip') as archive:
                self.assertEqual(archive.read('index.html'), repo.blob(base, 'index.html'))
            self.assertEqual(repo.blob('HEAD', 'index.html'), b'<h1>Second revision</h1>')
            self.assertFalse(git(repo.path, 'status', '--porcelain=v1'))
        finally:
            for runtime in app.runtimes.list():
                if runtime['running']:app.runtimes.stop(runtime['id'])
            server.shutdown();server.server_close();thread.join(2);app.close()
