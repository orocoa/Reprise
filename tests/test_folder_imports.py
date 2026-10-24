"""Synthetic originals are always retained; no deletion executor is invoked."""
import hashlib
import io
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch
import zipfile

from reprise.folder_imports import zip_members
from reprise.service import Reprise
from test_runtime import fixture


class FolderImportTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('folder-import')
        self.folders = []
        self.common = bytes(range(256)) * 128
        for index in range(3):
            path = self.root / ('draft-' + str(index + 1))
            path.mkdir()
            (path / 'asset.bin').write_bytes(self.common)
            (path / 'index.html').write_text('<h1>Draft %s</h1>' % index)
            (path / 'empty').mkdir()
            self.folders.append(path)
        self.app = Reprise(self.root / 'data')
        self.usage = patch('reprise.folder_imports.in_use', return_value='not-observed')
        self.usage.start()

    def tearDown(self):
        self.usage.stop()
        self.app.close()

    def spec(self):
        return {'name': 'Explicit version collection', 'versions': [
            {'path': str(path), 'title': 'Version %s' % (i + 1)} for i, path in enumerate(self.folders)]}

    def wait(self, job, status='complete'):
        deadline = time.monotonic() + 30
        while job['status'] in ('queued', 'running', 'cancelling') and time.monotonic() < deadline:
            time.sleep(.03)
            job = self.app.jobs.get(job['id'])
        self.assertEqual(job['status'], status, job)
        return job

    def run_import(self, spec=None):
        return self.wait(self.app.folder_imports.start(spec or self.spec()))['result']

    def test_one_project_order_dedup_restore_and_cost_accounting(self):
        originals = {str(p): ((p / 'index.html').read_bytes(), (p / 'index.html').stat().st_mtime_ns) for p in self.folders}
        report = self.run_import()
        self.assertEqual(len(report['versions']), 3)
        self.assertEqual([v['removal_candidate'] for v in report['versions']], [True, True, False])
        repository = self.app.projects.repository(report['project_id'])
        objects = []
        for i, version in enumerate(report['versions']):
            manifest = repository.manifest(version['sha'])
            self.assertEqual(manifest['origin']['position'], i + 1)
            self.assertEqual(manifest['source'], str(self.folders[i]))
            self.assertTrue(all('xattrs' in e for e in manifest['entries'].values()))
            self.assertEqual((Path(version['recovery_path']) / 'index.html').read_bytes(), originals[str(self.folders[i])][0])
            objects.append(manifest['entries']['asset.bin']['oid'])
            self.assertTrue(version['verification']['readback_verified'])
        self.assertEqual(len(set(objects)), 1)
        self.assertLess(report['versions'][1]['stats']['new_bytes'], len(self.common))
        self.assertEqual(self.app.projects.record(report['project_id'])['path'], str(self.folders[-1]))
        self.assertGreater(report['recovery_file_bytes'], report['candidate_logical_bytes'])
        self.assertIsNone(report['physical_free_delta_estimate_bytes'])
        self.assertFalse(report['originals_removed'])
        for p in self.folders:
            self.assertEqual(((p / 'index.html').read_bytes(), (p / 'index.html').stat().st_mtime_ns), originals[str(p)])

    def test_changed_original_and_in_use_original_are_removed_from_candidates(self):
        report = self.run_import()
        (self.folders[0] / 'index.html').write_text('new unsaved content')
        with patch('reprise.folder_imports.in_use', return_value='in-use'):
            updated = self.app.folder_imports.review(report['id'])
        self.assertTrue(all(not v['removal_candidate'] for v in updated['versions']))
        self.assertEqual(updated['candidate_allocated_bytes'], 0)
        self.assertTrue(any('变化' in b for b in updated['versions'][0]['blockers']))
        self.assertTrue(Path(updated['review_receipt']).is_file())
        self.assertTrue(self.app.folder_imports.get(report['id'])['versions'][0]['removal_candidate'])

    def test_review_does_not_combine_original_and_cost_allocation_across_volumes(self):
        from types import SimpleNamespace
        report = self.run_import()
        data_device = self.app.directory.stat().st_dev
        other_volume = SimpleNamespace(stat=lambda: SimpleNamespace(st_dev=data_device + 1))
        with patch.object(self.app, 'directory', other_volume):
            reviewed = self.app.folder_imports.review(report['id'])
        self.assertTrue(reviewed['versions'][0]['removal_candidate'])
        self.assertFalse(reviewed['candidate_costs_share_data_volume'])
        self.assertIsNone(reviewed['modeled_net_after_source_removal_bytes'])
        self.assertIsNone(reviewed['conditional_net_if_readbacks_also_removed_bytes'])

    def test_nested_git_and_hardlinks_block_whole_original_directory(self):
        (self.folders[0] / '.git').mkdir()
        os.link(self.folders[1] / 'asset.bin', self.root / 'outside-hardlink.bin')
        report = self.run_import()
        self.assertFalse(report['versions'][0]['removal_candidate'])
        self.assertFalse(report['versions'][1]['removal_candidate'])
        self.assertTrue((self.folders[0] / '.git').is_dir())

    def test_nested_or_existing_current_project_rejected_without_new_history(self):
        spec = self.spec()
        spec['versions'][0]['path'] = str(self.root)
        with self.assertRaises(ValueError):
            self.app.folder_imports.start(spec)
        self.assertEqual(self.app.projects.summaries(), [])
        self.app.projects.add(str(self.folders[-1]), kind='folder')
        with self.assertRaises(ValueError):
            self.app.folder_imports.start(self.spec())

    def test_explicit_existing_project_appends_without_rewriting_earlier_history(self):
        project = self.app.projects.add(str(self.folders[-1]), kind='folder')
        previous = self.app.projects.snapshot(project['id'], 'Already saved')
        spec = self.spec()
        spec['project_id'] = project['id']
        report = self.run_import(spec)
        repository = self.app.projects.repository(project['id'])
        self.assertEqual(report['project_id'], project['id'])
        self.assertEqual(repository.resolve(previous['sha']), previous['sha'])
        history = repository.history()['commits']
        self.assertEqual(len(history), 4)
        self.assertEqual(history[-1]['sha'], previous['sha'])
        self.assertEqual(history[-1]['parents'], [])

    def test_distinct_zip_bytes_share_internal_file_content(self):
        spec = self.spec()
        archives = []
        for i, folder in enumerate(self.folders[:2]):
            archive_path = self.root / ('release-%s.zip' % i)
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.comment = ('Different release envelope %s' % i).encode()
                archive.writestr('asset.bin', self.common)
                archive.writestr('index.html', (folder / 'index.html').read_bytes())
                archive.writestr('empty/', b'')
            archives.append(archive_path)
            spec['versions'][i] = {'path': str(archive_path), 'title': 'Release %s' % i, 'zip_mode': 'contents'}
        before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in archives]
        report = self.run_import(spec)
        repository = self.app.projects.repository(report['project_id'])
        blobs = [repository.manifest(v['sha'])['entries']['asset.bin']['oid'] for v in report['versions']]
        self.assertEqual(len(set(blobs)), 1)
        for version in report['versions'][:2]:
            manifest = repository.manifest(version['sha'])
            origin = manifest['origin']
            self.assertFalse(origin['byte_identical_zip_recoverable'])
            self.assertEqual(origin['zip_mode'], 'contents')
            self.assertTrue(all('xattrs' not in e for e in manifest['entries'].values()))
            self.assertFalse(version['verification']['extended_attributes_verified'])
        self.assertEqual(before, [hashlib.sha256(p.read_bytes()).hexdigest() for p in archives])
        del spec['versions'][0]['zip_mode']
        with self.assertRaises(ValueError):
            self.app.folder_imports.validate(spec)

    def test_hostile_zip_paths_duplicates_and_links_never_extract(self):
        for names in ([('../escape', b'x')], [('a', b'x'), ('a/b', b'y')], [('A.txt', b'x'), ('a.txt', b'y')]):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as archive:
                for name, content in names:
                    archive.writestr(name, content)
            stream.seek(0)
            with zipfile.ZipFile(stream) as archive, self.assertRaises(ValueError):
                zip_members(archive)
        self.assertFalse((self.root.parent / 'escape').exists())

    def test_failed_readback_never_returns_removal_candidates(self):
        with patch('reprise.folder_imports.verify_restore', side_effect=ValueError('Synthetic restore failure')):
            job = self.wait(self.app.folder_imports.start(self.spec()), 'failed')
        reports = list((self.root / 'data/folder-imports').glob('*/report.json'))
        report = json.loads(reports[0].read_text())
        self.assertEqual(report['status'], 'incomplete')
        self.assertFalse(any(v.get('removal_candidate') for v in report['versions']))
        self.assertTrue(all(p.is_dir() for p in self.folders))

    def test_restored_reports_have_rebased_evidence_and_no_inherited_candidate_verdict(self):
        from reprise.backup import create_backup, restore_backup
        from reprise.projects import ProjectStore
        report = self.run_import()
        self.app.close()
        backup, target = self.root / 'backup', self.root / 'restored-data'
        create_backup(self.root / 'data', backup)
        restore_backup(backup, target)
        restored = json.loads((target / 'folder-imports' / report['id'] / 'report.json').read_text())
        self.assertEqual(restored['status'], 'restored-review-required')
        self.assertTrue(all(not v['removal_candidate'] for v in restored['versions']))
        for v in restored['versions']:
            self.assertTrue(Path(v['recovery_path']).is_relative_to(target))
            self.assertTrue(Path(v['recovery_path']).is_dir())
        for job_path in (target / 'jobs').glob('*.json'):
            job = json.loads(job_path.read_text())
            if job['operation'] == 'import-folders':
                self.assertEqual(job['result']['status'], 'restored-review-required')
                self.assertFalse(job['result']['versions'][0]['removal_candidate'])
