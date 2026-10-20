"""Verified snapshots and portable ZIPs, without modifying imported repositories."""
import os
from pathlib import Path
import secrets
import stat
import zipfile

from .storage import now, read_json, write_json


class RecoveryStore:
    def __init__(self, directory, projects):
        self.directory = Path(directory).resolve() / 'recoveries'
        self.projects = projects

    def destination(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('请填写新的恢复目录或 ZIP 路径。')
        target = Path(value).expanduser().absolute()
        if os.path.lexists(target):
            raise ValueError('目标已经存在，请选择新路径；不会覆盖现有文件。')
        resolved = target.resolve()
        for record in self.projects.records():
            # Include linked-worktree common Git storage, even when the worktree
            # itself has moved. A missing source must not block other recovery.
            roots = [Path(record['path']).resolve()]
            try:
                source = self.projects.repository(record['id'])
                info = source.info()
                roots.append((source.path / os.fsdecode(source._run('rev-parse', '--git-common-dir')[:-1])).resolve())
                roots.extend(Path(info[key]).resolve() for key in ('git_dir', 'common_dir', 'work_tree') if info.get(key))
            except (ValueError, OSError):
                pass
            if any(resolved == root or root in resolved.parents for root in roots):
                raise ValueError('恢复目标必须位于已登记源仓库之外。')
        return target

    def create(self, repository, project, sha, operation, destination=None, cancel=None):
        identifier = secrets.token_hex(16)
        folder = self.directory / identifier
        folder.mkdir(parents=True, exist_ok=False)
        record = {'id': identifier, 'project_id': project, 'sha': sha,
                  'operation': operation, 'created_at': now(), 'status': 'running'}
        target = self.destination(destination) if destination else folder / ('version.zip' if operation == 'export' else 'snapshot')
        record['path'] = str(target)
        receipt = folder / 'receipt.json'
        write_json(receipt, record, private=True)
        try:
            if cancel:
                cancel.check()
            snapshot = target if operation == 'restore' else folder / 'snapshot'
            report = repository.materialize(sha, snapshot, cancel=cancel)
            if operation == 'export':
                target.parent.mkdir(parents=True, exist_ok=True)
                # Exclusive creation also protects against a competing exporter.
                with target.open('xb') as stream, zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED, strict_timestamps=False) as archive:
                    for root, directories, files in os.walk(snapshot, followlinks=False):
                        for name in sorted(directories + files):
                            if cancel:
                                cancel.check()
                            path = Path(root) / name
                            relative = path.relative_to(snapshot).as_posix()
                            if path.is_symlink():
                                entry = zipfile.ZipInfo(relative)
                                entry.create_system = 3
                                entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                                archive.writestr(entry, os.readlink(path).encode('utf-8', 'surrogateescape'))
                            elif path.is_dir():
                                archive.writestr(relative + '/', b'')
                            else:
                                entry = zipfile.ZipInfo.from_file(path, relative, strict_timestamps=False)
                                entry.compress_type = zipfile.ZIP_DEFLATED
                                with path.open('rb') as source, archive.open(entry, 'w', force_zip64=True) as output:
                                    while True:
                                        if cancel:
                                            cancel.check()
                                        chunk = source.read(1024 * 1024)
                                        if not chunk:
                                            break
                                        output.write(chunk)
            if cancel:
                cancel.check()
            record.update(status='complete', report=report, finished_at=now())
            if operation == 'export' and destination is None:
                record['download_url'] = '/downloads/' + identifier
            write_json(receipt, record, private=True)
            return record
        except BaseException as error:
            record.update(status='incomplete', error=str(error), finished_at=now())
            write_json(receipt, record, private=True)
            raise

    def download(self, identifier):
        if len(identifier) != 32 or any(c not in '0123456789abcdef' for c in identifier):
            raise KeyError('Unknown export')
        record = read_json(self.directory / identifier / 'receipt.json', required=True)
        if record.get('status') != 'complete' or record.get('operation') != 'export':
            raise KeyError('Export is not complete')
        path = Path(record['path'])
        expected = self.directory / identifier / 'version.zip'
        if path != expected or path.is_symlink() or not path.is_file():
            raise ValueError('Export file is unavailable')
        return path
