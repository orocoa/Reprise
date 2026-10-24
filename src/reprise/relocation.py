"""Explicit, read-only-source relocation with identity checks and retained receipts.

Migration copies to a new directory; it never moves or deletes a source. Git is
only inspected, with the same isolated, read-only commands as Repository.
"""
import base64
import contextlib
import ctypes
import fnmatch
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import posixpath
import secrets
import shutil
import stat
import sys

from .cancellation import check
from .folders import _directory, _open_file, signature
from .git import Repository
from .metadata import xattrs, has_acl
from .maintenance import DataLease
from .storage import locked, now, read_json, write_json

MAX_ENTRIES = 250000
MAX_BYTES = 128 * 1024 * 1024 * 1024
CHUNK = 1024 * 1024


def _overlap(left, right):
    return left == right or left in right.parents or right in left.parents


def _path(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 4096 or '\0' in value:
        raise ValueError('请填写本地目录路径。')
    return Path(value).expanduser().resolve()


def _raw(projects):
    return read_json(projects.file, {'schema': 1, 'projects': []})


def _record(projects, identifier):
    identifier = projects.identify(identifier)
    record = projects.record(identifier)
    if record.get('kind') == 'archive':
        raise ValueError('旧归档登记由独立归档目录管理；此操作不会改写归档 registry 或 overlay。')
    raw = next((p for p in _raw(projects)['projects'] if p['id'] == identifier), None)
    if raw is None:
        raise ValueError('项目没有可重新关联的源目录登记。')
    return raw


def _paths(projects, record, target, *, exists=True, protected_roots=()):
    source = Path(record['path']).resolve()
    target = _path(target)
    data = projects.directory.resolve()
    if _overlap(source, data) or _overlap(target, data):
        raise ValueError('项目源目录、目标目录与 Reprise data 必须互不包含。')
    if source != target and _overlap(source, target):
        raise ValueError('目标目录与原目录不能互相包含。')
    if exists and not target.is_dir():
        raise ValueError('重新关联的目录不存在：' + str(target))
    for other in projects.records():
        if other['id'] != record['id'] and Path(other['path']).resolve() == target:
            raise ValueError('目标目录已由其他项目登记，不能合并或覆盖项目身份。')
    for value in protected_roots:
        root = Path(value).expanduser().resolve()
        if _overlap(source, root) or _overlap(target, root):
            raise ValueError('源目录或目标目录包含受保护的运行目录；请先停止相关运行。')
    return source, target


def _excluded(relative, rules, skip_git):
    return (skip_git and relative.split('/')[-1].casefold() == '.git') or any(
        fnmatch.fnmatchcase(relative, rule) or fnmatch.fnmatchcase(relative + '/', rule) or
        relative == rule.removesuffix('/**') for rule in rules)


def _scan(root, cancel=None, *, exclude=(), skip_git=False, metadata=False):
    """Bounded streamed hashes; no symlink traversal and no inode identity guesses."""
    check(cancel)
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError('源目录已不可用或已被替换。')
    root_stat = root.stat()
    entries, total = {}, 0
    def meta(path, value):
        result = {'mode': stat.S_IMODE(value.st_mode) & 0o777,
                  'mtime_ns': value.st_mtime_ns, 'xattrs': xattrs(path)}
        if metadata and stat.S_IMODE(value.st_mode) & 0o7000:
            raise ValueError('目录迁移暂不复制特殊权限位；原文件保留：' + str(path))
        if metadata and has_acl(path):
            raise ValueError('目录迁移暂不复制 ACL；原文件保留：' + str(path))
        return result
    root_meta = meta(root, root_stat) if metadata else {}
    def fail(error):
        raise error
    with _directory(root) as root_fd:
        for directory, directories, files in os.walk(root, followlinks=False, onerror=fail):
            check(cancel)
            directories.sort()
            for name in sorted(directories + files):
                check(cancel)
                path = Path(directory) / name
                relative = path.relative_to(root).as_posix()
                if _excluded(relative, exclude, skip_git):
                    if name in directories:
                        directories.remove(name)
                    continue
                if len(entries) >= MAX_ENTRIES:
                    raise ValueError('目录超过迁移检查的文件数量上限。')
                value = path.lstat()
                kind = ('link' if stat.S_ISLNK(value.st_mode) else
                        'dir' if stat.S_ISDIR(value.st_mode) else
                        'file' if stat.S_ISREG(value.st_mode) else None)
                if kind is None:
                    raise ValueError('不能迁移或验证特殊文件：' + relative)
                entry = {'kind': kind, 'signature': signature(value)}
                if metadata:
                    entry.update(meta(path, value))
                if kind == 'file':
                    total += value.st_size
                    if total > MAX_BYTES:
                        raise ValueError('目录超过 128 GiB 迁移检查上限，请分开管理。')
                    digest = hashlib.sha256()
                    with _open_file(root_fd, relative) as stream:
                        if signature(os.fstat(stream.fileno())) != entry['signature']:
                            raise ValueError('检查期间文件发生变化：' + relative)
                        size = 0
                        while True:
                            check(cancel)
                            chunk = stream.read(CHUNK)
                            if not chunk:
                                break
                            size += len(chunk)
                            if size > value.st_size:
                                raise ValueError('检查期间文件发生变化：' + relative)
                            digest.update(chunk)
                        if size != value.st_size or signature(os.fstat(stream.fileno())) != entry['signature']:
                            raise ValueError('检查期间文件发生变化：' + relative)
                    entry.update(size=size, sha256=digest.hexdigest())
                elif kind == 'link':
                    target = os.readlink(path)
                    normalized = posixpath.normpath(posixpath.join(posixpath.dirname(relative), target))
                    if (not target or target.startswith('/') or '\\' in target or
                            normalized == '..' or normalized.startswith('../')):
                        raise ValueError('链接必须位于项目目录内部：' + relative)
                    try:
                        path.resolve().relative_to(root)
                    except (ValueError, RuntimeError):
                        raise ValueError('链接必须位于项目目录内部且不能循环：' + relative) from None
                    entry.update(target=target, size=len(os.fsencode(target)),
                                 sha256=hashlib.sha256(os.fsencode(target)).hexdigest())
                entries[relative] = entry
                if signature(path.lstat()) != entry['signature']:
                    raise ValueError('检查期间路径发生变化：' + relative)
    if signature(root.stat()) != signature(root_stat):
        raise ValueError('检查期间目录发生变化。')
    return {'entries': entries, 'root': root_meta, 'root_signature': signature(root_stat),
            'logical_bytes': total}


def _content(entries):
    return {name: ({'kind': 'dir'} if entry['kind'] == 'dir' else
                   {key: entry[key] for key in ('kind', 'size', 'sha256', 'target') if key in entry})
            for name, entry in entries.items()}


def _portable(scan):
    return {'root': scan['root'], 'entries': {
        name: {key: value for key, value in entry.items() if key != 'signature'}
        for name, entry in scan['entries'].items()}}


def git_anchor(repository):
    """Persist real commit identities, without altering the imported repository."""
    info = repository.info()
    commits = ([info['head']] if info['head'] else []) + [
        item['sha'] for item in repository.refs() if item.get('target_type') == 'commit']
    return {'format': 'reprise-git-anchor-v1', 'object_format': info['object_format'],
            'commits': list(dict.fromkeys(commits))[:32], 'recorded_at': now()}


def _git_identity(anchor, candidate, cancel=None):
    info = candidate.info()
    if (not isinstance(anchor, dict) or anchor.get('format') != 'reprise-git-anchor-v1' or
            anchor.get('object_format') != info['object_format'] or not anchor.get('commits')):
        raise ValueError('原目录离线且没有可验证的 Git 锚点；不能按名称或候选目录自动认定身份。')
    for sha in anchor['commits']:
        check(cancel)
        if not isinstance(sha, str) or len(sha) not in (40, 64) or any(c not in '0123456789abcdef' for c in sha):
            raise ValueError('Git 身份锚点无效。')
        try:
            candidate.resolve(sha)
            data = candidate._run('cat-file', 'commit', sha, max_output=4 * 1024 * 1024)
            algorithm = hashlib.sha256 if info['object_format'] == 'sha256' else hashlib.sha1
            if algorithm(('commit %d\0' % len(data)).encode('ascii') + data).hexdigest() != sha:
                raise ValueError('Git 锚点对象校验失败。')
            reachable = bool(candidate._run('for-each-ref', '--contains=' + sha, '--format=%(refname)'))
            if not reachable and info['head']:
                candidate._run('merge-base', '--is-ancestor', sha, info['head'])
                reachable = True
            if reachable:
                return sha
        except ValueError:
            continue
    raise ValueError('候选 Git 目录没有可验证的共同提交或引用；没有重新关联。')


def _inspect(projects, record, target, cancel=None, protected_roots=()):
    check(cancel)
    source, target = _paths(projects, record, target, protected_roots=protected_roots)
    online = source.is_dir()
    kind = record.get('kind', 'git')
    if kind == 'folder':
        if online:
            original = _scan(source, cancel)
            candidate = _scan(target, cancel)
            if _content(original['entries']) != _content(candidate['entries']):
                raise ValueError('候选文件夹与当前源目录的路径、内容或链接不一致；未保存改动也必须保留。')
            if original != _scan(source, cancel):
                raise ValueError('验证期间源目录发生变化。')
            evidence = {'method': 'online-source-bytes', 'entries': len(candidate['entries'])}
        else:
            candidate = _scan(target, cancel, exclude=record.get('exclusions', []), skip_git=True)
            repository = projects.folders.repository(record)
            head = repository.info()['head']
            if not head:
                raise ValueError('原文件夹离线且没有已保存版本，不能自动认定候选目录。')
            # Read the complete project history, rather than a UI page of 50 rows.
            revisions = repository._run('rev-list', repository.ref).decode('ascii').splitlines()
            matched = None
            for sha in revisions:
                check(cancel)
                if _content(repository.manifest(sha)['entries']) == _content(candidate['entries']):
                    matched = sha
                    break
                repository._manifests.clear()
            if matched is None:
                raise ValueError('候选文件夹未精确匹配任何已保存版本的路径、字节与链接。')
            evidence = {'method': 'saved-folder-version', 'sha': matched,
                        'entries': len(candidate['entries']),
                        'exclusions': record.get('exclusions', []), 'git_metadata_excluded': True}
        limitations = ['身份验证核对相对路径、文件字节和链接；不凭同名、mtime 或 inode 认定。']
    else:
        candidate = Repository(target, status_directory=projects.directory / 'git-status')
        if candidate.path != target:
            raise ValueError('请选择 Git 项目的根目录。')
        anchor = git_anchor(Repository(source, status_directory=projects.directory / 'git-status')) if online else record.get('git_identity_anchor')
        common = _git_identity(anchor, candidate, cancel)
        evidence = {'method': 'online-git-common-commit' if online else 'saved-git-anchor', 'sha': common}
        limitations = ['Git 身份验证确认共同真实提交；重新关联不会复制未提交内容或改写 Git 元数据。']
    check(cancel)
    return {'project_id': record['id'], 'kind': kind, 'source': str(source), 'target': str(target),
            'source_available': online, 'identity_evidence': evidence,
            'scope': 'source-directory-registration', 'limitations': limitations, 'not_deleted': True}


def _leased(function):
    @wraps(function)
    def execute(projects, *args, **kwargs):
        with DataLease(projects.directory):
            return function(projects, *args, **kwargs)
    return execute


@_leased
def inspect_relink(projects, identifier, new_path, cancel=None, protected_roots=()):
    """Return reviewable evidence; this does not modify a project registration."""
    return _inspect(projects, _record(projects, identifier), new_path, cancel, protected_roots)


@_leased
def relink(projects, identifier, new_path, cancel=None, protected_roots=()):
    """Revalidate under projects.lock and replace only the stored source path."""
    with projects.lock, locked(projects.lockfile):
        record = _record(projects, identifier)
        result = _inspect(projects, record, new_path, cancel, protected_roots)
        document = _raw(projects)
        current = next(p for p in document['projects'] if p['id'] == record['id'])
        if current != record:
            raise ValueError('项目登记在验证期间发生变化，请重试。')
        check(cancel)
        current['path'] = result['target']
        write_json(projects.file, document, private=True)
        projects.cache.clear()
        return {**result, 'relinked': True}


def _migratable_git(projects, source):
    repository = Repository(source, status_directory=projects.directory / 'git-status')
    git = source / '.git'
    info = repository.info()
    if (repository.bare or not git.is_dir() or git.is_symlink() or repository.git_dir != git.resolve() or
            (git / 'commondir').exists() or (git / 'worktrees').exists()):
        raise ValueError('此 Git 使用 bare、linked worktree 或共享元数据；请先自行准备完整副本后使用验证重新关联。')
    if info['partial_clone']:
        raise ValueError('部分克隆可能依赖外部对象；不能声明完整目录迁移。')
    if (git / 'objects/info/alternates').exists() or (git / 'objects/info/http-alternates').exists():
        raise ValueError('Git 对象库依赖外部 alternates，暂不能完整目录迁移。')
    config = repository._run('config', '--local', '--list', '--null').split(b'\0')
    for item in config:
        key = item.partition(b'\n')[0].lower()
        if key in (b'core.worktree', b'core.bare'):
            if key == b'core.worktree' or item.partition(b'\n')[2] == b'true':
                raise ValueError('Git 配置含外部工作目录，暂不能完整目录迁移。')
        if key.startswith(b'include.') or key.startswith(b'includeif.'):
            raise ValueError('Git 配置依赖 include 文件，暂不能完整目录迁移。')
    return repository


def _fd_xattrs(fd, values=None):
    """Read/restore xattrs on a held inode, including Apple's system Python."""
    if hasattr(os, 'listxattr'):
        current = {key: os.getxattr(fd, key) for key in os.listxattr(fd)}
        if sum(map(len, current.values())) > 2 * 1024 * 1024:
            raise ValueError('扩展属性超过迁移上限。')
        if values is not None:
            decoded = {key: base64.b64decode(value, validate=True) for key, value in values.items()}
            for key in set(current) - set(decoded):
                os.removexattr(fd, key)
            for key, value in decoded.items():
                if current.get(key) != value:
                    os.setxattr(fd, key, value)
        else:
            return {key: base64.b64encode(value).decode('ascii') for key, value in current.items()}
    elif sys.platform == 'darwin':
        lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
        lib.flistxattr.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
        lib.flistxattr.restype = ctypes.c_ssize_t
        lib.fgetxattr.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
        lib.fgetxattr.restype = ctypes.c_ssize_t
        lib.fsetxattr.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
        lib.fsetxattr.restype = ctypes.c_int
        lib.fremovexattr.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        lib.fremovexattr.restype = ctypes.c_int
        size = lib.flistxattr(fd, None, 0, 0)
        if size < 0 or size > 2 * 1024 * 1024:
            raise OSError(ctypes.get_errno(), '无法读取迁移目标扩展属性')
        names = ctypes.create_string_buffer(size)
        if lib.flistxattr(fd, names, size, 0) != size:
            raise ValueError('迁移目标扩展属性发生变化。')
        current, total = {}, 0
        for key in names.raw.split(b'\0'):
            if not key:
                continue
            length = lib.fgetxattr(fd, key, None, 0, 0, 0)
            if length < 0 or total + length > 2 * 1024 * 1024:
                raise OSError(ctypes.get_errno(), '无法完整读取迁移目标扩展属性')
            buffer = ctypes.create_string_buffer(length)
            if lib.fgetxattr(fd, key, buffer, length, 0, 0) != length:
                raise ValueError('迁移目标扩展属性发生变化。')
            total += length
            current[os.fsdecode(key)] = buffer.raw
        if values is None:
            return {key: base64.b64encode(value).decode('ascii') for key, value in current.items()}
        decoded = {key: base64.b64decode(value, validate=True) for key, value in values.items()}
        for key in set(current) - set(decoded):
            if lib.fremovexattr(fd, os.fsencode(key), 0):
                raise OSError(ctypes.get_errno(), '无法恢复迁移目标扩展属性')
        for key, value in decoded.items():
            if current.get(key) == value:
                continue
            if lib.fsetxattr(fd, os.fsencode(key), value, len(value), 0, 0):
                raise OSError(ctypes.get_errno(), '无法恢复迁移目标扩展属性')
    else:
        raise ValueError('此平台不支持完整迁移扩展属性。')
    if _fd_xattrs(fd) != values:
        raise ValueError('迁移目标扩展属性读回不一致。')


def xattrs_fd(fd):
    return _fd_xattrs(fd)


def restore_xattrs_fd(fd, values):
    return _fd_xattrs(fd, values)


@contextlib.contextmanager
def _parent(root_fd, name):
    directory = os.dup(root_fd)
    try:
        pieces = name.split('/')
        for piece in pieces[:-1]:
            next_fd = os.open(piece, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = next_fd
        yield directory, pieces[-1]
    finally:
        os.close(directory)


def _copy(source, target, scan, cancel=None):
    # All target writes are relative to open, no-follow directory descriptors;
    # a concurrently substituted directory symlink cannot redirect writes.
    with _directory(source) as source_fd, _directory(target) as target_fd:
        for name, entry in scan['entries'].items():
            check(cancel)
            with _parent(target_fd, name) as (parent, basename):
                if entry['kind'] == 'dir':
                    os.mkdir(basename, mode=0o700, dir_fd=parent)
                elif entry['kind'] == 'link':
                    os.symlink(entry['target'], basename, dir_fd=parent)
                else:
                    with _open_file(source_fd, name) as stream:
                        if signature(os.fstat(stream.fileno())) != entry['signature']:
                            raise ValueError('复制前源文件发生变化：' + name)
                        fd = os.open(basename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                     0o600, dir_fd=parent)
                        with os.fdopen(fd, 'wb') as output:
                            digest, size = hashlib.sha256(), 0
                            while True:
                                check(cancel)
                                chunk = stream.read(CHUNK)
                                if not chunk:
                                    break
                                size += len(chunk)
                                if size > entry['size']:
                                    raise ValueError('复制期间源文件发生变化：' + name)
                                output.write(chunk)
                                digest.update(chunk)
                            output.flush()
                            os.fsync(output.fileno())
                        if (size != entry['size'] or digest.hexdigest() != entry['sha256'] or
                                signature(os.fstat(stream.fileno())) != entry['signature']):
                            raise ValueError('复制期间源文件发生变化：' + name)
        for name, entry in sorted(scan['entries'].items(), key=lambda pair: pair[0].count('/'), reverse=True):
            check(cancel)
            with _parent(target_fd, name) as (parent, basename):
                flags = os.O_RDONLY | os.O_NOFOLLOW
                if entry['kind'] == 'dir':
                    flags |= os.O_DIRECTORY
                if entry['kind'] == 'link':
                    if sys.platform != 'darwin':
                        # Linux cannot open a symlink as an xattr-capable fd;
                        # regular Linux symlinks cannot carry user xattrs.
                        if entry['xattrs']:
                            raise ValueError('此平台不能安全恢复链接扩展属性。')
                        os.utime(basename, ns=(entry['mtime_ns'], entry['mtime_ns']), dir_fd=parent, follow_symlinks=False)
                        continue
                    flags = os.O_RDONLY | getattr(os, 'O_SYMLINK', 0x200000)
                fd = os.open(basename, flags, dir_fd=parent)
                try:
                    expected = {'file': stat.S_ISREG, 'dir': stat.S_ISDIR, 'link': stat.S_ISLNK}[entry['kind']]
                    if not expected(os.fstat(fd).st_mode):
                        raise ValueError('复制目标类型在恢复元数据前发生变化：' + name)
                    _fd_xattrs(fd, entry['xattrs'])
                    os.fchmod(fd, entry['mode'])
                    if entry['kind'] == 'link':
                        os.utime(basename, ns=(entry['mtime_ns'], entry['mtime_ns']), dir_fd=parent, follow_symlinks=False)
                    else:
                        os.utime(fd, ns=(entry['mtime_ns'], entry['mtime_ns']))
                finally:
                    os.close(fd)
        _fd_xattrs(target_fd, scan['root']['xattrs'])
        os.fchmod(target_fd, scan['root']['mode'])
        os.utime(target_fd, ns=(scan['root']['mtime_ns'], scan['root']['mtime_ns']))



@_leased
def migrate(projects, identifier, destination, cancel=None, protected_roots=()):
    """Copy, read back, revalidate, then relink. Every failure keeps its copy."""
    with projects.lock, locked(projects.lockfile):
        record = _record(projects, identifier)
        if Path(destination).expanduser().is_symlink():
            raise ValueError('迁移目标必须是全新目录，不能使用符号链接。')
        source, target = _paths(projects, record, destination, exists=False, protected_roots=protected_roots)
        if target.exists() or target.is_symlink():
            raise ValueError('迁移目标必须是全新目录；已有目标不会被合并或覆盖。')
        if not source.is_dir():
            raise ValueError('原目录不可用，请准备可验证副本后使用重新关联。')
    receipts = projects.directory / 'relocations'
    if receipts.is_symlink():
        raise ValueError('迁移记录目录不能是符号链接。')
    receipts.mkdir(mode=0o700, parents=True, exist_ok=True)
    receipt_path = receipts / (secrets.token_hex(16) + '.json')
    receipt = {'format': 'reprise-relocation-v1', 'project_id': record['id'], 'kind': record.get('kind', 'git'),
               'source': str(source), 'target': str(target), 'created_at': now(),
               'not_deleted': True, 'status': 'checking', 'receipt_path': str(receipt_path),
               'scope': 'source-directory-copy-and-relink',
               'limitations': ['保留原目录；不安装依赖、不执行项目；ACL、特殊权限位和特殊文件会明确拒绝。',
                               '保留字节、链接、mode、mtime 和扩展属性；不保留所有者、硬链接关系或文件系统克隆关系。',
                               '不会重写文件内绝对路径；外部依赖须另行迁移与配置。',
                               '单次检查上限为 250000 项、128 GiB；内容按块读取。']}
    write_json(receipt_path, receipt, private=True)
    try:
        check(cancel)
        if record.get('kind', 'git') == 'git':
            _migratable_git(projects, source)
        before = _scan(source, cancel, metadata=True)
        if record.get('kind', 'git') == 'git' and any(
                name != '.git' and name.split('/')[-1].casefold() == '.git'
                for name in before['entries']):
            raise ValueError('包含嵌套 Git 或子模块元数据，暂不能完整目录迁移。')
        check(cancel)
        # Parent must exist. Account for file allocation overhead as well as
        # payload bytes; an interrupted copy must not consume the last space.
        needed = before['logical_bytes'] + len(before['entries']) * 4096 + 64 * 1024 * 1024
        if shutil.disk_usage(target.parent).free < needed:
            raise ValueError('迁移目标可用空间不足；需容纳文件字节、目录开销和 64 MiB 余量。')
        target.mkdir(mode=0o700)
        receipt['status'] = 'copying'
        write_json(receipt_path, receipt, private=True)
        _copy(source, target, before, cancel)
        after = _scan(source, cancel, metadata=True)
        restored = _scan(target, cancel, metadata=True)
        if before != after:
            raise ValueError('复制期间源目录发生变化；登记未切换，副本保留。')
        if _portable(before) != _portable(restored):
            raise ValueError('迁移副本逐项读回与源目录不一致；登记未切换。')
        if record.get('kind', 'git') == 'git':
            moved = _migratable_git(projects, target)
            moved._run('fsck', '--full', '--strict', max_output=4 * 1024 * 1024, timeout=300)
        with projects.lock, locked(projects.lockfile):
            document = _raw(projects)
            current = next((p for p in document['projects'] if p['id'] == record['id']), None)
            if current != record:
                raise ValueError('项目登记在复制期间发生变化；副本保留，登记未切换。')
            _paths(projects, record, str(target), protected_roots=protected_roots)
            if before != _scan(source, cancel, metadata=True) or _portable(before) != _portable(_scan(target, cancel, metadata=True)):
                raise ValueError('切换前源目录或副本发生变化；登记未切换。')
            check(cancel)
            # Persist the verification first, so a later receipt write failure
            # cannot turn a successfully changed registration into a failed job.
            receipt.update(status='verified', entries=len(before['entries']), logical_bytes=before['logical_bytes'],
                           verification={'method': 'sha256-paths-links-metadata',
                                         'manifest_sha256': hashlib.sha256(json.dumps(_portable(before), sort_keys=True, ensure_ascii=True).encode('ascii')).hexdigest()})
            write_json(receipt_path, receipt, private=True)
            current['path'] = str(target)
            write_json(projects.file, document, private=True)
            projects.cache.clear()
        receipt.update(status='complete', relinked=True, completed_at=now())
        try:
            write_json(receipt_path, receipt, private=True)
        except (OSError, ValueError) as error:
            receipt['receipt_warning'] = str(error)
        return receipt
    except Exception as error:
        receipt.update(status='failed', error=str(error), failed_at=now())
        try:
            write_json(receipt_path, receipt, private=True)
        except (OSError, ValueError):
            pass
        raise
