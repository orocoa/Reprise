"""The same graph contract for synthetic DAGs and real, read-only Git snapshots."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from reprise.service import Reprise
from reprise.workspace import project_snapshot
from test_git import git
from test_runtime import fixture


NODE = os.environ.get('REPRISE_NODE') or shutil.which('node')
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(NODE, 'graph tests need Node 18+; set REPRISE_NODE')
class GraphTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('git-graph')
        self.source = self.root / 'source'
        self.source.mkdir()
        git(self.source, 'init', '-b', 'trunk')
        git(self.source, 'config', 'user.name', 'Graph test')
        git(self.source, 'config', 'user.email', 'graph@example.invalid')
        (self.source / 'uncommitted.txt').write_text('keep me')
        self.tree = subprocess.check_output(
            ['git', '-C', str(self.source), 'hash-object', '-w', '-t', 'tree', '--stdin'], input=b'').decode().strip()
        self.app = Reprise(self.root / 'state')

    def tearDown(self):
        self.app.close()

    def make_commit(self, message, parents=(), date='2020-01-01T00:00:00+00:00'):
        env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date,
                   GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        args = ['git', '-C', str(self.source), 'commit-tree', self.tree, '-m', message]
        for parent in parents:
            args.extend(['-p', parent])
        return subprocess.check_output(args, env=env, stderr=subprocess.PIPE).decode().strip()

    def fingerprint(self, path):
        # Read every byte of Git metadata and working files; imports must be inert.
        return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in path.rglob('*') if p.is_file()}

    def graph_snapshot(self, path=None):
        path = path or self.source
        before = self.fingerprint(path)
        project = self.app.projects.add(str(path))
        snapshot = project_snapshot(self.app, project['id'])
        self.assertEqual(before, self.fingerprint(path))
        options = {'mainTip': snapshot['project']['head'], 'refs': [
            {'name': r['name'], 'tip': r['sha'], 'kind': r['kind']}
            for r in snapshot['refs'] if r['target_type'] == 'commit']}
        payload = {'commits': [dict(id=c['sha'], parents=c['parents'], order=len(snapshot['commits']) - i)
                               for i, c in enumerate(snapshot['commits'])], 'options': options}
        result = subprocess.run([NODE, str(ROOT / 'tests' / 'graph-contract.cjs')],
                                input=json.dumps(payload), capture_output=True, text=True, timeout=30)
        (self.root / ('graph-%s.log' % project['id'])).write_text(result.stderr)
        (self.root / ('snapshot-%s.json' % project['id'])).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
        self.assertEqual(result.returncode, 0, result.stderr)
        graph = json.loads(result.stdout)
        (self.root / ('layout-%s.json' % project['id'])).write_text(json.dumps(graph, indent=2))
        return snapshot, graph

    def test_synthetic_layout_contracts(self):
        result = subprocess.run([NODE, '--test', str(ROOT / 'tests' / 'graph-layout.test.cjs')],
                                capture_output=True, text=True, timeout=30)
        (self.root / 'layout-tests.log').write_text(result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_real_octopus_merge_skewed_dates_refs_and_independent_root(self):
        root = self.make_commit('same title', date='2030-01-01T00:00:00+00:00')
        main = self.make_commit('main', [root])
        feature = self.make_commit('feature', [root])
        later = self.make_commit('not merged', [feature])
        other = self.make_commit('other', [root])
        merge = self.make_commit('ordinary title', [main, feature, other])
        orphan = self.make_commit('same title')
        git(self.source, 'update-ref', 'refs/heads/trunk', merge)
        git(self.source, 'update-ref', 'refs/heads/实验', later)
        git(self.source, 'update-ref', 'refs/remotes/upstream/topic', other)
        git(self.source, 'update-ref', 'refs/heads/unrelated', orphan)
        git(self.source, 'tag', '-a', 'release', '-m', 'annotated', merge)
        _, graph = self.graph_snapshot()
        rows = {n['id']: n for n in graph['rows']}
        self.assertEqual(graph['mainPath'], [merge, main, root])
        self.assertEqual(rows[merge]['parents'], [main, feature, other])
        self.assertTrue(rows[merge]['isMerge'])
        self.assertEqual(len(rows[merge]['refs']), 2)
        self.assertEqual(rows[orphan]['parents'], [])
        self.assertFalse(any(e['childId'] == merge and e['parentId'] == later for e in graph['edges']))
        self.assertLess(rows[main]['row'], rows[root]['row'], 'Topology overrides a future-dated ancestor')

    def test_same_tree_messages_and_rewritten_commits_do_not_invent_merges(self):
        root = self.make_commit('root')
        original = self.make_commit('feature change', [root])
        base = self.make_commit('new base', [root])
        rewritten = self.make_commit('feature change', [base])
        squash = self.make_commit('Merge feature', [rewritten])
        git(self.source, 'update-ref', 'refs/heads/trunk', squash)
        git(self.source, 'update-ref', 'refs/heads/old-feature', original)
        _, graph = self.graph_snapshot()
        self.assertEqual(graph['mainPath'], [squash, rewritten, base, root])
        self.assertFalse(any(n['isMerge'] for n in graph['rows']))
        self.assertFalse(any(e['childId'] == squash and e['parentId'] == original for e in graph['edges']))
        self.assertEqual(len(graph['rows']), 5, 'Equal trees/messages are distinct full-SHA commits')

    def test_empty_bare_detached_and_linked_worktree_snapshots(self):
        _, empty = self.graph_snapshot()
        self.assertEqual(empty['rows'], [])
        self.assertEqual(empty['laneCount'], 0)
        root = self.make_commit('root')
        tip = self.make_commit('tip', [root])
        git(self.source, 'update-ref', 'refs/heads/trunk', tip)
        bare = self.root / 'bare.git'
        git(self.root, 'clone', '--bare', str(self.source), str(bare))
        _, graph = self.graph_snapshot(bare)
        self.assertEqual(graph['mainPath'], [tip, root])
        git(self.source, 'checkout', '--detach', root)
        snapshot, graph = self.graph_snapshot()
        self.assertIsNone(snapshot['project']['repository']['branch'])
        self.assertEqual(graph['mainPath'], [root])
        self.assertEqual(len(graph['rows']), 2, 'Detached HEAD does not discard branch refs')
        linked = self.root / 'linked'
        git(self.source, 'worktree', 'add', '--detach', str(linked), tip)
        _, graph = self.graph_snapshot(linked)
        self.assertEqual(graph['mainPath'], [tip, root])

    def test_shallow_clone_keeps_raw_parent_as_boundary(self):
        root = self.make_commit('root')
        tip = self.make_commit('tip', [root])
        git(self.source, 'update-ref', 'refs/heads/trunk', tip)
        shallow = self.root / 'shallow'
        git(self.root, 'clone', '--depth=1', self.source.as_uri(), str(shallow))
        snapshot, graph = self.graph_snapshot(shallow)
        self.assertTrue(snapshot['project']['repository']['shallow'])
        self.assertEqual(graph['rows'][0]['parents'], [root])
        self.assertEqual(graph['mainBoundary'], root)
        self.assertEqual(graph['boundaries'][0]['id'], root)
        self.assertTrue(graph['edges'][0]['missingParent'])

    def test_real_sha256_repository(self):
        path = self.root / 'sha256'
        path.mkdir()
        try:
            git(path, 'init', '-b', 'trunk', '--object-format=sha256')
        except subprocess.CalledProcessError:
            self.skipTest('This Git does not support SHA-256 repositories')
        git(path, 'config', 'user.name', 'Graph test')
        git(path, 'config', 'user.email', 'graph@example.invalid')
        (path / 'README.txt').write_text('first')
        git(path, 'add', '.')
        git(path, 'commit', '-m', 'first')
        snapshot, graph = self.graph_snapshot(path)
        self.assertEqual(len(snapshot['project']['head']), 64)
        self.assertEqual(graph['rows'][0]['id'], snapshot['project']['head'])
