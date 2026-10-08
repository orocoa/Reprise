import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from reprise.git import Repository


def git(path, *args):
    env = os.environ.copy()
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0')
    return subprocess.check_output(['git', '-C', str(path), *args], env=env, stderr=subprocess.PIPE).decode().strip()


class GitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        git(self.source, 'init', '-b', 'main')
        git(self.source, 'config', 'user.name', 'Test User')
        git(self.source, 'config', 'user.email', 'test@example.invalid')

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, name='one', content='one', message='change'):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        git(self.source, 'add', '--', name)
        git(self.source, 'commit', '-m', message)
        return git(self.source, 'rev-parse', 'HEAD')

    def test_unborn_then_root_diff_and_pagination(self):
        repo = Repository(self.source)
        self.assertIsNone(repo.info()['head'])
        self.assertEqual(repo.history()['commits'], [])
        self.assertFalse(repo.status()['dirty'])
        root = self.commit()
        self.assertEqual(repo.diff(root)['counts']['added'], 1)
        self.assertIsNone(repo.diff(root)['base'])
        second = self.commit('two')
        page = repo.history(limit=1)
        self.assertTrue(page['has_more'])
        self.assertEqual(page['commits'][0]['parents'], [root])
        self.assertEqual(repo.history(limit=1, offset=1)['commits'][0]['sha'], root)
        self.assertEqual(repo.diff(second)['base'], root)

    def test_bare_worktree_and_detached_head(self):
        sha = self.commit()
        bare = self.root / 'archive.git'
        git(self.root, 'clone', '--bare', str(self.source), str(bare))
        repo = Repository(bare)
        self.assertTrue(repo.info()['bare'])
        self.assertFalse(repo.status()['available'])
        self.assertEqual(repo.history()['commits'][0]['sha'], sha)
        worktree = self.root / 'linked'
        git(self.source, 'worktree', 'add', '--detach', str(worktree), sha)
        linked = Repository(worktree)
        self.assertEqual(linked.info()['path'], str(worktree.resolve()))
        self.assertIsNone(linked.info()['branch'])
        self.assertNotEqual(linked.info()['git_dir'], str(worktree / '.git'))
        self.assertEqual(linked.blob('HEAD', 'one'), b'one')

    def test_real_merge_parents_and_explicit_comparison(self):
        original = self.commit()
        git(self.source, 'checkout', '-b', 'feature')
        feature = self.commit('feature')
        git(self.source, 'checkout', 'main')
        main = self.commit('main')
        git(self.source, 'merge', '--no-ff', 'feature', '-m', 'merge')
        repo = Repository(self.source)
        merged = repo.resolve('HEAD')
        self.assertEqual(repo.diff(merged)['parents'], [main, feature])
        self.assertEqual(repo.diff(merged)['base'], main)
        self.assertEqual(repo.diff(merged, feature)['base'], feature)
        self.assertEqual(repo.history()['commits'][0]['parents'], [main, feature])
        git(self.source, 'tag', '-a', 'release', '-m', 'release')
        tagged = next(r for r in repo.refs() if r['name'] == 'refs/tags/release')
        self.assertEqual(tagged['sha'], merged)
        self.assertIn('refs/tags/release', repo.history()['commits'][0]['refs'])

    def test_filenames_and_renames_roundtrip(self):
        odd = 'folder/a file\twith\nnewline.txt'
        original = self.commit(odd, 'not empty' * 20)
        repo = Repository(self.source)
        self.assertEqual(repo.tree(original)[0]['path'], odd)
        self.assertEqual(repo.diff(original)['files'][0]['path'], odd)
        self.assertEqual(repo.blob(original, odd), ('not empty' * 20).encode())
        renamed = 'renamed\tfile\n.txt'
        git(self.source, 'mv', '--', odd, renamed)
        self.assertEqual(repo.status()['changes'][0]['old_path'], odd)
        git(self.source, 'commit', '-m', 'rename')
        change = repo.diff('HEAD')['files'][0]
        self.assertTrue(change['status'].startswith('R'))
        self.assertEqual((change['path'], change['old_path']), (renamed, odd))
        snapshot = self.root / 'snapshot'
        repo.materialize('HEAD', snapshot)
        self.assertEqual((snapshot / renamed).read_text(), 'not empty' * 20)

    def test_snapshot_preserves_worktree_and_skips_filters(self):
        self.commit('.gitattributes', '*.txt filter=evil\n')
        git(self.source, 'config', 'filter.evil.smudge', 'touch NEVER_EXECUTED')
        self.commit('hello.txt', 'committed')
        (self.source / 'hello.txt').write_text('dirty source')
        repo = Repository(self.source)
        before = (self.source / '.git/index').read_bytes()
        snapshot = self.root / 'snapshot'
        result = repo.materialize('HEAD', snapshot)
        self.assertEqual((snapshot / 'hello.txt').read_text(), 'committed')
        self.assertEqual((self.source / 'hello.txt').read_text(), 'dirty source')
        self.assertEqual((self.source / '.git/index').read_bytes(), before)
        self.assertFalse((self.source / 'NEVER_EXECUTED').exists())
        self.assertFalse(result['filters_executed'])
        with self.assertRaisesRegex(ValueError, 'already exists'):
            repo.materialize('HEAD', snapshot)
        with self.assertRaisesRegex(ValueError, 'outside the source'):
            repo.materialize('HEAD', self.source / 'new-snapshot')

    def test_safe_and_unsafe_symlinks(self):
        self.commit('nested/file', 'data')
        os.symlink('nested/file', self.source / 'good')
        git(self.source, 'add', 'good')
        git(self.source, 'commit', '-m', 'safe symlink')
        repo = Repository(self.source)
        snapshot = self.root / 'good-snapshot'
        repo.materialize('HEAD', snapshot)
        self.assertTrue((snapshot / 'good').is_symlink())
        self.assertEqual((snapshot / 'good').read_text(), 'data')
        os.symlink('../../outside', self.source / 'bad')
        git(self.source, 'add', 'bad')
        git(self.source, 'commit', '-m', 'unsafe symlink')
        failed = self.root / 'failed-snapshot'
        with self.assertRaisesRegex(ValueError, 'escapes'):
            repo.materialize('HEAD', failed)
        self.assertTrue(failed.is_dir())
        self.assertFalse(os.path.lexists(failed / 'bad'))

    def test_gitlinks_and_lfs_are_explicit(self):
        sha = self.commit('asset.bin', 'version https://git-lfs.github.com/spec/v1\noid sha256:' + '0' * 64 + '\nsize 10\n')
        git(self.source, 'update-index', '--add', '--cacheinfo', '160000,%s,modules/child' % sha)
        git(self.source, 'commit', '-m', 'gitlink')
        repo = Repository(self.source)
        result = repo.materialize('HEAD', self.root / 'snapshot')
        self.assertEqual(result['lfs_pointers'], ['asset.bin'])
        self.assertEqual(result['submodules'], [{'path': 'modules/child', 'sha': sha}])
        self.assertEqual(len(result['warnings']), 2)

    def test_shallow_reports_true_parent_without_fetch(self):
        parent = self.commit()
        head = self.commit('two')
        shallow = self.root / 'shallow'
        git(self.root, 'clone', '--depth=1', self.source.as_uri(), str(shallow))
        repo = Repository(shallow)
        self.assertTrue(repo.info()['shallow'])
        self.assertEqual(repo.history()['commits'][0]['parents'], [parent])
        with self.assertRaises(ValueError):
            repo.diff(head)

    def test_input_validation_and_limits(self):
        self.commit('large', 'hello')
        repo = Repository(self.source)
        for revision in ('--help', '', 'HEAD\n--help'):
            with self.assertRaises(ValueError):
                repo.resolve(revision)
        with self.assertRaises(ValueError):
            repo.blob('HEAD', '../outside')
        with self.assertRaises(ValueError):
            repo.blob('HEAD', 'large', max_bytes=4)
        for limit in (0, -1, 201):
            with self.assertRaises(ValueError):
                repo.history(limit=limit)
        with self.assertRaises(ValueError):
            Repository(self.root)

    def test_sha256_repository_when_supported(self):
        source = self.root / 'sha256'
        source.mkdir()
        try:
            git(source, 'init', '--object-format=sha256', '-b', 'main')
        except subprocess.CalledProcessError:
            self.skipTest('Git does not support SHA-256 repositories')
        git(source, 'config', 'user.name', 'Test')
        git(source, 'config', 'user.email', 'test@example.invalid')
        (source / 'index.html').write_text('<h1>SHA256</h1>')
        git(source, 'add', '.')
        git(source, 'commit', '-m', 'root')
        repo = Repository(source)
        self.assertEqual(repo.info()['object_format'], 'sha256')
        self.assertEqual(len(repo.resolve('HEAD')), 64)
        self.assertEqual(repo.diff('HEAD')['counts']['added'], 1)
        repo.materialize('HEAD', self.root / 'sha256-snapshot')


if __name__ == '__main__':
    unittest.main()
