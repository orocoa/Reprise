"""Thin Skill connections create new copies or read-only reuse exact copies."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
import zipfile

from reprise.desktop_bundle import connect_skill
from test_desktop_bundle import make_bundle
from test_runtime import fixture


class SkillConnectionTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('skill-connection')
        self.resources, _ = make_bundle(self.root)
        self.source = self.resources / 'skills' / 'reprise'
        original = Path(__file__).resolve().parents[1] / 'skills' / 'reprise'
        shutil.copytree(original, self.source)
        self.target = self.root / 'new agent' / 'skills' / 'reprise'

    def test_creates_thin_copy_and_pointer_without_touching_agent_settings(self):
        settings = self.root / 'agent-settings.json'
        settings.write_bytes(b'{"unchanged": true}\n')
        legacy = self.source / 'assets' / 'runtime'
        legacy.mkdir(parents=True)
        (legacy / 'unneeded-copy.py').write_text('Must not copy a second runtime')
        result = connect_skill(self.resources, self.target)
        self.assertTrue(result['connected'])
        self.assertFalse(result['agent_settings_modified'])
        self.assertEqual((self.target / 'SKILL.md').read_bytes(),
                         (self.source / 'SKILL.md').read_bytes())
        self.assertEqual(json.loads((self.target / 'bundle-location.json').read_text()),
                         {'schema': 1, 'resources': str(self.resources)})
        self.assertTrue(os.access(self.target / 'scripts' / 'reprise', os.X_OK))
        self.assertFalse((self.target / 'assets').exists())
        self.assertEqual(settings.read_bytes(), b'{"unchanged": true}\n')

    def test_existing_destination_is_rejected_without_overwriting_its_files(self):
        self.target.mkdir(parents=True)
        marker = self.target / 'SKILL.md'
        marker.write_text('existing skill must remain')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            connect_skill(self.resources, self.target)
        self.assertEqual(marker.read_text(), 'existing skill must remain')
        self.assertEqual(list(self.target.iterdir()), [marker])

    @staticmethod
    def tree_state(root):
        return {str(path.relative_to(root)): (
            path.lstat().st_ino, path.lstat().st_mode, path.lstat().st_mtime_ns,
            path.lstat().st_ctime_ns,
            path.read_bytes() if path.is_file() and not path.is_symlink() else None)
            for path in [root, *root.rglob('*')]}

    def test_identical_connection_is_reused_without_writing(self):
        first = connect_skill(self.resources, self.target)
        self.assertFalse(first['reused'])
        before = self.tree_state(self.target)
        second = connect_skill(self.resources, self.target)
        self.assertTrue(second['connected'])
        self.assertTrue(second['reused'])
        self.assertFalse(second['agent_settings_modified'])
        self.assertEqual(self.tree_state(self.target), before)

    def test_connection_modes_and_reuse_do_not_depend_on_umask(self):
        previous = os.umask(0o077)
        try:
            connect_skill(self.resources, self.target)
            before = self.tree_state(self.target)
            self.assertTrue(connect_skill(self.resources, self.target)['reused'])
            self.assertEqual(self.tree_state(self.target), before)
        finally:
            os.umask(previous)

    def test_reused_connection_can_export_a_new_zip_without_changing_the_copy(self):
        connect_skill(self.resources, self.target)
        before = self.tree_state(self.target)
        archive = self.target.parent / 'reuse.zip'
        result = connect_skill(self.resources, self.target, archive=archive)
        self.assertTrue(result['reused'])
        self.assertEqual(self.tree_state(self.target), before)
        with zipfile.ZipFile(archive) as package:
            self.assertEqual(package.read('reprise/bundle-location.json'),
                             (self.target / 'bundle-location.json').read_bytes())
            self.assertEqual(package.read('reprise/SKILL.md'),
                             (self.source / 'SKILL.md').read_bytes())
        before_archive = archive.read_bytes()
        with self.assertRaisesRegex(ValueError, 'ZIP already exists'):
            connect_skill(self.resources, self.target, archive=archive)
        self.assertEqual(archive.read_bytes(), before_archive)

    def test_changed_connections_are_refused_without_writes(self):
        def pointer_change(target):
            pointer = target / 'bundle-location.json'
            value = json.loads(pointer.read_text())
            value['resources'] = str(self.root / 'another runtime')
            pointer.write_text(json.dumps(value))

        def linked_file(target):
            path = target / 'scripts' / 'reprise'
            kept = target.parent / (target.name + '-retained-entry')
            path.rename(kept)
            path.symlink_to(kept)

        def linked_directory(target):
            path = target / 'scripts'
            kept = target.parent / (target.name + '-retained-scripts')
            path.rename(kept)
            path.symlink_to(kept, target_is_directory=True)

        mutations = {
            'pointer': pointer_change,
            'extra-file': lambda target: (target / 'user-note').write_text('keep me'),
            'extra-directory': lambda target: (target / 'user-folder').mkdir(),
            'content': lambda target: (target / 'SKILL.md').write_text('modified'),
            'entry-mode': lambda target: (target / 'scripts/reprise').chmod(0o644),
            'pointer-mode': lambda target: (target / 'bundle-location.json').chmod(0o600),
            'directory-mode': lambda target: (target / 'scripts').chmod(0o700),
            'file-symlink': linked_file,
            'directory-symlink': linked_directory,
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                target = self.target.parent / name
                connect_skill(self.resources, target)
                mutate(target)
                before = self.tree_state(target)
                archive = self.root / (name + '.zip')
                with self.assertRaisesRegex(ValueError, 'not an identical connection'):
                    connect_skill(self.resources, target, archive=archive)
                self.assertEqual(self.tree_state(target), before)
                self.assertFalse(archive.exists())

    def test_oversized_existing_file_is_refused_before_reading_content(self):
        connect_skill(self.resources, self.target)
        with (self.target / 'SKILL.md').open('ab') as stream:
            stream.truncate(64 * 1024 * 1024)
        original_fdopen = os.fdopen
        opened = []

        def tracking_fdopen(descriptor, *args, **kwargs):
            stream = original_fdopen(descriptor, *args, **kwargs)
            if os.fstat(descriptor).st_size == 64 * 1024 * 1024:
                opened.append(stream)
                stream.read = lambda *_: self.fail('oversized user file must not be read')
            return stream

        with patch('reprise.desktop_bundle.os.fdopen', side_effect=tracking_fdopen):
            with self.assertRaisesRegex(ValueError, 'not an identical connection'):
                connect_skill(self.resources, self.target)
        self.assertEqual(len(opened), 1)

    def test_file_replaced_during_validation_is_not_reused(self):
        connect_skill(self.resources, self.target)
        original_open = os.open
        victim = self.target / 'SKILL.md'
        retained = self.root / 'retained-skill-before-race.md'
        victim_identity = victim.stat().st_ino
        substituted = []

        def substitute_after_open(path, *args, **kwargs):
            descriptor = original_open(path, *args, **kwargs)
            if path == 'SKILL.md' and os.fstat(descriptor).st_ino == victim_identity:
                victim.rename(retained)
                victim.write_bytes(retained.read_bytes())
                victim.chmod(retained.stat().st_mode & 0o777)
                substituted.append(True)
            return descriptor

        with patch('reprise.desktop_bundle.os.open', side_effect=substitute_after_open):
            with self.assertRaisesRegex(ValueError, 'not an identical connection'):
                connect_skill(self.resources, self.target)
        self.assertEqual(substituted, [True])
        self.assertEqual(victim.read_bytes(), retained.read_bytes())

    def test_upload_zip_contains_the_connected_copy_and_preserves_entry_mode(self):
        archive = self.target.parent / 'Reprise-skill.zip'
        result = connect_skill(self.resources, self.target, archive=archive)
        self.assertEqual(result['archive'], str(archive))
        self.assertEqual(result['archive_profile'], 'standard-connected-skill')
        self.assertEqual(len(result['archive_sha256']), 64)
        with zipfile.ZipFile(archive) as package:
            self.assertEqual(package.read('reprise/SKILL.md'), (self.target / 'SKILL.md').read_bytes())
            self.assertEqual(json.loads(package.read('reprise/bundle-location.json')),
                             {'schema': 1, 'resources': str(self.resources)})
            self.assertTrue(package.getinfo('reprise/scripts/reprise').external_attr >> 16 & 0o111)
            self.assertTrue(all(name.startswith('reprise/') and '../' not in name
                                for name in package.namelist()))
            self.assertFalse(any('/assets/runtime/' in name for name in package.namelist()))

    def test_zip_export_cannot_substitute_a_concurrent_target_edit_for_this_bundle(self):
        from reprise import desktop_bundle
        connect_skill(self.resources, self.target)
        original_check = desktop_bundle._same_skill_connection
        different = {'schema': 1, 'resources': str(self.root / 'another runtime')}

        def edit_after_check(*args):
            matched = original_check(*args)
            self.assertTrue(matched)
            (self.target / 'bundle-location.json').write_text(json.dumps(different))
            (self.target / 'SKILL.md').write_text('Concurrent target change must not be exported')
            return matched

        archive = self.target.parent / 'race-export.zip'
        with patch('reprise.desktop_bundle._same_skill_connection', side_effect=edit_after_check):
            result = connect_skill(self.resources, self.target, archive=archive)
        self.assertTrue(result['reused'])
        self.assertEqual(result['resources'], str(self.resources))
        with zipfile.ZipFile(archive) as package:
            self.assertEqual(json.loads(package.read('reprise/bundle-location.json'))['resources'],
                             result['resources'])
            self.assertEqual(package.read('reprise/SKILL.md'), (self.source / 'SKILL.md').read_bytes())
        # Do not undo another writer's edit while fixing the export receipt.
        self.assertEqual(json.loads((self.target / 'bundle-location.json').read_text()), different)

    def test_existing_or_unsafe_zip_does_not_claim_a_new_skill_destination(self):
        archive = self.root / 'existing.zip'
        archive.write_bytes(b'existing material')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            connect_skill(self.resources, self.target, archive=archive)
        self.assertEqual(archive.read_bytes(), b'existing material')
        self.assertFalse(self.target.exists())
        for unsafe in (self.resources / 'new.zip', self.target / 'recursive.zip'):
            with self.subTest(path=unsafe), self.assertRaisesRegex(ValueError, 'outside'):
                connect_skill(self.resources, self.target, archive=unsafe)
        self.assertFalse(self.target.exists())

    def test_zip_parent_symlink_is_rejected_without_external_writes(self):
        outside = self.root / 'outside zip'
        outside.mkdir()
        link = self.root / 'zip-parent-link'
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symbolic links'):
            connect_skill(self.resources, self.target, archive=link / 'new.zip')
        self.assertFalse(self.target.exists())
        self.assertEqual(list(outside.iterdir()), [])

    def test_existing_empty_destination_is_also_rejected(self):
        self.target.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            connect_skill(self.resources, self.target)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_symlink_destination_and_parent_are_rejected_without_external_writes(self):
        outside = self.root / 'outside'
        outside.mkdir()
        link = self.root / 'linked-parent'
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symbolic links'):
            connect_skill(self.resources, link / 'new' / 'reprise')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            connect_skill(self.resources, link)
        self.assertEqual(list(outside.iterdir()), [])

    def test_connection_cannot_modify_the_runtime_bundle(self):
        with self.assertRaisesRegex(ValueError, 'outside the runtime bundle'):
            connect_skill(self.resources, self.resources / 'another-skill')
        self.assertFalse((self.resources / 'another-skill').exists())

    def test_concurrent_destination_claim_is_not_reused(self):
        self.target.parent.mkdir(parents=True)
        original_mkdir = os.mkdir

        def claim_first(path, *args, **kwargs):
            if path == self.target.name and 'dir_fd' in kwargs:
                original_mkdir(path, *args, **kwargs)
            return original_mkdir(path, *args, **kwargs)

        with patch('reprise.desktop_bundle.os.mkdir', side_effect=claim_first):
            with self.assertRaises(FileExistsError):
                connect_skill(self.resources, self.target)
        self.assertEqual(list(self.target.iterdir()), [])

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS system plutil locator')
    def test_bridge_creates_a_connected_skill_that_invokes_the_existing_root(self):
        root_entry = self.resources / 'reprise'
        root_entry.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
        root_entry.chmod(0o755)
        bridge = Path(__file__).resolve().parents[1] / 'src/reprise/desktop_entry.py'
        result = subprocess.run([
            sys.executable, '-I', '-S', '-B', str(bridge), 'connect-skill',
            '--resources', str(self.resources), '--to', str(self.target)],
            cwd=str(self.root), capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertTrue(json.loads(result.stdout)['connected'])
        connected = subprocess.run([
            '/bin/sh', str(self.target / 'scripts' / 'reprise'),
            'open', '--workbench', '--lang', 'en', '--no-browser'],
            env={'PATH': '/no-developer-tools', 'HOME': str(self.root)},
            cwd=str(self.root), capture_output=True, text=True, timeout=10)
        self.assertEqual(connected.returncode, 0, connected.stderr)
        self.assertEqual(connected.stdout.splitlines(),
                         ['open', '--workbench', '--lang', 'en', '--no-browser'])

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS system plutil locator')
    def test_upload_imported_zip_keeps_the_same_runtime_without_host_developer_tools(self):
        root_entry = self.resources / 'reprise'
        root_entry.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
        root_entry.chmod(0o755)
        archive = self.target.parent / 'Reprise-skill.zip'
        bridge = Path(__file__).resolve().parents[1] / 'src/reprise/desktop_entry.py'
        result = subprocess.run([
            sys.executable, '-I', '-S', '-B', str(bridge), 'connect-skill',
            '--resources', str(self.resources), '--to', str(self.target), '--zip', str(archive)],
            cwd=str(self.root), capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['archive'], str(archive))
        imported = self.root / 'synthetic client import'
        with zipfile.ZipFile(archive) as package:
            package.extractall(imported)
        # Retained legacy shell bridge still handles an import losing exec bits.
        # Current source-Skill instructions no longer advertise this distribution.
        entry = imported / 'reprise/scripts/reprise'
        entry.chmod(0o644)
        self.assertFalse(os.access(entry, os.X_OK))
        command = ['/bin/sh', str(entry), 'doctor']
        invoked = subprocess.run(command,
            env={'PATH': '/no-developer-tools', 'HOME': str(self.root)},
            capture_output=True, text=True, timeout=10)
        self.assertEqual(invoked.returncode, 0, invoked.stderr)
        self.assertEqual(invoked.stdout.splitlines(), ['doctor'])

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS export command')
    def test_double_click_export_command_uses_the_same_connection_and_leaves_old_skills(self):
        import shlex
        project = Path(__file__).resolve().parents[1]
        bridge = project / 'src/reprise/desktop_entry.py'
        root_entry = self.resources / 'reprise'
        # Mirror only the root command dispatch; the real bridge and connection
        # implementation create the ZIP and runtime pointer under test.
        root_entry.write_text('#!/bin/sh\nshift\nexec %s -I -S -B %s connect-skill --resources %s "$@"\n' %
                              (shlex.quote(sys.executable), shlex.quote(str(bridge)),
                               shlex.quote(str(self.resources))))
        root_entry.chmod(0o755)
        command = self.resources / 'Prepare Skill.command'
        shutil.copy2(project / 'desktop/macos/Prepare Skill.command', command)
        output = self.root / 'Downloads with spaces'
        output.mkdir()
        previous = self.root / 'installed Skill'
        previous.mkdir()
        (previous / 'SKILL.md').write_bytes(b'previous user skill stays here')
        result = subprocess.run(['/bin/sh', str(command), str(output)],
                                env={**os.environ, 'HOME': str(self.root)},
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout.splitlines()[0])
        self.assertEqual(Path(receipt['archive']).parent.parent, output)
        self.assertTrue(Path(receipt['archive']).is_file())
        self.assertEqual((previous / 'SKILL.md').read_bytes(), b'previous user skill stays here')
        with zipfile.ZipFile(receipt['archive']) as package:
            self.assertEqual(json.loads(package.read('reprise/bundle-location.json'))['resources'],
                             str(self.resources))

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS export command')
    def test_export_command_rejects_runtime_output_before_writing_anything(self):
        project = Path(__file__).resolve().parents[1]
        command = self.resources / 'Prepare Skill.command'
        shutil.copy2(project / 'desktop/macos/Prepare Skill.command', command)
        before = sorted(str(path.relative_to(self.resources)) for path in self.resources.rglob('*'))
        result = subprocess.run(['/bin/sh', str(command), str(self.resources)],
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('outside', result.stderr)
        self.assertEqual(sorted(str(path.relative_to(self.resources)) for path in self.resources.rglob('*')),
                         before)
