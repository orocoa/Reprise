import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch
import zlib

from reprise.cancellation import Cancelled
from reprise.integrity import IntegrityError, _Batch, verify_project
from reprise.projects import ProjectStore
from test_runtime import fixture


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('integrity')
        self.source = self.root / 'source'
        self.source.mkdir()
        self.projects = ProjectStore(self.root / 'state')
        self.project = self.projects.add(str(self.source), kind='folder')
        self.identifier = self.project['id']
        self.store = self.projects.folders

    def save(self):
        return self.projects.snapshot(self.identifier)['sha']

    def verify(self, sha='HEAD', cancel=None):
        return verify_project(self.projects, self.identifier, sha, cancel)

    def manifest(self, sha):
        return copy.deepcopy(self.projects.repository(self.identifier).manifest(sha))

    def object_path(self, oid):
        return self.store.path / 'objects' / oid[:2] / oid[2:]

    def forge(self, original, manifest=None, *, omit=(), extra=(), snapshot_bytes=None):
        """Create deliberately invalid owned test versions, preserving originals."""
        manifest = self.manifest(original) if manifest is None else manifest
        data = json.dumps(manifest, sort_keys=True).encode() if snapshot_bytes is None else snapshot_bytes
        oid, _, _ = self.store.blob(io.BytesIO(data), len(data))
        rows = [b'100644 ' + oid.encode() + b'\tsnapshot.json\0']
        for name, entry in manifest['entries'].items():
            if entry['kind'] == 'dir' or name in omit:
                continue
            mode = '120000' if entry['kind'] == 'link' else '100755' if entry['mode'] & 0o111 else '100644'
            rows.append(mode.encode() + b' ' + entry['oid'].encode() + b'\tpayload/' + os.fsencode(name) + b'\0')
        for path, mode, oid in extra:
            rows.append(mode.encode() + b' ' + oid.encode() + b'\t' + os.fsencode(path) + b'\0')
        index = self.root / ('forge-%d.index' % len(list(self.root.glob('forge-*.index'))))
        self.store.run('update-index', '-z', '--index-info', input=b''.join(rows), index=index)
        tree = self.store.run('write-tree', index=index)
        sha = self.store.run('commit-tree', tree, '-p', original, input=b'Integrity adversarial test\n')
        self.store.run('update-ref', 'refs/heads/folders/' + self.identifier, sha)
        return sha

    def assert_failed(self, sha='HEAD', expected=None):
        with self.assertRaises(IntegrityError) as caught:
            self.verify(sha)
        self.assertEqual(caught.exception.report['status'], 'failed')
        self.assertLessEqual(len(str(caught.exception)), 512)
        if expected:
            self.assertIn(expected, str(caught.exception))
        return caught.exception.report

    def test_reads_unique_bytes_once_and_does_not_require_original_folder(self):
        content = b'exact saved bytes\x00' * 100000
        (self.source / 'a.bin').write_bytes(content)
        (self.source / 'b.bin').write_bytes(content)
        (self.source / 'empty').mkdir()
        (self.source / 'link').symlink_to('a.bin')
        sha = self.save()
        self.source.rename(self.root / 'source-offline')
        with patch.object(self.projects, 'repository', side_effect=AssertionError('No ensure or source access')):
            report = self.verify(sha)
        self.assertEqual(report['status'], 'verified')
        self.assertEqual(report['sha'], sha)
        self.assertEqual(report['project_id'], self.identifier)
        self.assertEqual(report['checked_files'], 3)
        self.assertEqual(report['checked_objects'], 2)
        self.assertEqual(report['checked_bytes'], len(content) + len(b'a.bin'))
        self.assertIn('独立备份', ' '.join(report['limitations']))

    def test_empty_saved_version_is_valid_but_unsaved_folder_fails(self):
        self.assert_failed(expected='所选版本不存在')
        sha = self.save()
        report = self.verify(sha)
        self.assertEqual(report['status'], 'verified')
        self.assertEqual(report['checked_files'], 0)
        self.assertEqual(report['checked_objects'], 0)
        self.assertEqual(report['checked_bytes'], 0)

    def test_selected_sha_stays_exact_after_a_newer_version(self):
        path = self.source / 'note'
        path.write_text('first')
        old = self.save()
        path.write_text('second')
        new = self.save()
        self.assertEqual(self.verify(old)['sha'], old)
        self.assertEqual(self.verify()['sha'], new)

    def test_missing_payload_object_fails_without_source_fallback(self):
        (self.source / 'note').write_text('private content remains in source')
        sha = self.save()
        oid = self.manifest(sha)['entries']['note']['oid']
        self.object_path(oid).rename(self.root / 'missing-object-preserved')
        report = self.assert_failed(sha, '对象缺失')
        self.assertEqual(report['checked_files'], 0)
        self.assertNotIn('private content', json.dumps(report))

    def test_corrupt_object_content_fails_even_with_valid_zlib_and_size(self):
        (self.source / 'note').write_text('original bytes')
        sha = self.save()
        oid = self.manifest(sha)['entries']['note']['oid']
        path = self.object_path(oid)
        shutil.copy2(path, self.root / 'original-object-preserved')
        content = b'forged   bytes'
        self.assertEqual(len(content), len(b'original bytes'))
        path.write_bytes(zlib.compress(b'blob 14\0' + content))
        self.assert_failed(sha, '地址校验失败')

    def test_manifest_digest_and_size_cannot_lie(self):
        (self.source / 'note').write_text('actual')
        sha = self.save()
        manifest = self.manifest(sha)
        manifest['entries']['note']['sha256'] = hashlib.sha256(b'lie').hexdigest()
        forged = self.forge(sha, manifest)
        self.assert_failed(forged, 'SHA256')
        manifest = self.manifest(sha)
        manifest['entries']['note']['size'] += 1
        manifest['entries']['note']['signature'][3] += 1
        manifest['stats'].update(files=1, logical_bytes=7, unique_bytes=7)
        forged = self.forge(sha, manifest)
        self.assert_failed(forged, '对象长度')

    def test_manifest_and_payload_must_reference_exact_same_paths(self):
        (self.source / 'note').write_text('kept')
        sha = self.save()
        forged = self.forge(sha, omit=('note',))
        self.assert_failed(forged, '未出现在 payload')
        oid = self.manifest(sha)['entries']['note']['oid']
        forged = self.forge(sha, extra=[('payload/hidden', '100644', oid)])
        self.assert_failed(forged, '清单外')
        forged = self.forge(sha, extra=[('unexpected', '100644', oid)])
        self.assert_failed(forged, '根目录')

    def test_folder_identity_and_current_project_history_are_required(self):
        (self.source / 'note').write_text('one')
        sha = self.save()
        manifest = self.manifest(sha)
        manifest['project_id'] = 'another-project'
        forged = self.forge(sha, manifest)
        self.assert_failed(forged, '项目身份')
        other = self.root / 'other-source'
        other.mkdir()
        (other / 'note').write_text('different project')
        project = self.projects.add(str(other), kind='folder')
        saved = self.projects.snapshot(project['id'])
        self.assert_failed(saved['sha'], '不属于此项目')

    def test_rejects_invalid_metadata_and_unsafe_paths(self):
        (self.source / 'note').write_text('a')
        sha = self.save()
        for invalid in [None, -1, 0o1000, True, '777']:
            manifest = self.manifest(sha)
            manifest['root']['mode'] = invalid
            self.assert_failed(self.forge(sha, manifest), '权限或时间')
        manifest = self.manifest(sha)
        manifest['entries']['note']['xattrs'] = {'unsafe': 'not base64!'}
        self.assert_failed(self.forge(sha, manifest), '扩展属性')
        manifest = self.manifest(sha)
        manifest['entries']['../escape'] = manifest['entries'].pop('note')
        data = json.dumps(manifest).encode()
        self.assert_failed(self.forge(sha, self.manifest(sha), snapshot_bytes=data), 'Unsafe Git path')

    def test_symbolic_links_are_checked_from_saved_namespace_without_following(self):
        (self.source / 'note').write_text('unchanged')
        (self.source / 'alias').symlink_to('note')
        sha = self.save()
        for target in ['../outside', 'alias', '/absolute']:
            manifest = self.manifest(sha)
            encoded = os.fsencode(target)
            oid, digest, _ = self.store.blob(io.BytesIO(encoded), len(encoded))
            entry = manifest['entries']['alias']
            entry.update(oid=oid, sha256=digest, size=len(encoded), target=target)
            entry['signature'][3] = len(encoded)
            manifest['stats']['logical_bytes'] = len(encoded) + len(b'unchanged')
            manifest['stats']['unique_bytes'] = manifest['stats']['logical_bytes']
            manifest['stats']['new_bytes'] = manifest['stats']['read_bytes'] = 0
            self.assert_failed(self.forge(sha, manifest), '链接')

    def test_duplicate_json_keys_are_not_silently_accepted(self):
        (self.source / 'note').write_text('actual')
        sha = self.save()
        data = json.dumps(self.manifest(sha)).encode()
        data = b'{"project_id":"misleading",' + data[1:]
        self.assert_failed(self.forge(sha, snapshot_bytes=data), '重复字段')

    def test_false_exclusion_and_invalid_timestamp_do_not_pass(self):
        (self.source / 'note').write_text('actual')
        sha = self.save()
        manifest = self.manifest(sha)
        manifest['excluded'] = ['note']
        self.assert_failed(self.forge(sha, manifest), '重叠')
        manifest = self.manifest(sha)
        manifest['created_at'] = 'not a date'
        self.assert_failed(self.forge(sha, manifest), '记录时间')

    def test_git_and_legacy_archives_are_explicitly_unsupported(self):
        for kind in ('git', 'archive'):
            record = {**self.projects.record(self.identifier), 'kind': kind}
            with patch.object(self.projects, 'record', return_value=record):
                self.assert_failed(expected='仅支持普通文件夹')

    def test_cancellation_never_reports_verified(self):
        (self.source / 'note').write_bytes(b'large' * 1000000)
        sha = self.save()
        class Token:
            def __init__(self):
                self.count = 0
                self.armed = False
            def check(self):
                self.count += self.armed
                if self.count > 3:
                    raise Cancelled()
        token = Token()
        read = _Batch.read
        def arm(batch, oid, kind, **kwargs):
            if kind == 'blob' and not kwargs.get('collect'):
                token.armed = True
            return read(batch, oid, kind, **kwargs)
        with patch.object(_Batch, 'read', arm):
            with self.assertRaises(Cancelled):
                self.verify(sha, token)

    def test_read_timeout_is_a_failed_check(self):
        sha = self.save()
        with patch('reprise.integrity.TIMEOUT', 0):
            self.assert_failed(sha, '超时')

    def test_library_missing_or_symlink_is_rejected_without_creation(self):
        absent = self.root / 'absent' / 'objects.git'
        with patch.object(self.store, 'path', absent):
            self.assert_failed(expected='内容库不存在')
        self.assertFalse(absent.parent.exists())
        alias = self.root / 'alias.git'
        alias.symlink_to(self.store.path, target_is_directory=True)
        with patch.object(self.store, 'path', alias):
            self.assert_failed(expected='符号链接')

    def test_external_alternates_do_not_supply_missing_local_payload(self):
        (self.source / 'note').write_text('only the library may supply this payload')
        sha = self.save()
        oid = self.manifest(sha)['entries']['note']['oid']
        external = self.root / 'outside-library-secret-path'
        (external / oid[:2]).mkdir(parents=True)
        self.object_path(oid).rename(external / oid[:2] / oid[2:])
        alternates = self.store.path / 'objects/info/alternates'
        alternates.write_text(str(external) + '\n')
        # The original loophole is real: ordinary Git still supplies the blob.
        self.assertEqual(self.store.run('cat-file', '-s', oid), str(len(b'only the library may supply this payload')))
        with patch('reprise.integrity.subprocess.Popen', side_effect=AssertionError('Reject before Git starts')):
            report = self.assert_failed(sha, '替代对象来源')
        self.assertNotIn(str(external), json.dumps(report))
        self.assertFalse(self.object_path(oid).exists())

    def test_empty_alternates_are_allowed_but_symlink_alternates_are_rejected(self):
        sha = self.save()
        alternates = self.store.path / 'objects/info/alternates'
        alternates.touch()
        self.assertEqual(self.verify(sha)['status'], 'verified')
        alternates.rename(self.root / 'empty-alternates-preserved')
        alternates.symlink_to(self.root / 'unread-external-alternates')
        with patch('reprise.integrity.subprocess.Popen', side_effect=AssertionError('Reject before Git starts')):
            self.assert_failed(sha, '符号链接')

    def test_objects_info_and_pack_directory_symlinks_are_rejected(self):
        for relative in ('objects', 'objects/info', 'objects/pack'):
            with self.subTest(relative=relative):
                source = self.root / ('source-' + relative.replace('/', '-'))
                source.mkdir()
                (source / 'note').write_text('saved')
                projects = ProjectStore(self.root / ('state-' + relative.replace('/', '-')))
                identifier = projects.add(str(source), kind='folder')['id']
                sha = projects.snapshot(identifier)['sha']
                path = projects.folders.path / relative
                external = self.root / ('external-' + relative.replace('/', '-'))
                path.rename(external)
                path.symlink_to(external, target_is_directory=True)
                with patch('reprise.integrity.subprocess.Popen', side_effect=AssertionError('Reject before Git starts')):
                    with self.assertRaises(IntegrityError) as caught:
                        verify_project(projects, identifier, sha)
                self.assertIn('符号链接', str(caught.exception))

    def test_requested_loose_fanout_and_object_symlinks_are_rejected(self):
        (self.source / 'note').write_text('saved payload')
        sha = self.save()
        oid = self.manifest(sha)['entries']['note']['oid']
        path = self.object_path(oid)
        external = self.root / 'external-object'
        path.rename(external)
        path.symlink_to(external)
        self.assert_failed(sha, '符号链接')
        # Preserve the first symlink, then test a symlink in its parent path.
        path.rename(self.root / 'object-link-preserved')
        external.rename(path)
        fanout = path.parent
        external_fanout = self.root / 'external-fanout'
        fanout.rename(external_fanout)
        fanout.symlink_to(external_fanout, target_is_directory=True)
        self.assert_failed(sha, '符号链接')

    def test_pack_and_index_symlinks_are_rejected_and_internal_pack_is_supported(self):
        (self.source / 'note').write_text('packed payload')
        sha = self.save()
        pack = self.store.path / 'objects/pack'
        # pack-objects adds a genuine pack and index without deleting loose files.
        prefix = str(pack / 'pack')
        process = subprocess.run(['git', '--git-dir=' + str(self.store.path), 'pack-objects', '--revs', prefix],
                                 input=(sha + '\n').encode(), stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, check=True, timeout=30)
        name = process.stdout.decode().strip()
        oid = self.manifest(sha)['entries']['note']['oid']
        self.object_path(oid).rename(self.root / 'loose-payload-preserved')
        self.assertEqual(self.verify(sha)['status'], 'verified')
        for extension in ('.pack', '.idx'):
            path = pack / ('pack-' + name + extension)
            preserved = self.root / ('external' + extension)
            path.rename(preserved)
            path.symlink_to(preserved)
            with patch('reprise.integrity.subprocess.Popen', side_effect=AssertionError('Reject before Git starts')):
                self.assert_failed(sha, '符号链接')
            path.rename(self.root / ('pack-link-preserved' + extension))
            preserved.rename(path)

    def test_unrelated_loose_symlink_is_not_scanned_and_metadata_scan_is_bounded(self):
        sha = self.save()
        unused = self.store.path / 'objects/ff'
        unused.mkdir(exist_ok=True)
        (unused / ('f' * 38)).symlink_to(self.root / 'unread-unrelated-object')
        self.assertEqual(self.verify(sha)['status'], 'verified')
        info = self.store.path / 'objects/info'
        (info / 'bounded-check').touch()
        with patch('reprise.integrity.MAX_STORAGE_ENTRIES', 0):
            self.assert_failed(sha, '安全条目上限')

    def test_ancestry_commits_are_guarded_before_reading_their_objects(self):
        path = self.source / 'note'
        path.write_text('first')
        first = self.save()
        path.write_text('middle')
        middle = self.save()
        path.write_text('head')
        self.save()
        loose = self.object_path(middle)
        external = self.root / 'external-ancestor'
        loose.rename(external)
        loose.symlink_to(external)
        self.assert_failed(first, '符号链接')

    def test_external_git_common_directory_is_rejected_without_reading_it(self):
        sha = self.save()
        external = self.root / 'unread-common-directory'
        (self.store.path / 'commondir').write_text(str(external) + '\n')
        with patch('reprise.integrity.subprocess.Popen', side_effect=AssertionError('Reject before Git starts')):
            report = self.assert_failed(sha, '公共目录')
        self.assertNotIn(str(external), json.dumps(report))


if __name__ == '__main__':
    unittest.main()
