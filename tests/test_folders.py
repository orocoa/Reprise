import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch
import zipfile

from reprise.service import Reprise
from reprise import workspace
from test_runtime import fixture


class FolderTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('folders')
        self.source = self.root / 'documents'
        self.source.mkdir()
        self.app = Reprise(self.root / 'state')
        self.project = self.app.projects.add(str(self.source), kind='folder')
        self.identifier = self.project['id']

    def tearDown(self):
        self.app.close()

    def save(self, title='Version'):
        return self.app.projects.snapshot(self.identifier, title)

    def test_shared_content_across_paths_versions_and_folders_without_source_git(self):
        (self.source / 'one.txt').write_text('Shared content')
        (self.source / 'two.txt').write_text('Shared content')
        first = self.save('First')
        repo = self.app.projects.repository(self.identifier)
        self.assertEqual(len({e['oid'] for e in repo.tree(first['sha'])}), 1)
        self.assertEqual(first['stats']['new_bytes'], len(b'Shared content'))
        self.assertEqual(first['stats']['logical_bytes'], 2 * len(b'Shared content'))
        self.assertFalse((self.source / '.git').exists())
        self.assertEqual(self.app.projects.folders.directory.stat().st_mode & 0o777, 0o700)
        second = self.save()
        self.assertTrue(second['unchanged'])
        self.assertEqual(second['stats']['read_bytes'], 0)
        other = self.root / 'other'
        other.mkdir()
        (other / 'renamed.txt').write_text('Shared content')
        project = self.app.projects.add(str(other), kind='folder')
        saved = self.app.projects.snapshot(project['id'])
        self.assertEqual(saved['stats']['new_bytes'], 0)
        self.assertEqual(len(repo.history()['commits']), 1)
        with self.assertRaises(ValueError):
            repo.resolve(saved['sha'])
        repo._run('fsck', '--full', '--strict')

    def test_same_size_same_mtime_edits_create_exact_distinct_versions(self):
        path = self.source / 'draft.txt'
        path.write_text('first')
        first = self.save('First draft')
        before = path.stat()
        path.write_text('other')
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        second = self.save('Revised draft')
        self.assertNotEqual(first['sha'], second['sha'])
        repo = self.app.projects.repository(self.identifier)
        self.assertEqual(repo.blob(first['sha'], 'draft.txt'), b'first')
        self.assertEqual(repo.blob(second['sha'], 'draft.txt'), b'other')
        self.assertEqual(repo.diff(second['sha'])['files'], [{'status': 'M', 'path': 'draft.txt'}])
        view = workspace.project_snapshot(self.app, self.identifier)
        self.assertEqual(view['project']['kind'], 'folder')
        self.assertEqual(len(view['commits']), 2)
        self.assertEqual(next(c for c in view['commits'] if c['sha'] == second['sha'])['parents'], [first['sha']])

    def test_catalog_history_reads_decorations_once_and_keeps_pages_and_parents(self):
        from reprise.storage import write_json
        for number in range(4):
            (self.source / 'draft.txt').write_text('Draft %d' % number)
            self.save('Draft %d' % number)
        repo = self.app.projects.repository(self.identifier)
        original = repo.history()['commits']
        # This retained synthetic catalog exercises the independent-version
        # reader without deleting any content or changing its original edges.
        write_json(repo.path / 'reprise-snapshots.json',
                   {self.identifier: [c['sha'] for c in original]})
        with patch.object(repo, '_run', wraps=repo._run) as commands:
            page = repo.history(limit=2, offset=1)
        self.assertEqual(sum(call.args[0] == 'for-each-ref' for call in commands.call_args_list), 1)
        self.assertEqual(page['commits'], original[1:3])
        self.assertTrue(page['has_more'])
        self.assertEqual(page['next_offset'], 3)
        with patch.object(repo, '_run', wraps=repo._run) as commands:
            tips = repo.history_tips([original[0]['sha']])
        self.assertEqual(sum(call.args[0] == 'for-each-ref' for call in commands.call_args_list), 1)
        self.assertEqual(tips['commits'], original)
        refs = repo.refs()
        with patch.object(repo, '_run', wraps=repo._run) as commands:
            supplied = repo.history_tips([original[0]['sha']], refs=refs)
        self.assertFalse(any(call.args[0] == 'for-each-ref' for call in commands.call_args_list))
        self.assertEqual(supplied, tips)

        (self.source / 'draft.txt').write_text('Newly saved draft')
        latest = self.save('Newly saved draft')
        fresh = repo.history()['commits']
        self.assertEqual(fresh[0]['sha'], latest['sha'])
        self.assertEqual(fresh[0]['refs'], [repo.ref])
        self.assertEqual(fresh[1]['refs'], [])
        self.assertEqual(fresh[0]['parents'], [original[0]['sha']])

    def test_partial_recovery_and_zip_preserve_files_empty_directories_and_metadata(self):
        self.source.chmod(0o700)
        (self.source / 'empty').mkdir()
        (self.source / 'notes').mkdir()
        path = self.source / 'notes' / 'draft.txt'
        path.write_text('Recover exactly')
        path.chmod(0o640)
        os.utime(path, ns=(1500000000000000000, 1500000000000000000))
        (self.source / 'unrelated.txt').write_text('Keep out of selected export')
        (self.source / 'link').symlink_to('notes/draft.txt')
        saved = self.save()
        repo = self.app.projects.repository(self.identifier)
        recovered = self.root / 'recovered'
        repo.materialize(saved['sha'], recovered)
        self.assertEqual(recovered.stat().st_mode & 0o777, 0o700)
        self.assertTrue((recovered / 'empty').is_dir())
        self.assertEqual((recovered / 'link').readlink(), Path('notes/draft.txt'))
        self.assertEqual((recovered / 'notes/draft.txt').stat().st_mode & 0o777, 0o640)
        self.assertEqual((recovered / 'notes/draft.txt').stat().st_mtime_ns, 1500000000000000000)
        result = self.app.recovery.create(repo, self.identifier, saved['sha'], 'export', paths=['notes/draft.txt'])
        with zipfile.ZipFile(result['path']) as archive:
            self.assertEqual(archive.read('notes/draft.txt'), b'Recover exactly')
            self.assertNotIn('unrelated.txt', archive.namelist())
            self.assertIsNone(archive.testzip())
        self.assertFalse((recovered / 'snapshot.json').exists())
        repo.materialize(saved['sha'], self.root / 'empty-only', paths=['empty'])
        self.assertEqual(list((self.root / 'empty-only').iterdir()), [self.root / 'empty-only/empty'])
        with self.assertRaises(ValueError):
            repo.materialize(saved['sha'], self.root / 'escape', paths=['../draft.txt'])

    def test_restore_works_after_original_folder_is_unavailable(self):
        (self.source / 'draft.md').write_text('Saved without the original')
        saved = self.save()
        self.source.rename(self.root / 'source-offline')
        repo = self.app.projects.repository(self.identifier)
        self.assertFalse(repo.info()['source_available'])
        self.assertFalse(repo.status()['available'])
        repo.materialize(saved['sha'], self.root / 'restored-offline')
        self.assertEqual((self.root / 'restored-offline/draft.md').read_text(), 'Saved without the original')

    def test_external_symlinks_special_files_and_nested_data_fail_before_publish(self):
        (self.source / 'outside').symlink_to('../')
        with self.assertRaises(ValueError):
            self.save()
        self.assertIsNone(self.app.projects.get(self.identifier)['head'])
        with self.assertRaises(ValueError):
            self.app.projects.add(str(self.root), kind='folder')

    def test_concurrent_mutation_never_publishes_an_inconsistent_version(self):
        path = self.source / 'draft.txt'
        path.write_text('one')
        saved = self.save()
        path.write_text('two')
        blob = self.app.projects.folders.blob
        def mutate(*args, **kwargs):
            result = blob(*args, **kwargs)
            path.write_text('changed during capture')
            return result
        with patch.object(self.app.projects.folders, 'blob', side_effect=mutate):
            with self.assertRaises(ValueError):
                self.save()
        self.assertEqual(self.app.projects.get(self.identifier)['head'], saved['sha'])

    def test_nested_git_metadata_is_excluded_and_reported(self):
        (self.source / '.git').mkdir()
        (self.source / '.git/config').write_text('Never import or execute this')
        (self.source / 'text.md').write_text('Regular content')
        saved = self.save()
        repo = self.app.projects.repository(self.identifier)
        self.assertEqual(repo.manifest(saved['sha'])['excluded'], ['.git'])
        self.assertEqual([f['path'] for f in repo.tree(saved['sha'])], ['text.md'])

    def test_job_snapshot_is_cancellable_and_records_immutable_request(self):
        (self.source / 'note.txt').write_text('A saved note')
        job = self.app.execute(self.identifier, 'snapshot', {'title': 'Named version'})
        while job['status'] in ('queued', 'running', 'cancelling'):
            time.sleep(.01)
            job = self.app.jobs.get(job['id'])
        self.assertEqual(job['status'], 'complete', job)
        repo = self.app.projects.repository(self.identifier)
        self.assertEqual(repo.history()['commits'][0]['subject'], 'Named version')
        self.assertTrue(self.app.version(self.identifier, job['result']['sha'])['content'])

    def test_library_symlink_never_changes_source_permissions(self):
        from reprise.folders import FolderStore
        data = self.root / 'other-state'
        data.mkdir()
        (data / 'content').symlink_to(self.source, target_is_directory=True)
        before = self.source.stat().st_mode
        with self.assertRaises(ValueError):
            FolderStore(data).ensure()
        self.assertEqual(self.source.stat().st_mode, before)

    def test_offline_lease_blocks_direct_folder_reads_and_cli_without_metadata_write(self):
        import json
        import subprocess
        import sys
        from reprise.maintenance import DataLease, DataLeaseError
        from reprise.projects import ProjectStore
        (self.source / 'draft.md').write_text('saved')
        self.save()
        data = self.app.directory
        self.app.close()
        content = data / 'content'
        before = content.stat().st_ctime_ns
        with DataLease(data, exclusive=True):
            with self.assertRaises(DataLeaseError):
                ProjectStore(data).repository(self.identifier).history()
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
            for command in [('history', self.identifier), ('projects', '--details'),
                            ('export', '--repo', str(self.app.projects.folders.path), '--ref', 'HEAD',
                             '--to', str(self.root / 'legacy-export.zip'))]:
                result = subprocess.run([sys.executable, '-m', 'reprise', '--data', str(data), *command],
                    cwd=str(self.root), env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 1, result)
                self.assertIn('数据', result.stderr)
            self.assertEqual(content.stat().st_ctime_ns, before)
