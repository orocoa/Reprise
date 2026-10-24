"""Cost preview never creates content history or materialized copies."""
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import zipfile

from reprise.import_preflight import analyze
from reprise.service import Reprise
from test_runtime import fixture


class ImportPreflightTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('import-preflight')
        self.sources = []
        for n in range(3):
            path = self.root / ('draft-%d' % n)
            path.mkdir()
            (path / 'asset.bin').write_bytes(b'common' * 1000)
            (path / 'index.html').write_text('<h1>%d</h1>' % n)
            self.sources.append(path)
        self.app = Reprise(self.root / 'data')
        self.spec = {'name': 'Preview sample', 'versions': [
            {'path': str(p), 'title': 'Draft %d' % n} for n, p in enumerate(self.sources)]}

    def tearDown(self):
        self.app.close()

    def test_preview_has_no_history_or_recovery_and_keeps_uncertainty(self):
        result = analyze(self.app.folder_imports, self.spec)
        self.assertEqual(self.app.projects.summaries(), [])
        self.assertFalse(self.app.projects.folders.path.exists())
        self.assertFalse(self.app.recovery.directory.exists())
        self.assertFalse(result['readback_verified'])
        self.assertIsNone(result['modeled_net_after_source_removal_bytes'])
        self.assertEqual(result['additional_content_logical_bytes_min'], 0)
        self.assertEqual(result['additional_readback_logical_bytes_max'], result['expanded_logical_bytes'])
        self.assertGreater(result['capacity_budget_bytes'], 2 * result['expanded_logical_bytes'])
        self.assertEqual([v['keep'] for v in result['versions']], [False, False, True])
        self.assertEqual(result['source_volumes'][0]['input_logical_bytes'], result['expanded_logical_bytes'])

    def test_source_and_order_changes_invalidate_fingerprint_not_free_space(self):
        before = analyze(self.app.folder_imports, self.spec)['fingerprint']
        with patch('reprise.import_preflight.shutil.disk_usage', return_value=shutil._ntuple_diskusage(100, 99, 1)):
            low = analyze(self.app.folder_imports, self.spec)
        self.assertEqual(low['fingerprint'], before)
        self.assertFalse(low['capacity_available'])
        self.assertTrue(low['blockers'])
        self.assertFalse(self.app.projects.folders.path.exists())
        (self.sources[0] / 'index.html').write_text('changed')
        self.assertNotEqual(analyze(self.app.folder_imports, self.spec)['fingerprint'], before)

    def test_zip_declared_expansion_is_separate_from_original_archive(self):
        path = self.root / 'old.zip'
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('asset.bin', b'a' * 100000)
        spec = json.loads(json.dumps(self.spec))
        spec['versions'][0].update(path=str(path), zip_mode='contents')
        result = analyze(self.app.folder_imports, spec)
        row = result['versions'][0]
        self.assertEqual(row['expanded_logical_bytes'], 100000)
        self.assertEqual(row['original_logical_bytes'], path.stat().st_size)
        self.assertFalse(result['recovery_copies_created'])

    def test_git_exclusions_are_disclosed_without_becoming_removal_candidates(self):
        (self.sources[0] / '.git').mkdir()
        (self.sources[0] / '.git' / 'HEAD').write_text('private metadata')
        result = analyze(self.app.folder_imports, self.spec)
        self.assertTrue(result['versions'][0]['excluded'])
        self.assertFalse(result['source_safety_checked'])
        self.assertNotIn('removal_candidate', result['versions'][0])

    def test_changed_preview_is_rejected_before_project_registration(self):
        preview = self.app.folder_imports.analyze(self.spec)
        (self.sources[0] / 'index.html').write_text('changed after preview')
        with self.assertRaisesRegex(ValueError, '重新预检'):
            self.app.folder_imports.start({**self.spec, 'preflight_fingerprint': preview['fingerprint']})
        self.assertEqual(self.app.projects.summaries(), [])
        self.assertFalse(self.app.projects.folders.path.exists())

    def test_low_capacity_stops_before_source_hashing_or_project_registration(self):
        with patch('reprise.import_preflight.shutil.disk_usage', return_value=shutil._ntuple_diskusage(100, 99, 1)), \
                patch('reprise.folder_imports.source_state', side_effect=AssertionError('Must not read bodies')):
            with self.assertRaisesRegex(ValueError, '规划预算'):
                self.app.folder_imports.start(self.spec)
        self.assertEqual(self.app.projects.summaries(), [])
        self.assertFalse(self.app.recovery.directory.exists())

    def test_queue_time_change_keeps_failure_report_and_creates_no_snapshot(self):
        captured = []
        with patch.object(self.app.jobs, 'submit', side_effect=lambda project, operation, callback, **kw: captured.append(callback)):
            self.app.folder_imports.start(self.spec)
        (self.sources[1] / 'index.html').write_text('changed while queued')
        with self.assertRaisesRegex(ValueError, '排队期间'):
            captured[0](None)
        project = self.app.projects.summaries()[0]['id']
        self.assertEqual(self.app.projects.repository(project).history()['commits'], [])
        self.assertFalse(self.app.recovery.directory.exists())
        report = json.loads(next((self.root / 'data/folder-imports').glob('*/report.json')).read_text())
        self.assertEqual(report['status'], 'incomplete')
        self.assertEqual(report['versions'], [])
        self.assertTrue(all(p.is_dir() for p in self.sources))

    def test_restored_preview_cannot_inherit_capacity_clearance(self):
        from reprise.backup import _transform
        before = self.app.folder_imports.analyze(self.spec)
        result = _transform('jobs/example.json', {'operation': 'folder-import-preflight',
            'result': before, 'request': {'input': self.spec}, 'status': 'complete'},
            self.root / 'data', self.root / 'new-data')['result']
        self.assertFalse(result['capacity_available'])
        self.assertTrue(result['restored_historical_report'])
        self.assertIsNone(result['filesystem_free_bytes'])
        self.assertEqual(result['data_directory'], str(self.root / 'new-data'))

    def test_oversized_folder_is_rejected_by_preview_before_save(self):
        with patch('reprise.import_preflight.MAX_ENTRIES', 1):
            with self.assertRaisesRegex(ValueError, '上限'):
                self.app.folder_imports.analyze(self.spec)
        self.assertFalse(self.app.projects.folders.path.exists())

    def test_change_during_source_hashing_does_not_establish_a_new_baseline(self):
        import reprise.folder_imports as imports
        captured = []
        with patch.object(self.app.jobs, 'submit', side_effect=lambda project, operation, callback, **kw: captured.append(callback)):
            self.app.folder_imports.start(self.spec)
        real_state = imports.source_state
        changed = False
        def mutate_then_scan(*args, **kwargs):
            nonlocal changed
            if not changed:
                (self.sources[0] / 'index.html').write_bytes(b'late build' * 10000)
                changed = True
            return real_state(*args, **kwargs)
        with patch.object(imports, 'source_state', side_effect=mutate_then_scan):
            with self.assertRaisesRegex(ValueError, '正文期间'):
                captured[0](None)
        project = self.app.projects.summaries()[0]['id']
        self.assertEqual(self.app.projects.repository(project).history()['commits'], [])

    def test_change_at_snapshot_start_is_rejected_before_publication(self):
        captured = []
        with patch.object(self.app.jobs, 'submit', side_effect=lambda project, operation, callback, **kw: captured.append(callback)):
            self.app.folder_imports.start(self.spec)
        original = self.app.projects.folders.snapshot
        def mutate_then_save(*args, **kwargs):
            (self.sources[0] / 'index.html').write_bytes(b'new build after body scan')
            return original(*args, **kwargs)
        with patch.object(self.app.projects.folders, 'snapshot', side_effect=mutate_then_save):
            with self.assertRaisesRegex(ValueError, '未发布快照'):
                captured[0](None)
        project = self.app.projects.summaries()[0]['id']
        self.assertEqual(self.app.projects.repository(project).history()['commits'], [])

    def test_nested_device_is_rejected_without_an_import(self):
        target = self.sources[0] / 'asset.bin'
        original = Path.lstat
        class DeviceView:
            def __init__(self, actual):
                self.actual, self.st_dev = actual, actual.st_dev + 50000
            def __getattr__(self, name):
                return getattr(self.actual, name)
        def nested_device(path, *args, **kwargs):
            actual = original(path, *args, **kwargs)
            return DeviceView(actual) if path == target else actual
        with patch.object(Path, 'lstat', nested_device):
            with self.assertRaisesRegex(ValueError, '跨设备'):
                self.app.folder_imports.analyze(self.spec)
        self.assertEqual(self.app.projects.summaries(), [])

    def test_capacity_is_rechecked_at_publication_after_object_writes(self):
        captured = []
        with patch.object(self.app.jobs, 'submit', side_effect=lambda project, operation, callback, **kw: captured.append(callback)):
            self.app.folder_imports.start(self.spec)
        original_blob = self.app.projects.folders.blob
        original_usage = shutil.disk_usage
        wrote = False
        def blob(*args, **kwargs):
            nonlocal wrote
            value = original_blob(*args, **kwargs)
            wrote = True
            return value
        def usage(path):
            return shutil._ntuple_diskusage(100, 99, 1) if wrote else original_usage(path)
        with patch.object(self.app.projects.folders, 'blob', side_effect=blob), \
                patch('reprise.folder_imports.shutil.disk_usage', side_effect=usage):
            with self.assertRaisesRegex(ValueError, '发布前容量'):
                captured[0](None)
        project = self.app.projects.summaries()[0]['id']
        self.assertEqual(self.app.projects.repository(project).history()['commits'], [])

