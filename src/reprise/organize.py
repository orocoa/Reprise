"""Verify recovery first, then record explicit duplicate-copy selections.

This module never removes source files. A selection is a reviewable receipt,
not permission to delete adjacent files or unreferenced version objects.
"""
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import stat

from .cancellation import check
from .folders import FolderRepository, inventory, signature, _directory, _open_file
from .git import Repository, _safe_path
from .storage import now, read_json, write_json, locked
from .metadata import xattrs, has_acl


def digest(stream, cancel=None):
    result = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        check(cancel)
        result.update(chunk)
    return result.hexdigest()


def git_protections(source, paths, excluded=()):
    """Keep nested repositories intact, including their unarchived Git state.

    Only candidate ancestors and the enclosing index are inspected; no source
    content is read and no repository command writes to a source repository.
    """
    tracked, roots = set(), set()
    git = None
    try:
        git = Repository(source)
        if git.bare:
            roots.add(str(source))
        else:
            scope = source.relative_to(git.work_tree).as_posix()
            tracked.update(str(git.work_tree / os.fsdecode(path)) for path in
                           git._run('ls-files', '-z', '--', ':(literal)' + scope).split(b'\0') if path)
    except (OSError, ValueError):
        # An unreadable index or Git marker is not evidence that files are safe.
        if git is not None or any(os.path.lexists(root / '.git') for root in (source, *source.parents)):
            roots.add(str(source))
    for name in excluded:
        relative = Path(name)
        if relative.name.casefold() == '.git' and relative.parent != Path('.'):
            roots.add(str(source / relative.parent))
    visited = set()
    for name in paths:
        directory = (source / name).parent
        while directory == source or source in directory.parents:
            if directory in visited:
                break
            visited.add(directory)
            if directory != source and os.path.lexists(directory / '.git'):
                roots.add(str(directory))
            # Bare repositories do not have a .git marker. Preserve their
            # containing tree conservatively, including an unreadable repository.
            if ((directory / 'HEAD').is_file() and (directory / 'objects').is_dir()
                    and (directory / 'refs').is_dir()):
                roots.add(str(directory))
            if directory == source:
                break
            directory = directory.parent
    return tracked, roots


def verify_restore(repository, sha, destination, cancel=None, paths=None):
    """Read back every saved entry; do not equate object validation with disk recovery."""
    manifest = repository.manifest(sha)
    root = Path(destination)
    root_before = root.lstat()
    entries, excluded = inventory(root, cancel, device=root_before.st_dev)
    if excluded or any(e['signature'][0] != root_before.st_dev for e in entries.values()):
        raise ValueError('恢复目录含额外排除内容或跨设备挂载，不能完整核验。')
    expected = manifest['entries']
    if paths is not None:
        expected = {name: entry for name, entry in expected.items() if any(
            name == p or name.startswith(p + '/') or
            (entry['kind'] == 'dir' and p.startswith(name + '/')) for p in paths)}
    if set(entries) != set(expected):
        raise ValueError('恢复后的目录清单与版本不一致。')
    with _directory(root) as root_fd:
        for name, item in expected.items():
            check(cancel)
            actual = entries[name]
            if item['kind'] != actual['kind']:
                raise ValueError('恢复后的文件类型不一致：' + name)
            if item['kind'] == 'link':
                value = hashlib.sha256(os.fsencode(os.readlink(root / name))).hexdigest()
            elif item['kind'] == 'file':
                with _open_file(root_fd, name) as stream:
                    if signature(os.fstat(stream.fileno())) != actual['signature']:
                        raise ValueError('读回前恢复文件发生变化：' + name)
                    value = digest(stream, cancel)
                    if signature(os.fstat(stream.fileno())) != actual['signature']:
                        raise ValueError('读回期间恢复文件发生变化：' + name)
            else:
                value = None
            if value is not None and value != item['sha256']:
                raise ValueError('恢复读回校验失败：' + name)
            if item['kind'] != 'link' and (item['mode'] != actual['mode'] or item['mtime_ns'] != actual['mtime_ns']):
                raise ValueError('恢复后的权限或修改时间不一致：' + name)
            if 'xattrs' in item and xattrs(root / name) != item['xattrs']:
                raise ValueError('恢复后的扩展属性不一致：' + name)
            if signature((root / name).lstat()) != actual['signature']:
                raise ValueError('读回期间恢复路径发生变化：' + name)
    final_entries, final_excluded = inventory(root, cancel, device=root_before.st_dev)
    if final_entries != entries or final_excluded != excluded or signature(root.lstat()) != signature(root_before):
        raise ValueError('完整读回期间恢复目录发生变化，校验失效。')
    root_metadata = manifest.get('root', {})
    if (paths is None and (('mode' in root_metadata and stat.S_IMODE(root_before.st_mode) != root_metadata['mode']) or
            ('mtime_ns' in root_metadata and root_before.st_mtime_ns != root_metadata['mtime_ns']) or
            ('xattrs' in root_metadata and xattrs(root) != root_metadata['xattrs']))):
        raise ValueError('恢复根目录的元数据不一致。')
    attributes = all('xattrs' in entry for entry in expected.values())
    return {'readback_verified': True, 'verified_entries': len(expected),
            'extended_attributes_verified': attributes,
            'coverage': ['file bytes', 'relative paths', 'safe symlink targets', 'modes', 'modification times', 'empty directories'] + (['extended attributes'] if attributes else []),
            'limitations': ['ACLs, file-system flags and ownership are not fully archived.',
                            'Excluded paths and original Git metadata are outside this folder snapshot.',
                            'Application execution and dependency installation have not been tested.']}


class OrganizationStore:
    def __init__(self, directory, projects, recovery, runtimes):
        self.directory = Path(directory) / 'organization'
        self.projects, self.recovery, self.runtimes = projects, recovery, runtimes

    def file(self, identifier):
        if len(identifier) != 32 or any(c not in '0123456789abcdef' for c in identifier):
            raise ValueError('整理记录标识无效。')
        return self.directory / identifier / 'plan.json'

    def get(self, identifier):
        return read_json(self.file(identifier), required=True)

    @staticmethod
    def summary(plan):
        return {k: plan[k] for k in ('id', 'project_id', 'sha', 'status', 'created_at',
                'verification', 'candidate_count', 'duplicate_logical_bytes', 'selected_count',
                'source_files_removed', 'receipt', 'recovery_reused',
                'additional_recovery_logical_bytes') if k in plan}

    def protections(self):
        # Include stopped and uncertain runtime records: a stopped service must
        # never make a previously protected source eligible during this review.
        result = set()
        for runtime in self.runtimes.list():
            for key in ('source', 'path', 'snapshot', 'directory', 'workspace'):
                if isinstance(runtime.get(key), str):
                    result.add(str(Path(runtime[key]).resolve()))
        return sorted(result)

    def preview(self, identifier, sha, cancel=None):
        """Estimate review work from saved metadata, without a recovery copy."""
        check(cancel)
        record = self.projects.record(identifier)
        if record.get('kind') != 'folder':
            raise ValueError('整理预检用于已保存的普通文件夹；Git 原仓库与旧归档保持只读。')
        # An inspection must fail on a missing library, never initialize a new
        # empty object store in its place.
        repository = FolderRepository(self.projects.folders, record)
        sha = repository.resolve(sha)
        manifest = repository.manifest(sha)
        seen, logical, duplicated, files, copies = set(), 0, 0, 0, 0
        for entry in manifest['entries'].values():
            check(cancel)
            if entry['kind'] != 'file':
                continue
            files += 1
            logical += entry['size']
            if entry['sha256'] in seen:
                copies += 1
                duplicated += entry['size']
            seen.add(entry['sha256'])
        try:
            free = shutil.disk_usage(self.directory.parent).free
        except OSError:
            free = None
        return {'status': 'preview', 'project_id': identifier, 'sha': sha, 'files': files,
                'snapshot_logical_bytes': logical, 'duplicate_logical_bytes': duplicated,
                'duplicate_copy_count': copies, 'additional_restore_logical_bytes': logical,
                'filesystem_free_bytes': free, 'reclaimable_bytes': None,
                'source_files_removed': False, 'readback_verified': False,
                'source_safety_checked': False,
                'limitations': [
                    '只读已保存版本的清单，不需要原目录在线；不读取原文件或生成恢复副本。',
                    '重复统计只覆盖此快照内完全相同的常规文件，不含跨项目重复或当前源目录变化。',
                    '未校验内容对象、恢复能力或副本选择安全性；正式整理仍须完整恢复并读回核对。',
                    '预计新增恢复量是常规文件逻辑长度，不含元数据及日志，也不等于实际分配块。',
                    '文件系统可用空间只是当前观测，不保证稍后恢复空间充足；实际可释放量未知。',
                ]}

    def create(self, identifier, sha, cancel=None):
        record = self.projects.record(identifier)
        if record.get('kind') != 'folder':
            raise ValueError('整理副本用于已保存的普通文件夹；Git 原仓库与旧归档保持只读。')
        repository = self.projects.repository(identifier)
        manifest = repository.manifest(sha)
        frozen = self.protections()
        recovery = self.recovery.verified_copy(repository, identifier, sha, cancel)
        if recovery is None:
            recovery = self.recovery.create(repository, identifier, sha, 'restore', cancel=cancel)
        verification = recovery.get('verification') or verify_restore(repository, sha, recovery['path'], cancel)
        source = Path(record['path'])
        current, _ = inventory(source, cancel, record.get('exclusions', []))
        grouped = {}
        for name, entry in manifest['entries'].items():
            if entry['kind'] == 'file':
                grouped.setdefault(entry['sha256'], []).append((name, entry))
        candidates = []
        duplicate_paths = [name for values in grouped.values() if len(values) > 1 for name, _ in values]
        tracked, git_roots = git_protections(source, duplicate_paths, manifest.get('excluded', []))
        for values in grouped.values():
            if len(values) < 2:
                continue
            keeper = sorted(name for name, _ in values)[0]
            for name, entry in sorted(values):
                if name == keeper:
                    continue
                path = (source / name).absolute()
                reasons = []
                if str(path) in tracked or any(path == Path(p) or Path(p) in path.parents for p in git_roots):
                    reasons.append('受 Git 跟踪或位于 Git 存储中；保留原仓库文件。')
                if current.get(name, {}).get('signature') != entry['signature']:
                    reasons.append('原文件已变化或不可用。')
                if any(path == Path(p) or Path(p) in path.parents for p in frozen):
                    reasons.append('属于本轮固定保留的运行目录。')
                # Metadata beyond our restore contract cannot be silently discarded.
                try:
                    if 'xattrs' not in entry or xattrs(path) != entry['xattrs']:
                        reasons.append('扩展属性未归档或已变化。')
                    if has_acl(path):
                        reasons.append('含未完整归档的 ACL。')
                    if getattr(path.lstat(), 'st_flags', 0):
                        reasons.append('含未完整归档的文件系统标志。')
                except (ValueError, OSError) as error:
                    reasons.append(str(error))
                candidates.append({'path': name, 'keeper': keeper, 'bytes': entry['size'],
                                   'sha256': entry['sha256'], 'signature': entry['signature'],
                                   'selectable': not reasons, 'reasons': reasons})
        plan_id = secrets.token_hex(16)
        target = self.file(plan_id)
        plan = {'schema': 1, 'id': plan_id, 'project_id': identifier, 'sha': sha,
                'created_at': now(), 'status': 'verified', 'source': str(source),
                'frozen_protections': frozen, 'verification': verification,
                'frozen_git_protections': sorted(git_roots),
                'recovery_id': recovery['id'], 'recovery_path': recovery['path'],
                'recovery_reused': recovery.get('reused', False),
                'additional_recovery_logical_bytes': 0 if recovery.get('reused') else manifest['stats']['logical_bytes'],
                'candidates': candidates, 'candidate_count': len(candidates),
                'duplicate_logical_bytes': sum(c['bytes'] for c in candidates),
                'selected_paths': [], 'selected_count': 0, 'source_files_removed': False,
                'receipt': str(target), 'excluded': manifest.get('excluded', [])}
        write_json(target, plan, private=True)
        return self.summary(plan)

    def select(self, identifier, paths):
        if not isinstance(paths, list) or len(paths) > 200 or any(not isinstance(p, str) for p in paths):
            raise ValueError('一次请选择最多 200 个候选副本。')
        paths = list(dict.fromkeys(_safe_path(p) for p in paths))
        with locked(self.file(identifier).with_suffix('.lock')):
            plan = self.get(identifier)
            candidates = {c['path']: c for c in plan['candidates']}
            protected = set(plan['frozen_protections']) | set(self.protections())
            root = Path(plan['source'])
            tracked, git_roots = git_protections(root, paths, plan.get('excluded', []))
            git_roots.update(plan.get('frozen_git_protections', []))
            with _directory(root) as root_fd:
                for name in paths:
                    entry = candidates.get(name)
                    if not entry or not entry['selectable']:
                        raise ValueError('此副本不在可选择范围：' + name)
                    path = root / name
                    if str(path) in tracked or any(path == Path(p) or Path(p) in path.parents for p in git_roots):
                        raise ValueError('此副本受 Git 跟踪或属于 Git 项目目录，请保留。')
                    if any(path == Path(p) or Path(p) in path.parents for p in protected):
                        raise ValueError('此副本属于受保护目录。')
                    saved = self.projects.repository(plan['project_id']).manifest(plan['sha'])['entries'][name]
                    if xattrs(path) != saved.get('xattrs') or has_acl(path) or getattr(path.lstat(), 'st_flags', 0):
                        raise ValueError('副本具有未覆盖的文件属性，请保留。')
                    for relative in (name, entry['keeper']):
                        with _open_file(root_fd, relative) as stream:
                            before = signature(os.fstat(stream.fileno()))
                            if relative == name and before != entry['signature']:
                                raise ValueError('副本已变化，请重新校验。')
                            if digest(stream) != entry['sha256'] or signature(os.fstat(stream.fileno())) != before:
                                raise ValueError('原件或保留副本已变化，请重新校验。')
            plan.update(status='selection_saved', selected_paths=paths,
                        selected_count=len(paths), selected_at=now(), frozen_protections=sorted(protected),
                        frozen_git_protections=sorted(git_roots))
            write_json(self.file(identifier), plan, private=True)
            return self.summary(plan)
