"""Workspace integration preserves source identity, archive lineage and exact bases."""
import hashlib
import json
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
from urllib.request import urlopen

from reprise.server import LocalServer
from reprise.service import Reprise
from reprise.workspace import project_snapshot, file_comparison, context
from test_runtime import fixture, commit_repo
from test_git import git


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('workspace')
        self.repo = commit_repo(self.root / 'source')
        self.first = self.repo.resolve('HEAD')
        (self.repo.work_tree / 'index.html').write_text('<h1>Second</h1>')
        git(self.repo.work_tree, 'commit', '-am', 'second')
        self.second = self.repo.resolve('HEAD')
        (self.repo.work_tree / 'not-committed.txt').write_text('keep original')
        self.before = self.fingerprint()
        self.app = Reprise(self.root / 'state')
        self.project = self.app.projects.add(str(self.repo.work_tree))

    def fingerprint(self):
        return (git(self.repo.work_tree, 'rev-parse', 'HEAD'),
                git(self.repo.work_tree, 'show-ref'),
                git(self.repo.work_tree, 'status', '--porcelain'),
                hashlib.sha256((self.repo.work_tree / '.git/index').read_bytes()).hexdigest())

    def tearDown(self):
        self.app.close()
        self.assertEqual(self.before, self.fingerprint())

    def test_related_archives_deduplicate_and_keep_exact_source(self):
        archive = self.root / 'archive.git'
        git(self.root, 'clone', '--bare', str(self.repo.work_tree), str(archive))
        # An archive-only commit extends the same actual chain.
        tree = git(archive, 'rev-parse', self.second + '^{tree}')
        git(archive, 'config', 'user.name', 'Test')
        git(archive, 'config', 'user.email', 'test@example.invalid')
        extra = git(archive, 'commit-tree', tree, '-p', self.second, '-m', 'archive-only')
        git(archive, 'update-ref', 'refs/heads/main', extra)
        saved = self.app.projects.add(str(archive))
        self.app.projects.save_histories(self.project['id'], [saved['id']], [self.first, self.second, extra])
        result = project_snapshot(self.app, self.project['id'])
        self.assertEqual(len(result['commits']), 3)
        restored = next(c for c in result['commits'] if c['sha'] == extra)
        self.assertEqual(restored['source_project_id'], saved['id'])
        self.assertEqual(restored['parents'], [self.second])
        self.assertEqual(result['history_sources'][1]['unique_commits'], 1)
        restarted = Reprise(self.root / 'state')
        try:
            self.assertEqual(context(restarted, self.project['id'])['history_project_ids'], [saved['id']])
        finally:
            restarted.close()

    def test_unrelated_archive_is_rejected_without_saving_association(self):
        unrelated = commit_repo(self.root / 'unrelated')
        (unrelated.work_tree / 'different.txt').write_text('different identity')
        git(unrelated.work_tree, 'add', '.')
        git(unrelated.work_tree, 'commit', '--amend', '-m', 'unrelated')
        imported = self.app.projects.add(str(unrelated.work_tree))
        with self.assertRaisesRegex(ValueError, '共同提交'):
            self.app.projects.save_histories(self.project['id'], [imported['id']])
        self.assertNotIn('history_project_ids', self.app.projects.record(self.project['id']))

    def test_snapshot_paginates_exact_tips_and_preserves_notes(self):
        notes = {lang: {'title': 'custom', 'summary': 'saved', 'changes': ['change']} for lang in ('zh', 'en')}
        self.app.projects.save_notes(self.project['id'], notes, self.first)
        repository = self.app.projects.repository(self.project['id'])
        commits = repository.history()['commits']
        calls = []

        def pages(ref, limit, offset):
            calls.append((ref, offset))
            return {'commits': commits[offset:offset + 1], 'has_more': offset == 0, 'next_offset': offset + 1}

        with patch.object(self.app.projects, 'repository', return_value=repository), patch.object(repository, 'history', side_effect=pages):
            result = project_snapshot(self.app, self.project['id'])
        self.assertEqual(len(result['commits']), 2)
        self.assertEqual(next(c for c in result['commits'] if c['sha'] == self.first)['notes']['localizations'], notes)
        self.assertTrue(all(ref == self.second for ref, _ in calls))
        self.assertIn((self.second, 1), calls)

    def test_file_comparison_uses_requested_base_and_rejects_unlisted_paths(self):
        result = file_comparison(self.app, self.project['id'], self.second, 'index.html', self.first)
        self.assertEqual(result['base'], self.first)
        self.assertIn('Second', result['after']['text'])
        self.assertNotIn('Second', result['before']['text'])
        with self.assertRaisesRegex(ValueError, '变化清单'):
            file_comparison(self.app, self.project['id'], self.second, 'not-committed.txt', self.first)

    def test_http_context_and_bundled_fonts(self):
        server = LocalServer(('127.0.0.1', 0), self.app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = 'http://127.0.0.1:%s' % server.server_port
        try:
            for route in ('/', '/live.js', '/graph-layout.js', '/live.css', '/fonts/DepartureMono-1.500.woff2', '/fonts/ZhengGeDianHei-16.ttf', '/icons/feather-LICENSE'):
                with urlopen(url + route) as response:
                    self.assertEqual(response.status, 200)
                    self.assertTrue(response.read())
            with urlopen(url + '/api/workspace/context?' + urlencode({'project': self.project['id']})) as response:
                self.assertEqual(json.load(response)['project_id'], self.project['id'])
            with urlopen(url + '/api/workspace/snapshot?' + urlencode({'project': self.project['id']})) as response:
                self.assertEqual(len(json.load(response)['commits']), 2)
        finally:
            server.shutdown(); server.server_close(); thread.join(2)
