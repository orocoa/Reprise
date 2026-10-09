"""Opt-in real browser regression of locale, AI review and runtime controls."""
import os
import subprocess
import threading
import unittest
from pathlib import Path
from reprise.server import LocalServer
from reprise.service import Reprise
from test_runtime import fixture, commit_repo
from test_git import git
from test_ai import Stub, NOTES

@unittest.skipUnless(os.environ.get('REPRISE_BROWSER_TESTS') == '1', 'browser tests opt in')
class BrowserUITests(unittest.TestCase):
    def test_locale_review_persistence_and_runtime_controls(self):
        root=fixture('ui-acceptance')
        repo=commit_repo(root/'source')
        (repo.work_tree/'index.html').write_text('<h1>Second</h1>')
        git(repo.work_tree,'add','.');git(repo.work_tree,'commit','-m','原始提交二')
        sha=repo.resolve('HEAD')
        app=Reprise(root/'state');adapter=Stub();app.ai.adapter=adapter
        app.ai.save({'enabled':True,'endpoint':'https://fixture.invalid/v1','model':'exact-test-model','api_key':'test-key'})
        project=app.projects.add(str(repo.work_tree))
        server=LocalServer(('127.0.0.1',0),app)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            result=subprocess.run([os.environ['REPRISE_NODE'],str(Path(__file__).with_name('workspace_acceptance.mjs')),
                                   'http://127.0.0.1:%s/'%server.server_port,project['id'],sha,str(root)],
                                  capture_output=True,text=True,timeout=120)
            (root/'browser.log').write_text(result.stdout+'\n'+result.stderr)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(len(adapter.calls),1)
            self.assertEqual(app.projects.record(project['id'])['version_notes'][sha]['localizations'],NOTES)
            self.assertTrue(app.projects.get(project['id'])['recipe_approved'])
            self.assertFalse(any(r['running'] for r in app.runtime_list()))
        finally:
            server.shutdown();server.server_close();thread.join(2);app.close()
            for runtime in app.runtime_list():
                if runtime['running']:app.runtimes.stop(runtime['id'])
