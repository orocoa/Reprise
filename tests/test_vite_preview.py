"""A framework proposal is exact-version data until explicitly saved and run."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from reprise.projects import ProjectStore
from reprise.recipes import validate_recipe
from reprise.vite_preview import prepare_vite_preview


def manifest(dev='vite', **extra):
    return {'name': 'reprise-synthetic-vite', 'private': True,
            'scripts': {'dev': dev}, 'devDependencies': {'vite': '7.1.12'}, **extra}


def lock(package):
    return {'lockfileVersion': 3, 'packages': {
        '': {key: package[key] for key in ('dependencies', 'devDependencies', 'optionalDependencies') if key in package},
        'node_modules/vite': {'version': '7.1.12', 'resolved': 'https://registry.npmjs.org/vite/-/vite-7.1.12.tgz'}}}


class VitePreviewTests(unittest.TestCase):
    def setUp(self):
        artifacts = Path(__file__).resolve().parents[1] / 'work/test-artifacts/technical-refinement-20261024/vite'
        artifacts.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix='contracts-', dir=artifacts))
        self.source = self.root / 'source'
        self.source.mkdir()
        self.store = ProjectStore(self.root / 'state')
        self.identifier = self.store.add(str(self.source), kind='folder')['id']
        self.repository = self.store.repository(self.identifier)

    def write_package(self, root='.', package=None, locked=True):
        package = manifest() if package is None else package
        folder = self.source / root
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'package.json').write_text(json.dumps(package))
        if locked:
            (folder / 'package-lock.json').write_text(json.dumps(lock(package)))
        (folder / 'index.html').write_text('<div id="root"></div><script type="module" src="/src/main.jsx"></script>')
        return folder

    def snapshot(self):
        return self.store.snapshot(self.identifier, 'Synthetic Vite draft')['sha']

    def test_plan_does_not_execute_save_approval_or_modify_source(self):
        package = manifest()
        package['scripts'].update(preinstall='node install.js', predev='node before.js')
        self.write_package(package=package)
        sha = self.snapshot()
        original = self.store.file.read_bytes()
        source = {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob('*') if p.is_file()}
        with patch('subprocess.Popen', wraps=subprocess.Popen) as processes:
            plan = prepare_vite_preview(self.repository, sha)
        # The snapshot backend uses read-only Git commands; no npm, node,
        # version probe or application process may be started during planning.
        self.assertTrue(all(Path(call.args[0][0]).name == 'git' for call in processes.call_args_list))
        self.assertEqual(plan['status'], 'needs-approval')
        self.assertEqual(plan['recipe'], validate_recipe(plan['recipe']))
        self.assertEqual(plan['recipe']['adapter'], 'command-web')
        self.assertEqual(plan['recipe']['network'], 'local')
        self.assertTrue(plan['requires_save'])
        self.assertTrue(plan['requires_command_approval'])
        self.assertTrue(plan['execution']['runs_vite_config'])
        self.assertEqual(plan['execution']['scripts']['preinstall'], 'node install.js')
        self.assertEqual(plan['execution']['scripts']['predev'], 'node before.js')
        self.assertEqual(self.store.file.read_bytes(), original)
        self.assertFalse(self.store.get(self.identifier, sha)['recipe_approved'])
        self.assertEqual({p.relative_to(self.source): p.read_bytes() for p in self.source.rglob('*') if p.is_file()}, source)

    def test_uses_exact_snapshot_not_dirty_working_files(self):
        self.write_package()
        sha = self.snapshot()
        (self.source / 'package.json').write_text(json.dumps(manifest('arbitrary-command')))
        self.assertEqual(prepare_vite_preview(self.repository, sha)['status'], 'needs-approval')
        new = self.snapshot()
        self.assertEqual(prepare_vite_preview(self.repository, new)['reason'], 'dev-script-needs-configuration')
        for value in ('HEAD', sha[:12], None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'exact version SHA'):
                prepare_vite_preview(self.repository, value)

    def test_missing_lockfile_never_suggests_install_in_source(self):
        self.write_package(locked=False)
        result = prepare_vite_preview(self.repository, self.snapshot())
        self.assertEqual(result['reason'], 'missing-npm-lockfile')
        self.assertIsNone(result['recipe'])
        self.assertFalse((self.source / 'package-lock.json').exists())

    def test_nonstandard_scripts_use_existing_configuration_path(self):
        for command in ('vite --host 0.0.0.0', 'npm run generate && vite', 'vite; touch bad', 'vite\nserve', 'node server.js'):
            with self.subTest(command=command):
                self.write_package(package=manifest(command))
                result = prepare_vite_preview(self.repository, self.snapshot())
                self.assertEqual(result['reason'], 'dev-script-needs-configuration')
                self.assertIsNone(result['recipe'])

    def test_standard_vite_aliases_are_supported(self):
        for command in ('vite', 'vite dev', 'vite serve'):
            with self.subTest(command=command):
                self.write_package(package=manifest(command))
                result = prepare_vite_preview(self.repository, self.snapshot())
                self.assertEqual(result['status'], 'needs-approval')
                self.assertEqual(result['recipe']['commands']['start'][-1], '--strictPort')

    def test_lockfile_mismatch_is_configuration_issue(self):
        folder = self.write_package()
        data = lock(manifest())
        data['packages']['']['devDependencies']['vite'] = '8.0.0'
        (folder / 'package-lock.json').write_text(json.dumps(data))
        result = prepare_vite_preview(self.repository, self.snapshot())
        self.assertEqual(result['reason'], 'npm-lockfile-needs-configuration')
        self.assertIsNone(result['recipe'])

    def test_external_local_dependencies_and_links_are_not_supported(self):
        for record in ({'link': True, 'resolved': '../other'}, {'resolved': 'file:../other'},
                       {'resolved': 'git+https://example.invalid/dependency.git'}):
            with self.subTest(record=record):
                folder = self.write_package()
                data = lock(manifest())
                data['packages']['node_modules/other'] = record
                (folder / 'package-lock.json').write_text(json.dumps(data))
                result = prepare_vite_preview(self.repository, self.snapshot())
                self.assertEqual(result['reason'], 'npm-lockfile-needs-configuration')
                self.assertIsNone(result['recipe'])

    def test_multiple_packages_do_not_silently_select_example(self):
        self.write_package(package={'name': 'a-library'})
        self.write_package('examples/web')
        sha = self.snapshot()
        result = prepare_vite_preview(self.repository, sha)
        self.assertEqual(result['status'], 'choose-entry')
        self.assertIsNone(result['recipe'])
        self.assertEqual(prepare_vite_preview(self.repository, sha, root='examples/web')['status'], 'needs-approval')
        with self.assertRaises(ValueError):
            prepare_vite_preview(self.repository, sha, root='../outside')

    def test_workspace_and_other_package_manager_need_configuration(self):
        for package in (manifest(workspaces=['packages/*']), manifest(packageManager='pnpm@10.0.0')):
            with self.subTest(package=package):
                self.write_package(package=package)
                result = prepare_vite_preview(self.repository, self.snapshot())
                self.assertEqual(result['status'], 'needs-configuration')
                self.assertIsNone(result['recipe'])

    def test_no_vite_project_does_not_propose_arbitrary_commands(self):
        self.write_package(package={'name': 'plain', 'scripts': {'dev': 'node server.js'}})
        result = prepare_vite_preview(self.repository, self.snapshot())
        self.assertEqual(result['reason'], 'no-supported-vite-project')
        self.assertIsNone(result['recipe'])


if __name__ == '__main__':
    unittest.main()
