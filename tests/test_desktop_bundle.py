"""Private bundle environments; fixtures remain available as diagnostics."""
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from reprise import desktop_bundle
from reprise.git import _environment
from test_runtime import fixture


def make_bundle(root):
    resources = root / 'Reprise App' / 'Contents' / 'Resources'
    paths = {
        'python': 'runtime/python/bin/python3',
        'git': 'runtime/git/bin/git',
        'node': 'runtime/node/bin/node',
        'playwright': 'runtime/playwright',
        'browser': 'runtime/browser/Chromium',
        'git_exec': 'runtime/git/libexec/git-core',
        'browser_cache': 'runtime/browser-cache',
    }
    for name in ('python', 'git', 'node', 'browser'):
        target = resources / paths[name]
        target.parent.mkdir(parents=True, exist_ok=True)
        # Real subprocesses execute deterministic stand-ins, without downloads.
        script = '#!/bin/sh\nprintf "%s\\n" "fixture-' + name + '-1"\n'
        if name == 'node':
            script = (
                '#!/bin/sh\nif [ "$1" = "-e" ]; then\n'
                '  printf "%s\\n" "fixture-playwright-1"\n'
                'else\n  printf "%s\\n" "fixture-node-1"\nfi\n'
            )
        target.write_text(script)
        target.chmod(0o755)
    for name in ('playwright', 'git_exec', 'browser_cache'):
        (resources / paths[name]).mkdir(parents=True, exist_ok=True)
    (resources / paths['playwright'] / 'package.json').write_text(
        '{"version":"fixture-playwright-1"}')
    manifest = resources / 'runtime' / 'manifest.json'
    manifest.write_text(json.dumps({'schema': 1, 'paths': paths}))
    return resources, paths


class DesktopBundleTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('desktop-bundle')
        self.resources, self.paths = make_bundle(self.root)

    def save_paths(self, paths):
        (self.resources / 'runtime' / 'manifest.json').write_text(
            json.dumps({'schema': 1, 'paths': paths}))

    def test_environment_is_private_and_uses_only_bundle_or_system_bins(self):
        inherited = {
            'PATH': '/untrusted/bin', 'HOME': str(self.root),
            'REPRISE_DATA': str(self.root / 'existing-data'),
            'PYTHONPATH': '/untrusted/python', 'PYTHONHOME': '/untrusted/home',
            'NODE_OPTIONS': '--require=/untrusted/inject.js',
            'NODE_PATH': '/untrusted/modules', 'DYLD_INSERT_LIBRARIES': 'bad',
            'GIT_CONFIG_COUNT': '1', 'GIT_EXEC_PATH': '/untrusted/git',
            'PLAYWRIGHT_BROWSERS_PATH': '/untrusted/browsers',
            'REPRISE_BROWSER': '/untrusted/chrome', 'LANG': 'en_US.UTF-8',
        }
        original = dict(inherited)
        process_before = dict(os.environ)
        result = desktop_bundle.configure(self.resources, inherited)
        self.assertEqual(inherited, original)
        self.assertEqual(dict(os.environ), process_before)
        self.assertEqual(result['HOME'], str(self.root))
        self.assertEqual(result['REPRISE_DATA'], str(self.root / 'existing-data'))
        for key in ('PYTHONPATH', 'PYTHONHOME', 'NODE_OPTIONS', 'NODE_PATH',
                    'DYLD_INSERT_LIBRARIES', 'GIT_CONFIG_COUNT'):
            self.assertNotIn(key, result)
        self.assertNotIn('/untrusted', json.dumps(result))
        self.assertEqual(result['REPRISE_PLAYWRIGHT'],
                         str(self.resources / self.paths['playwright']))
        self.assertEqual(result['REPRISE_BROWSER'],
                         str(self.resources / self.paths['browser']))
        self.assertEqual(result['GIT_EXEC_PATH'],
                         str(self.resources / self.paths['git_exec']))
        directories = result['PATH'].split(os.pathsep)
        self.assertEqual(directories[-4:], ['/usr/bin', '/bin', '/usr/sbin', '/sbin'])
        self.assertTrue(all(str(self.resources) in value for value in directories[:-4]))

    def test_internal_executable_symlink_preserves_declared_command_name(self):
        declared = self.resources / self.paths['python']
        actual = declared.with_name('python3.12')
        declared.rename(actual)
        declared.symlink_to(actual.name)
        result = desktop_bundle.configure(self.resources, {})
        self.assertIn(str(declared.parent), result['PATH'].split(os.pathsep))
        _, paths = desktop_bundle.bundle_paths(self.resources)
        self.assertEqual(paths['python'], str(declared))

    def test_rejects_path_traversal_absolute_and_missing_components(self):
        for invalid in ('../outside', '/bin/sh', 'runtime/../node', '', None):
            with self.subTest(path=invalid):
                self.save_paths(dict(self.paths, node=invalid))
                with self.assertRaisesRegex(ValueError, 'Invalid desktop component'):
                    desktop_bundle.configure(self.resources, {})
        self.save_paths({key: value for key, value in self.paths.items() if key != 'node'})
        with self.assertRaisesRegex(ValueError, 'node'):
            desktop_bundle.configure(self.resources, {})

    def test_rejects_nonexecutable_and_wrong_directory_type(self):
        node = self.resources / self.paths['node']
        node.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'not executable'):
            desktop_bundle.configure(self.resources, {})
        node.chmod(0o755)
        self.save_paths(dict(self.paths, git_exec=self.paths['node']))
        with self.assertRaisesRegex(ValueError, 'not a directory'):
            desktop_bundle.configure(self.resources, {})

    def test_rejects_nested_dependency_symlink_that_escapes_resources(self):
        outside = self.root / 'outside.js'
        outside.write_text('throw Error("must not load");')
        dependency = self.resources / self.paths['playwright'] / 'nested.js'
        dependency.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'escapes Resources'):
            desktop_bundle.configure(self.resources, {})
        self.assertEqual(outside.read_text(), 'throw Error("must not load");')

    def test_optional_browser_cache_can_be_omitted(self):
        self.save_paths({key: value for key, value in self.paths.items()
                         if key != 'browser_cache'})
        result = desktop_bundle.configure(
            self.resources, {'PLAYWRIGHT_BROWSERS_PATH': '/outside'})
        self.assertNotIn('PLAYWRIGHT_BROWSERS_PATH', result)

    def test_git_derives_helper_path_and_discards_other_git_injections(self):
        inherited = {'REPRISE_BUNDLE_RESOURCES': str(self.resources),
                     'GIT_EXEC_PATH': '/outside', 'GIT_CONFIG_COUNT': '9',
                     'GIT_INDEX_FILE': '/outside/index', 'PATH': '/usr/bin:/bin'}
        with patch.dict(os.environ, inherited, clear=True):
            result = _environment()
        self.assertEqual(result['GIT_EXEC_PATH'],
                         str(self.resources / self.paths['git_exec']))
        self.assertNotIn('GIT_CONFIG_COUNT', result)
        self.assertNotIn('GIT_INDEX_FILE', result)
        self.assertEqual(result['GIT_CONFIG_GLOBAL'], os.devnull)
        with patch.dict(os.environ, {'GIT_EXEC_PATH': '/outside'}, clear=True):
            self.assertNotIn('GIT_EXEC_PATH', _environment())

    def test_doctor_runs_all_five_probes_without_creating_data(self):
        data = self.root / 'never-created-data'
        with patch.dict(os.environ, {'REPRISE_DATA': str(data)}):
            result = desktop_bundle.doctor(self.resources)
        self.assertTrue(result['ok'])
        self.assertEqual(set(result['versions']),
                         {'python', 'git', 'node', 'playwright', 'browser'})
        self.assertEqual(result['versions']['playwright'], 'fixture-playwright-1')
        self.assertFalse(data.exists())

    def test_doctor_failure_names_component_and_keeps_diagnostic(self):
        git = self.resources / self.paths['git']
        git.write_text('#!/bin/sh\nprintf "%s\\n" "fixture failure" >&2\nexit 2\n')
        with self.assertRaisesRegex(ValueError, 'git check failed: fixture failure'):
            desktop_bundle.doctor(self.resources)

    def test_declared_npm_is_validated_and_probed_without_installing(self):
        npm = self.resources / 'runtime/node/bin/npm'
        npm.write_text('#!/bin/sh\n[ "$1" = "--version" ] || exit 9\nprintf "fixture-npm-1\\n"\n')
        npm.chmod(0o755)
        self.save_paths(dict(self.paths, npm='runtime/node/bin/npm'))
        result = desktop_bundle.doctor(self.resources)
        self.assertEqual(result['versions']['npm'], 'fixture-npm-1')
        self.assertEqual(result['paths']['npm'], str(npm))

    def test_doctor_timeout_is_a_readable_failure(self):
        with patch('reprise.desktop_bundle.subprocess.run',
                   side_effect=subprocess.TimeoutExpired('fixture', 20)):
            with self.assertRaisesRegex(ValueError, 'python check timed out'):
                desktop_bundle.doctor(self.resources)
