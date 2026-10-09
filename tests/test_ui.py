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
    def test_graph_geometry_with_parallel_branches(self):
        root=fixture('graph-ui')
        repo=commit_repo(root/'source')
        git(repo.work_tree,'branch','-M','main')
        base=repo.resolve('HEAD')
        tree=git(repo.work_tree,'rev-parse',base+'^{tree}')
        branches=[]
        for i in range(7):
            sha=git(repo.work_tree,'commit-tree',tree,'-p',base,'-m','Parallel branch %s'%i)
            branches.append(sha)
            git(repo.work_tree,'update-ref','refs/heads/topic%s'%i,sha)
        args=['commit-tree',tree,'-m','Multi-parent merge']
        for sha in branches:args.extend(['-p',sha])
        tip=git(repo.work_tree,*args)
        git(repo.work_tree,'update-ref','refs/heads/main',tip)
        app=Reprise(root/'state')
        project=app.projects.add(str(repo.work_tree))
        note={'title':'A title wrapping within the narrow remaining text column',
              'summary':'Variable row heights are measured from the actual rendered content. '*5,'changes':['Graph fixture']}
        for sha in [base,*branches,tip]:
            app.projects.save_notes(project['id'],{lang:note for lang in ('zh','en')},sha)
        server=LocalServer(('127.0.0.1',0),app)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            result=subprocess.run([os.environ['REPRISE_NODE'],str(Path(__file__).with_name('graph_acceptance.mjs')),
                                   'http://127.0.0.1:%s/'%server.server_port,project['id'],'9',str(root)],
                                  capture_output=True,text=True,timeout=60)
            (root/'browser.log').write_text(result.stdout+'\n'+result.stderr)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        finally:
            server.shutdown();server.server_close();thread.join(2);app.close()

    def test_locale_review_persistence_and_runtime_controls(self):
        root=fixture('ui-acceptance')
        repo=commit_repo(root/'source')
        (repo.work_tree/'index.html').write_text('<h1>Second</h1>')
        git(repo.work_tree,'add','.');git(repo.work_tree,'commit','-m','原始提交二')
        sha=repo.resolve('HEAD')
        app=Reprise(root/'state');adapter=Stub();app.ai.adapter=adapter
        app.ai.save({'enabled':True,'endpoint':'https://fixture.invalid/v1','model':'exact-test-model','api_key':'test-key'})
        project=app.projects.add(str(repo.work_tree))
        (app.jobs.directory / 'broken-record.json').write_text('{broken JSON')
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
