"""Lifecycle choices touch only independently saved synthetic revisions."""
from pathlib import Path
import unittest
from unittest.mock import patch

from reprise.service import Reprise
from reprise.version_cleanup import plan, execute, options
from reprise.workspace import project_snapshot
from reprise.storage import write_json
from test_runtime import fixture, commit_repo


class VersionCleanupTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('version-cleanup')
        self.app = Reprise(self.root / 'data')
        self.addCleanup(self.app.close)
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'draft.txt').write_text('first')
        self.project = self.app.projects.add(str(self.source), kind='folder')
        self.first = self.app.projects.snapshot(self.project['id'], 'First')['sha']
        (self.source / 'draft.txt').write_text('second')
        self.second = self.app.projects.snapshot(self.project['id'], 'Second')['sha']

    def test_full_removal_clears_owned_picture_keeps_other_revision_and_original(self):
        image = self.root / 'picture.png'
        image.write_bytes(b'\x89PNG\r\n\x1a\nsynthetic')
        evidence = self.app.evidence.manual(self.app.projects.repository(self.project['id']),
            self.project['id'], {'sha': self.first, 'path': str(image), 'kind': 'image'})
        folder = self.app.evidence.directory / evidence['id']
        review = plan(self.app, self.project['id'], self.first, 'all')
        self.assertEqual(review['blockers'], [])
        with self.assertRaises(ValueError):
            execute(self.app, self.project['id'], review['id'], False)
        result = execute(self.app, self.project['id'], review['id'], True)
        self.assertEqual(result['status'], 'complete')
        self.assertFalse(folder.exists())
        repository = self.app.projects.repository(self.project['id'])
        self.assertEqual(repository.resolve('HEAD'), self.second)
        with self.assertRaises(ValueError):
            repository.resolve(self.first)
        self.assertEqual((self.source / 'draft.txt').read_text(), 'second')
        self.assertEqual((self.root / 'picture.png').read_bytes(), image.read_bytes())

    def test_environment_choice_with_no_environment_keeps_content_and_picture(self):
        review = plan(self.app, self.project['id'], self.first, 'environment')
        self.assertEqual(review['environment_ids'], [])
        result = execute(self.app, self.project['id'], review['id'], True)
        self.assertTrue(result['version_retained'])
        self.assertEqual(self.app.projects.repository(self.project['id']).resolve(self.first), self.first)

    def test_running_previews_are_reported_for_explicit_stop_and_review(self):
        rows = [{'id': 'a' * 32, 'project_id': self.project['id'], 'sha': self.first, 'running': True},
                {'id': 'b' * 32, 'project_id': self.project['id'], 'sha': self.first, 'status': 'cleanup_failed'},
                {'id': 'c' * 32, 'project_id': self.project['id'], 'sha': self.second, 'running': True}]
        with patch.object(self.app.runtimes, 'list', return_value=rows):
            review = plan(self.app, self.project['id'], self.first, 'all')
        self.assertEqual(review['active_runtime_ids'], ['a' * 32, 'b' * 32])
        self.assertIn('请先停止此版本的运行预览。', review['blockers'])

    def test_changed_picture_invalidates_plan_before_version_removal(self):
        image = self.root / 'picture.png'
        image.write_bytes(b'\x89PNG\r\n\x1a\noriginal')
        evidence = self.app.evidence.manual(self.app.projects.repository(self.project['id']),
            self.project['id'], {'sha': self.first, 'path': str(image), 'kind': 'image'})
        review = plan(self.app, self.project['id'], self.first, 'all')
        Path(evidence['items'][0]['path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, '变化'):
            execute(self.app, self.project['id'], review['id'], True)
        self.assertEqual(self.app.projects.repository(self.project['id']).resolve(self.first), self.first)

    def test_git_removal_clears_local_picture_and_list_but_preserves_source_history(self):
        repo = commit_repo(self.root / 'external-git')
        project = self.app.projects.add(str(repo.work_tree))
        sha = repo.resolve('HEAD')
        before = {str(p.relative_to(repo.work_tree)): p.read_bytes()
                  for p in repo.work_tree.rglob('*') if p.is_file()}
        image = self.root / 'git-picture.png'
        image.write_bytes(b'\x89PNG\r\n\x1a\nsynthetic')
        evidence = self.app.evidence.manual(repo, project['id'],
            {'sha': sha, 'path': str(image), 'kind': 'image'})
        self.assertFalse(options(self.app, project['id'], sha)['has_environment'])
        review = plan(self.app, project['id'], sha, 'all')
        self.assertEqual(review['blockers'], [])
        self.assertTrue(review['source_history_retained'])
        with self.assertRaises(ValueError):
            execute(self.app, project['id'], review['id'], False)
        result = execute(self.app, project['id'], review['id'], True)
        self.assertTrue(result['removed_from_reprise'])
        self.assertTrue(result['source_history_retained'])
        self.assertFalse((self.app.evidence.directory / evidence['id']).exists())
        self.assertEqual(project_snapshot(self.app, project['id'])['commits'], [])
        self.assertEqual(execute(self.app, project['id'], review['id'], True), result)
        self.assertEqual(repo.resolve('HEAD'), sha)
        self.assertEqual(before, {str(p.relative_to(repo.work_tree)): p.read_bytes()
                                  for p in repo.work_tree.rglob('*') if p.is_file()})
        self.assertTrue(image.exists())
        restarted = Reprise(self.app.directory)
        try:
            self.assertEqual(project_snapshot(restarted, project['id'])['commits'], [])
        finally:
            restarted.close()

    def test_paired_capture_removes_selected_media_and_keeps_other_sha_image(self):
        folder = self.app.evidence.directory / ('d' * 32)
        folder.mkdir()
        (folder / 'after.png').write_bytes(b'target picture')
        (folder / 'before.png').write_bytes(b'other version picture')
        record = {'id': folder.name, 'project_id': self.project['id'], 'sha': self.first,
                  'items': [{'sha': self.first, 'path': str(folder / 'after.png')},
                            {'sha': self.second, 'path': str(folder / 'before.png')}]}
        write_json(folder / 'record.json', record)
        review = plan(self.app, self.project['id'], self.first, 'all')
        self.assertEqual(review['blockers'], [])
        execute(self.app, self.project['id'], review['id'], True)
        self.assertFalse((folder / 'after.png').exists())
        self.assertEqual((folder / 'before.png').read_bytes(), b'other version picture')
        self.assertEqual(self.app.projects.repository(self.project['id']).resolve(self.second), self.second)
