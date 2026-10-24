"""Folder snapshots in a Reprise-owned Git object store; sources stay read-only.

The shared store deduplicates raw file bytes across folders and versions. A
snapshot tree contains payload/ and a manifest; the adapter exposes only the
original files to existing history, diff, preview and recovery services.
"""
import hashlib
from functools import wraps
import fnmatch
import io
import json
import os
from pathlib import Path
import posixpath
import re
import secrets
import shutil
import stat
import subprocess
import tempfile
import zlib

from .cancellation import check
from .git import Repository, _environment, _safe_path
from .storage import locked, now, read_json, write_json
from .content_lock import content_access
from .metadata import xattrs, restore_xattrs


def signature(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns]


def _raise(error):
    raise error


def exclusions(value):
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError('排除规则须为最多 100 条相对路径或通配符。')
    result = []
    for item in value:
        if (not isinstance(item, str) or not item.strip() or len(item) > 512 or
                item.startswith('/') or '\\' in item or '\0' in item or '..' in item.split('/')):
            raise ValueError('排除规则必须位于所选文件夹内。')
        result.append(item.strip().rstrip('/'))
    return sorted(set(result))


def inventory(source, cancel=None, exclude=(), *, device=None):
    """Metadata only; never traverse symlinks, special files or .git internals."""
    result, excluded = {}, []
    for root, directories, files in os.walk(source, followlinks=False,
                                           onerror=_raise):
        check(cancel)
        for name in sorted(directories + files):
            path = Path(root) / name
            relative = path.relative_to(source).as_posix()
            if name.casefold() == '.git' or any(
                    fnmatch.fnmatchcase(relative, pattern) or
                    fnmatch.fnmatchcase(relative + '/', pattern) or
                    relative == pattern.removesuffix('/**')
                    for pattern in exclude):
                if name in directories:
                    directories.remove(name)
                excluded.append(relative)
                continue
            _safe_path(relative)
            value = path.lstat()
            if device is not None and value.st_dev != device:
                raise ValueError('目录含跨设备挂载，请按磁盘分开管理。')
            kind = ('link' if stat.S_ISLNK(value.st_mode) else
                    'dir' if stat.S_ISDIR(value.st_mode) else
                    'file' if stat.S_ISREG(value.st_mode) else None)
            if kind is None:
                raise ValueError('不支持特殊文件：' + relative)
            entry = {'kind': kind, 'signature': signature(value),
                     'mode': stat.S_IMODE(value.st_mode) & 0o777,
                     'mtime_ns': value.st_mtime_ns, 'size': value.st_size if kind != 'dir' else 0}
            if kind == 'link':
                target = os.readlink(path)
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(relative), target))
                if (not target or target.startswith('/') or '\\' in target or
                        resolved == '..' or resolved.startswith('../')):
                    raise ValueError('链接必须指向文件夹内部：' + relative)
                try:
                    path.resolve().relative_to(source)
                except (ValueError, RuntimeError):
                    raise ValueError('链接必须指向文件夹内部且不能循环：' + relative) from None
                entry['target'] = target
                entry['size'] = len(os.fsencode(target))
            result[relative] = entry
        directories.sort()
    return result, sorted(excluded)


def _data_writer(function):
    @wraps(function)
    def guarded(self, *args, **kwargs):
        from .maintenance import DataLease
        root = self.directory.parent
        root.mkdir(parents=True, mode=0o700, exist_ok=True)
        with DataLease(root), content_access(self.directory):
            return function(self, *args, **kwargs)
    return guarded


class FolderStore:
    def __init__(self, directory):
        self.directory = Path(directory) / 'content'
        self.path = self.directory / 'objects.git'

    def catalog(self):
        self._recover_snapshot()
        return read_json(self.path / 'reprise-snapshots.json')

    def versions(self, identifier):
        catalog = self.catalog()
        if catalog is not None:
            return catalog.get(identifier, [])
        try:
            return self.run('rev-list', 'refs/heads/folders/' + identifier).splitlines()
        except ValueError:
            return []

    @_data_writer
    def ensure(self):
        if self.directory.is_symlink():
            raise ValueError('内容库目录不能是符号链接。')
        self.directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        # The library may contain files whose originals are private; parent
        # access must not be widened by the object store's default blob modes.
        self.directory.chmod(0o700)
        with locked(self.directory / 'init.lock'):
            if self.path.is_symlink():
                raise ValueError('内容库不能是符号链接。')
            if not self.path.exists():
                pending = read_json(self.directory / 'delete-transaction.json')
                if pending and pending.get('state') not in ('complete', 'rolled_back'):
                    raise ValueError('版本删除切换中断；原库仍在事务目录，未创建空库。')
                self.run('init', '--bare', '--template=', str(self.path), outside=True)
            self._recover_snapshot()

    def _boundary(self, value):
        """Atomically replace shallow roots, retaining interrupted staging files."""
        path = self.path / 'shallow'
        if path.is_symlink():
            raise ValueError('快照边界不能是符号链接。')
        if value is None:
            if path.exists():
                path.unlink()
        else:
            temporary = self.path / ('.shallow-' + secrets.token_hex(16))
            with temporary.open('x') as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)

    def _finish_snapshot(self, transaction, state):
        transaction = dict(transaction, state=state)
        write_json(self.directory / 'snapshot-transactions' / (transaction['id'] + '.json'),
                   transaction, private=True)
        write_json(self.directory / 'snapshot-transaction.json', transaction, private=True)

    @_data_writer
    def _recover_snapshot(self):
        """Recover only a journaled publication; never guess or discard objects.

        The catalog is the commit point. Before it changes, roll back refs and
        shallow roots; afterwards finish the recorded new state. Every recovery
        step is idempotent so another process exit can be retried on next access.
        """
        transaction = read_json(self.directory / 'snapshot-transaction.json')
        if not transaction or transaction.get('state') in ('complete', 'rolled_back'):
            return
        try:
            identifier = transaction['ref'].removeprefix('refs/heads/folders/')
            sha, old_sha = transaction['sha'], transaction['old_sha']
            old, new = transaction['old_catalog'], transaction['new_catalog']
            expected = {key: list(values) for key, values in old.items()}
            expected.setdefault(identifier, []).insert(0, sha)
            if (transaction['state'] != 'pending' or transaction.get('schema') != 1 or
                    not re.fullmatch('[0-9a-f]{32}', transaction['id']) or
                    not re.fullmatch('[0-9a-f]{20}', identifier) or
                    transaction['ref'] != 'refs/heads/folders/' + identifier or
                    not re.fullmatch('[0-9a-f]{40}', sha) or
                    (old_sha is not None and not re.fullmatch('[0-9a-f]{40}', old_sha)) or
                    old_sha != next(iter(old.get(identifier, [])), None) or new != expected or
                    transaction['snapshot_ref'] != 'refs/reprise/snapshots/' + identifier + '/' + sha):
                raise ValueError('invalid snapshot journal')
            old_boundary, new_boundary = transaction['old_boundary'], transaction['new_boundary']
            boundaries = set((old_boundary or '').splitlines())
            boundaries.update(s for values in new.values() for s in values)
            if (not all(re.fullmatch('[0-9a-f]{40}', s) for s in boundaries) or
                    new_boundary != ''.join(s + '\n' for s in sorted(boundaries))):
                raise ValueError('invalid snapshot boundaries')
        except (KeyError, TypeError, AttributeError, ValueError):
            raise ValueError('快照发布事务无效；保留现场，未更改内容库。') from None
        catalog = read_json(self.path / 'reprise-snapshots.json')
        boundary_path = self.path / 'shallow'
        if boundary_path.is_symlink():
            raise ValueError('快照边界不能是符号链接。')
        boundary = boundary_path.read_text() if boundary_path.exists() else None
        refs = dict(row.split(' ', 1) for row in self.run(
            'for-each-ref', '--format=%(refname) %(objectname)').splitlines())
        ref, snapshot_ref = transaction['ref'], transaction['snapshot_ref']
        if (catalog not in (old, new) or boundary not in (old_boundary, new_boundary) or
                refs.get(ref) not in (old_sha, sha) or refs.get(snapshot_ref) not in (None, sha)):
            raise ValueError('快照发布事务与当前内容库不一致；保留现场，未自动修复。')
        if self.run('cat-file', '-t', sha) != 'commit':
            raise ValueError('快照发布对象不可用；保留现场。')
        committed = catalog == new
        target = sha if committed else old_sha
        current = refs.get(ref)
        if current != target:
            if target:
                self.run('update-ref', ref, target, current or '0' * 40)
            elif current:
                self.run('update-ref', '-d', ref, current)
        if committed and snapshot_ref not in refs:
            self.run('update-ref', snapshot_ref, sha, '0' * 40)
        elif not committed and snapshot_ref in refs:
            self.run('update-ref', '-d', snapshot_ref, sha)
        target_boundary = new_boundary if committed else old_boundary
        if boundary != target_boundary:
            self._boundary(target_boundary)
        self._finish_snapshot(transaction, 'complete' if committed else 'rolled_back')

    def run(self, *args, input=None, index=None, outside=False, config=()):
        env = _environment()
        if index:
            env['GIT_INDEX_FILE'] = str(index)
        env.update(GIT_AUTHOR_NAME='Reprise', GIT_AUTHOR_EMAIL='reprise@localhost',
                   GIT_COMMITTER_NAME='Reprise', GIT_COMMITTER_EMAIL='reprise@localhost')
        command = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'gc.auto=0']
        for key, value in config:
            command += ['-c', key + '=' + value]
        if not outside:
            command += ['--git-dir=' + str(self.path)]
        process = subprocess.run(command + list(args), input=input, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, env=env, timeout=300)
        if process.returncode:
            raise ValueError(os.fsdecode(process.stderr[:8192]).strip() or '内容库操作失败。')
        return process.stdout.strip().decode('ascii')

    def repository(self, record):
        self.ensure()
        return FolderRepository(self, record)

    def blob(self, stream, size, cancel=None):
        """One bounded streaming read, without filters or per-file Git processes."""
        header = ('blob %d\0' % size).encode('ascii')
        oid, digest = hashlib.sha1(header), hashlib.sha256()
        compressor = zlib.compressobj()
        with tempfile.TemporaryFile() as pending:
            pending.write(compressor.compress(header))
            remaining = size
            while remaining:
                check(cancel)
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError('读取期间文件发生变化，请重新记录版本。')
                oid.update(chunk)
                digest.update(chunk)
                pending.write(compressor.compress(chunk))
                remaining -= len(chunk)
            if stream.read(1):
                raise ValueError('读取期间文件发生变化，请重新记录版本。')
            pending.write(compressor.flush())
            name = oid.hexdigest()
            destination = self.path / 'objects' / name[:2] / name[2:]
            exists = destination.exists()
            if destination.is_symlink() or destination.parent.is_symlink():
                raise ValueError('内容对象路径不能是符号链接。')
            if not exists:
                destination.parent.mkdir(exist_ok=True)
                pending.seek(0)
                # Publish only a complete object. Interrupted pending objects stay
                # available for diagnostics and can never masquerade as valid blobs.
                staging = self.directory / 'staging'
                staging.mkdir(exist_ok=True)
                temporary = staging / ('object-' + secrets.token_hex(16))
                with temporary.open('xb') as output:
                    shutil.copyfileobj(pending, output, 1024 * 1024)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, destination)
            return name, digest.hexdigest(), exists

    @_data_writer
    def snapshot(self, record, title='', cancel=None, origin=None, expected_state=None, pre_publish=None):
        if not isinstance(title, str) or len(title) > 120 or '\0' in title:
            raise ValueError('版本名称最多 120 个字符。')
        self.ensure()
        transaction = read_json(self.directory / 'delete-transaction.json')
        if transaction and transaction.get('state') not in ('complete', 'rolled_back'):
            raise ValueError('版本删除事务尚未完成；请先重试该删除计划，未保存新版本。')
        source = Path(record['path'])
        # One writer across all folders; readers keep using published immutable refs.
        with locked(self.directory / 'write.lock'):
            repository = self.repository(record)
            old_sha = repository.info()['head']
            old_manifest = repository.manifest(old_sha) if old_sha else {}
            previous = old_manifest.get('entries', {})
            root_stat = source.stat()
            root_metadata = {'mode': stat.S_IMODE(root_stat.st_mode) & 0o777,
                             'mtime_ns': root_stat.st_mtime_ns, 'xattrs': xattrs(source)}
            rules = record.get('exclusions', [])
            before, excluded = inventory(source, cancel, rules)
            entries, new_bytes, read_bytes, reused_files = {}, 0, 0, 0
            with _directory(source) as source_fd:
                for name, entry in before.items():
                    check(cancel)
                    entry = dict(entry)
                    old = previous.get(name)
                    entry['xattrs'] = (old['xattrs'] if old and 'xattrs' in old and
                        old['signature'] == entry['signature'] else xattrs(source / name))
                    if entry['kind'] == 'dir':
                        entries[name] = entry
                        continue
                    old = previous.get(name)
                    if old and old['signature'] == entry['signature'] and old.get('target') == entry.get('target'):
                        entry.update(oid=old['oid'], sha256=old['sha256'])
                        reused_files += 1
                    else:
                        if entry['kind'] == 'link':
                            stream = io.BytesIO(os.fsencode(entry['target']))
                        else:
                            stream = _open_file(source_fd, name)
                            if signature(os.fstat(stream.fileno())) != entry['signature']:
                                stream.close()
                                raise ValueError('读取期间文件发生变化：' + name)
                        with stream:
                            oid, digest, reused = self.blob(stream, entry['size'], cancel)
                            if entry['kind'] == 'file' and signature(os.fstat(stream.fileno())) != entry['signature']:
                                raise ValueError('读取期间文件发生变化：' + name)
                        entry.update(oid=oid, sha256=digest)
                        read_bytes += entry['size']
                        if not reused:
                            new_bytes += entry['size']
                    entries[name] = entry
            after, after_excluded = inventory(source, cancel, rules)
            if (before != after or excluded != after_excluded or
                    signature(source.stat()) != signature(root_stat)):
                raise ValueError('记录期间文件夹发生变化，请重新记录版本。')
            stats = {'files': sum(e['kind'] != 'dir' for e in entries.values()),
                     'logical_bytes': sum(e['size'] for e in entries.values()),
                     'unique_bytes': sum({e['oid']: e['size'] for e in entries.values() if 'oid' in e}.values()),
                     'new_bytes': new_bytes, 'read_bytes': read_bytes, 'reused_files': reused_files}
            if expected_state is not None:
                expected = expected_state['scan']
                fields = ('kind', 'signature', 'size', 'sha256', 'target', 'mode', 'mtime_ns', 'xattrs')
                if (signature(root_stat) != expected['root_signature'] or root_metadata != expected['root'] or
                        excluded != expected_state['excluded'] or set(entries) != set(expected['entries']) or
                        any(any(entry.get(field, 0 if field == 'size' else None) !=
                                    expected['entries'][name].get(field, 0 if field == 'size' else None)
                                for field in fields) for name, entry in entries.items())):
                    raise ValueError('输入在预检核验后发生变化；未发布快照，请重新预检。')
            if pre_publish is not None:
                pre_publish()
            if (old_sha and previous == entries and old_manifest.get('excluded', []) == excluded and
                    old_manifest.get('root') == root_metadata and old_manifest.get('origin') == origin):
                return {'sha': old_sha, 'unchanged': True, 'stats': stats}
            manifest = {'format': 'reprise-folder-v1', 'project_id': record['id'],
                        'source': str(source), 'created_at': now(), 'entries': entries,
                        'excluded': excluded, 'exclusion_rules': rules, 'stats': stats, 'root': root_metadata}
            if origin is not None:
                manifest['origin'] = origin
            return self._commit_snapshot(record, repository, old_sha, title, manifest, cancel)

    def _commit_snapshot(self, record, repository, old_sha, title, manifest, cancel):
        """Publish an already validated manifest under the caller content/write gates."""
        transaction = read_json(self.directory / 'delete-transaction.json')
        if transaction and transaction.get('state') not in ('complete', 'rolled_back'):
            raise ValueError('版本删除事务尚未完成；未发布新版本。')
        if repository.info()['head'] != old_sha:
            raise ValueError('版本库在发布前发生变化；已保留诊断。')
        entries, stats = manifest['entries'], manifest['stats']
        encoded = json.dumps(manifest, ensure_ascii=True, sort_keys=True).encode('utf-8')
        if len(encoded) > 32 * 1024 * 1024:
            raise ValueError('版本文件清单超过 32 MiB，请把文件夹分成多个项目后记录。')
        manifest_oid, _, _ = self.blob(io.BytesIO(encoded), len(encoded), cancel)
        rows = [b'100644 ' + manifest_oid.encode() + b'\tsnapshot.json\0']
        for name, entry in entries.items():
            if 'oid' not in entry:
                continue
            mode = '120000' if entry['kind'] == 'link' else '100755' if entry['mode'] & 0o111 else '100644'
            rows.append(mode.encode() + b' ' + entry['oid'].encode() + b'\tpayload/' + os.fsencode(name) + b'\0')
        staging = self.directory / 'staging'
        staging.mkdir(exist_ok=True)
        index = staging / (secrets.token_hex(16) + '.index')
        self.run('update-index', '-z', '--index-info', input=b''.join(rows), index=index)
        tree = self.run('write-tree', index=index)
        sha = self.run('commit-tree', tree, *(['-p', old_sha] if old_sha else []),
                       input=((title.strip() or '记录版本') + '\n').encode('utf-8'))
        check(cancel)
        catalog = self.catalog()
        if catalog is None:
            self.run('update-ref', repository.ref, sha, old_sha or '0' * 40)
        else:
            self._publish_snapshot(record['id'], repository.ref, old_sha, sha, catalog)
        return {'sha': sha, 'unchanged': False, 'stats': stats}

    def _publish_snapshot(self, identifier, ref, old_sha, sha, catalog):
        snapshot_ref = 'refs/reprise/snapshots/' + identifier + '/' + sha
        boundary = self.path / 'shallow'
        old_boundary = boundary.read_text() if boundary.exists() else None
        updated = {key: list(values) for key, values in catalog.items()}
        updated.setdefault(identifier, []).insert(0, sha)
        boundaries = set((old_boundary or '').splitlines())
        boundaries.update(s for values in updated.values() for s in values)
        new_boundary = ''.join(s + '\n' for s in sorted(boundaries))
        transaction = {'schema': 1, 'id': secrets.token_hex(16), 'state': 'pending',
                       'ref': ref, 'snapshot_ref': snapshot_ref, 'old_sha': old_sha, 'sha': sha,
                       'old_catalog': catalog, 'new_catalog': updated,
                       'old_boundary': old_boundary, 'new_boundary': new_boundary}
        write_json(self.directory / 'snapshot-transaction.json', transaction, private=True)
        try:
            self.run('update-ref', ref, sha, old_sha or '0' * 40)
            self.run('update-ref', snapshot_ref, sha)
            # Keep diagnostic roots too; rebuilding from only visible versions
            # would invalidate their retained missing-parent boundaries.
            self._boundary(new_boundary)
            write_json(self.path / 'reprise-snapshots.json', updated, private=True)
            self._finish_snapshot(transaction, 'complete')
        except BaseException:
            self._recover_snapshot()
            # The newly written commit, trees and blobs remain as diagnostics.
            raise


class _directory:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        self.fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        return self.fd

    def __exit__(self, *_):
        os.close(self.fd)


def _open_file(root_fd, name):
    directory = os.dup(root_fd)
    try:
        pieces = name.split('/')
        for piece in pieces[:-1]:
            next_fd = os.open(piece, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = next_fd
        fd = os.open(pieces[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise ValueError('文件类型已改变：' + name)
        return os.fdopen(fd, 'rb')
    finally:
        os.close(directory)


def _content_reader(function):
    @wraps(function)
    def guarded(self, *args, **kwargs):
        with content_access(self.store.directory):
            self.store._recover_snapshot()
            return function(self, *args, **kwargs)
    return guarded


class FolderRepository(Repository):
    def __init__(self, store, record):
        self.store, self.record = store, record
        self.ref = 'refs/heads/folders/' + record['id']
        with content_access(store.directory):
            super().__init__(store.path)
        self.work_tree = Path(record['path'])
        self._manifests = {}

    @_content_reader
    def _run(self, *args, **kwargs):
        return super()._run(*args, **kwargs)

    @_content_reader
    def resolve(self, revision):
        sha = super().resolve(self.ref if revision in ('HEAD', '--all') else revision)
        if self.store.catalog() is None:
            self._run('merge-base', '--is-ancestor', sha, self.ref)
        elif sha not in self.store.versions(self.record['id']):
            raise ValueError('此版本已删除或不属于该文件夹。')
        return sha

    def info(self):
        result = super().info()
        if self.store.catalog() is not None:
            result['warnings'] = ['受管快照按完整目录独立保留；已删除父版本仅显示原始 SHA 边界，不能恢复。']
        return {**result, 'path': self.record['path'], 'branch': None, 'kind': 'folder',
                'source_available': self.work_tree.is_dir(), 'managed_store': str(self.path)}

    def refs(self):
        return [r for r in super().refs() if r['name'] == self.ref]

    @_content_reader
    def history(self, ref='--all', limit=50, offset=0):
        if self.store.catalog() is not None:
            limit, offset = int(limit), int(offset)
            if not 1 <= limit <= 200 or not 0 <= offset <= 1000000:
                raise ValueError('History limit must be 1–200 and offset 0–1000000')
            versions = self.store.versions(self.record['id'])
            if ref not in ('--all', 'HEAD'):
                versions = versions[versions.index(self.resolve(ref)):]
            selected = versions[offset:offset + limit]
            # Decorations belong to this read, not to each retained snapshot.
            # A later read still observes newly saved versions and moved refs.
            refs = self.refs() if selected else []
            commits = [self._history(s, 1, 0, refs, True)['commits'][0] for s in selected]
            more = offset + limit < len(versions)
            return {'commits': commits, 'has_more': more, 'next_offset': offset + len(commits) if more else None}
        if not self.info()['head']:
            return {'commits': [], 'has_more': False, 'next_offset': None}
        return super().history('HEAD' if ref == '--all' else ref, limit, offset)

    @_content_reader
    def history_tips(self, tips, limit=2000, *, refs=None, shallow=None):
        if self.store.catalog() is None:
            return super().history_tips(tips, limit, refs=refs, shallow=shallow)
        versions = self.store.versions(self.record['id'])
        selected = versions[:limit]
        if refs is None:
            refs = self.refs() if selected else []
        commits = [self._history(s, 1, 0, refs, True)['commits'][0] for s in selected]
        return {'commits': commits, 'truncated_tips': tips[:1] if len(versions) > limit else []}

    @_content_reader
    def manifest(self, revision):
        sha = self.resolve(revision)
        if sha not in self._manifests:
            value = json.loads(Repository.blob(self, sha, 'snapshot.json', max_bytes=32 * 1024 * 1024))
            if value.get('format') != 'reprise-folder-v1' or value.get('project_id') != self.record['id']:
                raise ValueError('文件夹版本来源不匹配。')
            self._manifests[sha] = value
        return self._manifests[sha]

    @_content_reader
    def tree(self, revision):
        return [{**e, 'path': e['path'][8:]} for e in super().tree(revision) if e['path'].startswith('payload/')]

    def empty_directories(self, revision):
        return [name for name, entry in self.manifest(revision)['entries'].items() if entry['kind'] == 'dir']

    @_content_reader
    def blob(self, revision, path, max_bytes=1048576):
        return super().blob(revision, 'payload/' + _safe_path(path), max_bytes)

    @_content_reader
    def diff(self, target, base=None):
        result = super().diff(target, base)
        files = []
        for entry in result['files']:
            # Disable cross-boundary rename inference involving the manifest.
            if not entry['path'].startswith('payload/'):
                continue
            item = {**entry, 'path': entry['path'][8:]}
            if 'old_path' in item:
                if item['old_path'].startswith('payload/'):
                    item['old_path'] = item['old_path'][8:]
                else:
                    item.pop('old_path')
                    item['status'] = 'A'
            files.append(item)
        counts = dict.fromkeys(result['counts'], 0)
        names = {'A': 'added', 'M': 'modified', 'D': 'deleted', 'R': 'renamed', 'C': 'copied', 'T': 'type_changed'}
        for entry in files:
            counts[names.get(entry['status'][0], 'other')] += 1
        counts['total'] = len(files)
        return {**result, 'files': files, 'counts': counts}

    def status(self):
        try:
            current, _ = inventory(self.work_tree, exclude=self.record.get('exclusions', []))
            if not self.work_tree.is_dir():
                raise ValueError('原文件夹不可用；已保存版本仍可恢复。')
            head = self.info()['head']
            previous = self.manifest(head)['entries'] if head else {}
            changes = [{'path': name, 'status': 'D' if name not in current else 'A' if name not in previous else 'M'}
                       for name in sorted(set(current) | set(previous))
                       if current.get(name) is None or previous.get(name) is None or
                       current[name]['signature'] != previous[name]['signature']]
            return {'available': True, 'dirty': bool(changes), 'changes': changes,
                    'note': '根据文件元数据检测变化；记录版本时校验新增或变更的文件内容。'}
        except (OSError, ValueError) as error:
            return {'available': False, 'dirty': False, 'changes': [], 'reason': str(error)}

    @_content_reader
    def materialize(self, revision, destination, cancel=None, paths=None):
        # Owned folder snapshots are streamed and space-checked. Imported Git
        # repositories retain their existing default extraction bound.
        result = super().materialize(revision, destination, cancel, paths=paths, max_bytes=None)
        manifest = self.manifest(revision)
        target = Path(destination)
        def selected(name):
            return paths is None or any(name == p or name.startswith(p + '/') or p.startswith(name + '/') for p in paths)
        for name, entry in sorted(manifest['entries'].items(), key=lambda pair: pair[0].count('/'), reverse=True):
            check(cancel)
            _safe_path(name)
            if not selected(name):
                continue
            path = target.joinpath(*name.split('/'))
            if entry['kind'] == 'dir':
                path.mkdir(parents=True, exist_ok=True)
            if 'xattrs' in entry:
                restore_xattrs(path, entry['xattrs'])
            if entry['kind'] != 'link':
                path.chmod(entry['mode'])
                os.utime(path, ns=(entry['mtime_ns'], entry['mtime_ns']), follow_symlinks=False)
        result['warnings'].extend('未纳入此版本：' + p for p in manifest.get('excluded', []))
        root = manifest.get('root', {'mode': 0o700})
        if 'xattrs' in root:
            restore_xattrs(target, root['xattrs'])
        target.chmod(root['mode'])
        if 'mtime_ns' in root:
            os.utime(target, ns=(root['mtime_ns'], root['mtime_ns']))
        result['metadata'] = 'file modes, modification times, extended attributes and empty directories'
        from .organize import verify_restore
        result.update(verify_restore(self, revision, target, cancel, paths))
        return result
