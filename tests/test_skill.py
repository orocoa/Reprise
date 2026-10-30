"""The released skill works after extraction, without this checkout or agent env."""
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import unittest
import zipfile

from test_runtime import fixture, commit_repo
from reprise import __version__

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('reprise_skill_builder', ROOT / 'scripts/build_skill.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class PortableSkillTests(unittest.TestCase):
    def test_skill_ships_current_workbench_resources_without_retired_interfaces(self):
        root = fixture('skill-current-resources')
        package = root / 'reprise.zip'
        builder.build(package)
        prefix = 'reprise/assets/runtime/reprise/web/'
        with zipfile.ZipFile(package) as archive:
            html = archive.read(prefix + 'index.html').decode()
            resources = re.findall(r'(?:src|href)="([^"#]+)"', html)
            self.assertGreater(len(resources), 10)
            for name in resources:
                self.assertIn(prefix + name, archive.namelist(), 'Current workbench dependency is missing')
            for name in ('app.js', 'styles.css', 'paper-grid.css', 'browse-motion.js'):
                self.assertNotIn(prefix + name, archive.namelist())
                self.assertTrue((ROOT / 'web' / name).is_file(), 'Historical source stays in place')

    def test_reinstall_identical_skill_reuses_verified_runtime(self):
        root = fixture('skill-repeat-install')
        import_spec = importlib.util.spec_from_file_location('repeat_skill_installer', ROOT / 'scripts/install_skill.py')
        installer = importlib.util.module_from_spec(import_spec)
        from unittest.mock import patch
        with patch.dict(sys.modules, {'build_skill': builder}):
            import_spec.loader.exec_module(installer)
        destination = root / 'installed reprise'
        first = installer.install(destination, root / 'first')
        before = {p.relative_to(first['runtime']).as_posix(): p.read_bytes()
                  for p in Path(first['runtime']).rglob('*') if p.is_file()}
        second = installer.install(destination, root / 'second')
        self.assertFalse(first['runtime_reused'])
        self.assertTrue(second['runtime_reused'])
        self.assertEqual(first['runtime'], second['runtime'])
        self.assertTrue(second['verification']['package_integrity_verified'])
        self.assertEqual(before, {p.relative_to(second['runtime']).as_posix(): p.read_bytes()
                                 for p in Path(second['runtime']).rglob('*') if p.is_file()})

    def documented_open(self, skill, data, cwd, language):
        body = (skill / 'SKILL.md').read_text()
        row = next(line for line in body.splitlines() if line.startswith('| Open workbench in a browser /'))
        command = shlex.split(re.search(r'`([^`]+)`', row).group(1))
        # Execute the archive's documented entry instead of assuming a bridge.
        self.assertEqual(command[:2], ['python3', '$REPRISE'])
        command[:2] = [sys.executable, str(skill / 'scripts/reprise.py')]
        command[command.index('--lang') + 1] = language
        result = subprocess.run(command + ['--data', str(data)], cwd=cwd,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def test_installed_source_skill_documented_open_reuses_workbench_without_importing_cwd(self):
        root = fixture('installed-skill-entry')
        destination = root / 'client skills 中文' / 'reprise'
        output = root / 'retained installation'
        import_spec = importlib.util.spec_from_file_location('reprise_skill_installer', ROOT / 'scripts/install_skill.py')
        installer = importlib.util.module_from_spec(import_spec)
        from unittest.mock import patch
        with patch.dict(sys.modules, {'build_skill': builder}):
            import_spec.loader.exec_module(installer)
        installed = installer.install(destination, output, local_candidate=True)
        self.assertTrue(installed['verification']['package_integrity_verified'])
        cwd = root / 'unrelated caller'; cwd.mkdir()
        (cwd / 'index.html').write_text('<h1>Do not import this folder</h1>')
        data = root / 'isolated data'
        try:
            first = self.documented_open(destination, data, cwd, 'zh')
            second = self.documented_open(destination, data, cwd, 'en')
            self.assertIsNone(first['project_id'])
            self.assertIsNone(second['project_id'])
            self.assertIn('lang=zh', first['url'])
            self.assertIn('lang=en', second['url'])
            self.assertEqual(first['pid'], second['pid'])
            self.assertTrue(second['reused'])
            projects = subprocess.run([sys.executable, str(destination / 'scripts/reprise.py'),
                'projects', '--data', str(data)], cwd=cwd, capture_output=True, text=True, timeout=10)
            self.assertEqual(projects.returncode, 0, projects.stderr)
            self.assertEqual(json.loads(projects.stdout), [])
        finally:
            stopped = subprocess.run([sys.executable, str(destination / 'scripts/reprise.py'),
                'shutdown', '--data', str(data)], cwd=cwd, capture_output=True, text=True, timeout=15)
            self.assertEqual(stopped.returncode, 0, stopped.stderr)

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
            self.assertEqual(check['integrity_scope'], 'package-manifest')
            self.assertTrue(check['package_integrity_verified'])
            for arguments in [('--data', str(data), 'doctor'), ('doctor', '--data', str(data)),
                              ('--data=' + str(data), 'doctor'), ('doctor', '--data=' + str(data))]:
                diagnosed = call(*arguments)
                self.assertEqual(diagnosed['version'], __version__)
                self.assertTrue(diagnosed['package_integrity_verified'])
                self.assertFalse(data.exists(), 'doctor must not create the supplied data directory')
            try:
                blank = self.documented_open(skill, data, cwd, 'zh')
                self.assertIsNone(blank['project_id'])
                self.assertEqual(call('--data', str(data), 'projects'), [])
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
        data = root / 'must-not-create-data'
        result = subprocess.run([sys.executable, str(root / 'reprise/scripts/reprise.py'), '--data', str(data), 'doctor'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertIn('Modified bundled file: assets/runtime/reprise/cli.py', report['errors'])
        self.assertEqual(report['integrity_scope'], 'package-manifest')
        self.assertFalse(report['package_integrity_verified'])
        self.assertFalse(data.exists())

    def test_source_doctor_reports_actual_version_without_claiming_package_integrity(self):
        root = fixture('skill-source-doctor')
        script = ROOT / 'skills/reprise/scripts/reprise.py'
        data = root / 'data-that-must-not-exist'
        for arguments in [('doctor',), ('--data', str(data), 'doctor'), ('doctor', '--data', str(data)),
                          ('--data=' + str(data), 'doctor'), ('doctor', '--data=' + str(data))]:
            with self.subTest(arguments=arguments):
                result = subprocess.run([sys.executable, '-I', str(script), *arguments], cwd=root,
                                        text=True, capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                report = json.loads(result.stdout)
                self.assertEqual(report['version'], __version__)
                self.assertFalse(report['bundled'])
                self.assertEqual(report['integrity_scope'], 'source-only')
                self.assertEqual(report['checked_files'], 0)
                self.assertFalse(report['package_integrity_verified'])
                self.assertFalse(data.exists())
        # A path that is not even a directory is accepted without inspecting it.
        marker = root / 'private-data-marker'
        marker.write_text('Do not read this as Reprise state')
        result = subprocess.run([sys.executable, '-I', str(script), 'doctor', '--data', str(marker)],
                                cwd=root, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(marker.read_text(), 'Do not read this as Reprise state')

    def test_doctor_rejects_missing_or_empty_data_argument_without_falling_back_to_open(self):
        root = fixture('skill-doctor-arguments')
        script = ROOT / 'skills/reprise/scripts/reprise.py'
        for arguments in [('doctor', '--data'), ('doctor', '--data='), ('doctor', '--data', ''),
                          ('--data', str(root / 'unused'), 'doctor', '--data')]:
            with self.subTest(arguments=arguments):
                result = subprocess.run([sys.executable, '-I', str(script), *arguments], cwd=root,
                                        text=True, capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('--data', result.stderr)
                self.assertNotIn('Repository', result.stderr)
                self.assertNotIn('Traceback', result.stderr)
                self.assertEqual(list(root.iterdir()), [])

    def test_source_doctor_reads_version_statically_without_executing_runtime(self):
        root = fixture('skill-doctor-static-version')
        script = root / 'skills/reprise/scripts/reprise.py'
        script.parent.mkdir(parents=True)
        script.write_bytes((ROOT / 'skills/reprise/scripts/reprise.py').read_bytes())
        runtime = root / 'src/reprise'
        runtime.mkdir(parents=True)
        (runtime / '__init__.py').write_text('__version__ = "fixture-version"\nraise RuntimeError("Do not execute runtime")\n')
        result = subprocess.run([sys.executable, '-I', str(script), 'doctor'], cwd=root,
                                text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report['version'], 'fixture-version')
        self.assertEqual(report['integrity_scope'], 'source-only')
        self.assertEqual(report['checked_files'], 0)

    def test_doctor_reports_malformed_provenance_as_failed_diagnostic_json(self):
        root = fixture('skill-doctor-provenance')
        package = root / 'package.zip'
        builder.build(package)
        with zipfile.ZipFile(package) as archive:
            archive.extractall(root)
        (root / 'reprise/assets/runtime/provenance.json').write_text('{invalid-json')
        data = root / 'must-not-create-data'
        result = subprocess.run([sys.executable, str(root / 'reprise/scripts/reprise.py'), 'doctor', '--data', str(data)],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertFalse(report['ok'])
        self.assertFalse(report['package_integrity_verified'])
        self.assertTrue(any(error.startswith('Invalid runtime provenance:') for error in report['errors']))
        self.assertFalse(data.exists())
