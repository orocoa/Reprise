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

    def test_removed_git_parent_stays_a_boundary_and_is_not_reimported_from_archive(self):
        from reprise.version_cleanup import plan, execute
        archive = self.root / 'removed-parent-archive.git'
        git(self.root, 'clone', '--bare', str(self.repo.work_tree), str(archive))
        saved = self.app.projects.add(str(archive))
        self.app.projects.save_histories(self.project['id'], [saved['id']])
        old = project_snapshot(self.app, self.project['id'])['snapshot']
        review = plan(self.app, self.project['id'], self.first, 'all')
        execute(self.app, self.project['id'], review['id'], True)
        result = project_snapshot(self.app, self.project['id'])
        self.assertEqual([c['sha'] for c in result['commits']], [self.second])
        self.assertEqual(result['commits'][0]['parents'], [self.first])
        self.assertNotEqual(old, result['snapshot'])
        self.assertEqual(self.repo.resolve(self.first), self.first)

    def test_snapshot_reads_each_tip_once_and_tracks_metadata_changes(self):
        original = project_snapshot(self.app, self.project['id'])['snapshot']
        notes = {lang: {'title': 'custom', 'summary': 'saved', 'changes': ['change']} for lang in ('zh', 'en')}
        self.app.projects.save_notes(self.project['id'], notes, self.first)
        repository = self.app.projects.repository(self.project['id'])
        calls = []
        run = repository._run
        def counted(*args, **kwargs):
            calls.append(args)
            return run(*args, **kwargs)
        with patch.object(self.app.projects, 'repository', return_value=repository), patch.object(repository, '_run', side_effect=counted):
            result = project_snapshot(self.app, self.project['id'])
        self.assertEqual(len(result['commits']), 2)
        self.assertEqual(next(c for c in result['commits'] if c['sha'] == self.first)['notes']['localizations'], notes)
        self.assertEqual([args[1] for args in calls if args[0] == 'log'], [self.second])
        self.assertNotEqual(original, result['snapshot'], 'Saved notes are part of the displayed snapshot')
        git(self.repo.work_tree, 'update-ref', 'refs/heads/another-name', self.second)
        self.before = self.fingerprint()
        renamed = project_snapshot(self.app, self.project['id'])
        self.assertNotEqual(result['snapshot'], renamed['snapshot'], 'Ref changes matter even when tips are unchanged')

    def test_renamed_file_comparison_reports_original_path_for_baseline_recovery(self):
        # The renamed target path must not be reused for the old revision.
        with patch.object(self.app.projects, 'repository', return_value=self.repo), patch.object(self.repo, 'diff', return_value={
                'base': self.first, 'target': self.second,
                'files': [{'path': 'renamed.html', 'old_path': 'index.html', 'status': 'R100'}]}):
            result = file_comparison(self.app, self.project['id'], self.second, 'renamed.html', self.first)
        self.assertEqual(result['base_path'], 'index.html')
        self.assertIn('first', result['before']['text'])
        self.assertEqual(result['path'], 'renamed.html')

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
