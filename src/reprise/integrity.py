"""Read back one saved folder version without consulting or restoring its source.

This is a library-integrity check, not an independent backup or a restore test.
Git objects are streamed without filters, hooks, lazy fetches, or replacement
objects. Only metadata has an in-memory size cap; file contents stay bounded.
"""
import base64
import binascii
import datetime
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import select
import stat
import subprocess
import time

from .cancellation import check
from .git import _environment, _safe_path
from .metadata import MAX_XATTR_BYTES

CHUNK = 1024 * 1024
MAX_METADATA = 32 * 1024 * 1024
TIMEOUT = 300
MAX_STORAGE_ENTRIES = 4096
MAX_ANCESTORS = 100000
LIMITATIONS = [
    '仅检查所选完整 SHA 的文件夹版本及其引用对象；其他历史版本未检查。',
    '这是本机内容库完整性检查，不是独立备份或实际恢复演练。',
    '不检查原文件夹现状、应用能否运行或其他介质是否可用。',
]


class IntegrityError(ValueError):
    """A failed check with a bounded, body-free summary for durable jobs."""
    def __init__(self, message, report):
        self.report = {**report, 'status': 'failed', 'errors': [message[:512]]}
        super().__init__(message[:512])


class _Boundary:
    """Inspect names and stat data only, never alternate-path file contents.

    Scan the small Git metadata directories, not the loose-object inventory.
    Each requested loose-object path is checked separately before Git reads it.
    """
    def __init__(self, path, cancel):
        self.path, self.cancel = Path(path), cancel
        self.objects = self.path / 'objects'
        self.seen = set()

    def node(self, path, kind, *, optional=False):
        check(self.cancel)
        try:
            value = path.lstat()
        except FileNotFoundError:
            if optional:
                return None
            raise ValueError('内容库必需目录缺失；无法确认库内对象。') from None
        if stat.S_ISLNK(value.st_mode):
            raise ValueError('内容库存储路径包含符号链接；无法确认库内对象。')
        if not (stat.S_ISDIR(value.st_mode) if kind == 'dir' else stat.S_ISREG(value.st_mode)):
            raise ValueError('内容库存储路径类型无效。')
        return value

    def common(self):
        self.node(self.path.parent, 'dir')
        self.node(self.path, 'dir')
        self.node(self.objects, 'dir')
        # An owned bare store must not redirect its common Git directory.
        if self.node(self.path / 'commondir', 'file', optional=True) is not None:
            raise ValueError('内容库配置了外部公共目录；无法确认库内对象。')
        info = self.objects / 'info'
        self.node(info, 'dir', optional=True)
        for name in ('alternates', 'http-alternates'):
            value = self.node(info / name, 'file', optional=True)
            if value is not None and value.st_size:
                raise ValueError('内容库配置了替代对象来源；本次检查不读取外部路径。')
        budget = [MAX_STORAGE_ENTRIES]
        def scan(directory, depth=0):
            if self.node(directory, 'dir', optional=True) is None:
                return
            if depth > 4:
                raise ValueError('内容库存储元数据目录超过安全层数。')
            with os.scandir(directory) as items:
                for entry in items:
                    check(self.cancel)
                    budget[0] -= 1
                    if budget[0] < 0:
                        raise ValueError('内容库存储元数据超过安全条目上限。')
                    value = entry.stat(follow_symlinks=False)
                    if stat.S_ISLNK(value.st_mode):
                        raise ValueError('内容库 pack 或 info 元数据包含符号链接。')
                    if stat.S_ISDIR(value.st_mode):
                        scan(Path(entry.path), depth + 1)
                    elif not stat.S_ISREG(value.st_mode):
                        raise ValueError('内容库 pack 或 info 元数据类型无效。')
        scan(info)
        scan(self.objects / 'pack')

    def object(self, oid):
        check(self.cancel)
        # No directory enumeration here: unrelated loose objects stay untouched.
        self.node(self.objects, 'dir')
        fanout = self.objects / oid[:2]
        if self.node(fanout, 'dir', optional=True) is not None:
            self.node(fanout / oid[2:], 'file', optional=True)
        self.seen.add(oid)

    def finish(self):
        self.common()
        for oid in tuple(self.seen):
            self.object(oid)


class _Reader:
    def __init__(self, process, cancel):
        self.process, self.cancel = process, cancel
        self.buffer = bytearray()
        self.deadline = time.monotonic() + TIMEOUT

    def read(self, size):
        while not self.buffer:
            check(self.cancel)
            if time.monotonic() >= self.deadline:
                raise ValueError('内容库读取超时；未完成完整性检查。')
            if not select.select([self.process.stdout], [], [], .1)[0]:
                continue
            value = os.read(self.process.stdout.fileno(), min(CHUNK, max(size, 4096)))
            if not value:
                return b''
            self.buffer.extend(value)
        value = bytes(self.buffer[:size])
        del self.buffer[:size]
        return value

    def exact(self, size):
        value = bytearray()
        while len(value) < size:
            chunk = self.read(size - len(value))
            if not chunk:
                raise ValueError('内容对象缺失、损坏或读取中断。')
            value.extend(chunk)
        return bytes(value)

    def line(self):
        value = bytearray()
        while len(value) < 256:
            char = self.exact(1)
            if char == b'\n':
                return bytes(value)
            value.extend(char)
        raise ValueError('内容对象响应格式无效。')


class _Git:
    def __init__(self, path, cancel):
        self.path, self.cancel = path, cancel
        self.boundary = _Boundary(path, cancel)

    def start(self, *args, batch=False):
        check(self.cancel)
        self.boundary.common()
        command = ['git', '--no-pager', '--no-optional-locks',
                   '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
                   '-c', 'gc.auto=0', '--git-dir=' + str(self.path), *args]
        try:
            return subprocess.Popen(command, stdin=subprocess.PIPE if batch else subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    env=_environment())
        except OSError:
            raise ValueError('无法启动 Git，完整性检查未执行。') from None

    @staticmethod
    def close(process):
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()
        if process.stdin:
            process.stdin.close()

    def run(self, *args):
        process = self.start(*args)
        reader, result = _Reader(process, self.cancel), bytearray()
        try:
            while True:
                value = reader.read(4096)
                if not value:
                    break
                result.extend(value)
                if len(result) > 4096:
                    raise ValueError('内容库版本响应超过安全上限。')
            while process.poll() is None:
                check(self.cancel)
                if time.monotonic() >= reader.deadline:
                    raise ValueError('内容库版本读取超时。')
                time.sleep(.01)
            if process.returncode:
                raise ValueError('所选版本不存在、不属于此项目，或内容库对象不可读。')
            return bytes(result)
        finally:
            self.close(process)


class _Batch:
    def __init__(self, git):
        self.git = git

    def __enter__(self):
        self.process = self.git.start('cat-file', '--batch', batch=True)
        self.reader = _Reader(self.process, self.git.cancel)
        return self

    def __exit__(self, *_):
        self.git.close(self.process)

    def read(self, oid, kind, *, collect=False, expected_size=None):
        check(self.git.cancel)
        self.git.boundary.object(oid)
        self.reader.deadline = time.monotonic() + TIMEOUT
        try:
            self.process.stdin.write(oid.encode('ascii') + b'\n')
            self.process.stdin.flush()
        except (BrokenPipeError, OSError):
            raise ValueError('内容库对象读取中断。') from None
        row = self.reader.line().split(b' ')
        if len(row) != 3 or row[0] != oid.encode('ascii') or row[1] != kind.encode('ascii'):
            raise ValueError('所引用内容对象缺失或对象类型不一致。')
        try:
            size = int(row[2])
        except ValueError:
            raise ValueError('内容对象长度格式无效。') from None
        if size < 0 or (expected_size is not None and size != expected_size):
            raise ValueError('内容对象长度与版本清单不一致。')
        if collect and size > MAX_METADATA:
            raise ValueError('版本元数据超过 32 MiB 安全上限。')
        identity = hashlib.sha1((kind + ' ' + str(size) + '\0').encode('ascii'))
        digest, remaining = hashlib.sha256(), size
        contents = bytearray() if collect else None
        while remaining:
            check(self.git.cancel)
            chunk = self.reader.exact(min(CHUNK, remaining))
            identity.update(chunk)
            digest.update(chunk)
            if collect:
                contents.extend(chunk)
            remaining -= len(chunk)
        if self.reader.exact(1) != b'\n' or identity.hexdigest() != oid:
            raise ValueError('内容对象地址校验失败；对象字节损坏或被替换。')
        return {'size': size, 'sha256': digest.hexdigest(),
                'data': bytes(contents) if collect else None}


def _integer(value, minimum=None, maximum=None):
    return (type(value) is int and (minimum is None or value >= minimum)
            and (maximum is None or value <= maximum))


def _metadata(value):
    if (not isinstance(value, dict) or not _integer(value.get('mode'), 0, 0o777)
            or not _integer(value.get('mtime_ns'))):
        raise ValueError('版本权限或时间元数据无效。')
    attributes = value.get('xattrs', {})
    if not isinstance(attributes, dict):
        raise ValueError('版本扩展属性格式无效。')
    total = 0
    for name, encoded in attributes.items():
        if (not isinstance(name, str) or not name or '\0' in name
                or not isinstance(encoded, str)):
            raise ValueError('版本扩展属性格式无效。')
        try:
            total += len(base64.b64decode(encoded, validate=True))
        except (binascii.Error, ValueError):
            raise ValueError('版本扩展属性编码无效。') from None
        if total > MAX_XATTR_BYTES:
            raise ValueError('版本扩展属性超过 2 MiB 安全上限。')


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('版本清单包含重复字段或路径。')
        result[key] = value
    return result


def _hex(value, length):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{%d}' % length, value) is not None


def _manifest(data, identifier):
    try:
        manifest = json.loads(data, object_pairs_hook=_pairs,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError('版本清单包含非法数值。')))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ValueError('版本清单不是有效的有界 JSON 对象。') from None
    if (not isinstance(manifest, dict) or manifest.get('format') != 'reprise-folder-v1'
            or manifest.get('project_id') != identifier):
        raise ValueError('文件夹版本格式或项目身份不匹配。')
    if (not isinstance(manifest.get('source'), str) or '\0' in manifest['source']
            or not Path(manifest['source']).is_absolute()
            or not isinstance(manifest.get('created_at'), str)):
        raise ValueError('版本来源或记录时间元数据无效。')
    try:
        created = datetime.datetime.fromisoformat(manifest['created_at'])
    except ValueError:
        raise ValueError('版本记录时间无效。') from None
    if created.tzinfo is None:
        raise ValueError('版本记录时间缺少时区。')
    _metadata(manifest.get('root'))
    entries = manifest.get('entries')
    if not isinstance(entries, dict):
        raise ValueError('版本文件清单格式无效。')
    for name, entry in entries.items():
        _safe_path(name)
        _metadata(entry)
        kind = entry.get('kind')
        if kind not in ('dir', 'file', 'link') or not _integer(entry.get('size'), 0):
            raise ValueError('版本文件类型或长度无效。')
        signature = entry.get('signature')
        if (not isinstance(signature, list) or len(signature) != 6
                or not all(_integer(item) for item in signature)
                or min(signature[:4]) < 0
                or not {'dir': stat.S_ISDIR, 'file': stat.S_ISREG, 'link': stat.S_ISLNK}[kind](signature[2])
                or stat.S_IMODE(signature[2]) & 0o777 != entry['mode']
                or signature[4] != entry['mtime_ns']):
            raise ValueError('版本文件身份元数据无效。')
        parent = posixpath.dirname(name)
        if parent and (parent not in entries or not isinstance(entries[parent], dict)
                       or entries[parent].get('kind') != 'dir'):
            raise ValueError('版本路径的父目录缺失或类型不安全。')
        if kind == 'dir':
            if entry['size'] or any(key in entry for key in ('oid', 'sha256', 'target')):
                raise ValueError('版本目录元数据与内容对象不一致。')
        else:
            if (not _hex(entry.get('oid'), 40) or not _hex(entry.get('sha256'), 64)
                    or signature[3] != entry['size']):
                raise ValueError('版本内容对象标识、摘要或长度无效。')
            if kind == 'link':
                target = entry.get('target')
                if (not isinstance(target, str) or not target or '\0' in target
                        or target.startswith('/') or '\\' in target
                        or len(os.fsencode(target)) != entry['size']):
                    raise ValueError('版本符号链接目标无效。')
                if hashlib.sha256(os.fsencode(target)).hexdigest() != entry['sha256']:
                    raise ValueError('版本符号链接目标与内容摘要不一致。')
            elif 'target' in entry:
                raise ValueError('普通文件不得包含符号链接目标。')
    # Resolve saved links in the saved namespace, never against the live source.
    def resolve(parts, active=()):
        resolved = []
        for piece in parts:
            if piece in ('', '.'):
                continue
            if piece == '..':
                if not resolved:
                    raise ValueError('版本符号链接越出保存范围。')
                resolved.pop()
                continue
            resolved.append(piece)
            name = '/'.join(resolved)
            if entries.get(name, {}).get('kind') == 'link':
                if name in active or len(active) >= 256:
                    raise ValueError('版本符号链接循环或层数超过安全上限。')
                resolved = resolve(resolved[:-1] + entries[name]['target'].split('/'), active + (name,))
        return resolved
    for name, entry in entries.items():
        if entry['kind'] == 'link':
            resolve(name.split('/'))
    blobs = [entry for entry in entries.values() if entry['kind'] != 'dir']
    unique = {entry['oid']: entry['size'] for entry in blobs}
    stats = manifest.get('stats')
    expected = {'files': len(blobs), 'logical_bytes': sum(e['size'] for e in blobs),
                'unique_bytes': sum(unique.values())}
    if not isinstance(stats, dict) or any(not _integer(stats.get(k), 0) or stats[k] != v for k, v in expected.items()):
        raise ValueError('版本统计与文件清单不一致。')
    for key, maximum in [('new_bytes', expected['unique_bytes']), ('read_bytes', expected['logical_bytes']),
                         ('reused_files', expected['files'])]:
        if not _integer(stats.get(key), 0, maximum):
            raise ValueError('版本保存统计无效。')
    if (not isinstance(manifest.get('excluded'), list)
            or not all(isinstance(p, str) and _safe_path(p) for p in manifest['excluded'])):
        raise ValueError('版本排除路径格式无效。')
    excluded = set(manifest['excluded'])
    if len(excluded) != len(manifest['excluded']):
        raise ValueError('版本排除路径重复。')
    for name in entries:
        parent = name
        while parent:
            if parent in excluded:
                raise ValueError('版本排除路径与已保存内容重叠。')
            parent = posixpath.dirname(parent)
    from .folders import exclusions
    exclusions(manifest.get('exclusion_rules'))
    return manifest


def _tree(data):
    result, offset = {}, 0
    while offset < len(data):
        end = data.find(b'\0', offset)
        if end < 0 or end + 21 > len(data):
            raise ValueError('版本目录对象格式无效。')
        row = data[offset:end].split(b' ', 1)
        if len(row) != 2 or row[0] not in (b'40000', b'100644', b'100755', b'120000'):
            raise ValueError('版本目录包含不支持的对象类型。')
        name = os.fsdecode(row[1])
        _safe_path(name)
        if '/' in name or name in result:
            raise ValueError('版本目录对象包含重复或不安全名称。')
        result[name] = (row[0].decode('ascii'), data[end + 1:end + 21].hex())
        offset = end + 21
    return result


def _parents(data):
    result = []
    for row in data.split(b'\n\n', 1)[0].split(b'\n'):
        if row.startswith(b'parent '):
            value = row[7:].decode('ascii')
            if not _hex(value, 40):
                raise ValueError('版本提交父节点格式无效。')
            result.append(value)
    return result


def verify_project(projects, identifier, revision='HEAD', cancel=None):
    from .content_lock import content_access
    with content_access(projects.folders.directory):
        return _verify_project(projects, identifier, revision, cancel)


def _verify_project(projects, identifier, revision='HEAD', cancel=None):
    """Verify an exact owned-folder snapshot; raise IntegrityError on failure.

    checked_objects/checked_bytes count unique payload blobs only; checked_files
    counts regular-file and symlink references. Metadata is checked separately.
    A cancellation keeps the existing Cancelled exception and never reports green.
    """
    report = {'status': 'failed', 'project_id': identifier, 'sha': None,
              'checked_files': 0, 'checked_objects': 0, 'checked_bytes': 0,
              'checked_metadata_objects': 0, 'limitations': list(LIMITATIONS)}
    try:
        check(cancel)
        record = projects.record(identifier)
        if record.get('kind') != 'folder':
            raise ValueError('完整性检查仅支持普通文件夹已存版本；Git 与旧归档须使用各自校验流程。')
        path = projects.folders.path
        if path.is_symlink() or path.parent.is_symlink() or not path.is_dir():
            raise ValueError('本机内容库不存在或目录为符号链接；未创建或修复内容库。')
        if revision != 'HEAD' and not _hex(revision, 40):
            raise ValueError('请选择已存版本的完整 SHA 或 HEAD。')
        if not isinstance(identifier, str) or not re.fullmatch('[A-Za-z0-9_-]{1,128}', identifier):
            raise ValueError('文件夹项目标识无效。')
        git = _Git(path, cancel)
        ref = 'refs/heads/folders/' + identifier
        # Resolve a plain ref without asking Git to traverse commit objects.
        # The ancestry walk below checks each object path before reading it.
        head = git.run('rev-parse', '--verify', '--end-of-options', ref).decode('ascii').strip()
        sha = head if revision == 'HEAD' else revision
        if not _hex(head, 40) or not _hex(sha, 40):
            raise ValueError('文件夹版本未解析为完整 SHA。')
        report['sha'] = sha
        with _Batch(git) as batch:
            from .storage import read_json
            catalog = read_json(path / 'reprise-snapshots.json')
            if catalog is not None and sha not in catalog.get(identifier, []):
                raise ValueError('所选版本不存在或不属于此项目。')
            pending, ancestors = [sha if catalog is not None else head], set()
            deadline = time.monotonic() + TIMEOUT
            while pending:
                check(cancel)
                if time.monotonic() >= deadline or len(ancestors) >= MAX_ANCESTORS:
                    raise ValueError('项目历史归属检查超过时间或节点安全上限。')
                ancestor = pending.pop()
                if ancestor in ancestors:
                    continue
                ancestors.add(ancestor)
                data = batch.read(ancestor, 'commit', collect=True)['data']
                report['checked_metadata_objects'] += 1
                if ancestor == sha:
                    break
                pending.extend(_parents(data))
            else:
                raise ValueError('所选版本不存在或不属于此项目。')
            cache = {(sha, 'commit'): data}
            def metadata(oid, kind):
                key = (oid, kind)
                if key not in cache:
                    cache[key] = batch.read(oid, kind, collect=True)['data']
                    report['checked_metadata_objects'] += 1
                return cache[key]
            commit = metadata(sha, 'commit')
            first = commit.split(b'\n', 1)[0]
            if not first.startswith(b'tree ') or not _hex(first[5:].decode('ascii'), 40):
                raise ValueError('版本提交缺少有效目录对象。')
            root = _tree(metadata(first[5:].decode('ascii'), 'tree'))
            if ('snapshot.json' not in root or root['snapshot.json'][0] != '100644'
                    or set(root) - {'snapshot.json', 'payload'}
                    or ('payload' in root and root['payload'][0] != '40000')):
                raise ValueError('版本根目录与文件夹格式不一致。')
            manifest = _manifest(metadata(root['snapshot.json'][1], 'blob'), identifier)
            entries, actual = manifest['entries'], {}
            pending = [('', root['payload'][1])] if 'payload' in root else []
            while pending:
                check(cancel)
                prefix, tree_oid = pending.pop()
                for name, (mode, oid) in _tree(metadata(tree_oid, 'tree')).items():
                    relative = prefix + name
                    entry = entries.get(relative)
                    if entry is None or relative in actual:
                        raise ValueError('版本 payload 包含清单外或重复路径。')
                    if mode == '40000':
                        if entry['kind'] != 'dir':
                            raise ValueError('版本目录与清单文件类型不一致。')
                        pending.append((relative + '/', oid))
                        actual[relative] = None
                    else:
                        expected_mode = ('120000' if entry['kind'] == 'link' else
                                         '100755' if entry['mode'] & 0o111 else '100644')
                        if entry['kind'] == 'dir' or mode != expected_mode or oid != entry['oid']:
                            raise ValueError('版本 payload 对象或权限与清单不一致。')
                        actual[relative] = oid
            expected_files = {name for name, e in entries.items() if e['kind'] != 'dir'}
            if expected_files != {name for name, oid in actual.items() if oid is not None}:
                raise ValueError('版本清单引用文件未出现在 payload 中。')
            verified = {}
            for name in sorted(expected_files):
                check(cancel)
                entry = entries[name]
                if entry['oid'] not in verified:
                    verified[entry['oid']] = batch.read(entry['oid'], 'blob', expected_size=entry['size'])
                    report['checked_objects'] += 1
                    report['checked_bytes'] += entry['size']
                value = verified[entry['oid']]
                if value['size'] != entry['size'] or value['sha256'] != entry['sha256']:
                    raise ValueError('版本文件 SHA256 或长度与清单不一致。')
                report['checked_files'] += 1
        git.boundary.finish()
        check(cancel)
        return {**report, 'status': 'verified', 'errors': []}
    except (ValueError, OSError, UnicodeError, RecursionError) as error:
        if isinstance(error, IntegrityError):
            raise
        message = str(error) if isinstance(error, ValueError) else '内容库读取失败或版本元数据无效；检查未完成。'
        raise IntegrityError(message, report) from None
