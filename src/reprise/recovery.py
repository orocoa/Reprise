"""Verified snapshots and portable ZIPs, without modifying imported repositories."""
import os
from pathlib import Path
import secrets
import stat
import zipfile

from .backup import _directory, _write_json
from .storage import now, read_json


class RecoveryStore:
    def __init__(self, directory, projects):
        self.directory = Path(directory).resolve() / 'recoveries'
        self.projects = projects

    def verified_copy(self, repository, project, sha, cancel=None):
        """Reuse for verification only; ordinary restore still creates a new copy."""
        from .recovery_reuse import verified_copy
        return verified_copy(self, repository, project, sha, cancel)

    def reveal(self, identifier):
        """Reveal a completed recorded output, never a caller-supplied path."""
        import subprocess
        import sys
        if not isinstance(identifier, str) or len(identifier) != 32 or any(c not in '0123456789abcdef' for c in identifier):
            raise ValueError('Invalid recovery identity')
        folder = self.directory / identifier
        receipt = folder / 'receipt.json'
        if folder.is_symlink() or receipt.is_symlink():
            raise ValueError('Recovery receipt cannot be a symlink')
        record = read_json(receipt)
        if record.get('id') != identifier or record.get('status') != 'complete' or record.get('operation') not in ('restore', 'export'):
            raise ValueError('Only completed recovery outputs can be revealed')
        target = Path(record['path'])
        if not target.is_absolute() or target.is_symlink() or not target.exists():
            raise ValueError('Recovery output is missing or is a symbolic link')
        if sys.platform == 'darwin':
            command = ['open', '-R', str(target)]
        elif sys.platform == 'win32':
            command = ['explorer', '/select,', str(target)]
        else:
            command = ['xdg-open', str(target.parent)]
        subprocess.run(command, check=True, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {'revealed': True, 'path': str(target)}

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

    def create(self, repository, project, sha, operation, destination=None, cancel=None, paths=None):
        identifier = secrets.token_hex(16)
        folder = self.directory / identifier
        target = (self.destination(destination) if destination else
                  self.destination(str(folder / ('version.zip' if operation == 'export' else 'snapshot'))))
        # Open each ancestor without following links. A replaced recoveries
        # name must not redirect receipt creation into a registered source.
        with _directory(self.directory.parent) as parent:
            try:
                os.mkdir(self.directory.name, mode=0o700, dir_fd=parent)
            except FileExistsError:
                pass
            descriptor = os.open(
                self.directory.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent)
            try:
                os.mkdir(identifier, mode=0o700, dir_fd=descriptor)
            finally:
                os.close(descriptor)
        record = {'id': identifier, 'project_id': project, 'sha': sha,
                  'operation': operation, 'created_at': now(), 'status': 'running', 'paths': paths}
        record['path'] = str(target)
        receipt = folder / 'receipt.json'
        _write_json(receipt, record)
        try:
            if cancel:
                cancel.check()
            # Suggestions are not reservations; repeat source/collision checks
            # after creating the separately anchored receipt directory.
            self.destination(str(target))
            snapshot = target if operation == 'restore' else folder / 'snapshot'
            if snapshot != target:
                self.destination(str(snapshot))
            report = repository.materialize(sha, snapshot, cancel=cancel, **({'paths': paths} if paths is not None else {}))
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
            _write_json(receipt, record)
            return record
        except BaseException as error:
            record.update(status='incomplete', error=str(error), finished_at=now())
            _write_json(receipt, record)
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
