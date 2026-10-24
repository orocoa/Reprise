"""Source relocation contracts: exact content, stable identity, no deletion."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

from reprise.cancellation import Cancelled
from reprise.projects import ProjectStore
from reprise.storage import read_json, write_json
from reprise import relocation
from test_runtime import fixture, commit_repo


class RelocationTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('relocation')
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'draft.txt').write_text('first')
        (self.source / 'empty').mkdir()
        (self.source / 'link').symlink_to('draft.txt')
        self.projects = ProjectStore(self.root / 'data')
        self.record = self.projects.add(str(self.source), name='Stable project', kind='folder')
        self.identifier = self.record['id']

    def test_migrate_keeps_versions_id_all_metadata_and_original_then_saves_third(self):
        first = self.projects.snapshot(self.identifier, 'first')
        (self.source / 'draft.txt').write_text('second')
        second = self.projects.snapshot(self.identifier, 'second')
        document = read_json(self.projects.file)
        document['projects'][0].update(aliases=['Alias'], version_notes={'test': {'saved': True}},
                                       version_recipes={'test': {'saved': True}}, history_catalog=['a' * 40])
        write_json(self.projects.file, document)
        before = self.projects.record(self.identifier)
        destination = self.root / 'migrated'
        result = relocation.migrate(self.projects, self.identifier, str(destination))
        self.assertEqual(result['status'], 'complete')
        self.assertTrue(result['not_deleted'])
        self.assertTrue(self.source.is_dir())
        self.assertTrue((destination / 'empty').is_dir())
        self.assertEqual(os.readlink(destination / 'link'), 'draft.txt')
        self.assertEqual(destination.stat().st_mode & 0o777, self.source.stat().st_mode & 0o777)
        after = self.projects.record(self.identifier)
        self.assertEqual(after, {**before, 'path': str(destination)})
        self.assertEqual(self.projects.add(str(destination), kind='folder')['id'], self.identifier)
        self.assertEqual(len(self.projects.records()), 1)
        with self.assertRaises(ValueError):
            self.projects.add(str(self.source), kind='folder')
        (destination / 'draft.txt').write_text('third')
        third = self.projects.snapshot(self.identifier, 'third')
        repository = self.projects.repository(self.identifier)
        self.assertEqual([entry['sha'] for entry in repository.history()['commits']],
                         [third['sha'], second['sha'], first['sha']])
        self.assertEqual((self.source / 'draft.txt').read_text(), 'second')

    def test_relink_online_requires_all_current_unsaved_bytes_not_name_or_mtime(self):
        self.projects.snapshot(self.identifier)
        candidate = self.root / 'candidate'
        shutil.copytree(self.source, candidate, symlinks=True)
        before = (candidate / 'draft.txt').stat()
        (self.source / 'draft.txt').write_text('other')
        os.utime(self.source / 'draft.txt', ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, '未保存'):
            relocation.inspect_relink(self.projects, self.identifier, str(candidate))
        shutil.copy2(self.source / 'draft.txt', candidate / 'draft.txt')
        inspection = relocation.inspect_relink(self.projects, self.identifier, str(candidate))
        self.assertEqual(inspection['identity_evidence']['method'], 'online-source-bytes')
        self.assertEqual(self.projects.record(self.identifier)['path'], str(self.source))
        relocation.relink(self.projects, self.identifier, str(candidate))
        self.assertEqual(self.projects.record(self.identifier)['path'], str(candidate))

    def test_offline_relink_accepts_exact_saved_version_and_rejects_extra_or_wrong_bytes(self):
        saved = self.projects.snapshot(self.identifier)
        candidate = self.root / 'candidate'
        shutil.copytree(self.source, candidate, symlinks=True)
        self.source.rename(self.root / 'offline')
        (candidate / 'draft.txt').write_text('other')
        with self.assertRaisesRegex(ValueError, '精确匹配'):
            relocation.relink(self.projects, self.identifier, str(candidate))
        (candidate / 'draft.txt').write_text('first')
        (candidate / 'extra').write_text('not in version')
        with self.assertRaises(ValueError):
            relocation.relink(self.projects, self.identifier, str(candidate))
        (candidate / 'extra').rename(self.root / 'retained-extra')
        result = relocation.relink(self.projects, self.identifier, str(candidate))
        self.assertEqual(result['identity_evidence']['sha'], saved['sha'])

    def test_offline_unversioned_folder_and_wrong_or_owned_paths_refused(self):
        candidate = self.root / 'candidate'
        shutil.copytree(self.source, candidate, symlinks=True)
        self.projects.add(str(candidate), kind='folder')
        with self.assertRaisesRegex(ValueError, '其他项目'):
            relocation.relink(self.projects, self.identifier, str(candidate))
        self.source.rename(self.root / 'offline')
        unowned = self.root / 'unowned'
        shutil.copytree(candidate, unowned, symlinks=True)
        with self.assertRaisesRegex(ValueError, '没有已保存'):
            relocation.relink(self.projects, self.identifier, str(unowned))
        with self.assertRaises(ValueError):
            relocation.migrate(self.projects, self.identifier, str(self.root / 'migrate'))

    def test_existing_nested_data_protected_and_external_symlink_targets_refused(self):
        for path in (self.source, self.source / 'child', self.root, self.projects.directory / 'child'):
            with self.assertRaises(ValueError):
                relocation.migrate(self.projects, self.identifier, str(path))
        with self.assertRaisesRegex(ValueError, '受保护'):
            relocation.migrate(self.projects, self.identifier, str(self.root / 'copy'), protected_roots=[self.source])
        (self.source / 'outside').symlink_to('../data')
        with self.assertRaisesRegex(ValueError, '链接'):
            relocation.migrate(self.projects, self.identifier, str(self.root / 'copy'))
        self.assertEqual(self.projects.record(self.identifier)['path'], str(self.source))

    def test_source_change_during_copy_retains_failed_copy_and_receipt_without_switch(self):
        copy = relocation._copy
        destination = self.root / 'copy'
        def change(*args, **kwargs):
            result = copy(*args, **kwargs)
            (self.source / 'draft.txt').write_text('changed during copy')
            return result
        with patch.object(relocation, '_copy', side_effect=change):
            with self.assertRaisesRegex(ValueError, '源目录发生变化'):
                relocation.migrate(self.projects, self.identifier, str(destination))
        self.assertTrue(destination.is_dir())
        self.assertEqual(self.projects.record(self.identifier)['path'], str(self.source))
        receipts = list((self.projects.directory / 'relocations').glob('*.json'))
        self.assertEqual(len(receipts), 1)
        self.assertEqual(json.loads(receipts[0].read_text())['status'], 'failed')

    def test_concurrent_registration_edit_is_preserved_and_prevents_switch(self):
        copy = relocation._copy
        def change(*args, **kwargs):
            result = copy(*args, **kwargs)
            document = read_json(self.projects.file)
            document['projects'][0]['name'] = 'Concurrent name'
            write_json(self.projects.file, document)
            return result
        with patch.object(relocation, '_copy', side_effect=change):
            with self.assertRaisesRegex(ValueError, '登记在复制期间发生变化'):
                relocation.migrate(self.projects, self.identifier, str(self.root / 'copy'))
        self.assertEqual(self.projects.record(self.identifier)['name'], 'Concurrent name')
        self.assertEqual(self.projects.record(self.identifier)['path'], str(self.source))

    def test_cancel_during_copy_retains_files_and_does_not_switch(self):
        destination = self.root / 'copy'
        class Cancel:
            def check(self):
                if (destination / 'draft.txt').exists():
                    raise Cancelled()
        with self.assertRaises(Cancelled):
            relocation.migrate(self.projects, self.identifier, str(destination), cancel=Cancel())
        self.assertTrue(destination.is_dir())
        self.assertEqual(self.projects.record(self.identifier)['path'], str(self.source))
        self.assertEqual(read_json(next((self.projects.directory / 'relocations').glob('*.json')))['status'], 'failed')

    def test_git_migration_preserves_history_refs_dirty_untracked_and_offline_anchor(self):
        source = self.root / 'git'
        repository = commit_repo(source)
        head = repository.resolve('HEAD')
        record = self.projects.add(str(source), name='Git')
        self.assertEqual(record['git_identity_anchor']['commits'][0], head)
        (source / 'index.html').write_text('unsaved work')
        (source / 'untracked').write_text('keep me')
        destination = self.root / 'git-copy'
        result = relocation.migrate(self.projects, record['id'], str(destination))
        self.assertEqual(result['status'], 'complete')
        self.assertEqual((destination / 'index.html').read_text(), 'unsaved work')
        self.assertEqual((destination / 'untracked').read_text(), 'keep me')
        self.assertEqual(self.projects.repository(record['id']).resolve('HEAD'), head)
        self.assertEqual(self.projects.add(str(destination))['id'], record['id'])
        another = self.root / 'another-copy'
        shutil.copytree(destination, another)
        destination.rename(self.root / 'offline-git')
        inspected = relocation.inspect_relink(self.projects, record['id'], str(another))
        self.assertEqual(inspected['identity_evidence'], {'method': 'saved-git-anchor', 'sha': head})
        relocation.relink(self.projects, record['id'], str(another))
        self.assertEqual(self.projects.repository(record['id']).resolve('HEAD'), head)

    def test_legacy_git_offline_without_anchor_and_unrelated_git_refused(self):
        source = self.root / 'git'
        commit_repo(source)
        record = self.projects.add(str(source))
        other = self.root / 'unrelated'
        repository = commit_repo(other)
        # fixture commits may have identical SHA; create real divergent content.
        (other / 'index.html').write_text('different repository')
        subprocess.run(['git', '-C', str(other), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(other), 'commit', '--amend', '-qm', 'different'], check=True)
        with self.assertRaisesRegex(ValueError, '共同提交'):
            relocation.relink(self.projects, record['id'], str(other))
        copy = self.root / 'accurate'
        shutil.copytree(source, copy)
        document = read_json(self.projects.file)
        next(p for p in document['projects'] if p['id'] == record['id']).pop('git_identity_anchor')
        write_json(self.projects.file, document)
        source.rename(self.root / 'offline-git')
        with self.assertRaisesRegex(ValueError, '没有可验证'):
            relocation.relink(self.projects, record['id'], str(copy))

    def test_linked_git_migration_rejected_but_verified_relink_supported(self):
        source = self.root / 'git'
        commit_repo(source)
        linked = self.root / 'linked'
        subprocess.run(['git', '-C', str(source), 'worktree', 'add', '-q', '--detach', str(linked)], check=True)
        record = self.projects.add(str(linked))
        with self.assertRaisesRegex(ValueError, 'linked worktree'):
            relocation.migrate(self.projects, record['id'], str(self.root / 'linked-copy'))
        result = relocation.relink(self.projects, record['id'], str(source))
        self.assertEqual(result['identity_evidence']['method'], 'online-git-common-commit')

    def test_git_alternates_and_include_refused_without_registration_change(self):
        source = self.root / 'git'
        commit_repo(source)
        record = self.projects.add(str(source))
        (source / '.git/objects/info/alternates').write_text(str(source / '.git/objects'))
        with self.assertRaisesRegex(ValueError, 'alternates'):
            relocation.migrate(self.projects, record['id'], str(self.root / 'git-copy'))
        self.assertEqual(self.projects.record(record['id'])['path'], str(source))

    def test_archive_overlay_stays_virtual_and_cannot_be_relinked_or_migrated(self):
        group = {'id': 'legacy-group', 'native_project_id': 'legacy-stable-id',
                 'view_repository': str(self.root / 'legacy-view'), 'name': 'Legacy archive',
                 'aliases': [], 'snapshots': []}
        raw_before = self.projects.file.read_bytes()
        with patch('reprise.archives.groups', return_value=[group]):
            for operation in (relocation.relink, relocation.migrate):
                with self.assertRaisesRegex(ValueError, '旧归档'):
                    operation(self.projects, 'legacy-stable-id', str(self.root / 'target'))
            self.assertEqual(self.projects.file.read_bytes(), raw_before)
            another = self.root / 'new-folder'
            another.mkdir()
            self.projects.add(str(another), kind='folder')
            self.assertEqual(len(self.projects.records()), 3)
        self.assertEqual(len(read_json(self.projects.file)['projects']), 2)
        self.assertNotIn('legacy-stable-id', self.projects.file.read_text())

    def test_metadata_xattrs_mode_and_mtime_are_verified_in_migration(self):
        from reprise.metadata import xattrs, restore_xattrs
        path = self.source / 'draft.txt'
        path.chmod(0o640)
        os.utime(path, ns=(1600000000000000000, 1600000000000000000))
        attributes = xattrs(path)
        attributes['com.reprise.test' if sys.platform == 'darwin' else 'user.reprise-test'] = base64.b64encode(b'attribute').decode('ascii')
        restore_xattrs(path, attributes)
        destination = self.root / 'metadata-copy'
        relocation.migrate(self.projects, self.identifier, str(destination))
        copied = destination / 'draft.txt'
        self.assertEqual(copied.stat().st_mode & 0o777, 0o640)
        self.assertEqual(copied.stat().st_mtime_ns, 1600000000000000000)
        self.assertEqual(xattrs(copied), xattrs(path))

    def test_bare_git_migrate_refused_but_anchored_relink_supported(self):
        source = self.root / 'git'
        commit_repo(source)
        bare = self.root / 'bare.git'
        subprocess.run(['git', 'clone', '-q', '--bare', str(source), str(bare)], check=True)
        record = self.projects.add(str(bare))
        with self.assertRaisesRegex(ValueError, 'bare'):
            relocation.migrate(self.projects, record['id'], str(self.root / 'bare-copy'))
        relocation.relink(self.projects, record['id'], str(source))
        self.assertEqual(self.projects.record(record['id'])['path'], str(source))

    def test_exclusive_offline_maintenance_blocks_direct_project_writes_and_relocation(self):
        from reprise.maintenance import DataLease, DataLeaseError
        destination = self.root / 'copy'
        with DataLease(self.projects.directory, exclusive=True):
            for operation in (
                    lambda: self.projects.add(str(self.source), kind='folder'),
                    lambda: self.projects.snapshot(self.identifier),
                    lambda: relocation.inspect_relink(self.projects, self.identifier, str(self.source)),
                    lambda: relocation.relink(self.projects, self.identifier, str(self.source)),
                    lambda: relocation.migrate(self.projects, self.identifier, str(destination))):
                with self.assertRaises(DataLeaseError):
                    operation()
        self.assertFalse(destination.exists())

    def test_migrate_rejects_dangling_target_symlink_and_special_permission_bits(self):
        link = self.root / 'target-link'
        outside = self.root / 'missing'
        link.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, '符号链接'):
            relocation.migrate(self.projects, self.identifier, str(link))
        self.assertFalse(outside.exists())
        self.source.chmod(0o1700)
        with self.assertRaisesRegex(ValueError, '特殊权限位'):
            relocation.migrate(self.projects, self.identifier, str(self.root / 'copy'))
        self.assertEqual(self.projects.record(self.identifier)['path'], str(self.source))

    def test_git_then_explicit_folder_keep_independent_kind_history_at_same_path(self):
        source = self.root / 'dual-kind'
        repository = commit_repo(source)
        git = self.projects.add(str(source))
        folder = self.projects.add(str(source), kind='folder')
        self.assertNotEqual(git['id'], folder['id'])
        self.assertEqual((git['kind'], folder['kind']), ('git', 'folder'))
        saved = self.projects.snapshot(folder['id'], 'Folder version')
        self.assertNotEqual(saved['sha'], repository.resolve('HEAD'))
        self.assertEqual(self.projects.add(str(source), kind='folder')['id'], folder['id'])
        self.assertEqual(self.projects.add(str(source))['id'], git['id'])
        self.assertEqual(self.projects.add(str(source), kind='git')['id'], git['id'])
        self.assertEqual(self.projects.repository(git['id']).resolve('HEAD'), repository.resolve('HEAD'))

    def test_folder_first_default_git_does_not_reuse_folder_identity(self):
        source = self.root / 'folder-first'
        commit_repo(source)
        folder = self.projects.add(str(source), kind='folder')
        git = self.projects.add(str(source))
        self.assertEqual(git['kind'], 'git')
        self.assertNotEqual(folder['id'], git['id'])
        self.assertEqual(self.projects.add(str(source), kind='folder')['id'], folder['id'])
        self.assertEqual(self.projects.add(str(source))['id'], git['id'])

    def test_folder_migration_reuses_same_kind_and_new_git_keeps_independent_identity(self):
        source = self.root / 'dual-source'
        repository = commit_repo(source)
        git = self.projects.add(str(source))
        folder = self.projects.add(str(source), kind='folder')
        saved = self.projects.snapshot(folder['id'])
        destination = self.root / 'folder-destination'
        relocation.migrate(self.projects, folder['id'], str(destination))
        self.assertEqual(self.projects.add(str(destination), kind='folder')['id'], folder['id'])
        self.assertEqual(self.projects.record(git['id'])['path'], str(source))
        new_git = self.projects.add(str(destination))
        self.assertEqual(new_git['kind'], 'git')
        self.assertNotIn(new_git['id'], (folder['id'], git['id']))
        self.assertEqual(self.projects.add(str(destination), kind='folder')['id'], folder['id'])
        self.assertEqual(self.projects.repository(folder['id']).resolve('HEAD'), saved['sha'])
        self.assertEqual(self.projects.repository(new_git['id']).resolve('HEAD'), repository.resolve('HEAD'))
        # A directory occupied by the other kind is explicitly refused, rather
        # than changing or consuming the other project's registration.
        with self.assertRaisesRegex(ValueError, '其他项目'):
            relocation.relink(self.projects, git['id'], str(destination))
        self.assertEqual(self.projects.record(git['id'])['path'], str(source))
        self.assertEqual(self.projects.record(folder['id'])['path'], str(destination))
