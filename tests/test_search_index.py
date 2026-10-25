"""A bounded name index is equivalent to exact first-parent diffs and stays read-only."""
import hashlib
import json
import subprocess
import threading
import unittest
import urllib.request
from pathlib import Path

from reprise.git import Repository
from reprise.service import Reprise
from reprise.server import LocalServer
from reprise.workspace import search_index
from test_git import git
from test_runtime import fixture, commit_repo


def fingerprint(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


class SearchIndexTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('search-index')
        self.repo = commit_repo(self.root / 'source')
        self.app = Reprise(self.root / 'state')

    def tearDown(self):
        self.app.close()

    def test_batch_equals_root_rename_empty_and_first_parent_merge_diffs(self):
        source = self.repo.work_tree
        root = self.repo.resolve('HEAD')
        git(source, 'branch', 'topic', root)
        (source / 'odd\tname\nfile.txt').write_text('Keep exact content.\n')
        (source / root).write_text('A filename equal to a requested commit SHA.\n')
        git(source, 'add', '.'); git(source, 'commit', '-m', 'Add unusual names')
        added = self.repo.resolve('HEAD')
        (source / 'odd\tname\nfile.txt').rename(source / 'renamed\nfile.txt')
        git(source, 'add', '-A'); git(source, 'commit', '-m', 'Rename exact content')
        renamed = self.repo.resolve('HEAD')
        git(source, 'commit', '--allow-empty', '-m', 'No file changes')
        empty = self.repo.resolve('HEAD')
        branch = git(source, 'branch', '--show-current')
        git(source, 'switch', 'topic')
        (source / 'topic.txt').write_text('Another parent.\n')
        git(source, 'add', '.'); git(source, 'commit', '-m', 'Topic change')
        topic = self.repo.resolve('HEAD')
        git(source, 'switch', branch)
        git(source, 'merge', '--no-ff', 'topic', '-m', 'Merge topic')
        merged = self.repo.resolve('HEAD')
        project = self.app.projects.add(str(source))
        before = fingerprint(source)
        shas = [merged, root, renamed, empty, topic, added]
        actual = search_index(self.app, project['id'], shas)['paths']
        for sha in shas:
            expected = [p for f in self.repo.diff(sha)['files'] for p in (f['path'], f.get('old_path')) if p]
            self.assertEqual(sorted(actual[sha]), sorted(expected), sha)
        self.assertEqual(actual[empty], [])
        self.assertEqual(actual[merged], ['topic.txt'])
        self.assertEqual(before, fingerprint(source))

    def test_input_is_full_sha_only_and_bounded(self):
        for value in (None, 'HEAD', ['HEAD'], ['a' * 40 + '\nHEAD'], ['a' * 40] * 129, [False]):
            with self.assertRaises(ValueError):
                self.repo.search_index(value)
        with self.assertRaises(ValueError):
            self.repo.search_index(['0' * 40])
        self.assertEqual(self.repo.search_index([]), {})

    def test_shallow_missing_parent_is_not_indexed_as_a_root(self):
        source = self.repo.work_tree
        (source / 'second.txt').write_text('Second revision')
        git(source, 'add', '.'); git(source, 'commit', '-m', 'Second')
        shallow = self.root / 'shallow'
        subprocess.run(['git', 'clone', '-q', '--depth=1', source.as_uri(), str(shallow)], check=True)
        repository = Repository(shallow)
        before = fingerprint(shallow)
        with self.assertRaisesRegex(ValueError, 'parent is unavailable'):
            repository.search_index([repository.resolve('HEAD')])
        self.assertEqual(before, fingerprint(shallow))

    def test_sha256_repositories_keep_full_identifiers(self):
        source = self.root / 'sha256'; source.mkdir()
        result = subprocess.run(['git', '-C', str(source), 'init', '-q', '--object-format=sha256', '-b', 'main'], capture_output=True)
        if result.returncode:
            self.skipTest('Installed Git does not support SHA-256')
        git(source, 'config', 'user.name', 'Fixture'); git(source, 'config', 'user.email', 'fixture@example.invalid')
        (source / 'name.txt').write_text('Content')
        git(source, 'add', '.'); git(source, 'commit', '-m', 'Initial')
        repository = Repository(source); sha = repository.resolve('HEAD')
        self.assertEqual(len(sha), 64)
        self.assertEqual(repository.search_index([sha]), {sha: ['name.txt']})

    def test_folder_snapshots_use_their_own_diff_contract(self):
        source = self.root / 'folder'; source.mkdir()
        (source / 'one.txt').write_text('First')
        p = self.app.projects.add(str(source), kind='folder')
        first = self.app.projects.snapshot(p['id'])['sha']
        (source / 'two.txt').write_text('Second')
        second = self.app.projects.snapshot(p['id'])['sha']
        actual = search_index(self.app, p['id'], [first, second])['paths']
        self.assertEqual(actual[first], ['one.txt'])
        self.assertEqual(actual[second], ['two.txt'])

    def test_http_batch_route_returns_only_paths(self):
        p = self.app.projects.add(str(self.repo.work_tree)); sha = self.repo.resolve('HEAD')
        server = LocalServer(('127.0.0.1', 0), self.app)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            request = urllib.request.Request('http://127.0.0.1:%s/api/projects/%s/search-index' % (server.server_port, p['id']),
                data=json.dumps({'shas': [sha]}).encode(), method='POST',
                headers={'Content-Type': 'application/json', 'X-Reprise-Token': server.token})
            with urllib.request.urlopen(request) as response:
                value = json.load(response)
            expected = [f['path'] for f in self.repo.diff(sha)['files']]
            self.assertEqual(value, {'paths': {sha: expected}})
        finally:
            server.shutdown(); server.server_close(); thread.join(2)
