"""Verification reuses exact internal copies, rechecking bytes and metadata."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from reprise.recovery_reuse import verified_copy
from reprise.service import Reprise
from test_runtime import fixture


class RecoveryReuseTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('recovery-reuse')
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'draft.txt').write_bytes(b'first draft')
        self.app = Reprise(self.root / 'data')
        self.project = self.app.projects.add(str(self.source), kind='folder')['id']
        self.sha = self.app.projects.snapshot(self.project, 'First draft')['sha']
        self.repository = self.app.projects.repository(self.project)

    def tearDown(self):
        self.app.close()

    def restore(self, **kwargs):
        return self.app.recovery.create(self.repository, self.project, self.sha, 'restore', **kwargs)

    def reuse(self):
        return verified_copy(self.app.recovery, self.repository, self.project, self.sha)

    def test_exact_copy_is_read_back_without_creating_a_second_snapshot(self):
        existing = self.restore()
        before = sorted(self.app.recovery.directory.glob('*/snapshot'))
        result = self.reuse()
        self.assertEqual(result['path'], existing['path'])
        self.assertTrue(result['verification']['readback_verified'])
        self.assertTrue((Path(existing['path']).parent / 'reuse-checks' / (result['reuse_check'] + '.json')).is_file())
        self.assertEqual(before, sorted(self.app.recovery.directory.glob('*/snapshot')))

    def test_corrupt_bytes_are_rejected_and_preserved_even_with_original_mtime(self):
        existing = self.restore()
        path = Path(existing['path']) / 'draft.txt'
        stamp = path.stat()
        path.write_bytes(b'wrong draft')
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        self.assertIsNone(self.reuse())
        self.assertEqual(path.read_bytes(), b'wrong draft')
        diagnostic = list(path.parent.parent.glob('reuse-checks/*.json'))
        self.assertEqual(len(diagnostic), 1)

    def test_external_or_partial_restore_is_not_reused(self):
        external = self.restore(destination=str(self.root / 'external'))
        self.restore(paths=['draft.txt'])
        self.assertIsNone(self.reuse())
        self.assertTrue(Path(external['path']).is_dir())

    def test_new_version_cannot_borrow_an_older_copy(self):
        self.restore()
        (self.source / 'draft.txt').write_bytes(b'second draft')
        sha = self.app.projects.snapshot(self.project, 'Second draft')['sha']
        self.assertIsNone(verified_copy(self.app.recovery, self.repository, self.project, sha))

    def test_additional_git_directory_invalidates_reuse_without_removal(self):
        existing = self.restore()
        git = Path(existing['path']) / '.git'
        git.mkdir()
        (git / 'HEAD').write_text('extra')
        self.assertIsNone(self.reuse())
        self.assertTrue((git / 'HEAD').is_file())

    def test_repeated_full_review_reuses_copy_but_preserves_separate_plans(self):
        first = self.app.organization.create(self.project, self.sha)
        second = self.app.organization.create(self.project, self.sha)
        self.assertNotEqual(first['id'], second['id'])
        self.assertFalse(first['recovery_reused'])
        self.assertTrue(second['recovery_reused'])
        self.assertEqual(second['additional_recovery_logical_bytes'], 0)
        self.assertEqual(len(list(self.app.recovery.directory.glob('*/snapshot'))), 1)

    def test_diagnostic_symlink_does_not_write_outside_recovery(self):
        existing = self.restore()
        outside = self.root / 'unrelated'
        outside.mkdir()
        (Path(existing['path']).parent / 'reuse-checks').symlink_to(outside, target_is_directory=True)
        self.assertIsNone(self.reuse())
        self.assertEqual(list(outside.iterdir()), [])

    def test_mid_scan_edit_of_an_already_read_file_invalidates_reuse(self):
        import reprise.organize as organize
        (self.source / 'z-last.txt').write_bytes(b'last file')
        self.sha = self.app.projects.snapshot(self.project, 'Two files')['sha']
        existing = self.restore()
        target = Path(existing['path']) / 'draft.txt'
        real_digest = organize.digest
        reads = 0
        def mutate_after_read(stream, cancel=None):
            nonlocal reads
            value = real_digest(stream, cancel)
            reads += 1
            if reads == 2:
                target.write_bytes(b'changed while checking')
            return value
        with patch.object(organize, 'digest', side_effect=mutate_after_read):
            self.assertIsNone(self.reuse())
        self.assertEqual(target.read_bytes(), b'changed while checking')
        self.assertTrue(list(target.parent.parent.glob('reuse-checks/*.json')))

