"""Data accounting stays read-only and confined to the selected local tree."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from reprise.cancellation import Cancelled
from reprise.storage_report import storage_report
from test_runtime import fixture


def by_key(report):
    return {item['key']: item for item in report['categories']}


class StorageReportTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('storage-report')
        self.data = self.root / 'state'
        self.data.mkdir()

    def test_categories_are_disjoint_and_only_file_metadata_is_read(self):
        payloads = {'content/objects.git/blob': b'content',
                    'recoveries/id/snapshot/a': b'restored',
                    'runtimes/id/worktree/a': b'runtime',
                    'evidence/id/a.png': b'media',
                    'jobs/job.json': b'not-json',
                    'projects.json': b'not-read',
                    'unknown/note': b'other'}
        expected_allocated = 0
        for name, value in payloads.items():
            path = self.data / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
            expected_allocated += path.stat().st_blocks * 512
        # Contents may be malformed, unreadable, or contain source references;
        # neither Python file APIs nor a content read is needed for accounting.
        with patch('builtins.open', side_effect=AssertionError('body read')), \
                patch.object(Path, 'open', side_effect=AssertionError('body read')):
            report = storage_report(self.data)
        self.assertEqual(report['schema'], 1)
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(report['storage_path'], str(self.data))
        self.assertEqual(report['files'], len(payloads))
        self.assertEqual(report['logical_bytes'], sum(map(len, payloads.values())))
        self.assertEqual(report['allocated_bytes'], expected_allocated)
        self.assertEqual(report['hardlink_aliases'], 0)
        self.assertIsNone(report['reclaimable_bytes'])
        self.assertGreater(report['filesystem_free_bytes'], 0)
        self.assertEqual(report['warnings'], [])
        categories = by_key(report)
        self.assertEqual(categories['state']['files'], 2)
        self.assertEqual(categories['recoveries']['logical_bytes'], len(b'restored'))
        for field in ('files', 'directories', 'symlinks', 'logical_bytes', 'allocated_bytes'):
            self.assertEqual(report[field], sum(item[field] for item in categories.values()))
        json.dumps(report)

    def test_hard_links_count_paths_but_not_bytes_twice_across_categories(self):
        # Create the lower-priority category first to exercise reassignment.
        (self.data / 'runtimes').mkdir()
        first = self.data / 'runtimes/shared'
        first.write_bytes(b'one physical inode')
        (self.data / 'content').mkdir()
        os.link(first, self.data / 'content/same')
        os.link(first, self.data / 'content/also-same')
        report = storage_report(self.data)
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(report['files'], 3)
        self.assertEqual(report['hardlink_aliases'], 2)
        self.assertEqual(report['logical_bytes'], first.stat().st_size)
        self.assertEqual(report['allocated_bytes'], first.stat().st_blocks * 512)
        categories = by_key(report)
        self.assertEqual(categories['content']['logical_bytes'], first.stat().st_size)
        self.assertEqual(categories['runtimes']['logical_bytes'], 0)

    def test_symlinks_and_source_registration_do_not_scan_external_files(self):
        external = self.root / 'private-source'
        external.mkdir()
        (external / 'private-body').write_bytes(b'outside' * 10000)
        (self.data / 'source-link').symlink_to(external, target_is_directory=True)
        (self.data / 'file-link').symlink_to(external / 'private-body')
        (self.data / 'missing-link').symlink_to(external / 'missing')
        registration = json.dumps({'projects': [{'path': str(external)}]}).encode()
        (self.data / 'projects.json').write_bytes(registration)
        actual_stat = os.stat

        def guarded_stat(path, *args, **kwargs):
            if isinstance(path, (str, Path)) and str(external) in str(path):
                raise AssertionError('external path was scanned')
            return actual_stat(path, *args, **kwargs)

        with patch('reprise.storage_report.os.stat', side_effect=guarded_stat):
            report = storage_report(self.data)
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(report['symlinks'], 3)
        self.assertEqual(report['files'], 1)
        self.assertEqual(report['logical_bytes'], len(registration))
        self.assertEqual(report['directories'], 0)

    def test_missing_root_is_partial_and_does_not_create_data(self):
        missing = self.root / 'absent' / 'data'
        report = storage_report(missing)
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(report['logical_bytes'], 0)
        self.assertIsNone(report['filesystem_free_bytes'])
        self.assertEqual(report['warnings'][0]['code'], 'missing_directory')
        self.assertFalse(missing.parent.exists())

    def test_root_symlink_is_rejected_and_non_directory_is_rejected(self):
        link = self.root / 'linked-state'
        link.symlink_to(self.data, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, '符号链接'):
            storage_report(link)
        plain = self.root / 'plain'
        plain.write_bytes(b'file')
        with self.assertRaisesRegex(ValueError, '必须是目录'):
            storage_report(plain)

    def test_unreadable_entries_are_aggregated_without_exposing_path_list(self):
        for name in ('sensitive-one', 'sensitive-two', 'good'):
            (self.data / name).write_bytes(b'abc')
        actual_stat = os.stat

        def fail_private(path, *args, **kwargs):
            if path in ('sensitive-one', 'sensitive-two'):
                raise PermissionError('private detail must not leak')
            return actual_stat(path, *args, **kwargs)

        with patch('reprise.storage_report.os.stat', side_effect=fail_private):
            report = storage_report(self.data)
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(report['files'], 1)
        self.assertEqual(report['logical_bytes'], 3)
        warning = next(item for item in report['warnings'] if item['code'] == 'metadata_unreadable')
        self.assertEqual(warning['count'], 2)
        self.assertNotIn('sensitive', json.dumps(report))
        self.assertNotIn('private detail', json.dumps(report))

    def test_unreadable_directory_does_not_prevent_other_category_accounting(self):
        (self.data / 'content').mkdir()
        (self.data / 'content/hidden').write_bytes(b'uncounted')
        (self.data / 'evidence').mkdir()
        (self.data / 'evidence/known').write_bytes(b'counted')
        blocked_inode = (self.data / 'content').stat().st_ino
        actual_scandir = os.scandir

        def fail_directory(fd):
            if os.fstat(fd).st_ino == blocked_inode:
                raise PermissionError('unreadable content')
            return actual_scandir(fd)

        with patch('reprise.storage_report.os.scandir', side_effect=fail_directory):
            report = storage_report(self.data)
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(report['logical_bytes'], len(b'counted'))
        self.assertEqual(by_key(report)['content']['files'], 0)
        self.assertEqual(by_key(report)['evidence']['files'], 1)
        self.assertEqual(report['directories'], 2)

    def test_directory_replaced_by_symlink_during_scan_cannot_escape(self):
        original = self.data / 'content'
        original.mkdir()
        (original / 'local').write_bytes(b'local')
        external = self.root / 'external'
        external.mkdir()
        (external / 'secret').write_bytes(b'never read')
        actual_open = os.open
        replaced = False

        def replace_before_open(path, flags, *args, **kwargs):
            nonlocal replaced
            if path == 'content' and not replaced:
                replaced = True
                original.rename(self.root / 'retained-original')
                original.symlink_to(external, target_is_directory=True)
            return actual_open(path, flags, *args, **kwargs)

        with patch('reprise.storage_report.os.open', side_effect=replace_before_open):
            report = storage_report(self.data)
        self.assertTrue(replaced)
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(report['files'], 0)
        self.assertEqual(report['logical_bytes'], 0)
        self.assertEqual((external / 'secret').read_bytes(), b'never read')

    def test_nested_different_device_is_skipped(self):
        (self.data / 'mounted').mkdir()
        (self.data / 'mounted/secret').write_bytes(b'outside')
        actual_stat = os.stat

        def other_device(path, *args, **kwargs):
            value = actual_stat(path, *args, **kwargs)
            if path == 'mounted':
                return SimpleNamespace(st_mode=value.st_mode, st_dev=value.st_dev + 1,
                                       st_ino=value.st_ino)
            return value

        with patch('reprise.storage_report.os.stat', side_effect=other_device):
            report = storage_report(self.data)
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(report['directories'], 1)
        self.assertEqual(report['files'], 0)
        self.assertEqual(report['warnings'][0]['code'], 'nested_mount_skipped')

    def test_missing_allocation_remains_unknown_without_losing_logical_accounting(self):
        path = self.data / 'content'
        path.write_bytes(b'content')
        actual_stat = os.stat

        def without_blocks(name, *args, **kwargs):
            value = actual_stat(name, *args, **kwargs)
            if name == 'content':
                return SimpleNamespace(st_mode=value.st_mode, st_dev=value.st_dev,
                                       st_ino=value.st_ino, st_nlink=value.st_nlink,
                                       st_size=value.st_size)
            return value

        with patch('reprise.storage_report.os.stat', side_effect=without_blocks):
            report = storage_report(self.data)
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(report['logical_bytes'], len(b'content'))
        self.assertIsNone(report['allocated_bytes'])
        self.assertIsNone(by_key(report)['content']['allocated_bytes'])
        self.assertEqual(report['warnings'][0]['code'], 'allocation_unavailable')

    def test_depth_and_hardlink_limits_return_partial_instead_of_unbounded_state(self):
        (self.data / 'content').mkdir()
        (self.data / 'content/a').write_bytes(b'content')
        with patch('reprise.storage_report._MAX_DEPTH', 1):
            report = storage_report(self.data)
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(report['files'], 0)
        self.assertEqual(report['warnings'][0]['code'], 'depth_limit_reached')
        os.link(self.data / 'content/a', self.data / 'content/alias')
        with patch('reprise.storage_report._MAX_LINK_IDENTITIES', 0):
            report = storage_report(self.data)
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(report['logical_bytes'], 0)
        self.assertEqual(report['warnings'][0]['code'], 'hardlink_limit_reached')

    def test_mounted_file_from_another_device_is_not_charged_to_root_volume(self):
        (self.data / 'mounted-file').write_bytes(b'outside')
        actual_stat = os.stat

        def other_device(path, *args, **kwargs):
            value = actual_stat(path, *args, **kwargs)
            return SimpleNamespace(st_mode=value.st_mode, st_dev=value.st_dev + 1)

        with patch('reprise.storage_report.os.stat', side_effect=other_device):
            report = storage_report(self.data)
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(report['files'], 1)
        self.assertEqual(report['logical_bytes'], 0)
        self.assertEqual(report['warnings'][0]['code'], 'nested_mount_skipped')

    def test_cancellation_propagates_and_directory_descriptors_are_closed(self):
        (self.data / 'content').mkdir()
        (self.data / 'content/a').write_bytes(b'data')
        opened = []
        actual_open = os.open

        def tracked_open(*args, **kwargs):
            fd = actual_open(*args, **kwargs)
            opened.append(fd)
            return fd

        class Cancel:
            def check(self):
                if len(opened) >= 2:
                    raise Cancelled()

        with patch('reprise.storage_report.os.open', side_effect=tracked_open):
            with self.assertRaises(Cancelled):
                storage_report(self.data, cancel=Cancel())
        self.assertEqual(len(opened), 2)
        for fd in opened:
            with self.assertRaises(OSError):
                os.fstat(fd)


if __name__ == '__main__':
    unittest.main()
