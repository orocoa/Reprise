"""The thin Skill locator needs no host developer tools and installs nothing."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from test_runtime import fixture


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / 'skills' / 'reprise' / 'scripts' / 'reprise'


class SkillBundleLocatorTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('skill-bundle-locator')
        self.env = {'PATH': '/no-host-developer-tools', 'HOME': str(self.root)}

    def make_runtime(self, name):
        runtime = self.root / name
        (runtime / 'runtime').mkdir(parents=True)
        (runtime / 'runtime' / 'manifest.json').write_text('{"schema":1}')
        entry = runtime / 'reprise'
        entry.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nexit "${REPRISE_TEST_EXIT:-0}"\n')
        entry.chmod(0o755)
        return runtime

    def make_skill(self, directory):
        script = directory / 'scripts' / 'reprise'
        script.parent.mkdir(parents=True)
        shutil.copy2(ENTRY, script)
        return script

    def call(self, script, *arguments, env=None):
        return subprocess.run(['/bin/sh', str(script), *arguments],
                              cwd=str(self.root), env=self.env if env is None else env,
                              text=True, capture_output=True, timeout=10)

    def pointer(self, script, runtime, schema=1):
        path = script.parent.parent / 'bundle-location.json'
        path.write_text(json.dumps({'schema': schema, 'resources': str(runtime)},
                                   ensure_ascii=False))

    def test_same_package_root_is_found_without_host_tools_or_a_pointer(self):
        runtime = self.make_runtime('便携包 with spaces')
        script = self.make_skill(runtime / 'skills' / 'reprise')
        arguments = ('save', '/pages/site one', '--title', '第二稿', '--capture-static')
        result = self.call(script, *arguments)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), list(arguments))
        self.assertFalse((script.parent.parent / 'bundle-location.json').exists())

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS system plutil locator')
    def test_copied_skill_uses_json_pointer_and_preserves_literal_arguments(self):
        runtime = self.make_runtime('运行时 "quoted" $(not-a-command)')
        script = self.make_skill(self.root / 'separate skill')
        self.pointer(script, runtime)
        arguments = ('open', '--workbench', '--lang', 'en', '--no-browser', '')
        result = self.call(script, *arguments)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), list(arguments))

    def test_explicit_runtime_override_wins_and_exit_status_is_preserved(self):
        colocated = self.make_runtime('colocated')
        override = self.make_runtime('override')
        (colocated / 'reprise').write_text('#!/bin/sh\nexit 99\n')
        script = self.make_skill(colocated / 'skills' / 'reprise')
        result = self.call(script, 'doctor', env=dict(
            self.env, REPRISE_RUNTIME_ROOT=str(override), REPRISE_TEST_EXIT='6'))
        self.assertEqual(result.returncode, 6, result.stderr)
        self.assertEqual(result.stdout, 'doctor\n')

    def test_missing_runtime_is_reported_without_creating_or_downloading_files(self):
        script = self.make_skill(self.root / 'detached skill')
        before = sorted(str(path) for path in self.root.rglob('*'))
        result = self.call(script, 'doctor')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Runtime not found', result.stderr)
        self.assertIn('No download was attempted', result.stderr)
        self.assertEqual(sorted(str(path) for path in self.root.rglob('*')), before)

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS system plutil locator')
    def test_pointer_schema_and_absolute_path_are_checked(self):
        runtime = self.make_runtime('existing')
        script = self.make_skill(self.root / 'copied skill')
        self.pointer(script, runtime, schema=2)
        result = self.call(script, 'doctor')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Unsupported', result.stderr)
        self.pointer(script, 'relative/runtime')
        result = self.call(script, 'doctor')
        self.assertEqual(result.returncode, 1)
        self.assertIn('absolute path', result.stderr)

    def test_incomplete_runtime_is_rejected_before_calling_its_entry(self):
        runtime = self.make_runtime('incomplete')
        script = self.make_skill(runtime / 'skills' / 'reprise')
        (runtime / 'reprise').chmod(0o644)
        result = self.call(script, 'doctor')
        self.assertEqual(result.returncode, 1)
        self.assertIn('not executable', result.stderr)
        self.assertEqual(result.stdout, '')
