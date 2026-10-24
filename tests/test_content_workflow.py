"""Local privacy boundaries, verified reviews and installed-archive compatibility."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from reprise.git import Repository, _environment
from reprise.service import Reprise
from reprise.storage import write_json
from reprise.organize import verify_restore
from test_runtime import fixture, commit_repo


def archive_fixture(root, data):
    source = root / 'original'
    (source / '.git').mkdir(parents=True)
    (source / '.git/config').write_bytes(b'[core]\nrepositoryformatversion = 0\n')
    (source / 'notes.txt').write_bytes(b'original archived content')
    repository = commit_repo(root / 'archive')
    entries, rows = [], []
    for number, path in enumerate([source, *sorted(source.rglob('*'))]):
        value = path.lstat()
        item = {'path': '.' if path == source else path.relative_to(source).as_posix(),
                'kind': 'dir' if path.is_dir() else 'file', 'mode': value.st_mode & 0o777,
                'atime_ns': value.st_atime_ns, 'mtime_ns': value.st_mtime_ns, 'xattrs': {}}
        if path.is_file():
            content = path.read_bytes()
            oid = repository._run('hash-object', '-w', '--stdin', input=content).decode().strip()
            item.update(oid=oid, size=len(content), sha256=hashlib.sha256(content).hexdigest())
            rows.append(f'100644 blob {oid}\tf{number}\n')
        entries.append(item)
    manifest = {'format': 'reprise-selected-snapshot-v1', 'label': 'L01', 'source': str(source), 'entries': entries}
    encoded = json.dumps(manifest).encode()
    oid = repository._run('hash-object', '-w', '--stdin', input=encoded).decode().strip()
    tree = repository._run('mktree', input=(''.join(rows)+f'100644 blob {oid}\tsnapshot.json\n').encode()).decode().strip()
    sha = repository._run('commit-tree', tree, input=b'Archive directory\n').decode().strip()
    repository._run('update-ref', 'refs/tags/L01', sha)
    view = root / 'view.git'
    subprocess.run(['git', 'clone', '--bare', str(repository.path), str(view)], check=True, capture_output=True)
    view_repository = Repository(view)
    view_sha = view_repository._run('commit-tree', tree, input=b'Independent view\n').decode().strip()
    view_repository._run('update-ref', 'refs/tags/L01', view_sha)
    view_repository._run('update-ref', 'refs/heads/master', view_sha)
    view_repository._run('symbolic-ref', 'HEAD', 'refs/heads/master')
    snapshot = {'label': 'L01', 'name': 'Old notes', 'aliases': ['Old notes alias'],
                'version_aliases': ['v1'], 'restore_name': 'old-notes', 'commit': sha,
                'view_commit': view_sha, 'source': str(source), 'files': 2, 'logical_bytes': 62}
    group = {'id': 'old-notes', 'name': 'Legacy notes', 'aliases': ['Archive alias'],
             'archive_repository': str(repository.path), 'view_repository': str(view),
             'snapshots': [snapshot], 'latest': 'L01'}
    write_json(data / 'named-archives/registry.json', {'schema': 1, 'projects': [group]}, private=True)
    return source, group, sha, view_sha


class ContentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('unified-content')
        self.data = self.root / 'state'
        self.source = self.root / 'documents'
        self.source.mkdir()
        self.app = Reprise(self.data)

    def tearDown(self):
        self.app.close()

    def save(self, exclude=None):
        project = self.app.projects.add(str(self.source), 'My notes', 'folder', exclude)
        saved = self.app.projects.snapshot(project['id'], 'Saved version')
        return project, saved

    def test_excluded_content_is_never_opened_and_default_processing_never_calls_ai_or_network(self):
        (self.source / 'private').mkdir()
        (self.source / 'private/secret.txt').write_text('DO NOT COPY THIS')
        (self.source / 'public.txt').write_text('Safe to version')
        from reprise import folders
        opener = folders._open_file
        seen = []
        def open_file(fd, path):
            seen.append(path)
            self.assertFalse(path.startswith('private'))
            return opener(fd, path)
        with patch('reprise.folders._open_file', side_effect=open_file), patch.object(self.app.ai, 'suggest', side_effect=AssertionError('AI called')), patch('socket.socket.connect', side_effect=AssertionError('Network called')):
            project, saved = self.save(['private/**'])
            repo = self.app.projects.repository(project['id'])
            recovered = self.root / 'recovered'
            repo.materialize(saved['sha'], recovered)
        self.assertEqual(seen, ['public.txt'])
        self.assertFalse((recovered / 'private').exists())
        self.assertEqual(repo.manifest(saved['sha'])['excluded'], ['private'])
        contract = self.app.privacy()
        self.assertFalse(contract['local_operations_use_ai'])
        self.assertFalse(contract['encrypted'])
        self.assertIn('command outputs', contract['agent_boundary'])
        self.assertEqual(contract['projects'][0]['exclusions'], ['private/**'])
        self.assertNotIn('path', self.app.projects.summaries()[0])
        self.assertEqual(self.data.stat().st_mode & 0o777, 0o700)

    def test_review_restores_and_reads_back_before_selection_without_removing_any_source(self):
        (self.source / 'a.txt').write_text('same content')
        (self.source / 'b.txt').write_text('same content')
        (self.source / 'empty').mkdir()
        project, saved = self.save()
        summary = self.app.organization.create(project['id'], saved['sha'])
        self.assertTrue(summary['verification']['readback_verified'])
        self.assertEqual(summary['candidate_count'], 1)
        plan = self.app.organization.get(summary['id'])
        self.assertEqual(plan['selected_paths'], [])
        self.assertEqual(Path(plan['receipt']).stat().st_mode & 0o777, 0o600)
        selected = self.app.organization.select(plan['id'], ['b.txt'])
        self.assertEqual(selected['selected_count'], 1)
        self.assertFalse(selected['source_files_removed'])
        self.assertEqual((self.source / 'a.txt').read_text(), 'same content')
        self.assertEqual((self.source / 'b.txt').read_text(), 'same content')
        self.assertEqual((Path(plan['recovery_path']) / 'b.txt').read_text(), 'same content')
        (self.source / 'b.txt').write_text('changed')
        with self.assertRaises(ValueError):
            self.app.organization.select(plan['id'], ['b.txt'])

    def test_runtime_protection_is_frozen_even_after_service_disappears(self):
        for name in ('a.txt', 'b.txt'):
            (self.source / name).write_text('same')
        project, saved = self.save()
        with patch.object(self.app.runtimes, 'list', return_value=[{'source': str(self.source), 'running': True}]):
            summary = self.app.organization.create(project['id'], saved['sha'])
        with patch.object(self.app.runtimes, 'list', return_value=[]):
            plan = self.app.organization.get(summary['id'])
            self.assertFalse(plan['candidates'][0]['selectable'])
            with self.assertRaises(ValueError):
                self.app.organization.select(plan['id'], ['b.txt'])
        self.assertTrue((self.source / 'b.txt').exists())

    def test_readback_failure_cannot_publish_a_verified_review(self):
        for name in ('a.txt', 'b.txt'):
            (self.source / name).write_text('same')
        project, saved = self.save()
        original = self.app.recovery.create
        def corrupt(*args, **kwargs):
            report = original(*args, **kwargs)
            (Path(report['path']) / 'b.txt').write_text('broken')
            return report
        with patch.object(self.app.recovery, 'create', side_effect=corrupt):
            with self.assertRaises(ValueError):
                self.app.organization.create(project['id'], saved['sha'])
        self.assertFalse(list((self.data / 'organization').glob('*/plan.json')))

    def test_git_worktree_files_are_protected_in_folder_review(self):
        repo = commit_repo(self.root / 'git-source')
        for name in ('a.txt', 'b.txt'):
            (repo.path / name).write_text('same')
        repo._run('add', 'a.txt', 'b.txt')
        project = self.app.projects.add(str(repo.path), kind='folder')
        saved = self.app.projects.snapshot(project['id'])
        summary = self.app.organization.create(project['id'], saved['sha'])
        plan = self.app.organization.get(summary['id'])
        self.assertTrue(all(not c['selectable'] for c in plan['candidates']))

    def test_review_preserves_nested_git_project_even_when_its_metadata_is_excluded(self):
        (self.source / 'a.txt').write_text('same')
        nested = self.source / 'nested'
        nested.mkdir()
        (nested / 'b.txt').write_text('same')
        subprocess.run(['git', 'init', '-q', str(nested)], check=True)
        subprocess.run(['git', '-C', str(nested), 'add', 'b.txt'], check=True)
        project, saved = self.save()
        summary = self.app.organization.create(project['id'], saved['sha'])
        plan = self.app.organization.get(summary['id'])
        self.assertIn('nested/.git', plan['excluded'])
        self.assertEqual(plan['candidates'][0]['path'], 'nested/b.txt')
        self.assertFalse(plan['candidates'][0]['selectable'])
        self.assertIn(str(nested), plan['frozen_git_protections'])
        with self.assertRaises(ValueError):
            self.app.organization.select(plan['id'], ['nested/b.txt'])
        self.assertTrue((nested / 'b.txt').is_file())

    def test_select_rechecks_git_tracking_added_after_review(self):
        for name in ('a.txt', 'b.txt'):
            (self.source / name).write_text('same')
        project, saved = self.save()
        summary = self.app.organization.create(project['id'], saved['sha'])
        plan = self.app.organization.get(summary['id'])
        self.assertTrue(plan['candidates'][0]['selectable'])
        subprocess.run(['git', 'init', '-q', str(self.source)], check=True)
        subprocess.run(['git', '-C', str(self.source), 'add', 'b.txt'], check=True)
        with self.assertRaisesRegex(ValueError, 'Git'):
            self.app.organization.select(plan['id'], ['b.txt'])
        self.assertEqual(self.app.organization.get(plan['id'])['selected_paths'], [])

    def test_select_rechecks_new_nested_git_marker_without_reading_invalid_config(self):
        (self.source / 'a.txt').write_text('same')
        nested = self.source / 'nested'
        nested.mkdir()
        (nested / 'b.txt').write_text('same')
        project, saved = self.save()
        summary = self.app.organization.create(project['id'], saved['sha'])
        self.assertTrue(self.app.organization.get(summary['id'])['candidates'][0]['selectable'])
        (nested / '.git').write_text('invalid Git marker must not make this safe')
        with self.assertRaisesRegex(ValueError, 'Git'):
            self.app.organization.select(summary['id'], ['nested/b.txt'])

    def test_nested_bare_repository_files_are_not_selectable(self):
        nested = self.source / 'archive.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(nested)], check=True)
        (self.source / 'a.txt').write_bytes((nested / 'HEAD').read_bytes())
        project, saved = self.save()
        summary = self.app.organization.create(project['id'], saved['sha'])
        plan = self.app.organization.get(summary['id'])
        candidate = next(item for item in plan['candidates'] if item['path'] == 'archive.git/HEAD')
        self.assertFalse(candidate['selectable'])
        self.assertIn(str(nested), plan['frozen_git_protections'])

    def test_git_tracking_scope_treats_bracketed_directory_literally(self):
        repo = commit_repo(self.root / 'git-source')
        source = repo.path / '[draft]'
        source.mkdir()
        for name in ('a.txt', 'b.txt'):
            (source / name).write_text('same')
        repo._run('add', '--', ':(literal)[draft]')
        project = self.app.projects.add(str(source), kind='folder')
        saved = self.app.projects.snapshot(project['id'])
        summary = self.app.organization.create(project['id'], saved['sha'])
        self.assertTrue(all(not item['selectable'] for item in self.app.organization.get(summary['id'])['candidates']))

    def test_organization_preview_reads_saved_metadata_without_source_or_recovery(self):
        for name in ('a.txt', 'b.txt'):
            (self.source / name).write_text('same')
        (self.source / 'different.txt').write_text('different')
        (self.source / 'empty').mkdir()
        project, saved = self.save()
        offline = {**self.app.projects.record(project['id']), 'path': str(self.root / 'unavailable')}
        with patch.object(self.app.projects, 'record', return_value=offline), \
                patch.object(self.app.recovery, 'create', side_effect=AssertionError('Recovery was created')), \
                patch('reprise.organize.inventory', side_effect=AssertionError('Source was scanned')), \
                patch('reprise.folders.inventory', side_effect=AssertionError('Source was scanned')):
            result = self.app.organization.preview(project['id'], 'HEAD')
        self.assertEqual(result['sha'], saved['sha'])
        self.assertEqual(result['status'], 'preview')
        self.assertEqual(result['files'], 3)
        self.assertEqual(result['snapshot_logical_bytes'], 17)
        self.assertEqual(result['additional_restore_logical_bytes'], 17)
        self.assertEqual(result['duplicate_logical_bytes'], 4)
        self.assertEqual(result['duplicate_copy_count'], 1)
        self.assertIsNone(result['reclaimable_bytes'])
        self.assertFalse(result['readback_verified'])
        self.assertFalse(result['source_safety_checked'])
        self.assertFalse(result['source_files_removed'])
        self.assertFalse((self.data / 'recoveries').exists())
        self.assertFalse((self.data / 'organization').exists())

    def test_organization_preview_counts_only_regular_files_and_tolerates_unknown_free_space(self):
        (self.source / 'file.txt').write_text('same')
        (self.source / 'alias.txt').symlink_to('file.txt')
        project, saved = self.save()
        with patch('reprise.organize.shutil.disk_usage', side_effect=OSError('Unavailable')):
            result = self.app.organization.preview(project['id'], saved['sha'])
        self.assertEqual(result['files'], 1)
        self.assertEqual(result['snapshot_logical_bytes'], 4)
        self.assertEqual(result['duplicate_copy_count'], 0)
        self.assertIsNone(result['filesystem_free_bytes'])

    def test_organization_preview_does_not_recreate_a_missing_library(self):
        (self.source / 'draft.txt').write_text('preserve the real library')
        project, saved = self.save()
        missing = self.root / 'missing-library-state'
        missing.mkdir()
        (missing / 'projects.json').write_bytes((self.data / 'projects.json').read_bytes())
        result = subprocess.run([sys.executable, 'run.py', '--data', str(missing),
                                 'organize', project['id'], '--sha', saved['sha'], '--check'],
                                text=True, capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((missing / 'content').exists())
        self.assertFalse((missing / 'recoveries').exists())
        with patch.object(self.app.projects.folders, 'path', missing / 'content/objects.git'):
            with self.assertRaises(ValueError):
                self.app.organization.preview(project['id'], saved['sha'])
        self.assertFalse((missing / 'content').exists())
        self.assertEqual((self.source / 'draft.txt').read_text(), 'preserve the real library')

    def test_organization_preview_cancellation_does_not_create_recovery_or_plan(self):
        from reprise.cancellation import Cancelled
        for name in ('a.txt', 'b.txt'):
            (self.source / name).write_text('same')
        project, saved = self.save()
        class CancelOnSecondEntry:
            def __init__(self):
                self.calls = 0
            def check(self):
                self.calls += 1
                if self.calls == 3:
                    raise Cancelled()
        with self.assertRaises(Cancelled):
            self.app.organization.preview(project['id'], saved['sha'], CancelOnSecondEntry())
        self.assertFalse((self.data / 'recoveries').exists())
        self.assertFalse((self.data / 'organization').exists())

    def test_organization_check_service_does_not_detect_projects_or_read_recipes(self):
        (self.source / 'index.html').write_text('<title>Saved page</title>')
        (self.source / '.reprise.json').write_text('{"adapter":"static-web"}')
        project, saved = self.save()
        with patch.object(self.app.projects, 'get', side_effect=AssertionError('Project detection was invoked')), \
                patch.object(self.app.projects, 'detected', side_effect=AssertionError('Detection was invoked')), \
                patch.object(self.app.projects, 'resolve_recipe', side_effect=AssertionError('Recipe was read')), \
                patch.object(self.app.recovery, 'create', side_effect=AssertionError('Recovery was created')):
            job = self.app.execute(project['id'], 'organize-check', {'sha': saved['sha']})
            self.app.jobs.close()
            result = self.app.jobs.get(job['id'])
        self.assertEqual(result['status'], 'complete', result)
        self.assertEqual(result['request']['sha'], saved['sha'])
        self.assertEqual(result['result']['status'], 'preview')
        self.assertFalse(result['result']['readback_verified'])
        self.assertFalse((self.data / 'recoveries').exists())
        self.assertFalse((self.data / 'organization').exists())

    def test_old_named_archive_core_and_legacy_cli_restore_original_nested_git(self):
        source, group, sha, view_sha = archive_fixture(self.root, self.data)
        project = self.app.projects.record(self.app.projects.identify('Archive alias'))
        self.assertEqual(project['kind'], 'archive')
        repository = self.app.projects.repository(project['id'])
        # Listing an archive must not expand its potentially >100 MiB manifest.
        with patch('reprise.archives.ArchiveRepository.tree', side_effect=AssertionError('Archive tree expanded')):
            self.assertEqual(self.app.projects.get(project['id'])['detected']['kind'], 'archive')
        # Legacy recovery data uses the streaming reader, not the text preview cap.
        with patch.object(repository.original, 'blob', side_effect=AssertionError('Preview reader used')):
            self.assertEqual(repository.manifest(view_sha)['format'], 'reprise-selected-snapshot-v1')
        self.assertEqual(repository.blob(view_sha, 'notes.txt'), b'original archived content')
        many = {str(i): {'kind': 'file', 'mode': 0o644, 'sha256': str(i)} for i in range(201)}
        with patch.object(repository, '_paths', return_value=many):
            diff = repository.diff(view_sha)
            self.assertEqual(diff['counts']['total'], 201)
            self.assertEqual(len(diff['files']), 200)
            self.assertTrue(diff['files_truncated'])
        target = self.root / 'core-restored'
        result = self.app.recovery.create(repository, project['id'], view_sha, 'restore', str(target))
        self.assertEqual((target / '.git/config').read_bytes(), (source / '.git/config').read_bytes())
        self.assertEqual(result['report']['archive_sha'], sha)
        self.assertEqual(result['report']['view_sha'], view_sha)
        for command in [('history', '--project', 'Archive alias'),
                        ('restore', '--project', 'Archive alias', '--ref', 'v1', '--to', str(self.root / 'cli-restored')),
                        ('export', '--project', 'Archive alias', '--ref', 'v1', '--to', str(self.root / 'cli-export.zip'))]:
            result = subprocess.run([sys.executable, 'run.py', '--data', str(self.data), *command], text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout))
        self.assertEqual((self.root / 'cli-restored/.git/config').read_bytes(), (source / '.git/config').read_bytes())
        import zipfile
        with zipfile.ZipFile(self.root / 'cli-export.zip') as exported:
            self.assertIsNone(exported.testzip())
            self.assertEqual(exported.read('.git/config'), (source / '.git/config').read_bytes())
        self.app.projects.add(str(self.source), 'Legacy notes', 'folder')
        ambiguous = subprocess.run([sys.executable, 'run.py', '--data', str(self.data), 'history', '--project', 'Legacy notes'], text=True, capture_output=True, timeout=30)
        self.assertEqual(ambiguous.returncode, 1)

    def test_cli_save_named_history_and_partial_restore_share_the_core(self):
        (self.source / 'a.txt').write_text('original')
        def call(*args):
            result = subprocess.run([sys.executable, 'run.py', *args, '--data', str(self.data)], text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        saved = call('save', str(self.source), '--name', 'My notes')
        self.assertEqual(saved['status'], 'complete')
        history = call('history', '--project', 'My notes')
        self.assertEqual(len(history['commits']), 1)
        self.assertEqual(len(call('refs', '--project', 'My notes')['refs']), 1)
        difference = call('compare', '--project', 'My notes', '--base', saved['result']['sha'], '--target', saved['result']['sha'])
        self.assertEqual(difference['diff']['counts']['total'], 0)
        rejected = subprocess.run([sys.executable, 'run.py', '--data', str(self.data), 'bundle', '--project', 'My notes', '--to', str(self.root / 'unexpected.bundle')], capture_output=True, text=True, timeout=30)
        self.assertEqual(rejected.returncode, 1)
        self.assertFalse((self.root / 'unexpected.bundle').exists())
        restored = call('restore', '--project', 'My notes', '--ref', saved['result']['sha'], '--path', 'a.txt', '--to', str(self.root / 'cli-selected'))
        self.assertEqual(restored['status'], 'complete')
        self.assertEqual((self.root / 'cli-selected/a.txt').read_text(), 'original')
