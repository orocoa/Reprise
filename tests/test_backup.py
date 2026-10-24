import fcntl
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from reprise import backup
from reprise.backup import BackupError, create_backup, restore_backup, verify_backup
from reprise.cancellation import Cancelled
from reprise.maintenance import DataLease, DataLeaseError
from reprise.metadata import xattrs
from reprise.projects import ProjectStore
from reprise.relocation import restore_xattrs_fd
from reprise.storage import write_json
from test_runtime import fixture


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('backup')
        self.data = self.root / 'data'
        self.data.mkdir(mode=0o700)
        self.source = self.root / 'original-documents'
        self.source.mkdir()
        (self.source / 'draft.txt').write_text('first draft')
        (self.source / 'empty').mkdir()
        (self.source / 'alias').symlink_to('draft.txt')
        self.projects = ProjectStore(self.data)
        self.record = self.projects.add(str(self.source), kind='folder')
        self.identifier = self.record['id']
        self.first = self.projects.snapshot(self.identifier, 'First')
        (self.source / 'draft.txt').write_text('second draft')
        self.second = self.projects.snapshot(self.identifier, 'Second')
        (self.data / 'empty-managed').mkdir()
        (self.data / 'managed-link').symlink_to('projects.json')
        self.destination = self.root / 'independent-backup'

    def save(self):
        return create_backup(self.data, self.destination)

    def test_backup_verify_restore_without_original_data_or_folder(self):
        path = self.data / 'private.txt'
        path.write_text('managed private bytes')
        path.chmod(0o640)
        os.utime(path, ns=(1500000000000000000, 1500000000000000000))
        with path.open('rb') as stream:
            attributes = xattrs(path)
            attributes['com.reprise.backup-test' if __import__('sys').platform == 'darwin' else 'user.reprise-backup-test'] = 'bWV0YWRhdGE='
            restore_xattrs_fd(stream.fileno(), attributes)
        expected_xattrs = xattrs(path)
        saved = self.save()
        self.assertEqual(saved['status'], 'complete')
        self.assertTrue(saved['readback_verified'])
        self.assertEqual(saved['device_relation'], 'same-device')
        self.assertFalse(saved['independent_physical_device_confirmed'])
        self.assertEqual(saved['external_dependencies']['counts']['folder_source'], 1)
        self.assertEqual(self.destination.stat().st_mode & 0o777, 0o700)
        self.assertFalse((self.destination / 'payload' / '.data-lease.lock').exists())
        self.assertEqual(verify_backup(self.destination)['status'], 'verified')
        self.data.rename(self.root / 'original-data-unavailable')
        self.source.rename(self.root / 'original-source-unavailable')
        target = self.root / 'restored-data'
        restored = restore_backup(self.destination, target)
        self.assertEqual(restored['status'], 'complete')
        self.assertTrue(Path(restored['receipt_path']).is_file())
        self.assertTrue((target / 'empty-managed').is_dir())
        self.assertEqual(os.readlink(target / 'managed-link'), 'projects.json')
        self.assertEqual((target / 'private.txt').read_text(), 'managed private bytes')
        self.assertEqual((target / 'private.txt').stat().st_mode & 0o777, 0o640)
        self.assertEqual((target / 'private.txt').stat().st_mtime_ns, 1500000000000000000)
        self.assertEqual(xattrs(target / 'private.txt'), expected_xattrs)
        projects = ProjectStore(target)
        repository = projects.repository(self.identifier)
        self.assertEqual(repository.resolve('HEAD'), self.second['sha'])
        self.assertEqual(len(repository.history()['commits']), 2)
        first = self.root / 'recovered-first'
        repository.materialize(self.first['sha'], first)
        self.assertEqual((first / 'draft.txt').read_text(), 'first draft')
        self.assertTrue((first / 'empty').is_dir())
        self.assertEqual(os.readlink(first / 'alias'), 'draft.txt')
        self.assertEqual(verify_backup(self.destination)['status'], 'verified')
        # A restored library can itself be backed up and restored again.
        again = self.root / 'second-backup'
        create_backup(target, again)
        restore_backup(again, self.root / 'second-restored-data')

    def test_verify_detects_file_corruption_missing_and_manifest_changes(self):
        self.save()
        path = self.destination / 'payload/projects.json'
        original, before = path.read_bytes(), path.stat()
        changed = original.replace(b'folder', b'broken', 1)
        path.write_bytes(changed)
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaises(BackupError):
            verify_backup(self.destination)
        # Preserve the failed corruption as an artifact before resetting fixture bytes.
        (self.root / 'corrupt-projects.json').write_bytes(changed)
        path.write_bytes(original)
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        manifest = self.destination / 'manifest.jsonl'
        manifest.rename(self.root / 'retained-original-manifest.jsonl')
        with self.assertRaises(BackupError):
            verify_backup(self.destination)
        manifest.write_bytes((self.root / 'retained-original-manifest.jsonl').read_bytes() + b'{}\n')
        with self.assertRaisesRegex(BackupError, '清单摘要'):
            verify_backup(self.destination)

    def test_extra_paths_and_tampered_manifest_paths_are_rejected(self):
        self.save()
        (self.destination / 'payload/extra').write_text('unexpected')
        with self.assertRaises(BackupError):
            verify_backup(self.destination)
        (self.destination / 'payload/extra').rename(self.root / 'retained-extra')
        lines = (self.destination / 'manifest.jsonl').read_bytes().splitlines(True)
        root_entry = json.loads(lines[0])
        os.utime(self.destination / 'payload', ns=(root_entry['mtime_ns'], root_entry['mtime_ns']))
        entry = json.loads(lines[1])
        entry['path'] = '../outside'
        lines[1] = backup._encoded(entry)
        content = b''.join(lines)
        (self.destination / 'manifest.jsonl').write_bytes(content)
        receipt = json.loads((self.destination / 'receipt.json').read_text())
        receipt['manifest'].update(sha256=hashlib.sha256(content).hexdigest(), bytes=len(content))
        write_json(self.destination / 'receipt.json', receipt, private=True)
        with self.assertRaisesRegex(BackupError, '不安全路径'):
            verify_backup(self.destination)

    def test_copy_failure_keeps_partial_and_failed_receipt(self):
        with patch('reprise.backup._copy_file', side_effect=OSError('simulated disk failure')):
            with self.assertRaises(BackupError):
                self.save()
        self.assertTrue((self.destination / 'payload').is_dir())
        receipt = json.loads((self.destination / 'receipt.json').read_text())
        self.assertEqual(receipt['status'], 'failed')
        self.assertTrue((self.destination / 'manifest.jsonl').exists())
        with self.assertRaises(BackupError):
            verify_backup(self.destination)

    def test_low_space_refuses_before_copy_and_receipt_failure_preserves_primary_error(self):
        from types import SimpleNamespace
        with patch('reprise.backup.os.statvfs', return_value=SimpleNamespace(f_bavail=1, f_frsize=4096)):
            with self.assertRaisesRegex(BackupError, '空间不足'):
                self.save()
        self.assertFalse(self.destination.exists())
        real = backup._write_json
        def failing_receipt(path, value):
            if value.get('status') == 'failed':
                raise OSError('simulated receipt write full')
            return real(path, value)
        with patch('reprise.backup._copy_file', side_effect=OSError('primary copy failure')):
            with patch('reprise.backup._write_json', side_effect=failing_receipt):
                with self.assertRaisesRegex(BackupError, 'primary copy failure') as raised:
                    self.save()
        self.assertIn('receipt_error', raised.exception.report)
        self.assertEqual(json.loads((self.destination / 'receipt.json').read_text())['status'], 'running')
        with self.assertRaises(BackupError):
            verify_backup(self.destination)

    def test_source_change_during_copy_never_publishes_green(self):
        real = backup._copy_file
        changed = [False]
        def mutate(source, destination, entry, cancel):
            result = real(source, destination, entry, cancel)
            if not changed[0]:
                changed[0] = True
                (self.data / 'concurrent-state').write_text('old client mutation')
            return result
        with patch('reprise.backup._copy_file', side_effect=mutate):
            with self.assertRaisesRegex(BackupError, '变化'):
                self.save()
        self.assertEqual(json.loads((self.destination / 'receipt.json').read_text())['status'], 'failed')

    def test_destination_parent_link_swap_never_writes_external_file(self):
        folder = self.data / 'managed-dir'
        folder.mkdir()
        (folder / 'payload.txt').write_text('managed bytes')
        external = self.root / 'external-do-not-write'
        external.mkdir()
        real = backup._copy_file
        def swap(source, destination, entry, cancel):
            if source.name == 'payload.txt':
                destination.parent.rename(destination.parent.with_name('retained-managed-dir'))
                destination.parent.symlink_to(external, target_is_directory=True)
            return real(source, destination, entry, cancel)
        with patch('reprise.backup._copy_file', side_effect=swap):
            with self.assertRaises(BackupError):
                self.save()
        self.assertFalse((external / 'payload.txt').exists())
        self.assertEqual(json.loads((self.destination / 'receipt.json').read_text())['status'], 'failed')

    def test_missing_managed_object_is_not_an_independent_success(self):
        repository = self.projects.repository(self.identifier)
        oid = next(row['oid'] for row in repository.tree(self.second['sha']) if row['path'] == 'draft.txt')
        object_path = self.projects.folders.path / 'objects' / oid[:2] / oid[2:]
        object_path.rename(self.root / ('retained-missing-object-' + oid))
        with self.assertRaisesRegex(BackupError, '对象或引用不完整'):
            self.save()
        self.assertEqual(json.loads((self.destination / 'receipt.json').read_text())['status'], 'failed')

    def test_missing_entire_managed_store_is_not_reported_as_empty(self):
        (self.data / 'content').rename(self.root / 'retained-unavailable-content')
        with self.assertRaisesRegex(BackupError, '内容库缺失'):
            self.save()
        self.assertEqual(json.loads((self.destination / 'receipt.json').read_text())['status'], 'failed')

    def test_cancel_propagates_and_keeps_backup_and_restore_partials(self):
        with patch('reprise.backup._copy_file', side_effect=Cancelled):
            with self.assertRaises(Cancelled):
                self.save()
        self.assertEqual(json.loads((self.destination / 'receipt.json').read_text())['status'], 'cancelled')
        good = self.root / 'good-backup'
        create_backup(self.data, good)
        target = self.root / 'cancelled-restore'
        with patch('reprise.backup._copy_file', side_effect=Cancelled):
            with self.assertRaises(Cancelled):
                restore_backup(good, target)
        receipts = list(self.root.glob('cancelled-restore.restore-*/receipt.json'))
        self.assertEqual(len(receipts), 1)
        self.assertEqual(json.loads(receipts[0].read_text())['status'], 'cancelled')
        self.assertTrue(target.exists())

    def test_active_shared_lease_legacy_server_and_lock_symlinks_block(self):
        with DataLease(self.data):
            with self.assertRaises(BackupError):
                self.save()
        self.assertFalse(self.destination.exists())
        with (self.data / 'server.lock').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BackupError):
                self.save()
        self.assertFalse(self.destination.exists())
        (self.data / '.data-lease.lock').rename(self.root / 'retained-lease-lock')
        (self.data / '.data-lease.lock').symlink_to(self.root / 'should-not-be-created')
        with self.assertRaises(DataLeaseError):
            with DataLease(self.data):
                pass
        self.assertFalse((self.root / 'should-not-be-created').exists())
        missing = self.root / 'absent-data'
        with self.assertRaises(DataLeaseError):
            with DataLease(missing):
                pass
        self.assertFalse(missing.exists())

    def test_external_links_targets_and_content_alternates_are_rejected(self):
        (self.data / 'outside').symlink_to('../original-documents/draft.txt')
        with self.assertRaises(BackupError):
            self.save()
        self.assertFalse(self.destination.exists())
        (self.data / 'outside').rename(self.root / 'retained-outside-link')
        for target in (self.data / 'inside', self.source / 'inside', self.data):
            with self.subTest(target=target):
                with self.assertRaises(BackupError):
                    create_backup(self.data, target)
        info = self.data / 'content/objects.git/objects/info'
        info.mkdir(exist_ok=True)
        (info / 'alternates').write_text(str(self.root / 'external-objects'))
        with self.assertRaisesRegex(BackupError, '替代对象'):
            self.save()
        self.assertEqual(json.loads((self.destination / 'receipt.json').read_text())['status'], 'failed')

    def test_internal_evidence_migrates_paths_but_notes_and_user_json_stay_exact(self):
        evidence = self.data / 'evidence' / 'capture-1'
        evidence.mkdir(parents=True)
        (evidence / 'manual.png').write_bytes(b'actual preserved preview')
        note = 'Keep literal old path: ' + str(self.data / 'evidence/capture-1/manual.png')
        record = {'id': 'capture-1', 'project_id': self.identifier, 'sha': self.second['sha'],
                  'status': 'complete', 'items': [{'path': str(evidence / 'manual.png'), 'title': note}],
                  'runtimes': [{'path': str(self.data / 'runtimes/r1/source'), 'log_path': str(self.data / 'runtimes/r1/runtime.log')}],
                  'note': note}
        write_json(evidence / 'record.json', record)
        runtime = self.data / 'runtimes' / 'r1'
        runtime.mkdir(parents=True)
        write_json(runtime / 'runtime.json', {'id': 'r1', 'status': 'stopped', 'path': str(runtime / 'source'),
                                            'root': str(runtime / 'source'), 'log_path': str(runtime / 'runtime.log'),
                                            'pid': 99999999, 'process_identity': 'historical', 'owner_pid': 99999999,
                                            'owner_identity': 'historical', 'process_trees': ['process-old.json'], 'recipe': {'note': note}})
        write_json(runtime / 'process-old.json', {'schema': 1, 'root_pid': 99999999, 'root_identity': 'historical',
                                                'members': [{'pid': 99999999, 'identity': 'historical'}], 'owner_marker': 'old'})
        write_json(evidence / 'after-browser-process.json', {'pid': 99999999, 'process_identity': 'historical'})
        write_json(self.data / 'server.json', {'pid': 99999999, 'identity': 'historical', 'url': 'http://127.0.0.1:1', 'data_directory': str(self.data)})
        write_json(self.data / 'unrelated.json', {'path': str(self.data / 'user.txt'), 'note': note})
        recovery = self.data / 'recoveries' / 'recovery-1'
        recovery.mkdir(parents=True)
        write_json(recovery / 'receipt.json', {'path': str(recovery / 'snapshot'), 'note': note})
        organization = self.data / 'organization' / 'plan-1'
        organization.mkdir(parents=True)
        write_json(organization / 'plan.json', {'schema': 1, 'source': str(self.source), 'receipt': str(organization / 'plan.json'),
                                              'recovery_path': str(recovery / 'snapshot'), 'selected_paths': ['draft.txt'], 'selected_count': 1,
                                              'frozen_protections': [str(runtime)], 'note': note})
        self.save()
        target = self.root / 'migrated'
        restored = restore_backup(self.destination, target)
        value = json.loads((target / 'evidence/capture-1/record.json').read_text())
        self.assertEqual(value['items'][0]['path'], str(target / 'evidence/capture-1/manual.png'))
        self.assertEqual(value['items'][0]['title'], note)
        self.assertEqual(value['note'], note)
        self.assertEqual((target / 'unrelated.json').read_bytes(), (self.data / 'unrelated.json').read_bytes())
        state = json.loads((target / 'runtimes/r1/runtime.json').read_text())
        self.assertEqual(state['status'], 'interrupted')
        self.assertIsNone(state['pid'])
        self.assertEqual(state['process_trees'], [])
        self.assertEqual(state['recipe']['note'], note)
        tree = json.loads((target / 'runtimes/r1/process-old.json').read_text())
        self.assertIsNone(tree['root_pid'])
        self.assertEqual(tree['members'], [])
        self.assertIsNone(json.loads((target / 'server.json').read_text())['pid'])
        plan = json.loads((target / 'organization/plan-1/plan.json').read_text())
        self.assertEqual(plan['recovery_path'], str(target / 'recoveries/recovery-1/snapshot'))
        self.assertEqual(plan['selected_paths'], [])
        self.assertTrue(restored['process_authority_disabled'])
        self.assertEqual((self.destination / 'payload/evidence/capture-1/record.json').read_bytes(), (evidence / 'record.json').read_bytes())
        self.data.rename(self.root / 'original-evidence-data-unavailable')
        self.source.rename(self.root / 'original-evidence-source-unavailable')
        from reprise.service import Reprise
        app = Reprise(target)
        try:
            artifact = app.evidence.file('capture-1/manual.png')
            self.assertEqual(artifact.read_bytes(), b'actual preserved preview')
            self.assertEqual(app.projects.repository(self.identifier).blob(self.second['sha'], 'draft.txt'), b'second draft')
        finally:
            app.close()

    def test_live_registered_preview_is_refused_after_service_exit(self):
        from reprise.processes import process_identity
        folder = self.data / 'runtimes' / 'live'
        folder.mkdir(parents=True)
        write_json(folder / 'runtime.json', {'status': 'running', 'pid': os.getpid(),
                                            'process_identity': process_identity(os.getpid())})
        with self.assertRaisesRegex(BackupError, '仍有已登记'):
            self.save()
        self.assertFalse(self.destination.exists())

    def test_unknown_live_runtime_or_job_identity_is_not_treated_as_offline(self):
        runtime = self.data / 'runtimes' / 'unknown' / 'runtime.json'
        write_json(runtime, {'status': 'running', 'pid': os.getpid(), 'process_identity': None})
        actual_kill = os.kill
        with patch('reprise.backup.os.kill', wraps=actual_kill) as observer:
            with self.assertRaisesRegex(BackupError, '无法核验'):
                self.save()
            self.assertIn((os.getpid(), 0), [call.args for call in observer.call_args_list])
            self.assertTrue(all(call.args[1] == 0 for call in observer.call_args_list))
        self.assertFalse(self.destination.exists())
        write_json(runtime, {'status': 'running', 'pid': None, 'process_identity': None})
        with self.assertRaisesRegex(BackupError, '缺少可核验'):
            self.save()
        runtime.rename(self.root / 'retained-unknown-runtime.json')
        write_json(self.data / 'jobs' / ('a' * 24 + '.json'),
                   {'id': 'a' * 24, 'status': 'running', 'owner_pid': os.getpid(), 'owner_identity': None})
        with self.assertRaisesRegex(BackupError, '无法核验'):
            self.save()
        self.assertFalse(self.destination.exists())

    def test_unknown_identity_only_proven_missing_pid_is_dead(self):
        with patch('reprise.backup.os.kill', side_effect=ProcessLookupError):
            self.assertFalse(backup._alive(99999999, None))
        with patch('reprise.backup.os.kill', side_effect=PermissionError):
            with self.assertRaisesRegex(ValueError, '无法核验'):
                backup._alive(99999999, None)
        with patch('reprise.processes.process_identity', return_value=None):
            with self.assertRaisesRegex(ValueError, '无法核验'):
                backup._alive(os.getpid(), 'unverifiable-identity')

    def test_restore_destination_inside_backup_or_source_is_rejected(self):
        self.save()
        for path in (self.destination / 'new-data', self.source / 'new-data', self.data / 'new-data'):
            with self.subTest(path=path):
                with self.assertRaises(BackupError):
                    restore_backup(self.destination, path)
                self.assertFalse(path.exists())

    def test_internal_legacy_archive_registry_is_relocated_and_stays_usable(self):
        from test_content_workflow import archive_fixture
        source, group, sha, view_sha = archive_fixture(self.data / 'legacy', self.data)
        saved = self.save()
        self.assertEqual(saved['external_dependencies']['counts']['archive_repository'], 0)
        self.assertEqual(saved['external_dependencies']['counts']['archive_view'], 0)
        self.data.rename(self.root / 'legacy-original-data-unavailable')
        restored_data = self.root / 'legacy-restored-data'
        restored = restore_backup(self.destination, restored_data)
        self.assertEqual(restored['external_dependencies']['counts']['archive_repository'], 0)
        projects = ProjectStore(restored_data)
        project = projects.record(projects.identify('Archive alias'))
        self.assertEqual(project['kind'], 'archive')
        repository = projects.repository(project['id'])
        self.assertEqual(repository.blob(view_sha, 'notes.txt'), b'original archived content')
        output = self.root / 'recovered-legacy-archive'
        report = repository.materialize(view_sha, output)
        self.assertEqual(report['archive_sha'], sha)
        self.assertEqual((output / 'notes.txt').read_bytes(), b'original archived content')
        self.assertTrue((output / '.git/config').is_file())

    def test_completed_export_job_and_nested_recovery_paths_follow_restored_library(self):
        from reprise.service import Reprise
        import time
        app = Reprise(self.data)
        try:
            job = app.execute(self.identifier, 'export', {'sha': self.second['sha']})
            deadline = time.monotonic() + 20
            while app.jobs.get(job['id'])['status'] in ('queued', 'running') and time.monotonic() < deadline:
                time.sleep(.02)
            finished = app.jobs.get(job['id'])
            self.assertEqual(finished['status'], 'complete')
        finally:
            app.close()

        self.save()
        self.data.rename(self.root / 'export-original-data-unavailable')
        self.source.rename(self.root / 'export-original-source-unavailable')
        target = self.root / 'restored-export-data'
        restore_backup(self.destination, target)
        app = Reprise(target)
        try:
            restored_job = app.jobs.get(job['id'])
            result = restored_job['result']
            self.assertTrue(Path(result['path']).is_file())
            self.assertTrue(Path(result['report']['path']).is_dir())
            self.assertTrue(str(result['path']).startswith(str(target) + '/'))
            receipt = json.loads((target / 'recoveries' / result['id'] / 'receipt.json').read_text())
            self.assertEqual(receipt['path'], result['path'])
            self.assertEqual(receipt['report']['path'], result['report']['path'])
            self.assertEqual(app.recovery.download(result['id']), Path(result['path']))
        finally:
            app.close()

    def test_known_job_schemas_migrate_locations_and_preserve_historical_statistics(self):
        note = 'User note must retain ' + str(self.data / 'runtimes/r1/source')
        cases = {
            'run': {'status': 'stopped', 'path': str(self.data / 'runtimes/r1/source'), 'log_path': str(self.data / 'runtimes/r1/runtime.log'),
                    'pid': 99999999, 'process_identity': 'old', 'recipe': {'note': note}},
            'capture': {'status': 'complete', 'items': [{'path': str(self.data / 'evidence/e1/screen.png'), 'title': note}],
                        'runtimes': [{'path': str(self.data / 'runtimes/r1/source'), 'log_path': str(self.data / 'runtimes/r1/runtime.log')}], 'note': note},
            'organize': {'receipt': str(self.data / 'organization/p1/plan.json'), 'selected_count': 3, 'note': note},
            'storage': {'storage_path': str(self.data), 'logical_bytes': 12345, 'note': note},
            'migrate': {'source': str(self.source), 'target': str(self.root / 'external-destination'), 'receipt_path': str(self.data / 'relocations/m1.json')},
            'custom-unknown': {'path': str(self.data / 'must-stay-original'), 'note': note},
        }
        jobs = self.data / 'jobs'
        jobs.mkdir()
        for index, (operation, result) in enumerate(cases.items()):
            identifier = '%024x' % index
            write_json(jobs / (identifier + '.json'), {'id': identifier, 'operation': operation, 'status': 'complete',
                                                      'request': {'to': str(self.data / 'recoveries/destination'), 'note': note}, 'result': result})
        write_json(self.data / 'relocations/m1.json', {'format': 'reprise-relocation-v1', 'receipt_path': str(self.data / 'relocations/m1.json'),
                                                     'source': str(self.source), 'target': str(self.root / 'external-destination'), 'note': note})
        self.save()
        target = self.root / 'job-migrated-data'
        restore_backup(self.destination, target)
        results = {operation: json.loads((target / 'jobs' / ('%024x.json' % index)).read_text())
                   for index, operation in enumerate(cases)}
        self.assertEqual(results['run']['result']['path'], str(target / 'runtimes/r1/source'))
        self.assertIsNone(results['run']['result']['pid'])
        self.assertEqual(results['run']['result']['recipe']['note'], note)
        self.assertEqual(results['capture']['result']['items'][0]['path'], str(target / 'evidence/e1/screen.png'))
        self.assertEqual(results['capture']['result']['note'], note)
        self.assertEqual(results['organize']['result']['receipt'], str(target / 'organization/p1/plan.json'))
        self.assertEqual(results['organize']['result']['selected_count'], 0)
        self.assertEqual(results['storage']['result']['storage_path'], str(self.data))
        self.assertEqual(results['storage']['result']['logical_bytes'], 12345)
        self.assertTrue(results['storage']['result']['restored_historical_report'])
        self.assertEqual(results['migrate']['result']['receipt_path'], str(target / 'relocations/m1.json'))
        self.assertEqual(results['custom-unknown']['result'], cases['custom-unknown'])
        self.assertEqual(json.loads((target / 'relocations/m1.json').read_text())['receipt_path'], str(target / 'relocations/m1.json'))



if __name__ == '__main__':
    unittest.main()
