"""Safe default destinations retain exact versions and never reserve paths."""
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from reprise.projects import ProjectStore
from reprise.recovery import RecoveryStore
from reprise.recovery_destination import suggest_destination
from reprise.storage import read_json, write_json
from test_git import git
from test_runtime import commit_repo, fixture


class RecoveryDestinationTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('recovery-destination')
        self.repository = commit_repo(self.root / 'source')
        self.sha = self.repository.resolve('HEAD')
        self.projects = ProjectStore(self.root / 'data')
        self.project = self.projects.add(str(self.repository.path), '网页草稿')['id']
        self.recoveries = RecoveryStore(self.root / 'data', self.projects)

    def source_bytes(self):
        return {path.relative_to(self.repository.path).as_posix(): path.read_bytes()
                for path in self.repository.path.rglob('*') if path.is_file()}

    def test_suggests_exact_old_version_without_creating_or_changing_files(self):
        (self.repository.path / 'index.html').write_text('second committed draft')
        git(self.repository.path, 'add', '.')
        git(self.repository.path, 'commit', '-m', 'Second draft')
        (self.repository.path / 'index.html').write_text('unsaved current draft')
        before = self.source_bytes()

        result = suggest_destination(self.recoveries, self.project, self.sha)

        target = Path(result['to'])
        self.assertEqual(result['project_id'], self.project)
        self.assertEqual(result['sha'], self.sha)
        self.assertEqual(result['display_label'], target.name)
        self.assertEqual(result['location'], 'source-sibling')
        self.assertEqual(target.parent, self.repository.path.parent)
        self.assertIn('网页草稿', target.name)
        self.assertFalse(self.recoveries.directory.exists())
        self.assertFalse(os.path.lexists(target))
        self.assertEqual(self.source_bytes(), before)

    def test_suggested_path_restores_exact_bytes_and_keeps_source(self):
        expected = self.repository.blob(self.sha, 'index.html')
        (self.repository.path / 'index.html').write_text('Keep this current draft')
        before = self.source_bytes()
        result = suggest_destination(self.recoveries, self.project, self.sha)

        receipt = self.recoveries.create(
            self.repository, self.project, self.sha, 'restore', result['to'])

        self.assertEqual(receipt['sha'], self.sha)
        self.assertEqual(receipt['status'], 'complete')
        self.assertEqual(receipt['path'], result['to'])
        self.assertEqual((Path(result['to']) / 'index.html').read_bytes(), expected)
        self.assertTrue(receipt['report']['object_hashes_verified'])
        self.assertEqual(self.source_bytes(), before)

    def test_restored_copy_can_be_added_edited_and_saved_as_a_new_project(self):
        before = self.source_bytes()
        result = suggest_destination(self.recoveries, self.project, self.sha)
        target = Path(result['to'])
        self.recoveries.create(
            self.repository, self.project, self.sha, 'restore', result['to'])

        project = self.projects.add(str(target), 'Continue this draft', kind='folder')
        self.assertNotEqual(project['id'], self.project)
        (target / 'index.html').write_text('<h1>Continued in the retrieved copy</h1>')
        saved = self.projects.snapshot(project['id'], 'Continued draft')
        repository = self.projects.repository(project['id'])

        self.assertEqual(repository.blob(saved['sha'], 'index.html'),
                         b'<h1>Continued in the retrieved copy</h1>')
        self.assertEqual(self.source_bytes(), before)
        self.assertFalse((target / '.git').exists())

    def saved_folder_at_unavailable_source(self, source):
        original = self.root / 'retained-folder'
        original.mkdir()
        (original / 'index.html').write_text('Saved before source became unavailable')
        project = self.projects.add(str(original), kind='folder')['id']
        sha = self.projects.snapshot(project)['sha']
        document = read_json(self.projects.file)
        next(p for p in document['projects'] if p['id'] == project)['path'] = str(source)
        write_json(self.projects.file, document, private=True)
        return project, sha

    def test_missing_source_with_available_parent_can_restore_and_continue(self):
        source = self.root / 'missing-original'
        project, sha = self.saved_folder_at_unavailable_source(source)
        result = suggest_destination(self.recoveries, project, sha)
        self.assertEqual(Path(result['to']).parent, source.parent)
        self.assertFalse(source.exists())
        self.recoveries.create(self.projects.repository(project), project, sha,
                               'restore', result['to'])
        continued = self.projects.add(result['to'], kind='folder')
        saved = self.projects.snapshot(continued['id'], 'Recovered draft')
        self.assertEqual(self.projects.repository(continued['id']).blob(
            saved['sha'], 'index.html'), b'Saved before source became unavailable')
        self.assertFalse(source.exists())

    def test_missing_parent_requires_user_location_without_creating_directories(self):
        parent = self.root / 'missing-parent'
        project, sha = self.saved_folder_at_unavailable_source(parent / 'source')
        with self.assertRaisesRegex(ValueError, '上级目录不可用'):
            suggest_destination(self.recoveries, project, sha)
        self.assertFalse(parent.exists())
        self.assertFalse(self.recoveries.directory.exists())

    def test_parent_without_write_permission_requires_user_location(self):
        with patch('reprise.recovery_destination.os.access', return_value=False):
            with self.assertRaisesRegex(ValueError, '不可写'):
                suggest_destination(self.recoveries, self.project, self.sha)
        self.assertFalse(self.recoveries.directory.exists())

    def test_symlink_parent_requires_user_location_without_writing_through_it(self):
        parent = self.root / 'linked-parent'
        parent.symlink_to(self.repository.path, target_is_directory=True)
        project, sha = self.saved_folder_at_unavailable_source(parent / 'source')
        before = self.source_bytes()
        with self.assertRaisesRegex(ValueError, '符号链接'):
            suggest_destination(self.recoveries, project, sha)
        self.assertEqual(self.source_bytes(), before)
        self.assertFalse(self.recoveries.directory.exists())

    def test_source_record_inside_data_cannot_put_a_copy_back_inside_data(self):
        project, sha = self.saved_folder_at_unavailable_source(
            self.projects.directory / 'missing-source')
        with self.assertRaisesRegex(ValueError, '数据目录之外'):
            suggest_destination(self.recoveries, project, sha)
        self.assertFalse(self.recoveries.directory.exists())

    def archive_destination_records(self, related=True):
        archive = {'id': 'archive-view', 'name': 'Saved archive', 'kind': 'archive',
                   'path': str(self.projects.directory / 'named-archives/views/example.git')}
        owner = dict(self.projects.record(self.project))
        if related:
            owner['history_project_ids'] = [archive['id']]
        return archive, owner

    def test_internal_archive_uses_related_project_sibling_outside_data(self):
        archive, owner = self.archive_destination_records()
        with patch.object(self.projects, 'record', return_value=archive), \
                patch.object(self.projects, 'records', return_value=[owner, archive]), \
                patch.object(self.projects, 'repository', return_value=self.repository):
            result = suggest_destination(self.recoveries, archive['id'], self.sha)
        target = Path(result['to'])
        self.assertEqual(target.parent, self.repository.path.parent)
        self.assertEqual(result['location'], 'related-project-sibling')
        self.assertFalse(target.exists())
        self.assertNotIn(self.projects.directory, target.parents)

    def test_unlinked_internal_archive_uses_documents_without_creating_files(self):
        archive, owner = self.archive_destination_records(related=False)
        home = self.root / 'user-home'
        documents = home / 'Documents'
        documents.mkdir(parents=True)
        with patch.object(self.projects, 'record', return_value=archive), \
                patch.object(self.projects, 'records', return_value=[owner, archive]), \
                patch.object(self.projects, 'repository', return_value=self.repository), \
                patch('reprise.recovery_destination.Path.home', return_value=home):
            result = suggest_destination(self.recoveries, archive['id'], self.sha)
        self.assertEqual(Path(result['to']).parent, documents)
        self.assertEqual(result['location'], 'documents')
        self.assertEqual(list(documents.iterdir()), [])

    def test_archive_skips_unwritable_related_root_and_documents_then_uses_home(self):
        archive, owner = self.archive_destination_records()
        home = self.root / 'available-home'
        home.mkdir()
        real_access = os.access
        with patch.object(self.projects, 'record', return_value=archive), \
                patch.object(self.projects, 'records', return_value=[owner, archive]), \
                patch.object(self.projects, 'repository', return_value=self.repository), \
                patch('reprise.recovery_destination.Path.home', return_value=home), \
                patch('reprise.recovery_destination.os.access',
                      side_effect=lambda path, mode: path == home and real_access(path, mode)):
            result = suggest_destination(self.recoveries, archive['id'], self.sha)
        self.assertEqual(Path(result['to']).parent, home)
        self.assertEqual(result['location'], 'home')
        self.assertEqual(list(home.iterdir()), [])

    def test_archive_skips_related_root_inside_registered_source(self):
        archive, owner = self.archive_destination_records()
        home = self.root / 'user-home'
        documents = home / 'Documents'
        documents.mkdir(parents=True)
        # The owner's sibling would still be inside this registered container.
        container = {'id': 'container', 'kind': 'folder', 'path': str(self.root)}
        # Put fallback outside that registered container using another fixture.
        outside = fixture('archive-recovery-outside')
        documents = outside / 'Documents'
        documents.mkdir()
        with patch.object(self.projects, 'record', return_value=archive), \
                patch.object(self.projects, 'records', return_value=[owner, archive, container]), \
                patch.object(self.projects, 'repository', return_value=self.repository), \
                patch('reprise.recovery_destination.Path.home', return_value=outside):
            # Use the actual registered-source validation with the supplied records.
            result = suggest_destination(self.recoveries, archive['id'], self.sha)
        self.assertEqual(Path(result['to']).parent, documents)
        self.assertEqual(result['location'], 'documents')
        self.assertEqual(list(documents.iterdir()), [])

    def test_sibling_inside_another_registered_folder_is_refused(self):
        container = self.root / 'registered-container'
        source = container / 'nested-project'
        source.mkdir(parents=True)
        (source / 'index.html').write_text('Nested project')
        self.projects.add(str(container), kind='folder')
        project = self.projects.add(str(source), kind='folder')['id']
        sha = self.projects.snapshot(project)['sha']
        with self.assertRaisesRegex(ValueError, '源仓库之外'):
            suggest_destination(self.recoveries, project, sha)
        self.assertEqual(list(container.iterdir()), [source])
        self.assertFalse(self.recoveries.directory.exists())

    def test_project_name_cannot_escape_or_create_oversized_filename(self):
        with patch.object(self.projects, 'record', wraps=self.projects.record) as record:
            original = self.projects.record(self.project)
            record.return_value = dict(original, name='../../\\\x00<草稿>/' * 30)
            record.side_effect = lambda identifier: (
                dict(original, name='../../\\\x00<草稿>/' * 30)
                if identifier == self.project else original)
            result = suggest_destination(self.recoveries, self.project, self.sha)

        target = Path(result['to'])
        self.assertEqual(target.parent, self.repository.path.parent)
        self.assertNotIn('..', target.name)
        self.assertNotIn('\\', target.name)
        self.assertNotIn('\x00', target.name)
        self.assertLess(len(os.fsencode(target.name)), 255)
        self.assertFalse(self.recoveries.directory.exists())

    def test_existing_file_and_dangling_link_are_not_overwritten(self):
        with patch('reprise.recovery_destination.secrets.token_hex', return_value='a' * 8):
            occupied = Path(suggest_destination(
                self.recoveries, self.project, self.sha)['to'])
        with patch('reprise.recovery_destination.secrets.token_hex', return_value='b' * 8):
            dangling = Path(suggest_destination(
                self.recoveries, self.project, self.sha)['to'])
        occupied.parent.mkdir(exist_ok=True)
        occupied.write_text('Keep existing output')
        dangling.symlink_to(self.root / 'missing')

        with patch('reprise.recovery_destination.secrets.token_hex',
                   side_effect=['a' * 8, 'b' * 8, 'c' * 8]):
            result = suggest_destination(self.recoveries, self.project, self.sha)

        self.assertNotIn(Path(result['to']), (occupied, dangling))
        self.assertFalse(os.path.lexists(result['to']))
        self.assertEqual(occupied.read_text(), 'Keep existing output')
        self.assertTrue(dangling.is_symlink())

    def test_invalid_unknown_and_changed_revision_never_produce_a_destination(self):
        for revision in ('HEAD', self.sha[:8], '', '../source', 'A' * 40, None):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                suggest_destination(self.recoveries, self.project, revision)
        with self.assertRaises(KeyError):
            suggest_destination(self.recoveries, 'unknown-project', self.sha)
        with self.assertRaises(ValueError):
            suggest_destination(self.recoveries, self.project, '0' * 40)
        with patch.object(self.projects, 'repository', return_value=self.repository):
            with patch.object(self.repository, 'resolve', return_value='a' * 40):
                with self.assertRaisesRegex(ValueError, '版本标识发生变化'):
                    suggest_destination(self.recoveries, self.project, self.sha)
        self.assertFalse(self.recoveries.directory.exists())

    def test_folder_cannot_use_another_projects_version(self):
        folders = []
        for name in ('first-folder', 'second-folder'):
            source = self.root / name
            source.mkdir()
            (source / 'index.html').write_text(name)
            project = self.projects.add(str(source), kind='folder')['id']
            snapshot = self.projects.snapshot(project)
            folders.append((project, snapshot['sha']))
        with self.assertRaises(ValueError):
            suggest_destination(self.recoveries, folders[0][0], folders[1][1])
        self.assertFalse(self.recoveries.directory.exists())

    def test_sha256_git_commit_is_preserved_when_supported(self):
        source = self.root / 'sha256-source'
        source.mkdir()
        try:
            git(source, 'init', '--object-format=sha256')
        except subprocess.CalledProcessError:
            self.skipTest('Installed Git does not support SHA-256 repositories')
        git(source, 'config', 'user.name', 'Reprise test')
        git(source, 'config', 'user.email', 'test@example.invalid')
        (source / 'index.html').write_text('SHA-256 draft')
        git(source, 'add', '.')
        git(source, 'commit', '-m', 'SHA-256 draft')
        sha = git(source, 'rev-parse', 'HEAD')
        project = self.projects.add(str(source))['id']

        result = suggest_destination(self.recoveries, project, sha)

        self.assertEqual(len(result['sha']), 64)
        self.assertEqual(result['sha'], sha)
        self.assertFalse(os.path.lexists(result['to']))

    def test_managed_root_symlink_is_refused_without_writing_source(self):
        before = self.source_bytes()
        self.recoveries.directory.symlink_to(self.repository.path, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, '符号链接'):
            suggest_destination(self.recoveries, self.project, self.sha)
        with self.assertRaises(ValueError):
            self.recoveries.create(self.repository, self.project, self.sha, 'restore')
        self.assertEqual(self.source_bytes(), before)

    def test_restore_rechecks_a_suggestion_occupied_by_a_file_or_link(self):
        for kind in ('file', 'link'):
            result = suggest_destination(self.recoveries, self.project, self.sha)
            target = Path(result['to'])
            target.parent.mkdir(exist_ok=True)
            if kind == 'file':
                target.write_text('Existing file must remain')
            else:
                target.symlink_to(self.repository.path, target_is_directory=True)
            before = self.source_bytes()
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, '已经存在'):
                self.recoveries.create(
                    self.repository, self.project, self.sha, 'restore', result['to'])
            self.assertEqual(self.source_bytes(), before)
            if kind == 'file':
                self.assertEqual(target.read_text(), 'Existing file must remain')
            else:
                self.assertTrue(target.is_symlink())

    def test_invalid_source_destination_is_rejected_before_receipt_creation(self):
        before = self.source_bytes()
        with self.assertRaisesRegex(ValueError, '源仓库'):
            self.recoveries.create(
                self.repository, self.project, self.sha, 'restore',
                str(self.repository.path / 'unexpected-copy'))
        self.assertFalse(self.recoveries.directory.exists())
        self.assertEqual(self.source_bytes(), before)

    def test_root_replaced_during_receipt_mkdir_cannot_redirect_the_write(self):
        root = self.recoveries.directory
        root.mkdir()
        retained = self.root / 'retained-recoveries'
        before = self.source_bytes()
        mkdir = os.mkdir
        swapped = False

        def replace_root(name, *args, **kwargs):
            nonlocal swapped
            if kwargs.get('dir_fd') is not None and name != root.name and not swapped:
                root.rename(retained)
                root.symlink_to(self.repository.path, target_is_directory=True)
                swapped = True
            return mkdir(name, *args, **kwargs)

        with patch('reprise.recovery.os.mkdir', side_effect=replace_root):
            with self.assertRaises((ValueError, OSError)):
                self.recoveries.create(self.repository, self.project, self.sha, 'restore')

        self.assertTrue(swapped)
        self.assertTrue(retained.is_dir())
        self.assertEqual(len(list(retained.iterdir())), 1)
        self.assertTrue(root.is_symlink())
        self.assertEqual(self.source_bytes(), before)

    def test_external_export_rechecks_its_intermediate_snapshot_destination(self):
        from reprise.backup import _write_json
        other = commit_repo(self.root / 'other-source')
        self.projects.add(str(other.path))
        before = {path.relative_to(other.path): path.read_bytes()
                  for path in other.path.rglob('*') if path.is_file()}
        root = self.recoveries.directory
        retained = self.root / 'retained-export-receipts'
        target = self.root / 'new-export.zip'
        swapped = False

        def replace_after_receipt(path, value):
            nonlocal swapped
            _write_json(path, value)
            if not swapped:
                root.rename(retained)
                root.symlink_to(other.path, target_is_directory=True)
                swapped = True

        with patch('reprise.recovery._write_json', side_effect=replace_after_receipt):
            with self.assertRaises((ValueError, OSError)):
                self.recoveries.create(
                    self.repository, self.project, self.sha, 'export', str(target))

        self.assertTrue(swapped)
        self.assertFalse(target.exists())
        after = {path.relative_to(other.path): path.read_bytes()
                 for path in other.path.rglob('*') if path.is_file()}
        self.assertEqual(after, before)
        self.assertEqual(sorted(path.name for path in other.path.iterdir()),
                         ['.git', 'clip.bin', 'index.html'])


if __name__ == '__main__':
    unittest.main()
