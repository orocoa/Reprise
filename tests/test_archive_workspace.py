"""Named snapshots and explicitly registered Git views keep distinct readers."""
import hashlib
import json
import unittest

from reprise.archives import ArchiveRepository
from reprise.git import Repository
from reprise.service import Reprise
from reprise.workspace import project_snapshot, file_comparison
from test_content_workflow import archive_fixture
from test_runtime import fixture


class ArchiveWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('archive-workspace')
        self.data = self.root / 'state'
        self.source, self.group, self.archive_sha, self.view_sha = archive_fixture(self.root, self.data)
        self.view = Repository(self.group['view_repository'])
        self.source_sha = Repository(self.group['archive_repository']).resolve('HEAD')
        self.view._run('update-ref', 'refs/heads/preserved-source', self.source_sha)
        self.before = self.fingerprint()
        self.app = Reprise(self.data)

    def fingerprint(self):
        return (self.view._run('show-ref'), self.view.resolve('HEAD'),
                hashlib.sha256((self.data / 'named-archives/registry.json').read_bytes()).hexdigest())

    def tearDown(self):
        self.app.close()
        self.assertEqual(self.before, self.fingerprint())

    def test_snapshot_only_view_ignores_unregistered_git_ref_without_expanding_manifests(self):
        project = self.app.projects.records()[0]
        repository = self.app.projects.repository(project['id'])
        self.assertFalse(repository.git_history)
        with self.assertRaisesRegex(ValueError, '版本不在已登记归档中'):
            repository.resolve(self.source_sha)
        snapshot = project_snapshot(self.app, project['id'])
        self.assertEqual([c['sha'] for c in snapshot['commits']], [self.view_sha])
        self.assertEqual(snapshot['commits'][0]['parents'], self.view._parents(self.view_sha))
        self.assertEqual(self.app.version(project['id'], self.view_sha)['diff']['files'][0]['path'], '.git/config')

    def test_registered_git_view_reads_source_history_and_pinned_snapshot_content(self):
        archive = self.app.projects.add(self.group['view_repository'])
        self.assertTrue(archive['archive_git_history'])
        live = self.app.projects.add(self.group['archive_repository'])
        self.app.projects.save_histories(live['id'], [archive['id']])
        snapshot = project_snapshot(self.app, live['id'])
        self.assertEqual({c['sha'] for c in snapshot['commits']}, {self.source_sha, self.archive_sha, self.view_sha})
        source = next(c for c in snapshot['commits'] if c['sha'] == self.source_sha)
        saved = next(c for c in snapshot['commits'] if c['sha'] == self.view_sha)
        self.assertEqual(source['history_kind'] if 'history_kind' in source else 'git', 'git')
        self.assertEqual(saved['history_kind'], 'archived_snapshots')
        self.assertEqual(saved['parents'], self.view._parents(self.view_sha))
        self.assertEqual(saved['source_project_id'], archive['id'])
        repository = self.app.projects.repository(archive['id'])
        self.assertEqual(repository.blob(self.view_sha, 'notes.txt'), b'original archived content')
        self.assertEqual(repository.blob(self.source_sha, 'index.html'), self.view.blob(self.source_sha, 'index.html'))
        self.assertIn('index.html', [f['path'] for f in repository.tree(self.source_sha)])
        detail = self.app.version(archive['id'], self.source_sha)
        self.assertEqual(detail['commit']['sha'], self.source_sha)
        self.assertEqual(detail['commit']['parents'], self.view._parents(self.source_sha))
        self.assertEqual(detail['diff'], self.view.diff(self.source_sha))
        restored = self.root / 'restored-source'
        repository.materialize(self.source_sha, restored)
        self.assertEqual((restored / 'index.html').read_bytes(), self.view.blob(self.source_sha, 'index.html'))
        # Persisting notes must not turn the explicit Git registration back into
        # a snapshot-only view on the next read.
        notes = {lang: {'title': 'Source', 'summary': 'Read source', 'changes': ['Preserved']}
                 for lang in ('zh', 'en')}
        self.app.projects.save_notes(archive['id'], notes, self.source_sha)
        self.assertTrue(self.app.projects.repository(archive['id']).git_history)

    def test_mixed_comparison_uses_the_manifest_for_the_snapshot_side(self):
        archive = self.app.projects.add(self.group['view_repository'])
        result = file_comparison(self.app, archive['id'], self.view_sha, 'notes.txt', self.source_sha)
        self.assertEqual(result['after']['text'], 'original archived content')
        self.assertTrue(result['before']['absent'])
