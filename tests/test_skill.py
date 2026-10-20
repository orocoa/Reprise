"""The released skill works after extraction, without this checkout or agent env."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import zipfile

from test_runtime import fixture, commit_repo

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('reprise_skill_builder', ROOT / 'scripts/build_skill.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class PortableSkillTests(unittest.TestCase):
    def test_profiles_are_self_contained_and_local_cli_opens_previews_recovers_exports(self):
        root = fixture('portable-skill')
        repository = commit_repo(root / 'user project 中文')
        expected = repository.blob('HEAD', 'index.html')
        cwd = root / 'unrelated caller';cwd.mkdir()
        env = {k: v for k, v in os.environ.items() if not k.startswith(('CODEX_', 'TRAE_', 'WORKBUDDY_', 'PYTHON'))}
        for profile, location in [('standard', '.agents/skills'), ('standard', '.trae/skills'), ('workbuddy', 'workbuddy/imported')]:
            package = root / (location.split('/')[0] + '.zip')
            builder.build(package, profile)
            with zipfile.ZipFile(package) as archive:
                self.assertTrue(all(n.startswith('reprise/') and '/work/' not in n and '/node_modules/' not in n for n in archive.namelist()))
                archive.extractall(root / location)
            skill = root / location / 'reprise'
            script = skill / 'scripts/reprise.py'
            data = root / location / 'state'
            def call(*args):
                result = subprocess.run([sys.executable, '-I', str(script), *args], cwd=cwd, env=env, text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                return json.loads(result.stdout)
            check = call('doctor')
            self.assertTrue(check['ok']);self.assertTrue(check['bundled']);self.assertGreater(check['checked_files'], 50)
            try:
                opened = call('--data', str(data), 'open', str(repository.path), '--no-browser')
                self.assertIsNotNone(opened['project_id'])
                project = call('--data', str(data), 'import', str(repository.path))
                self.assertEqual(call('--data', str(data), 'projects')[0]['id'], project['id'])
                target = root / (location.split('/')[0] + '-restored')
                restored = call('--data', str(data), 'restore', project['id'], '--sha', repository.resolve('HEAD'), '--to', str(target))
                self.assertEqual(restored['status'], 'complete')
                self.assertEqual((target / 'index.html').read_bytes(), expected)
                exported = call('--data', str(data), 'export', project['id'], '--to', str(target) + '.zip')
                self.assertEqual(exported['status'], 'complete')
                with zipfile.ZipFile(str(target) + '.zip') as archive:self.assertEqual(archive.read('index.html'), expected)
                # Assets must be the bundled copy, not fetched from the source checkout.
                import urllib.request
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(opened['url'].split('?')[0] + 'live-workspace.js') as response:
                    self.assertEqual(response.read(), (skill / 'assets/runtime/reprise/web/live-workspace.js').read_bytes())
            finally:
                call('--data', str(data), 'shutdown')

    def test_doctor_detects_incomplete_download(self):
        root = fixture('skill-corruption')
        package = root / 'package.zip';builder.build(package)
        with zipfile.ZipFile(package) as archive:archive.extractall(root)
        (root / 'reprise/assets/runtime/reprise/cli.py').write_text('modified runtime')
        result = subprocess.run([sys.executable, str(root / 'reprise/scripts/reprise.py'), 'doctor'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Modified bundled file: assets/runtime/reprise/cli.py', json.loads(result.stdout)['errors'])
