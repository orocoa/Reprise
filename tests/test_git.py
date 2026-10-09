import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from reprise.git import Repository


def git(path, *args):
    env = os.environ.copy()
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0')
    return subprocess.check_output(['git', '-C', str(path), *args], env=env, stderr=subprocess.PIPE).decode().strip()


class GitTests(unittest.TestCase):
    def setUp(self):
        artifacts = Path(__file__).resolve().parents[1] / 'work' / 'test-artifacts'
        artifacts.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix='git-', dir=artifacts))
        self.source = self.root / 'source'
        self.source.mkdir()
        git(self.source, 'init', '-b', 'main')
        git(self.source, 'config', 'user.name', 'Test User')
        git(self.source, 'config', 'user.email', 'test@example.invalid')

    def commit(self, name='one', content='one', message='change'):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        git(self.source, 'add', '--', name)
        git(self.source, 'commit', '-m', message)
        return git(self.source, 'rev-parse', 'HEAD')

    def test_unborn_then_root_diff_and_pagination(self):
        repo = Repository(self.source, status_directory=self.root / 'status-views')
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
        repo = Repository(self.source, status_directory=self.root / 'status-views')
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
        repo = Repository(self.source, status_directory=self.root / 'status-views')
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
        repo = Repository(self.source, status_directory=self.root / 'status-views')
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

    def filter_command(self, name, process=False):
        marker = self.root / (name + '-executed')
        script = self.root / (name + '.py')
        script.write_text('import sys\nfrom pathlib import Path\n' +
                          'Path(%r).write_text("unexpected filter execution")\n' % str(marker) +
                          ('sys.exit(9)\n' if process else 'sys.stdout.buffer.write(sys.stdin.buffer.read())\n'))
        return shlex.join([sys.executable, str(script)]), marker

    def test_status_disables_clean_filter_and_preserves_index(self):
        self.commit('.gitattributes', '*.txt filter=audit\n')
        self.commit('note.txt', 'committed\n')
        repo = Repository(self.source, status_directory=self.root / 'status-views')
        command, marker = self.filter_command('clean')
        git(self.source, 'config', 'filter.audit.clean', command)
        git(self.source, 'config', 'filter.audit.required', 'true')
        config = (self.source / '.git/config').read_bytes()
        index = (self.source / '.git/index').read_bytes()
        # Identical size forces Git to inspect contents rather than merely notice
        # a changed size; this was the release-audit execution path.
        (self.source / 'note.txt').write_text('different\n')
        state = repo.status()
        self.assertEqual(state['changes'], [{'path': 'note.txt', 'status': ' M'}])
        self.assertTrue(state['dirty'])
        self.assertEqual(state['disabled_filters'], ['audit'])
        self.assertFalse(state['filters_executed'])
        self.assertFalse(marker.exists())
        # A touched file with the original bytes stays clean without calling the
        # filter; neither the source index nor the filter configuration is edited.
        (self.source / 'note.txt').write_text('committed\n')
        self.assertFalse(repo.status()['dirty'])
        self.assertEqual((self.source / '.git/config').read_bytes(), config)
        self.assertEqual((self.source / '.git/index').read_bytes(), index)

    def test_included_process_filter_is_blocked_for_all_read_paths(self):
        self.commit('.gitattributes', '*.txt text eol=crlf filter=Audit.with.dots\n')
        sha = self.commit('note.txt', 'first\r\n')
        command, marker = self.filter_command('process', process=True)
        include = self.root / 'included-filter.config'
        subprocess.check_call(['git', 'config', '--file', str(include),
                               'filter.Audit.with.dots.process', command])
        subprocess.check_call(['git', 'config', '--file', str(include),
                               'filter.Audit.with.dots.clean', command])
        subprocess.check_call(['git', 'config', '--file', str(include),
                               'filter.Audit.with.dots.required', 'true'])
        git(self.source, 'config', 'include.path', str(include))
        repo = Repository(self.source, status_directory=self.root / 'status-views')
        index = (self.source / '.git/index').read_bytes()
        config = (self.source / '.git/config').read_bytes()
        self.assertEqual(repo.info()['head'], sha)
        self.assertTrue(repo.refs())
        self.assertEqual(repo.history()['commits'][0]['sha'], sha)
        self.assertTrue(repo.tree(sha))
        self.assertEqual(repo.blob(sha, 'note.txt'), b'first\n')
        self.assertEqual(repo.diff(sha)['counts']['added'], 1)
        result = repo.materialize(sha, self.root / 'no-filter-snapshot')
        self.assertFalse(result['filters_executed'])
        # Built-in CRLF normalization still works with custom drivers disabled.
        (self.source / 'note.txt').write_bytes(b'first\r\n')
        self.assertFalse(repo.status()['dirty'])
        (self.source / 'note.txt').write_bytes(b'other\r\n')
        self.assertEqual(repo.status()['changes'], [{'path': 'note.txt', 'status': ' M'}])
        self.assertFalse(marker.exists())
        self.assertEqual((self.source / '.git/index').read_bytes(), index)
        self.assertEqual((self.source / '.git/config').read_bytes(), config)

    def test_environment_and_global_filter_config_are_not_inherited(self):
        self.commit('.gitattributes', '*.txt filter=external\n')
        self.commit('note.txt', 'committed\n')
        command, marker = self.filter_command('external', process=True)
        global_config = self.root / 'global.config'
        subprocess.check_call(['git', 'config', '--file', str(global_config), 'filter.external.clean', command])
        (self.source / 'note.txt').write_text('different\n')
        with mock.patch.dict(os.environ, {
            'GIT_CONFIG_GLOBAL': str(global_config), 'GIT_CONFIG_SYSTEM': str(global_config),
            'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'filter.external.process',
            'GIT_CONFIG_VALUE_0': command,
        }):
            state = Repository(self.source, status_directory=self.root / 'status-views').status()
        self.assertEqual(state['changes'], [{'path': 'note.txt', 'status': ' M'}])
        self.assertEqual(state['disabled_filters'], [])
        self.assertFalse(marker.exists())

    def test_status_ignores_driver_added_after_config_snapshot(self):
        self.commit('.gitattributes', '*.txt filter=late\n')
        self.commit('note.txt', 'committed\n')
        include = self.root / 'racing-include.config'
        include.write_text('[core]\nfileMode = true\n')
        git(self.source, 'config', 'include.path', str(include))
        command, marker = self.filter_command('late-driver', process=True)
        (self.source / 'note.txt').write_text('different\n')
        repo = Repository(self.source, status_directory=self.root / 'status-views')
        original = repo._run
        injected = False

        def change_config_after_read(*args, **kwargs):
            nonlocal injected
            result = original(*args, **kwargs)
            if args == ('config', '--null', '--list', '--includes') and not injected:
                injected = True
                subprocess.check_call(['git', 'config', '--file', str(include), 'filter.late.process', command])
                subprocess.check_call(['git', 'config', '--file', str(include), 'filter.late.required', 'true'])
                git(self.source, 'config', 'filter.late.clean', command)
            return result

        with mock.patch.object(repo, '_run', side_effect=change_config_after_read):
            state = repo.status()
        self.assertTrue(injected)
        self.assertEqual(state['changes'], [{'path': 'note.txt', 'status': ' M'}])
        self.assertFalse(marker.exists())
        config = (Path(state['status_metadata']) / 'config').read_text()
        self.assertNotIn('filter', config)
        self.assertNotIn('include', config)

    def test_status_view_reuses_private_split_index_for_linked_worktree(self):
        sha = self.commit('note.txt', 'first\n')
        worktree = self.root / 'linked'
        git(self.source, 'worktree', 'add', '--detach', str(worktree), sha)
        git(worktree, 'update-index', '--split-index')
        linked = Repository(worktree, status_directory=self.root / 'status-views')
        index_path = linked._git_path('index')
        preserved = {path: path.read_bytes() for path in index_path.parent.glob('sharedindex.*')}
        preserved[index_path] = index_path.read_bytes()
        self.assertGreater(len(preserved), 1)
        state = linked.status()
        self.assertFalse(state['dirty'])
        view = Path(state['status_metadata'])
        self.assertEqual(view.stat().st_mode & 0o777, 0o700)
        self.assertEqual((view / 'index').stat().st_mode & 0o777, 0o600)
        self.assertFalse((view / 'index').is_symlink())
        self.assertEqual(linked.status()['status_metadata'], str(view))
        (worktree / 'note.txt').write_text('other\n')
        self.assertEqual(linked.status()['changes'], [{'path': 'note.txt', 'status': ' M'}])
        for path, content in preserved.items():
            self.assertEqual(path.read_bytes(), content)
        unsafe = self.source / '.git' / 'status-must-not-be-created'
        with self.assertRaisesRegex(ValueError, 'outside the source'):
            Repository(worktree, status_directory=unsafe).status()
        self.assertFalse(unsafe.exists())

    def test_status_preserves_native_encoding_and_info_excludes(self):
        self.commit('.gitattributes', 'encoded.txt working-tree-encoding=UTF-16\n')
        encoded = self.source / 'encoded.txt'
        encoded.write_bytes('hello'.encode('utf-16'))
        git(self.source, 'add', 'encoded.txt')
        git(self.source, 'commit', '-m', 'encoded fixture')
        (self.source / '.git/info/exclude').write_text('ignored-output.txt\n')
        (self.source / 'ignored-output.txt').write_text('untracked but excluded')
        repo = Repository(self.source, status_directory=self.root / 'status-views')
        self.assertEqual(repo.blob('HEAD', 'encoded.txt'), b'hello')
        encoded.write_bytes('hello'.encode('utf-16'))
        self.assertFalse(repo.status()['dirty'])
        encoded.write_bytes('world'.encode('utf-16'))
        self.assertEqual(repo.status()['changes'], [{'path': 'encoded.txt', 'status': ' M'}])

    def test_status_does_not_run_filters_in_submodule_worktree(self):
        child_source = self.root / 'child-source'
        child_source.mkdir()
        git(child_source, 'init', '-b', 'main')
        git(child_source, 'config', 'user.name', 'Test User')
        git(child_source, 'config', 'user.email', 'test@example.invalid')
        (child_source / '.gitattributes').write_text('*.txt filter=nested\n')
        (child_source / 'note.txt').write_text('first\n')
        git(child_source, 'add', '.')
        git(child_source, 'commit', '-m', 'child first')
        first = git(child_source, 'rev-parse', 'HEAD')
        (child_source / 'note.txt').write_text('later\n')
        git(child_source, 'add', '.')
        git(child_source, 'commit', '-m', 'child later')
        git(self.source, '-c', 'protocol.file.allow=always', 'submodule', 'add', str(child_source), 'child')
        git(self.source, 'commit', '-m', 'submodule fixture')
        child = self.source / 'child'
        command, marker = self.filter_command('nested', process=True)
        git(child, 'config', 'filter.nested.process', command)
        git(child, 'config', 'filter.nested.required', 'true')
        (child / 'note.txt').write_text('dirty\n')
        repo = Repository(self.source, status_directory=self.root / 'status-views')
        self.assertFalse(repo.status()['dirty'])
        self.assertFalse(marker.exists())
        # Gitlink identity differences remain visible while nested worktree
        # changes continue to be intentionally excluded.
        git(child, 'update-ref', 'HEAD', first)
        self.assertEqual(repo.status()['changes'], [{'path': 'child', 'status': ' M'}])
        self.assertFalse(marker.exists())

    def test_safe_and_unsafe_symlinks(self):
        self.commit('nested/file', 'data')
        os.symlink('nested/file', self.source / 'good')
        git(self.source, 'add', 'good')
        git(self.source, 'commit', '-m', 'safe symlink')
        repo = Repository(self.source, status_directory=self.root / 'status-views')
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
        repo = Repository(self.source, status_directory=self.root / 'status-views')
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
        repo = Repository(self.source, status_directory=self.root / 'status-views')
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
        # Retained fixtures live below the project checkout; an invalid gitfile
        # prevents Git from discovering that unrelated ancestor repository.
        (self.root / '.git').write_text('invalid repository metadata\n')
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
        self.assertFalse(repo.status()['dirty'])
        repo.materialize('HEAD', self.root / 'sha256-snapshot')


if __name__ == '__main__':
    unittest.main()
