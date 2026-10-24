"""Distribution boundaries, not a mocked claim of working bundled runtimes."""
import importlib.util
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import unittest

from test_runtime import fixture


SPEC = importlib.util.spec_from_file_location(
    'macos_builder', Path(__file__).resolve().parents[1] / 'scripts/build_macos_bundle.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class MacOSBuilderTests(unittest.TestCase):
    def test_changed_archive_rejected_before_output(self):
        root = fixture('bundle-input-integrity')
        (root / 'input.tar').write_bytes(b'changed upstream archive')
        lock = root / 'lock.json'
        lock.write_text(json.dumps({'min_macos': '13.5', 'components': {'test': {'archive': {
            'cache_file': 'input.tar', 'sha256': '0' * 64}}}}))
        with self.assertRaisesRegex(ValueError, 'changed pinned input'):
            builder.build(root, root / 'candidate', lock_path=lock)
        self.assertFalse((root / 'candidate').exists())

    def test_archive_escape_is_rejected(self):
        root = fixture('bundle-archive-boundary')
        archive = root / 'escape.tar'
        with tarfile.open(archive, 'w') as stream:
            item = tarfile.TarInfo('../outside')
            item.size = 4
            stream.addfile(item, io.BytesIO(b'nope'))
        with self.assertRaisesRegex(ValueError, 'escapes'):
            builder.extract(archive, root / 'extracted')
        self.assertFalse((root / 'outside').exists())

    def test_existing_candidate_is_not_overwritten(self):
        root = fixture('bundle-retention')
        candidate = root / 'candidate'
        candidate.mkdir()
        marker = candidate / 'keep.txt'
        marker.write_text('original')
        lock = root / 'lock.json'
        lock.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'previous builds are retained'):
            builder.build(root, candidate, lock_path=lock)
        self.assertEqual(marker.read_text(), 'original')

    def test_selected_copy_preserves_binary_mode_and_relative_symlink(self):
        root = fixture('bundle-copy')
        source = root / 'source'
        (source / 'bin').mkdir(parents=True)
        binary = source / 'bin/tool'
        binary.write_text('binary fixture')
        binary.chmod(0o755)
        (source / 'bin/alias').symlink_to('tool')
        (source / 'bin/unneeded').write_text('not selected')
        target = root / 'candidate'
        builder.copy_selected(source, target, ['bin/*'], ['bin/unneeded'])
        self.assertEqual((target / 'bin/tool').stat().st_mode & 0o777, 0o755)
        self.assertTrue((target / 'bin/alias').is_symlink())
        self.assertFalse((target / 'bin/unneeded').exists())
        self.assertEqual(builder.inventory(target)['bin/alias'], {'symlink': 'tool'})

    def test_minimum_version_is_required_before_writing_a_candidate(self):
        for minimum in (None, '', '13', '13.x', '13.5.0.1', 13.5):
            with self.subTest(minimum=minimum):
                root = fixture('bundle-minimum-validation')
                lock = root / 'lock.json'
                lock.write_text(json.dumps({'min_macos': minimum, 'components': {}}))
                with self.assertRaisesRegex(ValueError, 'min_macos'):
                    builder.build(root, root / 'candidate', lock_path=lock)
                self.assertFalse((root / 'candidate').exists())
                self.assertFalse((root / 'candidate-inputs').exists())

    def test_lock_minimum_propagates_to_runtime_and_package_manifests(self):
        root = fixture('bundle-minimum-manifest')
        archive = root / 'input.tar'
        with tarfile.open(archive, 'w') as stream:
            item = tarfile.TarInfo('payload/fixture.txt')
            item.size = 4
            stream.addfile(item, io.BytesIO(b'test'))
        lock = root / 'lock.json'
        lock.write_text(json.dumps({'min_macos': '14.2', 'paths': {}, 'components': {'fixture': {
            'archive': {'cache_file': 'input.tar', 'sha256': builder.digest(archive)},
            'archive_top_level': 'payload', 'destination': 'runtime', 'include': ['**']}}}))
        output = root / 'candidate'
        result = builder.build(root, output, lock_path=lock)
        self.assertEqual(result['min_macos'], '14.2')
        self.assertEqual(json.loads((output / 'runtime/manifest.json').read_text())['min_macos'], '14.2')
        package = json.loads((output / 'package-manifest.json').read_text())
        self.assertEqual(package['min_macos'], '14.2')
        self.assertEqual(package['files']['Prepare Skill.command']['mode'], '0o755')
        self.assertEqual((output / 'Prepare Skill.command').read_bytes(),
                         (builder.ROOT / 'desktop/macos/Prepare Skill.command').read_bytes())


@unittest.skipUnless(sys.platform == 'darwin', 'Uses the macOS system plutil JSON reader')
class MacOSLauncherVersionTests(unittest.TestCase):
    def launcher(self, current='27.0.1', minimum='13.5', probe_status=0,
                 missing_probe=False, real_system=False):
        root = fixture('macos-version-entry')
        manifest = root / 'runtime/manifest.json'
        manifest.parent.mkdir()
        manifest.write_text(json.dumps({} if minimum is None else {'min_macos': minimum}))
        marker = root / 'python-started.txt'
        python = root / 'runtime/python/bin/python3'
        python.parent.mkdir(parents=True)
        python.write_text('#!/bin/sh\nprintf "started\\n" > "$REPRISE_TEST_MARKER"\nprintf "%s\\n" "$@"\n')
        python.chmod(0o755)
        entry = root / 'app/reprise/desktop_entry.py'
        entry.parent.mkdir(parents=True)
        entry.write_text('# A marker-only Python stub is used; this file is never interpreted.\n')
        script = (builder.ROOT / 'desktop/macos/reprise').read_text()
        if not real_system:
            uname = root / 'uname fixture'
            uname.write_text('#!/bin/sh\ncase "$1" in -s) echo Darwin;; -m) echo arm64;; esac\n')
            uname.chmod(0o755)
            probe = root / 'sw_vers fixture'
            if not missing_probe:
                probe.write_text('#!/bin/sh\nprintf "%s\\n" "$REPRISE_TEST_MACOS"\nexit "$REPRISE_TEST_VERSION_STATUS"\n')
                probe.chmod(0o755)
            # Replace only platform probes. Execute the real launcher comparison,
            # manifest reader, error path, and Python forwarding unchanged.
            script = script.replace('/usr/bin/uname', shlex.quote(str(uname)))
            script = script.replace('/usr/bin/sw_vers', shlex.quote(str(probe)))
        executable = root / 'reprise'
        executable.write_text(script)
        executable.chmod(0o755)
        environment = {'PATH': '/no-host-developer-tools', 'REPRISE_TEST_MARKER': str(marker),
                       'REPRISE_TEST_MACOS': current, 'REPRISE_TEST_VERSION_STATUS': str(probe_status)}
        result = subprocess.run(['/bin/sh', str(executable), 'doctor'], cwd=root,
            env=environment, text=True, capture_output=True, timeout=10)
        (root / 'result.json').write_text(json.dumps({'current': current, 'minimum': minimum,
            'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
            'python_started': marker.exists(), 'real_system_probes': real_system}, indent=2) + '\n')
        return result, marker.exists()

    def test_version_boundaries_run_real_comparison_before_python(self):
        for current, supported in [('12.7.6', False), ('13.4.9', False), ('13.5', True),
                ('13.5.0', True), ('13.5.1', True), ('13.10', True), ('14.0', True), ('27.0.1', True)]:
            with self.subTest(current=current):
                result, started = self.launcher(current)
                self.assertEqual(started, supported, result.stderr)
                self.assertEqual(result.returncode, 0 if supported else 1, result.stderr)
                if supported:
                    self.assertIn('\ndoctor\n--resources\n', result.stdout)
                else:
                    self.assertIn('此包需要 macOS 13.5', result.stderr)
                    self.assertIn('requires macOS 13.5', result.stderr)

    def test_declared_minimum_is_read_from_manifest(self):
        result, started = self.launcher('14.1', '14.2')
        self.assertEqual(result.returncode, 1)
        self.assertFalse(started)
        self.assertIn('requires macOS 14.2', result.stderr)
        result, started = self.launcher('14.2', '14.2')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(started)

    def test_unreadable_or_invalid_system_version_never_starts_python(self):
        for arguments in ({'current': ''}, {'current': 'unknown'}, {'current': '13.5.0.1'},
                          {'probe_status': 1}, {'missing_probe': True}):
            with self.subTest(arguments=arguments):
                result, started = self.launcher(**arguments)
                self.assertEqual(result.returncode, 1)
                self.assertFalse(started)
                self.assertIn('尚未启动 Reprise', result.stderr)
                self.assertIn('Reprise has not started', result.stderr)

    def test_missing_or_invalid_minimum_never_starts_python(self):
        for minimum in (None, 'unknown', 13.5):
            with self.subTest(minimum=minimum):
                result, started = self.launcher(minimum=minimum)
                self.assertEqual(result.returncode, 1)
                self.assertFalse(started)
                self.assertIn('macOS', result.stderr)

    def test_actual_host_system_probes_pass_to_marker_python(self):
        machine = subprocess.check_output(['/usr/bin/uname', '-m'], text=True).strip()
        current = subprocess.check_output(['/usr/bin/sw_vers', '-productVersion'], text=True).strip()
        if machine != 'arm64' or tuple(int(part) for part in current.split('.')) < (13, 5):
            self.skipTest('The real-host acceptance probe needs a supported Apple silicon Mac')
        result, started = self.launcher(real_system=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(started)
