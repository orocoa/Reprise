"""Quick preparation is exact-version, read-only and never infers commands."""
import json
import subprocess
import unittest

from reprise.git import Repository
from reprise.projects import ProjectStore
from reprise.quick_preview import prepare_quick_preview
from reprise.recipes import validate_recipe
from test_git import git
from test_runtime import fixture


class QuickPreviewTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('quick-preview')
        self.source = self.root / 'source'
        self.source.mkdir()
        git(self.source, 'init', '-b', 'main')
        git(self.source, 'config', 'user.name', 'Reprise test')
        git(self.source, 'config', 'user.email', 'test@example.invalid')
        self.repository = Repository(self.source)

    def commit(self, files):
        for name, content in files.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        git(self.source, 'add', '.')
        git(self.source, 'commit', '-m', 'Synthetic webpage')
        return self.repository.resolve('HEAD')

    def test_static_proposal_is_normalized_and_requires_save(self):
        sha = self.commit({'index.html': '<h1>First draft</h1><script src="app.js"></script>', 'app.js': ''})
        before = git(self.source, 'status', '--porcelain')
        result = prepare_quick_preview(self.repository, sha)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['sha'], sha)
        self.assertTrue(result['requires_save'])
        self.assertEqual(result['recipe'], validate_recipe(result['recipe']))
        self.assertEqual(result['recipe']['commands'], {})
        self.assertEqual(result['recipe']['network'], 'local')
        self.assertEqual(git(self.source, 'status', '--porcelain'), before)
        self.assertEqual(sorted(p.name for p in self.source.iterdir()), ['.git', 'app.js', 'index.html'])

    def test_uses_selected_history_not_head_or_working_files(self):
        old = self.commit({'index.html': '<h1>Saved static page</h1>'})
        current = self.commit({'index.html': '<script src="app.tsx"></script>', 'app.tsx': 'export {}'})
        (self.source / 'index.html').write_text('<h1>Unsaved static page</h1>')
        self.assertEqual(prepare_quick_preview(self.repository, old)['status'], 'ready')
        self.assertEqual(prepare_quick_preview(self.repository, current)['status'], 'needs-configuration')
        self.assertEqual((self.source / 'index.html').read_text(), '<h1>Unsaved static page</h1>')
        for revision in ('HEAD', old[:8], 'main', None):
            with self.subTest(revision=revision), self.assertRaisesRegex(ValueError, 'exact version SHA'):
                prepare_quick_preview(self.repository, revision)

    def test_command_config_is_not_inherited_or_run(self):
        sha = self.commit({'index.html': '<h1>Local page</h1>', '.reprise.json': json.dumps({
            'adapter': 'command-web', 'commands': {'start': ['touch', 'SHOULD-NOT-EXIST']}})})
        result = prepare_quick_preview(self.repository, sha)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['recipe']['adapter'], 'static-web')
        self.assertEqual(result['recipe']['commands'], {})
        self.assertFalse((self.source / 'SHOULD-NOT-EXIST').exists())

    def test_framework_source_requires_configuration(self):
        sha = self.commit({'index.html': '<div id="root"></div>',
                           'package.json': '{"dependencies":{"vite":"1"},"scripts":{"dev":"vite"}}'})
        result = prepare_quick_preview(self.repository, sha)
        self.assertEqual(result['status'], 'needs-configuration')
        self.assertIsNone(result['recipe'])

    def test_built_output_is_available_without_running_source_build(self):
        sha = self.commit({'package.json': '{"dependencies":{"vite":"1"}}',
                           'index.html': '<script src="app.ts"></script>', 'app.ts': '',
                           'dist/index.html': '<script src="/assets/app.js"></script>', 'dist/assets/app.js': ''})
        result = prepare_quick_preview(self.repository, sha)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['recipe']['root'], 'dist')

    def test_multiple_sites_require_explicit_choice(self):
        sha = self.commit({'one/index.html': '<h1>One</h1>', 'two/index.html': '<h1>Two</h1>'})
        result = prepare_quick_preview(self.repository, sha)
        self.assertEqual(result['status'], 'choose-entry')
        self.assertIsNone(result['recipe'])
        self.assertEqual(prepare_quick_preview(self.repository, sha, root='two')['recipe']['root'], 'two')
        with self.assertRaises(ValueError):
            prepare_quick_preview(self.repository, sha, root='../other')

    def test_pages_within_one_site_do_not_force_project_choice(self):
        sha = self.commit({'index.html': '<h1>Home</h1>', 'about/index.html': '<h1>About</h1>'})
        result = prepare_quick_preview(self.repository, sha)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(len(result['candidates']), 1)

    def test_missing_asset_is_not_presented_as_ready(self):
        sha = self.commit({'index.html': '<img src="missing.png">'})
        result = prepare_quick_preview(self.repository, sha)
        self.assertEqual(result['status'], 'needs-configuration')
        self.assertEqual(result['reason'], 'missing-assets')
        self.assertEqual(result['candidates'][0]['missing_assets'], ['missing.png'])

    def test_unsupported_static_root_is_diagnostic_not_an_execution_proposal(self):
        sha = self.commit({'site:one/index.html': '<h1>Saved page with unusual directory name</h1>'})
        result = prepare_quick_preview(self.repository, sha)
        self.assertEqual(result['status'], 'needs-configuration')
        self.assertEqual(result['reason'], 'entry-path-needs-configuration')
        self.assertIsNone(result['recipe'])

    def test_remote_assets_do_not_silently_enable_network(self):
        sha = self.commit({'index.html': '<script src="https://example.invalid/app.js"></script>'})
        result = prepare_quick_preview(self.repository, sha)
        self.assertEqual(result['status'], 'needs-configuration')
        self.assertEqual(result['reason'], 'remote-assets')
        self.assertIsNone(result['recipe'])

    def test_remote_navigation_link_is_not_a_remote_asset(self):
        sha = self.commit({'index.html': '<a href="https://example.invalid/">External link</a>'})
        self.assertEqual(prepare_quick_preview(self.repository, sha)['status'], 'ready')

    def test_one_invalid_site_does_not_silently_choose_another(self):
        sha = self.commit({'one/index.html': '<img src="missing.png">', 'two/index.html': '<h1>Two</h1>'})
        self.assertEqual(prepare_quick_preview(self.repository, sha)['status'], 'choose-entry')
        self.assertEqual(prepare_quick_preview(self.repository, sha, root='one')['status'], 'needs-configuration')
        self.assertEqual(prepare_quick_preview(self.repository, sha, root='two')['status'], 'ready')

    def test_folder_snapshot_preparation_does_not_save_approval(self):
        folder = self.root / 'ordinary-folder'
        folder.mkdir()
        (folder / 'index.html').write_text('<h1>Folder page</h1>')
        store = ProjectStore(self.root / 'data')
        identifier = store.add(str(folder), kind='folder')['id']
        sha = store.snapshot(identifier, 'First draft')['sha']
        before = store.file.read_bytes()
        result = prepare_quick_preview(store.repository(identifier), sha)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(store.file.read_bytes(), before)
        self.assertFalse(store.get(identifier, sha)['recipe_approved'])
        self.assertFalse((folder / '.git').exists())

    def test_sha256_repository_uses_complete_object_id(self):
        folder = self.root / 'sha256-source'
        folder.mkdir()
        try:
            git(folder, 'init', '--object-format=sha256', '-b', 'main')
        except subprocess.CalledProcessError:
            self.skipTest('Host Git does not support SHA-256 repositories')
        git(folder, 'config', 'user.name', 'Reprise test')
        git(folder, 'config', 'user.email', 'test@example.invalid')
        (folder / 'index.html').write_text('<h1>SHA-256 page</h1>')
        git(folder, 'add', '.')
        git(folder, 'commit', '-m', 'Synthetic SHA-256 page')
        repository = Repository(folder)
        sha = repository.resolve('HEAD')
        self.assertEqual(len(sha), 64)
        result = prepare_quick_preview(repository, sha)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['sha'], sha)


if __name__ == '__main__':
    unittest.main()
