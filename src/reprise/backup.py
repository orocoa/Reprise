"""Offline, verified copies of Reprise-managed data, with explicit boundaries.

The original, backup and failed partial copies are retained. JSONL manifests and
chunked file I/O bound memory use independently of blob sizes. External imported
Git repositories and archive dependencies are reported, never traversed/copied.
This format detects accidental corruption; it is not a signed/authenticated or
encrypted archive. Restoration never inherits authority to stop old processes.
"""
import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import secrets
import select
import stat
import subprocess
import sys
import time

from .cancellation import Cancelled
from .git import _environment
from .maintenance import DataLease, LEASE_FILE
from .metadata import MAX_XATTR_BYTES, xattrs
from .relocation import xattrs_fd, restore_xattrs_fd
from .storage import now


FORMAT = 'reprise-managed-backup'
SCHEMA = 1
CHUNK = 1024 * 1024
MAX_JSON = 32 * 1024 * 1024
MAX_LINE = 4 * 1024 * 1024
MAX_ENTRIES = 2000000
MAX_DEPTH = 256
RESERVE = 64 * 1024 * 1024
EXCLUDED = frozenset((LEASE_FILE, 'server.lock', '.content-access.lock'))
LIMITATIONS = [
    '只复制 Reprise 数据目录；外部源 Git、普通文件夹原件及旧归档依赖未自动纳入。',
    '同设备副本不是独立物理磁盘防护；不同设备编号也不证明是独立物理磁盘。',
    '备份未加密，可能包含私密记录、日志或 API 密钥；目标根目录使用私有权限。',
    '保存文件、目录、安全相对符号链接、权限位、mtime 和扩展属性；不保证 ACL、owner、文件系统 flags、硬链接关系或稀疏布局。',
    '摘要与清单用于检测损坏，没有签名认证；不能抵御同时重写所有数据与校验记录的攻击。',
]


class BackupError(ValueError):
    def __init__(self, message, report=None):
        self.report = {**(report or {}), 'status': 'failed', 'errors': [str(message)[:512]]}
        super().__init__(str(message)[:512])


def _check(cancel):
    if cancel is not None:
        if hasattr(cancel, 'check'):
            cancel.check()
        elif callable(cancel) and cancel():
            raise Cancelled()


def _encoded(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':')) + '\n').encode('ascii')


def _pairs(values):
    result = {}
    for key, value in values:
        if key in result:
            raise ValueError('校验记录包含重复字段。')
        result[key] = value
    return result


def _json_bytes(value):
    return json.loads(value, object_pairs_hook=_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('非法数值。')))


def _read_json(path):
    with _regular(path) as stream:
        data = stream.read(MAX_JSON + 1)
    if len(data) > MAX_JSON:
        raise ValueError('管理元数据超过 32 MiB 安全上限。')
    return _json_bytes(data)


def _path(value, root=False):
    if root and value == '.':
        return value
    if (not isinstance(value, str) or not value or '\0' in value or '\\' in value or
            value.startswith('/') or any(p in ('', '.', '..') for p in value.split('/')) or
            len(value.split('/')) > MAX_DEPTH):
        raise ValueError('备份清单包含不安全路径。')
    return value


def _signature(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns]


@contextlib.contextmanager
def _directory(path):
    """Open every component without following a substituted directory link."""
    path = Path(path).absolute()
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


@contextlib.contextmanager
def _regular(path):
    path = Path(path)
    with _directory(path.parent) as directory:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_NONBLOCK', 0), dir_fd=directory)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('期望普通文件，遇到链接或特殊文件。')
        with os.fdopen(fd, 'rb') as stream:
            fd = None
            yield stream
    finally:
        if fd is not None:
            os.close(fd)


def _root(value):
    path = Path(value).expanduser().absolute()
    with _directory(path):
        pass
    return path.resolve()


def _link(root, path, target):
    if not isinstance(target, str) or not target or '\0' in target or target.startswith('/') or '\\' in target:
        raise ValueError('仅支持备份范围内的安全相对符号链接。')
    relative = path.relative_to(root).as_posix()
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(relative), target))
    if resolved == '..' or resolved.startswith('../'):
        raise ValueError('符号链接越出数据目录；未读取外部文件。')
    try:
        path.resolve().relative_to(root.resolve())
    except (ValueError, RuntimeError):
        raise ValueError('符号链接越出数据目录或形成循环；未读取外部文件。') from None
    if resolved in EXCLUDED:
        raise ValueError('符号链接指向未复制的维护锁。')


def _entry(root, path):
    with _directory(path.parent) as parent:
        value = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        kind = ('dir' if stat.S_ISDIR(value.st_mode) else 'file' if stat.S_ISREG(value.st_mode)
                else 'link' if stat.S_ISLNK(value.st_mode) else None)
        if kind is None:
            raise ValueError('数据目录包含特殊文件；未读取或省略。')
        target = os.readlink(path.name, dir_fd=parent) if kind == 'link' else None
        if kind == 'link' and sys.platform != 'darwin':
            attributes = xattrs(path)
            if attributes:
                raise ValueError('此平台不能通过安全描述符保存链接扩展属性。')
        else:
            flags = (os.O_RDONLY | getattr(os, 'O_SYMLINK', 0x200000) if kind == 'link' else
                     os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_NONBLOCK', 0) |
                     (os.O_DIRECTORY if kind == 'dir' else 0))
            fd = os.open(path.name, flags, dir_fd=parent)
            try:
                if _signature(os.fstat(fd)) != _signature(value):
                    raise ValueError('读取元数据前数据发生变化。')
                attributes = xattrs_fd(fd)
            finally:
                os.close(fd)
    relative = '.' if path == root else _path(path.relative_to(root).as_posix())
    if kind == 'link':
        if relative == 'content' or relative.startswith('content/'):
            raise ValueError('内容库包含符号链接，无法确认独立对象。')
        _link(root, path, target)
    record = {'path': relative, 'kind': kind, 'mode': stat.S_IMODE(value.st_mode),
              'mtime_ns': value.st_mtime_ns, 'size': value.st_size if kind != 'dir' else 0,
              'xattrs': attributes, 'signature': _signature(value)}
    if kind == 'link':
        record['target'] = target
    return record


def _walk(root, cancel=None, excluded=EXCLUDED):
    """Sorted component order, with directory exit events for metadata restore."""
    count = [0]
    def visit(path, depth):
        _check(cancel)
        if depth > MAX_DEPTH:
            raise ValueError('数据目录超过安全层数。')
        count[0] += 1
        if count[0] > MAX_ENTRIES:
            raise ValueError('数据目录超过两百万条目安全上限。')
        record = _entry(root, path)
        yield path, record, False
        if record['kind'] == 'dir':
            with _directory(path) as fd:
                with os.scandir(fd) as stream:
                    names = sorted(item.name for item in stream)
            for name in names:
                if path == root and name in excluded:
                    continue
                yield from visit(path / name, depth + 1)
            yield path, record, True
    yield from visit(root, 0)


def _inventory(root, cancel=None, excluded=EXCLUDED):
    digest, count = hashlib.sha256(), 0
    for unused, entry, leaving in _walk(root, cancel, excluded):
        if not leaving:
            digest.update(_encoded(entry))
            count += 1
    return digest.hexdigest(), count


def _hash_file(path, cancel=None):
    digest, length = hashlib.sha256(), 0
    with _regular(path) as stream:
        before = _signature(os.fstat(stream.fileno()))
        while True:
            _check(cancel)
            chunk = stream.read(CHUNK)
            if not chunk:
                break
            digest.update(chunk)
            length += len(chunk)
        if _signature(os.fstat(stream.fileno())) != before:
            raise ValueError('校验期间文件发生变化。')
    return digest.hexdigest(), length


def _metadata(path, entry):
    with _directory(path.parent) as parent:
        if entry['kind'] == 'link' and sys.platform != 'darwin':
            if entry['xattrs']:
                raise ValueError('此平台不能安全恢复链接扩展属性。')
            os.utime(path.name, ns=(entry['mtime_ns'], entry['mtime_ns']), dir_fd=parent, follow_symlinks=False)
            return
        flags = (os.O_RDONLY | getattr(os, 'O_SYMLINK', 0x200000) if entry['kind'] == 'link' else
                 os.O_RDONLY | os.O_NOFOLLOW | (os.O_DIRECTORY if entry['kind'] == 'dir' else 0))
        fd = os.open(path.name, flags, dir_fd=parent)
        try:
            matches = {'file': stat.S_ISREG, 'dir': stat.S_ISDIR, 'link': stat.S_ISLNK}[entry['kind']]
            if not matches(os.fstat(fd).st_mode):
                raise ValueError('恢复元数据前目标文件类型发生变化。')
            restore_xattrs_fd(fd, entry['xattrs'])
            os.fchmod(fd, entry['mode'])
            if entry['kind'] == 'link':
                os.utime(path.name, ns=(entry['mtime_ns'], entry['mtime_ns']), dir_fd=parent, follow_symlinks=False)
            else:
                os.utime(fd, ns=(entry['mtime_ns'], entry['mtime_ns']))
        finally:
            os.close(fd)


def _mkdir(path):
    with _directory(path.parent) as parent:
        os.mkdir(path.name, mode=0o700, dir_fd=parent)


def _symlink(path, target):
    with _directory(path.parent) as parent:
        os.symlink(target, path.name, dir_fd=parent)


def _write_json(path, value):
    """Atomic state replacement anchored to an opened no-follow parent."""
    name = '.' + path.name + '.' + secrets.token_hex(8)
    with _directory(path.parent) as parent:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(_encoded(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path.name, src_dir_fd=parent, dst_dir_fd=parent)


@contextlib.contextmanager
def _new_file(path):
    with _directory(path.parent) as parent:
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
    with os.fdopen(fd, 'wb') as stream:
        yield stream


def _room(directory, additional=0):
    value = os.statvfs(directory)
    if value.f_bavail * value.f_frsize < RESERVE + additional:
        raise ValueError('目标可用空间不足；需保留至少 64 MiB 余量，半成品和原数据均保留。')


def _capacity(root, parent, cancel):
    required = 0
    for unused, entry, leaving in _walk(root, cancel):
        if leaving:
            continue
        size = entry['size'] if entry['kind'] == 'file' else 0
        required += ((size + 4095) // 4096) * 4096 + 4096 + 2 * (len(_encoded(entry)) + 96)
    _room(parent, required)
    return required


def _copy_file(source, destination, entry, cancel):
    digest, length = hashlib.sha256(), 0
    _room(destination.parent, entry['size'])
    with _regular(source) as stream:
        if _signature(os.fstat(stream.fileno())) != entry['signature']:
            raise ValueError('复制前数据发生变化。')
        with _directory(destination.parent) as parent:
            fd = os.open(destination.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as output:
            while True:
                _check(cancel)
                chunk = stream.read(CHUNK)
                if not chunk:
                    break
                _room(destination.parent, len(chunk))
                output.write(chunk)
                digest.update(chunk)
                length += len(chunk)
            output.flush()
            os.fsync(output.fileno())
        if _signature(os.fstat(stream.fileno())) != entry['signature'] or length != entry['size']:
            raise ValueError('复制期间数据发生变化。')
    expected = digest.hexdigest()
    if _hash_file(destination, cancel) != (expected, length):
        raise ValueError('目标实际读回与源文件不一致。')
    return expected


def _copy(root, destination, manifest, cancel=None):
    counts = {'files': 0, 'directories': 0, 'links': 0, 'bytes': 0, 'entries': 0}
    for source, entry, leaving in _walk(root, cancel):
        target = destination if entry['path'] == '.' else destination / entry['path']
        if leaving:
            _metadata(target, entry)
            continue
        if entry['kind'] == 'dir':
            if entry['path'] != '.':
                _mkdir(target)
            counts['directories'] += 1
        elif entry['kind'] == 'file':
            entry['sha256'] = _copy_file(source, target, entry, cancel)
            _metadata(target, entry)
            counts['files'] += 1
            counts['bytes'] += entry['size']
        else:
            _symlink(target, entry['target'])
            _metadata(target, entry)
            counts['links'] += 1
        encoded = _encoded(entry)
        _room(destination, len(encoded))
        manifest.write(encoded)
        counts['entries'] += 1
    return counts


def _validate_entry(entry):
    if not isinstance(entry, dict):
        raise ValueError('清单条目不是对象。')
    _path(entry.get('path'), root=True)
    if entry.get('kind') not in ('dir', 'file', 'link'):
        raise ValueError('清单文件类型无效。')
    if entry['path'] == '.' and entry['kind'] != 'dir':
        raise ValueError('清单根目录无效。')
    if (type(entry.get('mode')) is not int or not 0 <= entry['mode'] <= 0o7777 or
            type(entry.get('mtime_ns')) is not int or type(entry.get('size')) is not int or entry['size'] < 0 or
            not isinstance(entry.get('xattrs'), dict)):
        raise ValueError('清单元数据无效。')
    size = 0
    for name, encoded in entry['xattrs'].items():
        if not isinstance(name, str) or not name or '\0' in name or not isinstance(encoded, str):
            raise ValueError('扩展属性格式无效。')
        size += len(base64.b64decode(encoded, validate=True))
    if size > MAX_XATTR_BYTES:
        raise ValueError('扩展属性超过安全上限。')
    if entry['kind'] == 'file' and not re.fullmatch('[0-9a-f]{64}', str(entry.get('sha256', ''))):
        raise ValueError('文件摘要无效。')
    if entry['kind'] == 'link' and not isinstance(entry.get('target'), str):
        raise ValueError('链接目标无效。')
    return entry


def _manifest_entries(path, cancel=None):
    previous, count = None, 0
    with _regular(path) as stream:
        while True:
            _check(cancel)
            line = stream.readline(MAX_LINE + 1)
            if not line:
                break
            if len(line) > MAX_LINE or not line.endswith(b'\n'):
                raise ValueError('清单行超过安全上限或不完整。')
            entry = _validate_entry(_json_bytes(line))
            key = () if entry['path'] == '.' else tuple(entry['path'].split('/'))
            if (previous is None and key != ()) or (previous is not None and key <= previous):
                raise ValueError('清单路径重复、乱序或根目录缺失。')
            previous = key
            count += 1
            if count > MAX_ENTRIES:
                raise ValueError('清单超过条目安全上限。')
            yield entry
    if not count:
        raise ValueError('清单为空。')


def _verify_payload(payload, manifest, cancel=None, excluded=EXCLUDED, changes=None):
    actual = (entry for unused, entry, leaving in _walk(payload, cancel, excluded) if not leaving)
    change = next(changes, None) if changes is not None else None
    counts = {'files': 0, 'directories': 0, 'links': 0, 'bytes': 0, 'entries': 0}
    for expected in _manifest_entries(manifest, cancel):
        current = next(actual, None)
        if current is None or current['path'] != expected['path']:
            raise ValueError('备份内容存在缺失路径或清单外路径。')
        if change is not None and expected['path'] == change['path']:
            expected = {**expected, 'size': change['size'], 'sha256': change['sha256']}
            change = next(changes, None)
        for key in ('kind', 'mode', 'mtime_ns', 'size', 'xattrs', 'target'):
            if current.get(key) != expected.get(key):
                raise ValueError('备份内容、权限、时间或扩展属性与清单不一致。')
        if expected['kind'] == 'file':
            if _hash_file(payload / expected['path'], cancel) != (expected['sha256'], expected['size']):
                raise ValueError('备份文件摘要或长度不一致。')
            counts['files'] += 1
            counts['bytes'] += expected['size']
        else:
            counts['directories' if expected['kind'] == 'dir' else 'links'] += 1
        counts['entries'] += 1
    if next(actual, None) is not None or change is not None:
        raise ValueError('备份内容存在清单外路径或无效迁移修改记录。')
    return counts


def _external(root, managed_root=None):
    """Inspect only local registration metadata, never walk external sources."""
    scope = root if managed_root is None else Path(managed_root)
    paths, counts = [], {'git': 0, 'folder_source': 0, 'archive_repository': 0, 'archive_view': 0, 'archive_source': 0}
    projects = root / 'projects.json'
    if projects.exists() or projects.is_symlink():
        value = _read_json(projects)
        if not isinstance(value, dict) or value.get('schema') != 1 or not isinstance(value.get('projects'), list):
            raise ValueError('项目登记格式不受支持，无法确定备份边界。')
        for record in value['projects']:
            if not isinstance(record, dict) or not isinstance(record.get('path'), str):
                raise ValueError('项目登记路径无效。')
            paths.append(('folder_source' if record.get('kind') == 'folder' else 'git', record['path']))
    registry = root / 'named-archives' / 'registry.json'
    if registry.exists() or registry.is_symlink():
        value = _read_json(registry)
        if not isinstance(value, dict) or value.get('schema') != 1 or not isinstance(value.get('projects'), list):
            raise ValueError('旧归档登记格式不受支持，无法确定备份边界。')
        for group in value['projects']:
            if not isinstance(group, dict) or not isinstance(group.get('snapshots', []), list):
                raise ValueError('旧归档登记条目格式无效。')
            paths.extend((kind, group[field]) for kind, field in
                         [('archive_repository', 'archive_repository'), ('archive_view', 'view_repository')])
            paths.extend(('archive_source', row['source']) for row in group.get('snapshots', []))
    roots, examples = [], []
    for kind, raw in paths:
        if not isinstance(raw, str) or not raw or not Path(raw).is_absolute():
            raise ValueError('登记的外部来源路径无效。')
        path = Path(raw).resolve()
        roots.append(path)
        logical = Path(raw)
        internal = ((logical == scope or scope in logical.parents) if managed_root is not None
                    else (path == scope or scope in path.parents))
        if internal:
            continue
        counts[kind] += 1
        if len(examples) < 20:
            examples.append({'kind': kind, 'path': str(path), 'included': False})
    return roots, {'counts': counts, 'total': sum(counts.values()), 'examples': examples,
                   'examples_truncated': sum(counts.values()) > len(examples),
                   'note': '仅读取登记信息；外部来源未复制，也未验证可恢复性。'}


def _destination(value, forbidden):
    target = Path(value).expanduser().absolute()
    if os.path.lexists(target):
        raise ValueError('目标已存在，请选择全新目录；不会覆盖。')
    # All parent components must already exist and must not be symlinks.
    with _directory(target.parent):
        pass
    resolved = target.resolve()
    for root in forbidden:
        if resolved == root or root in resolved.parents or resolved in root.parents:
            raise ValueError('目标不得与数据、备份或已登记源目录重叠。')
    return target


def _alive(pid, identity):
    if type(pid) is not int or pid <= 1:
        return False
    from .processes import process_identity
    if isinstance(identity, str) and identity:
        actual = process_identity(pid)
        if actual is not None:
            return actual == identity
    # Missing identity is uncertainty, not evidence that this PID exited.
    # Signal 0 observes existence/permission only; never terminate a process.
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        pass
    raise ValueError('无法核验已登记进程是否退出；请先停止原 Reprise 任务。')


def _offline(root, cancel=None):
    snapshot = root / 'content/snapshot-transaction.json'
    if snapshot.exists() and _read_json(snapshot).get('state') not in ('complete', 'rolled_back'):
        raise ValueError('快照保存事务尚未完成；请先打开版本历史恢复一致状态，再备份。')
    transaction = root / 'content/delete-transaction.json'
    if transaction.exists() and _read_json(transaction).get('state') not in ('complete', 'rolled_back'):
        raise ValueError('版本删除事务尚未完成；请先明确重试该计划或恢复原库，再备份。')
    for path, entry, leaving in _walk(root, cancel):
        if leaving or entry['kind'] != 'file' or path.suffix != '.json':
            continue
        parts = path.relative_to(root).parts
        known = ((len(parts) == 3 and parts[0] == 'runtimes' and
                  (parts[-1] == 'runtime.json' or parts[-1].startswith('process-'))) or
                 (len(parts) == 3 and parts[0] in ('evidence', 'captures') and
                  (parts[-1].endswith('-worker.json') or parts[-1].endswith('-ownership.json') or
                   parts[-1].endswith('-browser-process.json'))) or
                 (len(parts) == 2 and parts[0] == 'jobs'))
        if not known:
            continue
        value = _read_json(path)
        if not isinstance(value, dict):
            raise ValueError('无法确认任务是否离线，进程状态记录无效。')
        active_job = parts[0] == 'jobs' and value.get('status') in ('queued', 'running', 'cancelling')
        starter = value.get('status') in ('preparing', 'install', 'build', 'starting')
        active_runtime = parts[0] == 'runtimes' and parts[-1] == 'runtime.json' and value.get('status') == 'running'
        required = ('owner_pid' if active_job or starter else 'pid')
        if (active_job or starter or active_runtime) and (type(value.get(required)) is not int or value[required] <= 1):
            raise ValueError('活动运行或任务缺少可核验的进程身份；无法确认已离线，请先检查原 Reprise 任务。')
        identities = [(value.get('pid'), value.get('process_identity')),
                      (value.get('root_pid'), value.get('root_identity'))]
        if (parts[0] == 'jobs' or value.get('status') in ('preparing', 'install', 'build', 'starting')):
            identities.append((value.get('owner_pid'), value.get('owner_identity')))
        identities.extend((row.get('pid'), row.get('identity')) for row in value.get('members', []) if isinstance(row, dict))
        # Finished jobs may retain the server PID as historical provenance.
        if parts[0] == 'jobs' and value.get('status') not in ('queued', 'running', 'cancelling'):
            continue
        if any(_alive(pid, identity) for pid, identity in identities):
            raise ValueError('仍有已登记 Reprise 运行或任务存活；请先在原 Reprise 停止预览和任务，再停止 Reprise 后备份。')


def _content_check(root, cancel=None):
    repository = root / 'content' / 'objects.git'
    if not repository.exists():
        project_file = root / 'projects.json'
        if project_file.exists():
            value = _read_json(project_file)
            if not isinstance(value, dict) or not isinstance(value.get('projects'), list):
                raise ValueError('项目登记格式无效，不能确认内容库边界。')
            if any(isinstance(row, dict) and row.get('kind') == 'folder' for row in value['projects']):
                raise ValueError('已登记普通文件夹的内容库缺失，不能确认独立备份。')
        return {'status': 'absent', 'note': '没有已管理的普通文件夹对象库。'}
    # The walk rejects every content symlink, including symlinked loose objects.
    for unused, entry, leaving in _walk(root / 'content', cancel, excluded=frozenset()):
        if not leaving and entry['kind'] == 'link':
            raise ValueError('内容库存储不能依赖符号链接。')
    if (repository / 'commondir').exists():
        raise ValueError('内容库使用公共 Git 目录，不能认定为自包含备份。')
    for name in ('alternates', 'http-alternates'):
        path = repository / 'objects' / 'info' / name
        if path.exists() and path.stat().st_size:
            raise ValueError('内容库使用替代对象来源；本次未读取外部对象。')
    config = repository / 'config'
    if config.exists():
        with _regular(config) as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024 or re.search(br'(?im)^\s*\[\s*(?:include|includeif|extensions|remote)\b', raw):
            raise ValueError('内容库包含外部配置、远端或扩展配置，无法确认本地独立性。')
    if any(path.suffix == '.promisor' for path in (repository / 'objects' / 'pack').glob('*')):
        raise ValueError('内容库包含按需下载对象，不能认定为完整独立备份。')
    command = ['git', '--no-pager', '--no-optional-locks', '-c', 'core.hooksPath=/dev/null',
               '-c', 'core.fsmonitor=false', '-c', 'gc.auto=0', '--git-dir=' + str(repository),
               'fsck', '--full', '--strict', '--no-dangling', '--no-progress']
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, env=_environment())
    deadline = time.monotonic() + 300
    try:
        while True:
            _check(cancel)
            if time.monotonic() > deadline:
                raise ValueError('内容库完整检查超时，未确认备份成功。')
            if select.select([process.stdout], [], [], .1)[0]:
                if not os.read(process.stdout.fileno(), 8192):
                    break
        while process.poll() is None:
            _check(cancel)
            if time.monotonic() > deadline:
                raise ValueError('内容库完整检查超时。')
            time.sleep(.02)
        if process.returncode:
            raise ValueError('内容库 Git 对象或引用不完整，未确认独立备份。')
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()
    return {'status': 'verified', 'method': 'git-fsck-full-strict-local-only'}


def _receipt(directory, value):
    _write_json(directory / 'receipt.json', value)


def _failure_receipt(path, value, error):
    try:
        _write_json(path, value)
    except (OSError, ValueError) as receipt_error:
        if hasattr(error, 'report'):
            error.report['receipt_error'] = '失败回执未写入；原回执/半成品保留：' + str(receipt_error)[:200]
        else:
            error.receipt_error = '取消回执未写入；原回执/半成品保留。'


def create_backup(data_directory, destination, cancel=None):
    """Create an offline self-contained managed-data backup at a new directory."""
    return _create_backup(data_directory, destination, cancel, DataLease(_root(data_directory), exclusive=True))


def _create_backup(data_directory, destination, cancel, lease):
    """Shared implementation. Service callers already hold an exclusive lease."""
    report = {'schema': SCHEMA, 'format': FORMAT, 'status': 'running', 'operation': 'backup',
              'created_at': now(), 'limitations': list(LIMITATIONS), 'excluded_root_files': sorted(EXCLUDED)}
    target = None
    try:
        _check(cancel)
        root = _root(data_directory)
        with lease:
            before = _inventory(root, cancel)
            roots, external = _external(root)
            candidate = _destination(destination, [root, *roots])
            _offline(root, cancel)
            if _inventory(root, cancel) != before:
                raise ValueError('源数据在边界检查期间发生变化；未开始备份。')
            required = _capacity(root, candidate.parent, cancel)
            report.update(source_directory=str(root), directory=str(candidate), external_dependencies=external,
                          device_relation='same-device' if root.stat().st_dev == candidate.parent.stat().st_dev else 'different-device',
                          independent_physical_device_confirmed=False)
            report['space_estimate_bytes'] = required
            report['reserved_free_bytes'] = RESERVE
            _mkdir(candidate)
            target = candidate
            _receipt(target, report)
            payload = target / 'payload'
            _mkdir(payload)
            with _new_file(target / 'manifest.jsonl') as manifest:
                counts = _copy(root, payload, manifest, cancel)
                manifest.flush()
                os.fsync(manifest.fileno())
            os.chmod(target / 'manifest.jsonl', 0o600)
            if _inventory(root, cancel) != before:
                raise ValueError('源数据在备份期间发生变化；半成品保留，未确认成功。')
            managed = _content_check(payload, cancel)
            actual = _verify_payload(payload, target / 'manifest.jsonl', cancel)
            if actual != counts or _inventory(root, cancel) != before:
                raise ValueError('源数据或目标在备份校验期间发生变化。')
            digest, length = _hash_file(target / 'manifest.jsonl', cancel)
            _check(cancel)
            report.update(status='complete', finished_at=now(), counts=counts, content_store=managed,
                          manifest={'sha256': digest, 'bytes': length, 'entries': counts['entries']},
                          readback_verified=True, source_consistency_verified=True)
            _receipt(target, report)
        return report
    except Cancelled as error:
        if target is not None:
            _failure_receipt(target / 'receipt.json', {**report, 'status': 'cancelled', 'finished_at': now()}, error)
        raise
    except (ValueError, OSError, UnicodeError, KeyError, TypeError, RecursionError) as error:
        failure = BackupError(str(error), report)
        if target is not None:
            _failure_receipt(target / 'receipt.json', {**failure.report, 'finished_at': now()}, failure)
        raise failure from None


def _verify(backup_directory, cancel):
    root = _root(backup_directory)
    if set(path.name for path in root.iterdir()) != {'payload', 'manifest.jsonl', 'receipt.json'}:
        raise ValueError('备份目录包含额外路径或缺少必需文件。')
    receipt = _read_json(root / 'receipt.json')
    if (not isinstance(receipt, dict) or receipt.get('format') != FORMAT or
            receipt.get('schema') != SCHEMA or receipt.get('status') != 'complete'):
        raise ValueError('备份不完整或格式不受支持，不能恢复。')
    manifest = receipt.get('manifest')
    if (not isinstance(manifest, dict) or set(manifest) != {'sha256', 'bytes', 'entries'} or
            type(manifest.get('bytes')) is not int or
            type(manifest.get('entries')) is not int or not 1 <= manifest['entries'] <= MAX_ENTRIES or
            not re.fullmatch('[0-9a-f]{64}', str(manifest.get('sha256', '')))):
        raise ValueError('备份清单校验摘要无效。')
    expected = (manifest['sha256'], manifest['bytes'])
    if _hash_file(root / 'manifest.jsonl', cancel) != expected:
        raise ValueError('备份清单摘要不一致，清单已损坏或被修改。')
    before = _inventory(root / 'payload', cancel, excluded=frozenset())
    counts = _verify_payload(root / 'payload', root / 'manifest.jsonl', cancel, excluded=frozenset())
    managed = _content_check(root / 'payload', cancel)
    if (counts['entries'] != manifest['entries'] or counts != receipt.get('counts') or
            _inventory(root / 'payload', cancel, excluded=frozenset()) != before or
            _hash_file(root / 'manifest.jsonl', cancel) != expected or
            _read_json(root / 'receipt.json') != receipt):
        raise ValueError('备份在校验期间发生变化或统计不一致。')
    return root, receipt, counts, managed


def verify_backup(backup_directory, cancel=None):
    """Read-only verification; no repair, source access, network or process stop."""
    try:
        _check(cancel)
        root, receipt, counts, managed = _verify(backup_directory, cancel)
        source = receipt.get('source_directory')
        if not isinstance(source, str) or not Path(source).is_absolute():
            raise ValueError('备份缺少有效原数据目录记录。')
        unused, external = _external(root / 'payload', managed_root=source)
        _check(cancel)
        return {'schema': SCHEMA, 'operation': 'verify-backup', 'status': 'verified', 'directory': str(root),
                'counts': counts, 'manifest': receipt['manifest'], 'content_store': managed,
                'external_dependencies': external, 'readback_verified': True,
                'limitations': list(LIMITATIONS), 'verified_at': now()}
    except Cancelled:
        raise
    except (ValueError, OSError, UnicodeError, KeyError, TypeError, RecursionError) as error:
        if isinstance(error, BackupError):
            raise
        raise BackupError(str(error), {'operation': 'verify-backup'}) from None


def _relocated(value, old, new):
    if not isinstance(value, str) or not Path(value).is_absolute():
        return value
    path = Path(value)
    try:
        relative = path.relative_to(old)
    except ValueError:
        return value
    if '..' in relative.parts:
        raise ValueError('已知管理路径包含不安全父路径。')
    return str(new / relative)


def _transform(relative, value, old, new):
    """Only documented state-file fields change; notes/recipes/user JSON stay exact."""
    parts = relative.split('/')
    if not isinstance(value, dict):
        raise ValueError('已知管理状态文件格式无效，不能安全迁移。')
    def fields(row, names):
        if isinstance(row, dict):
            for name in names:
                if name in row:
                    row[name] = _relocated(row[name], old, new)
    process = False
    if relative == 'projects.json':
        if value.get('schema') != 1 or not isinstance(value.get('projects'), list):
            raise ValueError('无法迁移不受支持的项目登记格式。')
        for row in value['projects']:
            fields(row, ('path',))
            preference = row.get('preview_preferences', {})
            if preference.get('mode') == 'auto':
                # A copied preference is not consent to execute on this machine.
                row['preview_preferences'] = {'mode': 'remind', 'restored_auto_requires_confirmation': True}
    elif relative == 'named-archives/registry.json':
        if value.get('schema') != 1 or not isinstance(value.get('projects'), list):
            raise ValueError('无法迁移不受支持的旧归档登记格式。')
        for group in value['projects']:
            fields(group, ('archive_repository', 'view_repository'))
            for row in group.get('snapshots', []):
                fields(row, ('source',))
    elif relative == 'server.json':
        fields(value, ('data_directory',))
        for name in ('pid', 'identity', 'url', 'instance_id'):
            value[name] = None
        process = True
    elif len(parts) == 3 and parts[0] in ('evidence', 'captures'):
        if parts[-1] == 'record.json' or parts[-1].endswith('-result.json'):
            for row in value.get('items', []):
                fields(row, ('path',))
            for row in value.get('runtimes', []):
                fields(row, ('path', 'log_path'))
            if value.get('status') == 'running':
                value['status'] = 'interrupted'
        elif parts[-1].endswith('-input.json'):
            fields(value, ('output_dir', 'result_path', 'browser_process_path'))
        elif parts[-1].endswith(('-worker.json', '-browser-process.json', '-ownership.json')):
            process = True
    elif len(parts) == 3 and parts[0] == 'runtimes':
        if parts[-1] == 'runtime.json':
            fields(value, ('path', 'root', 'log_path', 'source'))
            value.update(status='interrupted', running=False, url=None, port=None,
                         process_trees=[], process_tree=None, startup_lock=False)
            process = True
        elif parts[-1].startswith('process-') and parts[-1].endswith('.json'):
            process = True
    elif len(parts) == 3 and parts[0] == 'environments' and parts[-1] == 'environment.json':
        fields(value, ('workspace',))
        for row in value.get('attempts', []):
            fields(row, ('workspace',))
        fields(value.get('materialization'), ('path',))
        fields(value.get('last_release'), ('receipt',))
        value.update(status='restored-rebuild-required', rebuild_verified=False,
                     restored_historical_report=True)
    elif len(parts) == 4 and parts[0] == 'environments' and parts[2] == 'releases':
        fields(value, ('receipt',))
        value['restored_historical_report'] = True
    elif len(parts) == 2 and parts[0] == 'version-deletions':
        fields(value, ('receipt_path',))
        value['restored_historical_report'] = True
        if parts[-1].endswith('.plan.json'):
            value['restored_review_required'] = True
    elif len(parts) == 3 and parts[0] == 'folder-imports':
        fields(value, ('report_path', 'review_receipt'))
        if isinstance(value.get('preflight'), dict):
            value['preflight'].update(restored_historical_report=True, capacity_available=False)
        for row in value.get('versions', []):
            fields(row, ('recovery_path',))
            row.update(removal_candidate=False, blockers=['从备份恢复的报告需要重新核对原件。'])
        value.update(status='restored-review-required', candidate_logical_bytes=0,
                     candidate_allocated_bytes=0, modeled_net_after_source_removal_bytes=None,
                     conditional_net_if_readbacks_also_removed_bytes=None, accounting_historical=True)
    elif relative == 'content/delete-transaction.json':
        fields(value, ('replacement', 'retired', 'receipt_path'))
        value['restored_historical_report'] = True
    elif len(parts) == 3 and parts[0] == 'recoveries' and parts[-1] == 'receipt.json':
        fields(value, ('path',))
        fields(value.get('report'), ('path',))
    elif len(parts) == 3 and parts[0] == 'organization' and parts[-1] == 'plan.json':
        fields(value, ('source', 'recovery_path', 'receipt'))
        if isinstance(value.get('frozen_protections'), list):
            value['frozen_protections'] = [_relocated(p, old, new) for p in value['frozen_protections']]
        # Selection concerned the old location. It is historical, not a new delete authority.
        value.update(status='restored-review-required', selected_paths=[], selected_count=0)
    elif len(parts) == 2 and parts[0] == 'relocations' and parts[-1].endswith('.json'):
        if value.get('format') == 'reprise-relocation-v1':
            # Source/target are historical external-project provenance.
            fields(value, ('receipt_path',))
    elif len(parts) == 2 and parts[0] == 'jobs' and parts[-1].endswith('.json'):
        operation, result, request = value.get('operation'), value.get('result'), value.get('request')
        if operation in ('restore', 'export'):
            fields(request, ('to',))
            fields(result, ('path',))
            if isinstance(result, dict):
                fields(result.get('report'), ('path',))
        elif operation == 'run' and isinstance(result, dict):
            value['result'] = _transform('runtimes/restored/runtime.json', result, old, new)
        elif operation == 'capture' and isinstance(result, dict):
            value['result'] = _transform('evidence/restored/record.json', result, old, new)
        elif operation == 'organize' and isinstance(result, dict):
            fields(result, ('receipt',))
            result.update(status='restored-review-required', selected_count=0)
        elif operation == 'folder-import-preflight' and isinstance(result, dict):
            fields(result, ('data_directory',))
            result.update(restored_historical_report=True, capacity_available=False,
                          filesystem_free_bytes=None, status='restored-preview-required')
        elif operation in ('import-folders', 'folder-import-review') and isinstance(result, dict):
            value['result'] = _transform('folder-imports/restored/report.json', result, old, new)
        elif operation == 'storage' and isinstance(result, dict):
            # These old disk numbers describe their original location/time.
            result['restored_historical_report'] = True
        elif operation == 'version-delete' and isinstance(result, dict):
            fields(result, ('receipt_path',))
            result['restored_historical_report'] = True
        elif operation in ('relink-check', 'relink', 'migrate', 'backup-check', 'data-restore'):
            fields(request, ('to', 'backup'))
            fields(result, ('target', 'destination', 'directory', 'backup_directory', 'receipt_path'))
            if isinstance(result, dict):
                result['restored_historical_report'] = True
        if value.get('status') in ('queued', 'running', 'cancelling'):
            value.update(status='failed', error='从备份恢复的任务已中断；未重新执行，请明确重试。', finished_at=now())
        process = True
    if process:
        for name in ('pid', 'process_identity', 'owner_pid', 'owner_identity', 'root_pid',
                     'root_identity', 'boot_identity', 'owner_marker'):
            if name in value:
                value[name] = None
        if 'members' in value:
            value['members'] = []
        value['restored_process_authority_disabled'] = True
    return value


def _known_json(relative):
    parts = relative.split('/')
    return (relative in ('projects.json', 'named-archives/registry.json', 'server.json', 'content/delete-transaction.json') or
            (len(parts) == 3 and parts[0] == 'folder-imports' and
             (parts[-1] == 'report.json' or (parts[-1].startswith('review-') and parts[-1].endswith('.json')))) or
            (len(parts) == 3 and parts[0] == 'environments' and parts[-1] == 'environment.json') or
            (len(parts) == 4 and parts[0] == 'environments' and parts[2] == 'releases' and parts[-1].endswith('.json')) or
            (len(parts) == 2 and parts[0] == 'version-deletions' and parts[-1].endswith(('.plan.json', '.receipt.json'))) or
            (len(parts) == 3 and parts[0] in ('evidence', 'captures', 'runtimes', 'recoveries', 'organization') and
             (parts[-1] in ('record.json', 'runtime.json', 'receipt.json', 'plan.json') or
              parts[-1].endswith(('-input.json', '-result.json', '-worker.json', '-browser-process.json', '-ownership.json')) or
              (parts[0] == 'runtimes' and parts[-1].startswith('process-') and parts[-1].endswith('.json')))) or
            (len(parts) == 2 and parts[0] in ('jobs', 'relocations') and parts[-1].endswith('.json')))


def _changes(path, cancel):
    with _regular(path) as stream:
        for line in stream:
            _check(cancel)
            if len(line) > MAX_LINE:
                raise ValueError('迁移修改记录过大。')
            yield _json_bytes(line)


def restore_backup(backup_directory, destination, cancel=None):
    """Restore verified data to a fresh root; keep sources and disable old PIDs."""
    report = {'schema': SCHEMA, 'operation': 'restore-backup', 'status': 'running', 'created_at': now(),
              'limitations': list(LIMITATIONS) + ['恢复不启动旧运行；进程身份已禁用，旧运行和活动任务需明确重新执行。']}
    target = sidecar = None
    try:
        _check(cancel)
        backup, original, counts, managed = _verify(backup_directory, cancel)
        source = original.get('source_directory')
        if not isinstance(source, str) or not Path(source).is_absolute():
            raise ValueError('备份缺少原数据目录，不能安全迁移内部路径。')
        old = Path(source)
        roots, external = _external(backup / 'payload', managed_root=old)
        candidate = _destination(destination, [backup, old, *roots])
        required = _capacity(backup / 'payload', candidate.parent, cancel)
        _mkdir(candidate)
        target = candidate
        sidecar = target.parent / (target.name + '.restore-' + secrets.token_hex(8))
        _mkdir(sidecar)
        report.update(directory=str(target), backup_directory=str(backup), source_directory=source,
                      receipt_path=str(sidecar / 'receipt.json'),
                      external_dependencies=external, device_relation='same-device' if backup.stat().st_dev == target.stat().st_dev else 'different-device',
                      independent_physical_device_confirmed=False)
        report['space_estimate_bytes'] = required
        report['reserved_free_bytes'] = RESERVE
        with DataLease(target, exclusive=True):
            _write_json(sidecar / 'receipt.json', report)
            root_entry = None
            for entry in _manifest_entries(backup / 'manifest.jsonl', cancel):
                _check(cancel)
                path = target if entry['path'] == '.' else target / entry['path']
                source_path = backup / 'payload' if entry['path'] == '.' else backup / 'payload' / entry['path']
                if entry['path'] == '.':
                    root_entry = entry
                elif entry['kind'] == 'dir':
                    _mkdir(path)
                elif entry['kind'] == 'file':
                    # Signature belongs to the payload copy, not its original inode.
                    copied = _copy_file(source_path, path, _entry(backup / 'payload', source_path), cancel)
                    if copied != entry['sha256']:
                        raise ValueError('恢复期间备份文件发生变化。')
                    _metadata(path, entry)
                else:
                    _link(backup / 'payload', source_path, entry['target'])
                    _symlink(path, entry['target'])
                    _metadata(path, entry)
            # Exit events restore directory times with only a depth-sized stack.
            for unused, entry, leaving in _walk(backup / 'payload', cancel, excluded=frozenset()):
                if leaving:
                    _metadata(target if entry['path'] == '.' else target / entry['path'], entry)
            _verify_payload(target, backup / 'manifest.jsonl', cancel)
            changed = 0
            with _new_file(sidecar / 'changes.jsonl') as changes:
                for entry in _manifest_entries(backup / 'manifest.jsonl', cancel):
                    if entry['kind'] != 'file' or not _known_json(entry['path']):
                        continue
                    _check(cancel)
                    path = target / entry['path']
                    value = _read_json(path)
                    before = _encoded(value)
                    result = _transform(entry['path'], value, old, target)
                    if _encoded(result) == before:
                        continue
                    _room(path.parent, len(_encoded(result)))
                    _write_json(path, result)
                    _metadata(path, entry)
                    digest, length = _hash_file(path, cancel)
                    changes.write(_encoded({'path': entry['path'], 'sha256': digest, 'size': length}))
                    changed += 1
                changes.flush()
                os.fsync(changes.fileno())
            os.chmod(sidecar / 'changes.jsonl', 0o600)
            for unused, entry, leaving in _walk(backup / 'payload', cancel, excluded=frozenset()):
                if leaving:
                    _metadata(target if entry['path'] == '.' else target / entry['path'], entry)
            restored_before = _inventory(target, cancel)
            actual = _verify_payload(target, backup / 'manifest.jsonl', cancel,
                                     changes=_changes(sidecar / 'changes.jsonl', cancel))
            restored_content = _content_check(target, cancel)
            # Full backup revalidation catches mutations during restore, without the old root.
            _verify(backup, cancel)
            if _inventory(target, cancel) != restored_before:
                raise ValueError('恢复目标在最终校验期间发生变化；未确认迁移成功。')
            digest, length = _hash_file(sidecar / 'changes.jsonl', cancel)
            _check(cancel)
            report.update(status='complete', finished_at=now(), counts=actual, content_store=restored_content,
                          source_manifest=original['manifest'], metadata_files_migrated=changed,
                          changes={'sha256': digest, 'bytes': length}, readback_verified=True,
                          process_authority_disabled=True)
            _write_json(sidecar / 'receipt.json', report)
            # Restore receipt writes must not replace the original data-root time.
            if root_entry is not None:
                _metadata(target, root_entry)
        return report
    except Cancelled as error:
        if sidecar is not None:
            _failure_receipt(sidecar / 'receipt.json', {**report, 'status': 'cancelled', 'finished_at': now()}, error)
        raise
    except (ValueError, OSError, UnicodeError, KeyError, TypeError, RecursionError) as error:
        failure = BackupError(str(error), report)
        if sidecar is not None:
            _failure_receipt(sidecar / 'receipt.json', {**failure.report, 'finished_at': now()}, failure)
        raise failure from None
