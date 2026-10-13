"""Evidence diagnostics disclose local locations without publishing private files."""
import json
import unittest

from reprise.evidence import EvidenceStore
from test_runtime import fixture


class EvidenceDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('evidence-diagnostics')
        self.store = EvidenceStore(self.root, None)
        self.store.directory.mkdir()

    def test_failed_capture_exposes_existing_local_diagnostics_without_media(self):
        identifier = 'a' * 32
        folder = self.store.directory / identifier
        folder.mkdir()
        record = {'id': identifier, 'source': 'automatic', 'sha': 'b' * 40,
                  'status': 'failed', 'items': [], 'errors': [{'error': 'worker failed'}]}
        (folder / 'record.json').write_text(json.dumps(record))
        (folder / 'after-browser.log').write_text('private retained browser log')
        public = self.store.public(record)
        self.assertEqual(public['local_directory'], str(folder))
        self.assertEqual(public['record_path'], str(folder / 'record.json'))
        self.assertEqual(public['browser_logs'], [str(folder / 'after-browser.log')])
        self.assertEqual(public['items'], [])
        for name in ('record.json', 'after-browser.log'):
            with self.subTest(name=name), self.assertRaises(KeyError):
                self.store.file(identifier + '/' + name)
        self.assertEqual((folder / 'after-browser.log').read_text(), 'private retained browser log')

    def test_diagnostic_paths_do_not_follow_record_ids_or_symlinks_outside_storage(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'record.json').write_text('{}')
        (self.store.directory / 'escaped').symlink_to(outside, target_is_directory=True)
        for identifier in ('../outside', str(outside), 'escaped', '.', None):
            with self.subTest(identifier=identifier):
                public = self.store.public({'id': identifier, 'items': [], 'local_directory': str(outside),
                                            'record_path': str(outside / 'record.json'), 'browser_logs': ['untrusted']})
                self.assertNotIn('local_directory', public)
                self.assertNotIn('record_path', public)
                self.assertNotIn('browser_logs', public)
