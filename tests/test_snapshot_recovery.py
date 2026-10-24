"""Retained synthetic subprocess crashes around managed snapshot publication.

These tests terminate the writer without unwinding Python finally/except blocks.
They distinguish a real interrupted publication from ordinary exception rollback.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from reprise.git import Repository
from reprise.service import Reprise
from reprise.backup import BackupError, create_backup, verify_backup


WRITER = r'''
import os
from pathlib import Path
import sys
from reprise import folders
from reprise.service import Reprise

data, identifier, old_sha, stage = sys.argv[1:]
branch = 'refs/heads/folders/' + identifier
original_run = folders.FolderStore.run
original_json = folders.write_json
original_replace = folders.os.replace
advanced = False

def run(store, *args, **kwargs):
    global advanced
    result = original_run(store, *args, **kwargs)
    if len(args) >= 3 and args[0] == 'update-ref':
        if args[1] == branch:
            if args[2] != old_sha:
                advanced = True
                if stage == 'branch':
                    os._exit(77)
            elif advanced and stage == 'rollback':
                os._exit(77)
        if args[1].startswith('refs/reprise/snapshots/' + identifier + '/') and stage == 'snapshot':
            os._exit(77)
    return result

def write_json(path, *args, **kwargs):
    if Path(path).name == 'reprise-snapshots.json' and stage == 'rollback':
        raise OSError('Synthetic catalog write failure; exit during rollback')
    result = original_json(path, *args, **kwargs)
    if Path(path).name == 'reprise-snapshots.json' and stage == 'catalog':
        os._exit(77)
    return result

def replace(source, destination, *args, **kwargs):
    result = original_replace(source, destination, *args, **kwargs)
    if Path(destination).name == 'shallow' and stage == 'shallow':
        os._exit(77)
    return result

folders.FolderStore.run = run
folders.write_json = write_json
folders.os.replace = replace
app = Reprise(data)
app.projects.snapshot(identifier, 'Interrupted third version')
app.close()
'''


class SnapshotRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[1]
        artifacts = Path(os.environ.get('REPRISE_TEST_ARTIFACT_DIR',
                         str(self.repo_root / 'work/test-artifacts'))) / 'snapshot-recovery'
        artifacts.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix=self._testMethodName + '-', dir=str(artifacts)))
        self.source = self.root / 'source'
        self.source.mkdir()
        self.data = self.root / 'data'
        self.app = Reprise(self.data)
        self.project = self.app.projects.add(str(self.source), kind='folder')['id']
        (self.source / 'draft.txt').write_text('First version\n')
        self.first = self.app.projects.snapshot(self.project, 'First')['sha']
        (self.source / 'draft.txt').write_text('Second version\n')
        (self.source / 'empty-folder').mkdir()
        self.retained = self.app.projects.snapshot(self.project, 'Second')['sha']
        self.store_path = self.app.projects.folders.path
        self.original_commit = Repository(self.store_path)._run('cat-file', 'commit', self.retained)
        plan = self.app.version_delete_plan(self.project, [self.first])
        self.app.delete_versions(self.project, plan['id'], confirm=True)
        self.app.close()
        (self.source / 'draft.txt').write_text('Third version\n')

    def tearDown(self):
        self.app.close()

    def interrupt(self, stage):
        response = subprocess.run(
            [sys.executable, '-c', WRITER, str(self.data), self.project, self.retained, stage],
            env=dict(os.environ, PYTHONPATH=str(self.repo_root / 'src')),
            cwd=str(self.repo_root), capture_output=True, text=True, timeout=30)
        (self.root / 'writer.stdout').write_text(response.stdout)
        (self.root / 'writer.stderr').write_text(response.stderr)
        self.assertEqual(response.returncode, 77, response.stderr)
        journal = json.loads((self.data / 'content/snapshot-transaction.json').read_text())
        (self.root / 'interrupted-journal.json').write_text(json.dumps(journal, indent=2))
        self.assertEqual(journal['state'], 'pending')
        return journal

    def assert_recovered(self, journal, committed=False):
        self.app = Reprise(self.data)
        repository = self.app.projects.repository(self.project)
        head = journal['sha'] if committed else self.retained
        self.assertEqual(repository.resolve('HEAD'), head)
        expected = [journal['sha'], self.retained] if committed else [self.retained]
        self.assertEqual([row['sha'] for row in repository.history()['commits']], expected)
        raw = Repository(self.store_path)
        self.assertEqual(raw._run('cat-file', 'commit', self.retained), self.original_commit)
        attempted_commit = raw._run('cat-file', 'commit', journal['sha'])
        self.assertIn(('parent ' + self.retained + '\n').encode(), attempted_commit)
        restored = self.root / 'restored-retained'
        report = repository.materialize(self.retained, restored)
        self.assertTrue(report['readback_verified'])
        self.assertEqual((restored / 'draft.txt').read_text(), 'Second version\n')
        self.assertTrue((restored / 'empty-folder').is_dir())
        checked = self.app.version_delete_plan(self.project, [self.retained])
        self.assertEqual(checked['selected_shas'], [self.retained])
        self.assertEqual((self.source / 'draft.txt').read_text(), 'Third version\n')
        recovered_journal = json.loads((self.data / 'content/snapshot-transaction.json').read_text())
        self.assertEqual(recovered_journal['state'], 'complete' if committed else 'rolled_back')
        (self.source / 'draft.txt').write_text('Fourth version after recovery\n')
        saved = self.app.projects.snapshot(self.project, 'Explicit save after recovery')['sha']
        self.assertNotEqual(saved, head)
        self.assertEqual(repository.resolve('HEAD'), saved)
        self.assertEqual([row['sha'] for row in repository.history()['commits']], [saved] + expected)
        raw._run('fsck', '--full', '--strict')
        (self.root / 'result.json').write_text(json.dumps({
            'retained': self.retained, 'attempted': journal['sha'], 'head_after_recovery': head,
            'saved_after_recovery': saved, 'readback_verified': True,
            'original_commit_sha256': hashlib.sha256(self.original_commit).hexdigest(),
            'recovered_state': recovered_journal['state'], 'fsck': True,
        }, indent=2))

    def test_exit_after_folder_ref_rolls_back_and_allows_explicit_retry(self):
        self.assert_recovered(self.interrupt('branch'))

    def test_exit_after_snapshot_ref_rolls_back_and_preserves_diagnostic(self):
        self.assert_recovered(self.interrupt('snapshot'))

    def test_exit_after_shallow_replace_rolls_back_and_preserves_parent_headers(self):
        self.assert_recovered(self.interrupt('shallow'))

    def test_exit_after_catalog_commit_finishes_publication(self):
        self.assert_recovered(self.interrupt('catalog'), committed=True)

    def test_exit_during_rollback_resumes_without_losing_retained_versions(self):
        self.assert_recovered(self.interrupt('rollback'))

    def store_state(self):
        raw = Repository(self.store_path)
        return {'refs': raw._run('for-each-ref', '--format=%(refname) %(objectname)'),
                'catalog': (self.store_path / 'reprise-snapshots.json').read_bytes(),
                'shallow': (self.store_path / 'shallow').read_bytes()}

    def assert_refuses_without_changing_store(self):
        before = self.store_state()
        self.app = Reprise(self.data)
        with self.assertRaises((ValueError, OSError)):
            self.app.projects.repository(self.project).resolve('HEAD')
        self.assertEqual(self.store_state(), before)
        self.assertEqual((self.source / 'draft.txt').read_text(), 'Third version\n')

    def test_unrecognized_journal_ref_refuses_without_mutating_store(self):
        journal = self.interrupt('snapshot')
        journal['ref'] = 'refs/heads/unrecognized-project'
        (self.data / 'content/snapshot-transaction.json').write_text(json.dumps(journal))
        self.assert_refuses_without_changing_store()

    def test_third_catalog_state_refuses_without_mutating_store(self):
        self.interrupt('snapshot')
        (self.store_path / 'reprise-snapshots.json').write_text(json.dumps({self.project: []}))
        self.assert_refuses_without_changing_store()

    def test_backup_refuses_pending_publication_then_succeeds_after_normal_recovery(self):
        journal = self.interrupt('snapshot')
        before = self.store_state()
        destination = self.root / 'blocked-backup'
        with self.assertRaisesRegex(BackupError, '快照.*事务'):
            create_backup(self.data, destination)
        self.assertFalse(destination.exists())
        self.assertEqual(self.store_state(), before)
        self.assert_recovered(journal)
        self.app.close()
        destination = self.root / 'recovered-backup'
        backup = create_backup(self.data, destination)
        self.assertEqual(backup['status'], 'complete')
        self.assertEqual(verify_backup(destination)['status'], 'verified')
        (self.root / 'backup-result.json').write_text(json.dumps(backup, indent=2))


if __name__ == '__main__':
    unittest.main()
