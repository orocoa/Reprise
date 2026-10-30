"""Single-file transport round trips and rejects hostile archive paths."""
import os
from pathlib import Path
import unittest
import zipfile

from reprise.service import Reprise
from reprise.projects import ProjectStore
from reprise.backup_file import export_file, import_file, _unpack
from reprise.maintenance import DataLease, DataLeaseError
from test_runtime import fixture


class BackupFileTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('backup-file')
        self.app = Reprise(self.root / 'data')
        self.addCleanup(self.app.close)
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'draft.txt').write_text('saved content')
        (self.source / 'link').symlink_to('draft.txt')
        (self.source / 'empty').mkdir()
        self.project = self.app.projects.add(str(self.source), kind='folder')
        self.saved = self.app.projects.snapshot(self.project['id'], 'Saved')

    def test_export_file_import_and_restore_exact_bytes_without_overwriting_live_library(self):
        archive = self.root / 'library.reprise-backup.zip'
        result = export_file(self.app, str(archive))
        self.assertTrue(result['readback_verified'])
        self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            export_file(self.app, str(archive))
        imported = import_file(self.app, str(archive))
        projects = ProjectStore(imported['path'])
        repo = projects.repository(self.project['id'])
        self.assertEqual(repo.resolve('HEAD'), self.saved['sha'])
        destination = self.root / 'readback'
        repo.materialize(self.saved['sha'], destination)
        self.assertEqual((destination / 'draft.txt').read_text(), 'saved content')
        self.assertEqual(os.readlink(destination / 'link'), 'draft.txt')
        self.assertTrue((destination / 'empty').is_dir())
        self.assertEqual(self.app.projects.repository(self.project['id']).resolve('HEAD'), self.saved['sha'])

    def test_exclusive_export_rejects_other_lease_and_restores_own_shared_lease(self):
        with DataLease(self.app.directory):
            with self.assertRaises(DataLeaseError):
                export_file(self.app, str(self.root / 'blocked.zip'))
        self.assertFalse((self.root / 'blocked.zip').exists())
        with self.assertRaises(DataLeaseError):
            with DataLease(self.app.directory, exclusive=True):
                pass
        self.assertTrue(export_file(self.app, str(self.root / 'later.zip'))['readback_verified'])

    def test_archive_traversal_duplicate_and_symlink_parent_are_rejected(self):
        for index, entries in enumerate((
            [('../outside', 'bad')],
            [('payload/x', 'one'), ('payload/x', 'two')],
            [('payload/link', 'x'), ('payload/link/file', 'bad')],
        )):
            archive = self.root / ('hostile-%s.zip' % index)
            with zipfile.ZipFile(archive, 'w') as z:
                for name, value in entries:
                    z.writestr(name, value)
            with self.assertRaises((ValueError, OSError)):
                _unpack(archive, self.root / ('unpack-%s' % index))
        self.assertFalse((self.root / 'outside').exists())

    def test_busy_task_prevents_export_before_any_copy(self):
        self.app.jobs.busy.add(self.project['id'])
        try:
            with self.assertRaisesRegex(ValueError, '任务'):
                export_file(self.app, str(self.root / 'busy.zip'))
        finally:
            self.app.jobs.busy.clear()
        self.assertFalse((self.root / 'busy.zip').exists())
