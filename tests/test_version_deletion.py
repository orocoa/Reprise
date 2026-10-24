"""Independent deletion contracts using only retained, synthetic fixtures."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from reprise.service import Reprise
from test_runtime import commit_repo, fixture


def content(label, size):
    return hashlib.shake_256(label.encode('ascii')).digest(size)


def source_state(path):
    return {str(item.relative_to(path)): {
        'sha256': hashlib.sha256(item.read_bytes()).hexdigest(),
        'mode': item.stat().st_mode,
        'mtime_ns': item.stat().st_mtime_ns,
    } for item in sorted(path.rglob('*')) if item.is_file()}


class VersionDeletionTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('version-deletion')
        self.source = self.root / 'source'
        self.other = self.root / 'other-project'
        self.source.mkdir()
        self.other.mkdir()
        self.app = Reprise(self.root / 'state')
        self.project = self.app.projects.add(str(self.source), kind='folder')['id']
        self.other_project = self.app.projects.add(str(self.other), kind='folder')['id']
        self.payloads = {
            'S': content('common', 1024), 'A': content('first-only', 3072),
            'J': content('joint-only', 4096), 'X': content('other-project-keeps', 2048),
            'Y': content('second-only', 5120), 'B': content('latest-keeps', 3072),
        }
        self.versions = []
        self.expected = {}
        for number, labels in enumerate((('A', 'J', 'X'), ('B', 'J', 'Y'), ('B', 'S', 'S')), 1):
            values = {'shared.bin': self.payloads['S'], 'draft.bin': self.payloads[labels[0]],
                      'joint.bin': self.payloads[labels[1]], 'cross.bin': self.payloads[labels[2]]}
            retained = self.root / 'inputs' / ('version-%d' % number)
            retained.mkdir(parents=True)
            for name, value in values.items():
                (self.source / name).write_bytes(value)
                (retained / name).write_bytes(value)
            saved = self.app.projects.snapshot(self.project, 'Version %d' % number)
            self.versions.append(saved['sha'])
            self.expected[saved['sha']] = values
        for name, label in (('shared.bin', 'S'), ('protected.bin', 'X')):
            (self.other / name).write_bytes(self.payloads[label])
        self.other_sha = self.app.projects.snapshot(self.other_project, 'Other project')['sha']
        self.source_before = source_state(self.source)
        self.other_before = source_state(self.other)

    def tearDown(self):
        self.app.close()

    def plan(self, *shas):
        return self.app.version_delete_plan(self.project, list(shas))

    def assert_sources_unchanged(self):
        self.assertEqual(source_state(self.source), self.source_before)
        self.assertEqual(source_state(self.other), self.other_before)
        self.assertFalse((self.source / '.git').exists())

    def assert_restore(self, project, sha, expected, label):
        repository = self.app.projects.repository(project)
        destination = self.root / label
        result = repository.materialize(sha, destination)
        self.assertTrue(result['readback_verified'], result)
        self.assertEqual({str(p.relative_to(destination)): p.read_bytes()
                          for p in destination.rglob('*') if p.is_file()}, expected)

    def test_joint_reclaim_is_not_sum_of_single_version_unique_bytes(self):
        first, second, _ = self.versions
        one = self.plan(first)
        two = self.plan(second)
        joint = self.plan(first, second)
        self.assertEqual(one['unique_content_bytes'], len(self.payloads['A']))
        self.assertEqual(two['unique_content_bytes'], len(self.payloads['Y']))
        expected = sum(len(self.payloads[key]) for key in ('A', 'J', 'Y'))
        self.assertEqual(joint['unique_content_bytes'], expected)
        self.assertGreater(expected, one['unique_content_bytes'] + two['unique_content_bytes'])
        self.assertEqual(joint['estimated_reclaim_bytes'], expected)
        self.assertEqual(set(joint['selected_shas']), {first, second})
        self.assertTrue(joint['history_state_loss'])
        self.assertTrue(joint['other_projects_protected'])
        self.assertEqual(joint['blockers'], [])
        self.assertEqual(len(self.app.projects.repository(self.project).history()['commits']), 3)
        self.assert_sources_unchanged()

    def test_confirm_is_required_and_plan_is_scoped_to_its_project(self):
        plan = self.plan(self.versions[0])
        with self.assertRaises((ValueError, PermissionError)):
            self.app.delete_versions(self.project, plan['id'], confirm=False)
        with self.assertRaises((ValueError, KeyError)):
            self.app.delete_versions(self.other_project, plan['id'], confirm=True)
        self.assertEqual(len(self.app.projects.repository(self.project).history()['commits']), 3)
        self.assert_restore(self.project, self.versions[0], self.expected[self.versions[0]], 'still-restorable')
        self.assert_sources_unchanged()

    def test_changed_saved_plan_cannot_delete_a_different_selection(self):
        plan = self.plan(self.versions[0])
        path = self.app.directory / 'version-deletions' / (plan['id'] + '.plan.json')
        (self.root / 'untampered-plan.json').write_bytes(path.read_bytes())
        changed = json.loads(path.read_text())
        changed['selected_shas'] = [self.versions[1]]
        path.write_text(json.dumps(changed))
        with self.assertRaises(ValueError):
            self.app.delete_versions(self.project, plan['id'], confirm=True)
        self.assertEqual({c['sha'] for c in self.app.projects.repository(self.project).history()['commits']},
                         set(self.versions))
        self.assert_restore(self.project, self.versions[1], self.expected[self.versions[1]], 'tampered-plan-readback')
        self.assert_sources_unchanged()

    def test_real_gc_keeps_other_projects_and_original_public_version_ids(self):
        first, second, latest = self.versions
        plan = self.plan(first, second)
        receipt = self.app.delete_versions(self.project, plan['id'], confirm=True)
        self.assertEqual(receipt['status'], 'verified', receipt)
        self.assertTrue(receipt['verification']['ok'], receipt)
        self.assertTrue(receipt['verification']['fsck'], receipt)
        self.assertTrue(receipt['retained_versions_verified'], receipt)
        self.assertFalse(receipt['source_files_removed'])
        self.assertTrue(Path(receipt['receipt_path']).is_file())
        for field in ('store_bytes_reclaimed', 'allocated_bytes_reclaimed', 'volume_free_delta'):
            self.assertIn(field, receipt)
        repository = self.app.projects.repository(self.project)
        self.assertEqual([row['sha'] for row in repository.history()['commits']], [latest])
        for deleted in (first, second):
            with self.assertRaises((ValueError, KeyError)):
                repository.resolve(deleted)
        for label in ('A', 'J', 'Y'):
            data = self.payloads[label]
            oid = hashlib.sha1(('blob %d\0' % len(data)).encode() + data).hexdigest()
            result = subprocess.run(['git', '--git-dir=' + str(self.app.projects.folders.path),
                                     'cat-file', '-e', oid], capture_output=True)
            self.assertNotEqual(result.returncode, 0, 'Unreferenced payload survived: ' + label)
        for label in ('S', 'X', 'B'):
            data = self.payloads[label]
            oid = hashlib.sha1(('blob %d\0' % len(data)).encode() + data).hexdigest()
            self.assertEqual(repository._run('cat-file', 'blob', oid), data)
        self.assert_restore(self.project, latest, self.expected[latest], 'retained-latest')
        self.assert_restore(self.other_project, self.other_sha,
                            {'shared.bin': self.payloads['S'], 'protected.bin': self.payloads['X']},
                            'retained-other-project')
        self.assert_sources_unchanged()

    def test_deleting_middle_version_preserves_both_sides_and_future_saves(self):
        first, second, latest = self.versions
        receipt = self.app.delete_versions(self.project, self.plan(second)['id'], confirm=True)
        self.assertEqual(receipt['status'], 'verified')
        self.assert_restore(self.project, first, self.expected[first], 'retained-earliest')
        self.assert_restore(self.project, latest, self.expected[latest], 'retained-newest')
        self.assertEqual({row['sha'] for row in self.app.projects.repository(self.project).history()['commits']},
                         {first, latest})
        (self.source / 'draft.bin').write_bytes(b'A new draft after garbage collection')
        saved = self.app.projects.snapshot(self.project, 'After deletion')['sha']
        self.assertEqual(self.app.projects.repository(self.project).resolve(saved), saved)
        with self.assertRaises((ValueError, KeyError)):
            self.app.projects.repository(self.project).resolve(second)

    def test_stale_plan_rejects_new_cross_project_reference(self):
        first = self.versions[0]
        plan = self.plan(first)
        (self.other / 'keep-first.bin').write_bytes(self.payloads['A'])
        self.app.projects.snapshot(self.other_project, 'Keep first content elsewhere')
        with self.assertRaises(ValueError):
            self.app.delete_versions(self.project, plan['id'], confirm=True)
        refreshed = self.plan(first)
        self.assertEqual(refreshed['unique_content_bytes'], 0)
        self.assertEqual(len(self.app.projects.repository(self.project).history()['commits']), 3)

    def test_zero_unique_bytes_still_reports_loss_of_history_state(self):
        (self.other / 'first.bin').write_bytes(self.payloads['A'])
        self.app.projects.snapshot(self.other_project, 'Same bytes elsewhere')
        plan = self.plan(self.versions[0])
        self.assertEqual(plan['unique_content_bytes'], 0)
        self.assertEqual(plan['estimated_reclaim_bytes'], 0)
        self.assertTrue(plan['history_state_loss'])
        self.assertGreater(plan['shared_file_count'], 0)

    def test_foreign_revision_and_imported_git_are_rejected_without_mutation(self):
        with self.assertRaises((ValueError, KeyError)):
            self.plan(self.other_sha)
        repo = commit_repo(self.root / 'imported-git')
        git_project = self.app.projects.add(str(repo.work_tree), kind='git')['id']
        before = source_state(repo.work_tree)
        with self.assertRaises(ValueError):
            self.app.version_delete_plan(git_project, [repo.resolve('HEAD')])
        self.assertEqual(source_state(repo.work_tree), before)
        self.assert_sources_unchanged()

    def test_local_plan_and_delete_do_not_open_network_or_expose_payload(self):
        marker = b'PRIVATE-CONTENT-SENTINEL-DO-NOT-EMIT'
        (self.source / 'private.txt').write_bytes(marker)
        saved = self.app.projects.snapshot(self.project, 'Private fixture')['sha']
        with patch.object(socket, 'create_connection', side_effect=AssertionError('network attempted')), \
                patch.object(socket.socket, 'connect', side_effect=AssertionError('network attempted')):
            plan = self.plan(saved)
            receipt = self.app.delete_versions(self.project, plan['id'], confirm=True)
        self.assertNotIn(marker.decode(), json.dumps(plan))
        self.assertNotIn(marker.decode(), json.dumps(receipt))
        self.assertEqual((self.source / 'private.txt').read_bytes(), marker)

    def test_service_job_records_explicit_plan_and_confirmation(self):
        plan = self.plan(self.versions[1])
        job = self.app.execute(self.project, 'version-delete', {'plan_id': plan['id'], 'confirm': True})
        deadline = time.monotonic() + 20
        while job['status'] in ('queued', 'running', 'cancelling') and time.monotonic() < deadline:
            time.sleep(.02)
            job = self.app.jobs.get(job['id'])
        self.assertEqual(job['status'], 'complete', job)
        self.assertEqual(job['result']['status'], 'verified', job)
        self.assertEqual(job['request']['plan_id'], plan['id'])
        self.assertIs(job['request']['confirm'], True)
        self.assert_sources_unchanged()

    def test_queued_job_cannot_change_when_callers_request_is_mutated(self):
        plan = self.plan(self.versions[1])
        body = {'plan_id': plan['id'], 'confirm': True}
        captured = {}
        def enqueue(identifier, operation, callback, **kwargs):
            captured.update(callback=callback, request=kwargs['request'])
            return {'status': 'queued'}
        with patch.object(self.app.jobs, 'submit', side_effect=enqueue):
            self.app.execute(self.project, 'version-delete', body)
        body.update(plan_id='0' * 32, confirm=False)
        self.assertEqual(captured['request'], {'plan_id': plan['id'], 'confirm': True})
        self.assertEqual(captured['callback']()['status'], 'verified')
        self.assert_sources_unchanged()

    def test_pack_failure_preserves_original_history_and_contents(self):
        plan = self.plan(self.versions[1])
        original = self.app.projects.folders.run
        def failing_pack(*args, **kwargs):
            if args[0] == 'pack-objects':
                raise ValueError('Injected pack failure')
            return original(*args, **kwargs)
        with patch.object(self.app.projects.folders, 'run', side_effect=failing_pack):
            with self.assertRaisesRegex(ValueError, 'Injected pack failure'):
                self.app.delete_versions(self.project, plan['id'], confirm=True)
        self.assertEqual({c['sha'] for c in self.app.projects.repository(self.project).history()['commits']},
                         set(self.versions))
        self.assert_restore(self.project, self.versions[1], self.expected[self.versions[1]], 'pack-failure-restore')
        self.assert_sources_unchanged()

    def test_replacement_verification_failure_never_switches_live_store(self):
        from reprise import version_deletion
        plan = self.plan(self.versions[1])
        original = version_deletion.verify_project
        def failing_verification(projects, *args, **kwargs):
            if projects is not self.app.projects:
                raise ValueError('Injected replacement verification failure')
            return original(projects, *args, **kwargs)
        with patch.object(version_deletion, 'verify_project', side_effect=failing_verification):
            with self.assertRaisesRegex(ValueError, 'Injected replacement verification failure'):
                self.app.delete_versions(self.project, plan['id'], confirm=True)
        self.assert_restore(self.project, self.versions[1], self.expected[self.versions[1]], 'verify-failure-restore')
        self.assert_sources_unchanged()

    def test_swap_failure_rolls_back_and_preserves_diagnostic_replacement(self):
        from reprise import version_deletion
        plan = self.plan(self.versions[1])
        original = os.replace
        store_path = self.app.projects.folders.path
        def failing_install(source, target):
            if str(source).endswith('.staging/content/objects.git') and Path(target) == store_path:
                raise OSError('Injected store swap failure')
            return original(source, target)
        with patch.object(version_deletion.os, 'replace', side_effect=failing_install):
            with self.assertRaisesRegex(OSError, 'Injected store swap failure'):
                self.app.delete_versions(self.project, plan['id'], confirm=True)
        transaction = json.loads((store_path.parent / 'delete-transaction.json').read_text())
        self.assertEqual(transaction['state'], 'rolled_back')
        self.assertTrue(Path(transaction['replacement']).is_dir())
        self.assert_restore(self.project, self.versions[1], self.expected[self.versions[1]], 'swap-failure-restore')
        self.assert_sources_unchanged()

    def test_reclaim_failure_keeps_survivors_and_records_pending_transaction(self):
        from reprise import version_deletion
        plan = self.plan(self.versions[1])
        with patch.object(version_deletion.shutil, 'rmtree', side_effect=OSError('Injected reclaim failure')):
            with self.assertRaisesRegex(OSError, 'Injected reclaim failure'):
                self.app.delete_versions(self.project, plan['id'], confirm=True)
        transaction = json.loads((self.app.projects.folders.directory / 'delete-transaction.json').read_text())
        self.assertEqual(transaction['state'], 'reclaiming')
        self.assertTrue(Path(transaction['retired']).is_dir())
        receipt_path = Path(transaction['receipt_path'])
        if receipt_path.exists():
            self.assertNotEqual(json.loads(receipt_path.read_text()).get('status'), 'verified')
        self.assert_restore(self.project, self.versions[0], self.expected[self.versions[0]], 'reclaim-failure-earliest')
        self.assert_restore(self.project, self.versions[2], self.expected[self.versions[2]], 'reclaim-failure-latest')
        with self.assertRaises(ValueError):
            self.plan(self.versions[0])
        with self.assertRaises(ValueError):
            self.app.projects.snapshot(self.project, 'Must wait for explicit recovery')
        from reprise.backup import BackupError, create_backup
        self.app.close()
        rejected_backup = self.root / 'pending-transaction-backup'
        with self.assertRaisesRegex(BackupError, '版本删除事务尚未完成'):
            create_backup(self.app.directory, rejected_backup)
        self.assertFalse(rejected_backup.exists())
        self.app = Reprise(self.root / 'state')
        resumed = self.app.delete_versions(self.project, plan['id'], confirm=True)
        self.assertEqual(resumed['status'], 'verified')
        self.assertFalse(Path(transaction['retired']).exists())
        self.assertEqual(json.loads((self.app.projects.folders.directory / 'delete-transaction.json').read_text())['state'],
                         'complete')
        self.assertEqual(self.app.delete_versions(self.project, plan['id'], confirm=True), resumed)
        self.assert_restore(self.project, self.versions[2], self.expected[self.versions[2]], 'resume-readback')
        self.assert_sources_unchanged()

    def test_prepared_interruption_rolls_back_before_new_plan(self):
        from reprise import version_deletion
        plan = self.plan(self.versions[1])
        with patch.object(version_deletion.shutil, 'rmtree', side_effect=OSError('Preserve pre-reclaim state')):
            with self.assertRaises(OSError):
                self.app.delete_versions(self.project, plan['id'], confirm=True)
        path = self.app.projects.folders.directory / 'delete-transaction.json'
        transaction = json.loads(path.read_text())
        # Simulate a process disappearing between the second rename and the
        # durable installed journal. Both complete stores remain as evidence.
        transaction['state'] = 'prepared'
        path.write_text(json.dumps(transaction))
        with self.assertRaisesRegex(ValueError, '重新预检'):
            self.app.delete_versions(self.project, plan['id'], confirm=True)
        self.assertEqual(json.loads(path.read_text())['state'], 'rolled_back')
        self.assertEqual({c['sha'] for c in self.app.projects.repository(self.project).history()['commits']},
                         set(self.versions))
        self.assert_restore(self.project, self.versions[1], self.expected[self.versions[1]], 'prepared-rollback-readback')
        self.assertTrue(Path(transaction['replacement']).is_dir())
        self.assertNotEqual(self.plan(self.versions[1])['id'], plan['id'])
        self.assert_sources_unchanged()

    def test_post_swap_verification_failure_restores_original_store(self):
        from reprise import version_deletion
        plan = self.plan(self.versions[1])
        original = version_deletion.verify_project
        def fail_installed(projects, *args, **kwargs):
            if projects is self.app.projects and self.app.projects.folders.catalog() is not None:
                raise ValueError('Injected installed-store verification failure')
            return original(projects, *args, **kwargs)
        with patch.object(version_deletion, 'verify_project', side_effect=fail_installed):
            with self.assertRaisesRegex(ValueError, 'Injected installed-store'):
                self.app.delete_versions(self.project, plan['id'], confirm=True)
        self.assertEqual({c['sha'] for c in self.app.projects.repository(self.project).history()['commits']},
                         set(self.versions))
        self.assert_restore(self.project, self.versions[1], self.expected[self.versions[1]], 'installed-failure-readback')
        self.assert_sources_unchanged()

    def test_delete_every_snapshot_then_save_into_empty_library(self):
        receipt = self.app.delete_versions(self.project, self.plan(*self.versions)['id'], confirm=True)
        self.assertEqual(receipt['status'], 'verified')
        self.assertEqual(self.app.projects.repository(self.project).history()['commits'], [])
        other_plan = self.app.version_delete_plan(self.other_project, [self.other_sha])
        receipt = self.app.delete_versions(self.other_project, other_plan['id'], confirm=True)
        self.assertEqual(receipt['status'], 'verified')
        self.assertEqual(receipt['retained_versions_verified'], 0)
        self.assertEqual(self.app.projects.folders.run('for-each-ref', '--format=%(refname)'), '')
        saved = self.app.projects.snapshot(self.project, 'First version after empty library')['sha']
        self.assertEqual([c['sha'] for c in self.app.projects.repository(self.project).history()['commits']], [saved])
        self.assert_restore(self.project, saved, self.expected[self.versions[-1]], 'empty-library-new-save')
        self.assert_sources_unchanged()

    def test_backup_restore_after_deletion_preserves_catalog_and_shared_content(self):
        from reprise.backup import create_backup, restore_backup, verify_backup
        self.app.delete_versions(self.project, self.plan(self.versions[1])['id'], confirm=True)
        old_plan = self.plan(self.versions[0])
        environment = self.app.directory / 'environments' / ('a' * 32) / 'environment.json'
        workspace = environment.parent / 'attempts' / 'kept-workspace'
        workspace.mkdir(parents=True)
        (workspace / 'lockfile.txt').write_text('Synthetic saved environment input')
        environment.write_text(json.dumps({'status': 'ready', 'rebuild_verified': True,
            'workspace': str(workspace), 'attempts': [{'workspace': str(workspace)}],
            'materialization': {'path': str(workspace)}}))
        self.app.close()
        backup = self.root / 'managed-backup'
        self.assertEqual(create_backup(self.app.directory, backup)['status'], 'complete')
        self.assertEqual(verify_backup(backup)['status'], 'verified')
        restored_data = self.root / 'restored-managed-data'
        self.assertEqual(restore_backup(backup, restored_data)['status'], 'complete')
        recovered = Reprise(restored_data)
        try:
            migrated = json.loads((restored_data / environment.relative_to(self.app.directory)).read_text())
            self.assertEqual(migrated['status'], 'restored-rebuild-required')
            self.assertIs(migrated['rebuild_verified'], False)
            self.assertTrue(migrated['restored_historical_report'])
            expected_workspace = str(restored_data / workspace.relative_to(self.app.directory))
            self.assertEqual(migrated['workspace'], expected_workspace)
            self.assertEqual(migrated['attempts'][0]['workspace'], expected_workspace)
            self.assertEqual(migrated['materialization']['path'], expected_workspace)
            with self.assertRaisesRegex(ValueError, '重新预检'):
                recovered.delete_versions(self.project, old_plan['id'], confirm=True)
            repository = recovered.projects.repository(self.project)
            self.assertEqual({c['sha'] for c in repository.history()['commits']},
                             {self.versions[0], self.versions[2]})
            for number in (0, 2):
                target = self.root / ('backup-version-%d' % number)
                self.assertTrue(repository.materialize(self.versions[number], target)['readback_verified'])
                self.assertEqual({str(p.relative_to(target)): p.read_bytes()
                                  for p in target.rglob('*') if p.is_file()}, self.expected[self.versions[number]])
            other = self.root / 'backup-other-project'
            recovered.projects.repository(self.other_project).materialize(self.other_sha, other)
            self.assertEqual((other / 'protected.bin').read_bytes(), self.payloads['X'])
        finally:
            recovered.close()
        self.assert_sources_unchanged()

    def test_unrecognized_ref_blocks_plan_and_invalidates_existing_plan(self):
        plan = self.plan(self.versions[1])
        self.app.projects.folders.run('update-ref', 'refs/user-kept/important', self.versions[1])
        with self.assertRaises(ValueError):
            self.plan(self.versions[1])
        with self.assertRaises(ValueError):
            self.app.delete_versions(self.project, plan['id'], confirm=True)
        self.assert_restore(self.project, self.versions[1], self.expected[self.versions[1]], 'unknown-ref-readback')
        self.assert_sources_unchanged()

    def test_shallow_boundary_preserves_original_commit_bytes_and_parent_headers(self):
        store = self.app.projects.folders
        original = {sha: store.run('cat-file', 'commit', sha) for sha in (*self.versions, self.other_sha)}
        first, deleted, latest = self.versions
        self.app.delete_versions(self.project, self.plan(deleted)['id'], confirm=True)
        for sha in (first, latest, self.other_sha):
            self.assertEqual(store.run('cat-file', 'commit', sha), original[sha])
        self.assertIn('parent ' + deleted + '\n', original[latest])
        self.assertEqual(set((store.path / 'shallow').read_text().splitlines()), {first, latest, self.other_sha})
        history = self.app.projects.repository(self.project).history()['commits']
        self.assertIn(deleted, next(row for row in history if row['sha'] == latest)['parents'])
        self.assert_sources_unchanged()

    def test_unreferenced_diagnostics_and_their_selected_parent_are_preserved(self):
        store = self.app.projects.folders
        loose = store.run('hash-object', '-w', '--stdin', input=b'Failed operation diagnostic bytes')
        tree = store.run('mktree', input=('100644 blob ' + loose + '\tdiagnostic.txt\n').encode())
        # A failed snapshot can have an unpublished commit whose ancestry
        # points into the version selection. Preserve its complete closure.
        orphan = store.run('commit-tree', tree, '-p', self.versions[1], input=b'Unpublished failed snapshot\n')
        expected = {oid: store.run('cat-file', '-p', oid) for oid in (loose, tree, orphan, self.versions[1])}
        plan = self.plan(self.versions[1])
        self.assertEqual(plan['unique_content_bytes'], 0)
        receipt = self.app.delete_versions(self.project, plan['id'], confirm=True)
        self.assertEqual(receipt['status'], 'verified')
        for oid, value in expected.items():
            self.assertEqual(store.run('cat-file', '-p', oid), value)
        self.assertEqual({c['sha'] for c in self.app.projects.repository(self.project).history()['commits']},
                         {self.versions[0], self.versions[2]})
        with self.assertRaises(ValueError):
            self.app.projects.repository(self.project).resolve(self.versions[1])
        self.assert_sources_unchanged()

    def test_saving_after_gc_preserves_diagnostic_shallow_boundaries(self):
        store = self.app.projects.folders
        first, middle, latest = self.versions
        self.app.delete_versions(self.project, self.plan(middle)['id'], confirm=True)
        tree = store.run('rev-parse', latest + '^{tree}')
        orphan = store.run('commit-tree', tree, '-p', latest, input=b'Unpublished diagnostic after first GC\n')
        self.app.delete_versions(self.project, self.plan(latest)['id'], confirm=True)
        self.assertIn(latest, (store.path / 'shallow').read_text().splitlines())
        original = store.run('cat-file', 'commit', orphan)
        (self.source / 'draft.bin').write_bytes(b'New snapshot must retain unrelated diagnostic boundaries')
        saved = self.app.projects.snapshot(self.project, 'Save after diagnostic-protected GC')['sha']
        self.assertIn(latest, (store.path / 'shallow').read_text().splitlines())
        store.run('fsck', '--full', '--strict')
        self.assertEqual(store.run('cat-file', 'commit', orphan), original)
        self.assertEqual({c['sha'] for c in self.app.projects.repository(self.project).history()['commits']},
                         {first, saved})

    def test_failed_catalog_publication_keeps_previous_versions_and_allows_retry(self):
        from reprise import folders
        first, middle, latest = self.versions
        self.app.delete_versions(self.project, self.plan(middle)['id'], confirm=True)
        value = b'Keep this failed publication diagnostic and allow a later explicit save'
        (self.source / 'draft.bin').write_bytes(value)
        original = folders.write_json
        def fail_catalog(path, *args, **kwargs):
            if Path(path).name == 'reprise-snapshots.json':
                raise OSError('Injected catalog publication failure')
            return original(path, *args, **kwargs)
        with patch.object(folders, 'write_json', side_effect=fail_catalog):
            with self.assertRaisesRegex(OSError, 'Injected catalog publication failure'):
                self.app.projects.snapshot(self.project, 'Interrupted catalog publication')
        repository = self.app.projects.repository(self.project)
        self.assertEqual(repository.resolve('HEAD'), latest)
        self.assertEqual({c['sha'] for c in repository.history()['commits']}, {first, latest})
        oid = hashlib.sha1(('blob %d\0' % len(value)).encode() + value).hexdigest()
        self.assertEqual(repository._run('cat-file', 'blob', oid), value)
        self.plan(first)
        saved = self.app.projects.snapshot(self.project, 'Explicit retry after failed save')['sha']
        self.assertEqual(repository.resolve('HEAD'), saved)

    def test_delete_waits_for_entire_concurrent_restore(self):
        from reprise import organize
        plan = self.plan(self.versions[1])
        repository = self.app.projects.repository(self.project)
        entered, allow_finish, delete_started, deleted = (threading.Event() for _ in range(4))
        errors = []
        original = organize.verify_restore
        def slow_readback(*args, **kwargs):
            entered.set()
            if not allow_finish.wait(10):
                raise RuntimeError('Test synchronization timed out')
            return original(*args, **kwargs)
        def restore():
            try:
                repository.materialize(self.versions[1], self.root / 'concurrent-restore')
            except BaseException as error:
                errors.append(error)
        def delete():
            delete_started.set()
            try:
                self.app.delete_versions(self.project, plan['id'], confirm=True)
            except BaseException as error:
                errors.append(error)
            finally:
                deleted.set()
        reader, deleter = threading.Thread(target=restore), threading.Thread(target=delete)
        with patch.object(organize, 'verify_restore', side_effect=slow_readback):
            reader.start()
            try:
                self.assertTrue(entered.wait(10))
                deleter.start()
                self.assertTrue(delete_started.wait(2))
                self.assertFalse(deleted.wait(.15), 'Deletion passed a running folder read')
            finally:
                allow_finish.set()
                reader.join(15)
                if deleter.ident is not None:
                    deleter.join(15)
        self.assertFalse(reader.is_alive())
        self.assertFalse(deleter.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual((self.root / 'concurrent-restore/draft.bin').read_bytes(), self.payloads['B'])
        self.assert_sources_unchanged()

    def test_content_gate_blocks_a_separate_process_snapshot_writer(self):
        from reprise.content_lock import content_access
        script = ("import sys; from reprise.service import Reprise; "
                  "app=Reprise(sys.argv[1]); print('ready',flush=True); "
                  "app.projects.snapshot(sys.argv[2],'Concurrent save'); app.close(); print('done',flush=True)")
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
        process = None
        try:
            with content_access(self.app.projects.folders.directory):
                process = subprocess.Popen([sys.executable, '-c', script, str(self.app.directory), self.project],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
                self.assertEqual(process.stdout.readline().strip(), 'ready')
                with self.assertRaises(subprocess.TimeoutExpired):
                    process.wait(timeout=.15)
            stdout, stderr = process.communicate(timeout=15)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertIn('done', stdout)
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate()
        self.assert_sources_unchanged()


if __name__ == '__main__':
    unittest.main()
