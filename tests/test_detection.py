import json
import tempfile
import unittest
from pathlib import Path

from reprise.git import Repository
from reprise.detection import detect
from test_git import git


class DetectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.source = Path(self.tmp.name) / 'source'
        self.source.mkdir()
        git(self.source, 'init', '-b', 'main')
        git(self.source, 'config', 'user.name', 'Test')
        git(self.source, 'config', 'user.email', 'test@example.invalid')

    def tearDown(self):
        self.tmp.cleanup()

    def files(self, entries):
        for name, content in entries.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        git(self.source, 'add', '.')
        git(self.source, 'commit', '-m', 'fixture')
        return detect(Repository(self.source))

    def test_unborn_unknown_and_historical_detection(self):
        repo = Repository(self.source)
        self.assertEqual(detect(repo)['kind'], 'empty')
        old = self.files({'data.csv': 'a,b\n1,2'})
        old_sha = repo.resolve('HEAD')
        self.assertEqual(old['kind'], 'unknown')
        self.files({'index.html': '<h1>Hello</h1>'})
        self.assertEqual(detect(repo, old_sha)['kind'], 'unknown')
        self.assertEqual(detect(repo)['kind'], 'static-web')

    def test_plain_static_has_automatic_recipe_no_commands(self):
        result = self.files({'index.html': '<h1>Demo</h1><script src="app.js"></script>', 'app.js': 'console.log("ready")'})
        self.assertTrue(result['capabilities']['capture'])
        self.assertEqual(result['recipe']['adapter'], 'static-web')
        self.assertEqual(result['recipe']['commands'], {})
        self.assertEqual(result['recipe']['root'], '.')

    def test_source_framework_requires_config(self):
        result = self.files({'package.json': json.dumps({'dependencies': {'react': '1', 'vite': '1'}, 'scripts': {'dev': 'vite'}}),
                             'index.html': '<script type="module" src="/src/main.tsx"></script>', 'src/main.tsx': 'export {}'})
        self.assertEqual(result['kind'], 'web-app')
        self.assertIsNone(result['recipe'])
        self.assertFalse(result['capabilities']['run'])
        self.assertTrue(result['capabilities']['history'])
        self.assertIn('dev', result['candidates'][0]['available_scripts'])

    def test_built_output_can_run_without_building_sources(self):
        result = self.files({'package.json': '{"dependencies":{"vite":"1"}}',
                             'index.html': '<script src="/src/app.ts"></script>', 'src/app.ts': '',
                             'dist/index.html': '<script src="/assets/app.js"></script>', 'dist/assets/app.js': ''})
        self.assertEqual(result['recipe']['root'], 'dist')
        self.assertTrue(result['capabilities']['run'])

    def test_nested_pages_use_enclosing_site_root(self):
        result = self.files({'index.html': '<h1>Home</h1>', 'about/index.html': '<h1>About</h1>'})
        self.assertEqual(result['recipe']['root'], '.')
        self.assertTrue(any(c.get('nested_page') for c in result['candidates']))

    def test_nested_page_absolute_assets_resolve_at_site_root(self):
        result = self.files({'dist/index.html': '<h1>Home</h1>', 'dist/about/index.html': '<link rel="stylesheet" href="/assets/theme.css"><img src="portrait.png">',
                             'dist/assets/theme.css': 'body{}', 'dist/about/portrait.png': 'image'})
        self.assertEqual(result['recipe']['root'], 'dist')
        self.assertFalse(any('missing committed' in w for w in result['warnings']))
        nested = next(c for c in result['candidates'] if c['root'] == 'dist/about')
        self.assertEqual(nested['serving_root'], 'dist')
        self.assertEqual(nested['missing_assets'], [])

    def test_nested_package_keeps_its_own_asset_root(self):
        result = self.files({'index.html': '<h1>Root site</h1>', 'apps/demo/package.json': '{}', 'apps/demo/index.html': '<h1>Demo</h1>',
                             'apps/demo/about/index.html': '<link rel="stylesheet" href="/assets/demo.css">', 'apps/demo/assets/demo.css': 'body{}'})
        self.assertIsNone(result['recipe'])
        self.assertFalse(any('missing committed' in w for w in result['warnings']))
        nested = next(c for c in result['candidates'] if c['root'] == 'apps/demo/about')
        self.assertEqual(nested['serving_root'], 'apps/demo')

    def test_canvas_rendering_does_not_imply_game(self):
        result = self.files({'index.html': '<canvas id="game"></canvas><script src="game.js"></script>', 'game.js': ''})
        self.assertEqual(result['kind'], 'static-web')
        self.assertTrue(any('Canvas rendering' in signal for signal in result['signals']))
        self.assertEqual(result['recipe']['adapter'], 'static-web')
        self.assertTrue(result['capabilities']['capture'])

    def test_rendering_library_is_not_a_game_engine(self):
        result = self.files({'package.json': '{"dependencies":{"three":"1"}}'})
        self.assertEqual(result['kind'], 'web-app')
        self.assertNotEqual(result['kind'], 'web-game')

    def test_explicit_game_engine_is_recognized(self):
        result = self.files({'package.json': '{"dependencies":{"phaser":"1"}}', 'index.html': '<canvas></canvas>'})
        self.assertEqual(result['kind'], 'web-game')
        self.assertEqual(result['recipe']['adapter'], 'static-web')

    def test_native_game_and_cli_dont_claim_browser_capture(self):
        result = self.files({'game/project.godot': 'config_version=5', 'tools/pyproject.toml': '[project]\nname="tool"'})
        self.assertEqual({c['kind'] for c in result['candidates']}, {'native-game', 'cli'})
        self.assertIsNone(result['recipe'])
        self.assertTrue(result['capabilities']['manual'])

    def test_monorepo_requires_selection(self):
        result = self.files({'apps/one/index.html': '<h1>one</h1>', 'apps/two/index.html': '<h1>two</h1>'})
        self.assertEqual(len(result['candidates']), 2)
        self.assertIsNone(result['recipe'])
        self.assertFalse(result['capabilities']['run'])
        self.assertTrue(any('Multiple runnable' in w for w in result['warnings']))

    def test_missing_assets_and_lfs_are_visible(self):
        result = self.files({'index.html': '<img src="gone.jpg"><script src="https://example.invalid/app.js"></script>',
                             '.gitattributes': '*.bin filter=lfs diff=lfs merge=lfs -text\n'})
        self.assertEqual(result['candidates'][0]['missing_assets'], ['gone.jpg'])
        self.assertTrue(any('missing committed' in w for w in result['warnings']))
        self.assertTrue(any('remote assets' in w for w in result['warnings']))
        self.assertTrue(any('Git LFS' in w for w in result['warnings']))

    def test_package_scripts_are_never_executed(self):
        result = self.files({'package.json': '{"scripts":{"start":"touch OWNED"}}'})
        self.assertFalse((self.source / 'OWNED').exists())
        self.assertIsNone(result['recipe'])
        self.assertFalse(result['capabilities']['run'])


if __name__ == '__main__':
    unittest.main()
