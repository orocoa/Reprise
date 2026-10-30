"""Single-file desktop backup transport over the verified managed-data format.

The original format, byte readback, metadata and restoration boundaries remain
canonical. Intermediate copies and failed imports are retained for diagnosis.
"""
import contextlib
import os
from pathlib import Path
import secrets
import shutil
import stat
import zipfile

from . import backup
from .storage import now, read_json, write_json


def _work(app):
    root = app.directory.parent / (app.directory.name + '-transfers')
    root.mkdir(mode=0o700, exist_ok=True)
    with backup._directory(root):
        pass
    target = root / secrets.token_hex(16)
    target.mkdir(mode=0o700)
    return target


def _pack(directory, filename):
    # A symlink's target is stored as text, not followed by ZipFile.write().
    with backup._new_file(filename) as stream, zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED,
                                                              allowZip64=True) as archive:
        for path, entry, leaving in backup._walk(directory, excluded=frozenset()):
            if leaving or entry['path'] == '.':
                continue
            name = entry['path'] + ('/' if entry['kind'] == 'dir' else '')
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            kind = {'dir': stat.S_IFDIR, 'file': stat.S_IFREG, 'link': stat.S_IFLNK}[entry['kind']]
            info.external_attr = (kind | entry['mode']) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            if entry['kind'] == 'link':
                archive.writestr(info, os.fsencode(entry['target']))
            elif entry['kind'] == 'dir':
                archive.writestr(info, b'')
            else:
                with backup._regular(path) as source, archive.open(info, 'w', force_zip64=True) as output:
                    shutil.copyfileobj(source, output, backup.CHUNK)


def _unpack(filename, target):
    target.mkdir(mode=0o700)
    links = []
    with backup._regular(filename) as source, zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        if not 1 <= len(entries) <= backup.MAX_ENTRIES:
            raise ValueError('备份文件条目数量无效。')
        names, total = set(), 0
        # Validate the entire index before writing any user-controlled path.
        for entry in entries:
            name = entry.filename.rstrip('/')
            backup._path(name)
            if name in names or name.split('/')[0] not in ('payload', 'manifest.jsonl', 'receipt.json'):
                raise ValueError('备份文件含重复或不支持的路径。')
            names.add(name)
            total += entry.file_size
            mode = entry.external_attr >> 16
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK):
                raise ValueError('备份文件包含特殊文件。')
            if entry.flag_bits & 1:
                raise ValueError('请先解锁加密的备份文件。')
        if total + backup.RESERVE > shutil.disk_usage(target).free:
            raise ValueError('没有足够空间导入备份。')
        for entry in entries:
            name = entry.filename.rstrip('/')
            destination = target / name
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode):
                if entry.file_size > 65536:
                    raise ValueError('备份链接过长。')
                link = os.fsdecode(archive.read(entry))
                backup._link(target, destination, link)
                links.append((destination, link))
                continue
            destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            if entry.is_dir():
                destination.mkdir(mode=0o700, exist_ok=True)
            else:
                with archive.open(entry) as content, backup._new_file(destination) as output:
                    shutil.copyfileobj(content, output, backup.CHUNK)
        # Create links last. No file can be extracted through a link parent.
        for destination, link in links:
            destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            if destination.exists() or destination.is_symlink():
                raise ValueError('备份链接与文件路径冲突。')
            destination.symlink_to(link)
    # Reapply exact payload metadata from the verified manifest. The ZIP's
    # metadata is deliberately not trusted or used as executable permissions.
    for entry in backup._manifest_entries(target / 'manifest.jsonl'):
        path = target / 'payload' if entry['path'] == '.' else target / 'payload' / entry['path']
        if path.is_dir() and not path.is_symlink():
            continue
        backup._metadata(path, entry)
    entries = backup._manifest_entries(target / 'manifest.jsonl')
    directories = [entry for entry in entries if entry['kind'] == 'dir']
    for entry in reversed(directories):
        path = target / 'payload' if entry['path'] == '.' else target / 'payload' / entry['path']
        backup._metadata(path, entry)
    return backup.verify_backup(target)


def export_file(app, filename):
    if not isinstance(filename, str) or not Path(filename).is_absolute():
        raise ValueError('请选择备份文件的保存位置。')
    with app.request_gate, app.jobs.lock:
        if app.jobs.busy:
            raise ValueError('请等待当前任务完成后再备份。')
        # Runtime observers and the canonical offline check reject active or
        # uncertain processes. No process is stopped automatically.
        if any(row.get('running') or row.get('status') in
               ('preparing', 'install', 'build', 'starting', 'cleanup_failed') for row in app.runtimes.list()):
            raise ValueError('请先停止正在运行的版本预览，再导出备份。')
        with app._data_lease.exclusive_scope():
            roots, unused = backup._external(app.directory)
            destination = backup._destination(filename, [app.directory, *roots])
            folder = _work(app)
            receipt = backup._create_backup(app.directory, folder / 'backup', None, contextlib.nullcontext())
            _pack(folder / 'backup', destination)
            # Verify the actual archive, not just the intermediate directory.
            verified = _unpack(destination, folder / 'readback')
            result = {'status': 'complete', 'path': str(destination), 'bytes': destination.stat().st_size,
                      'readback_verified': True, 'external_dependencies': verified['external_dependencies'],
                      'created_at': now(), 'format': 'reprise-backup-zip', 'backup': receipt}
            write_json(folder / 'export.json', result, private=True)
            return result


def import_file(app, filename):
    if not isinstance(filename, str) or not Path(filename).is_absolute():
        raise ValueError('请选择 Reprise 导出的备份文件。')
    folder = _work(app)
    try:
        _unpack(filename, folder / 'backup')
    except (zipfile.BadZipFile, EOFError) as error:
        raise ValueError('备份文件无效或已损坏，请选择 Reprise 导出的备份文件。') from error
    library = folder / 'library'
    restored = backup.restore_backup(folder / 'backup', library)
    result = {'id': folder.name, 'status': 'complete', 'path': str(library),
              'readback_verified': True, 'restored': restored, 'created_at': now()}
    write_json(folder / 'import.json', result, private=True)
    return result


def open_import(app, identifier, *, window=False):
    import re
    if not isinstance(identifier, str) or not re.fullmatch('[0-9a-f]{32}', identifier):
        raise ValueError('找不到导入的备份。')
    folder = app.directory.parent / (app.directory.name + '-transfers') / identifier
    with backup._directory(folder):
        pass
    record = read_json(folder / 'import.json')
    if not record or record.get('status') != 'complete' or Path(record['path']) != folder / 'library':
        raise ValueError('导入的备份尚未通过校验。')
    from .launcher import open_workbench
    result = open_workbench(folder / 'library', browser=False)
    if window:
        from .window import open_window
        result['window'] = open_window(folder / 'library', result['url'])
    return result
