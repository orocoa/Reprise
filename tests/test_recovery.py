"""The UI and agent CLI recover exact blobs without touching registered sources."""
import json
import os
from pathlib import Path
import time
import unittest
import zipfile

from reprise.cancellation import Cancellation, Cancelled
from reprise.service import Reprise
from reprise.storage import write_json
from test_git import git
from test_runtime import fixture, commit_repo


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('portable-recovery')
        self.repository = commit_repo(self.root / 'source with spaces 中文')
        self.sha = self.repository.resolve('HEAD')
        self.app = Reprise(self.root / 'data')
        self.project = self.app.projects.add(str(self.repository.path))['id']

    def tearDown(self):
        self.app.close()

    def wait(self, job):
        deadline = time.monotonic() + 15
        while job['status'] in ('queued', 'running', 'cancelling') and time.monotonic() < deadline:
            time.sleep(.03)
            job = self.app.jobs.get(job['id'])
        self.assertEqual(job['status'], 'complete', job)
        return job['result']

    def test_restore_and_zip_use_requested_sha_preserve_dirty_source_and_permissions(self):
        source = self.repository.path
        expected = self.repository.blob(self.sha, 'index.html')
        (source / 'index.html').write_text('dirty source')
        (source / 'untracked').write_text('retain me')
        before = git(source, 'status', '--porcelain=v1')
        target = self.root / 'new recovered 中文'
        result = self.wait(self.app.execute(self.project, 'restore', {'sha': self.sha, 'to': str(target)}))
        self.assertEqual(result['sha'], self.sha)
        self.assertEqual((target / 'index.html').read_bytes(), expected)
        self.assertFalse((target / '.git').exists())
        self.assertTrue(result['report']['object_hashes_verified'])
        exported = self.wait(self.app.execute(self.project, 'export', {'sha': self.sha}))
        with zipfile.ZipFile(self.app.recovery.download(exported['id'])) as archive:
            self.assertEqual(archive.read('index.html'), expected)
        self.assertEqual(git(source, 'status', '--porcelain=v1'), before)
        self.assertEqual((source / 'index.html').read_text(), 'dirty source')
        self.assertEqual((source / 'untracked').read_text(), 'retain me')
        with self.assertRaisesRegex(ValueError, '已经存在'):
            self.app.execute(self.project, 'restore', {'sha': self.sha, 'to': str(target)})

    def test_protects_all_sources_symlink_parents_and_linked_common_git(self):
        other = commit_repo(self.root / 'other source')
        self.app.projects.add(str(other.path))
        alias = self.root / 'alias'
        alias.symlink_to(other.path, target_is_directory=True)
        for path in (other.path / 'new', alias / 'new', self.repository.git_dir / 'new'):
            with self.assertRaisesRegex(ValueError, '源仓库'):
                self.app.recovery.destination(str(path))
        worktree = self.root / 'linked'
        git(other.path, 'worktree', 'add', '-b', 'linked', str(worktree))
        # Only the linked worktree is registered: common Git storage is still protected.
        isolated = Reprise(self.root / 'linked-data')
        try:
            isolated.projects.add(str(worktree))
            with self.assertRaisesRegex(ValueError, '源仓库'):
                isolated.recovery.destination(str(other.git_dir / 'new'))
        finally:
            isolated.close()

    def test_zip_preserves_executable_and_safe_symlink_and_reports_lfs(self):
        source = self.repository.path
        script = source / 'script.sh';script.write_text('#!/bin/sh\nexit 0\n');script.chmod(0o755)
        (source / 'internal-link').symlink_to('index.html')
        git(source, 'add', '.');git(source, 'commit', '-m', 'Modes and links')
        sha = self.repository.resolve('HEAD')
        result = self.app.recovery.create(self.repository, self.project, sha, 'export')
        with zipfile.ZipFile(result['path']) as archive:
            self.assertTrue((archive.getinfo('script.sh').external_attr >> 16) & 0o111)
            self.assertEqual(archive.read('internal-link'), b'index.html')
            self.assertEqual((archive.getinfo('internal-link').external_attr >> 16) & 0o170000, 0o120000)

    def test_cancelled_and_invalid_output_is_retained_and_cannot_download_arbitrary_paths(self):
        marker = self.root / 'cancel.json';write_json(marker, {})
        target = self.root / 'cancelled-target'
        with self.assertRaises(Cancelled):
            self.app.recovery.create(self.repository, self.project, self.sha, 'restore', str(target), Cancellation(marker))
        records = list(self.app.recovery.directory.glob('*/receipt.json'))
        self.assertEqual(json.loads(records[0].read_text())['status'], 'incomplete')
        self.assertFalse(target.exists())
        for bad in ('../../etc/passwd', 'a'*31, 'g'*32):
            with self.assertRaises(KeyError):self.app.recovery.download(bad)
        result = self.app.recovery.create(self.repository, self.project, self.sha, 'export', str(self.root / 'external.zip'))
        self.assertNotIn('download_url', result)
        with self.assertRaises(ValueError):self.app.recovery.download(result['id'])
