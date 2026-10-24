"""Adapters for existing named archives; no registry migration or source writes."""
import hashlib
import json
from pathlib import Path

from .git import Repository, _safe_path
from .storage import read_json
from . import archive_names
from .archive_snapshot import restore_snapshot, read_manifest


def groups(directory):
    path = Path(directory) / 'named-archives' / 'registry.json'
    if not path.is_file():
        return []
    return archive_names.load(path)['projects']


def overlay(records, directory):
    result = [dict(r) for r in records]
    for group in groups(directory):
        record = next((r for r in result if r['path'] == group['view_repository']), None)
        if record is None:
            record = {'id': group.get('native_project_id') or hashlib.sha256(
                group['view_repository'].encode()).hexdigest()[:20],
                'path': group['view_repository']}
            result.append(record)
        aliases = list(group.get('aliases', []))
        for entry in group['snapshots']:
            aliases.extend([entry['label'], entry['name'], *entry.get('aliases', [])])
        record.update(kind='archive', name=group['name'], aliases=list(dict.fromkeys(aliases)),
                      archive_group=group['id'])
    return result


class ArchiveRepository(Repository):
    def __init__(self, group):
        archive_names.verify_selection(group, group['snapshots'])
        self.group = group
        self.original = Repository(group['archive_repository'])
        self.entries = {e['view_commit']: e for e in group['snapshots']}
        self.manifests = {}
        super().__init__(group['view_repository'])

    def resolve(self, revision):
        revision = next((e['view_commit'] for e in self.entries.values()
                         if e['commit'] == revision), revision)
        sha = super().resolve(revision)
        if sha not in self.entries:
            raise ValueError('版本不在已登记归档中。')
        return sha

    def info(self):
        return {**super().info(), 'kind': 'archive', 'history_kind': 'archived_snapshots'}

    def manifest(self, revision):
        sha = self.resolve(revision)
        if sha not in self.manifests:
            commit = self.entries[sha]['commit']
            self.manifests[sha] = read_manifest(self.original, commit)
        return self.manifests[sha]

    def _paths(self, revision):
        manifest = self.manifest(revision)
        return {(Path(manifest['source']).name if e['path'] == '.' else e['path']): e
                for e in manifest['entries'] if e['path'] != '.' or e['kind'] != 'dir'}

    def tree(self, revision):
        return [{'path': path, 'type': 'blob', 'oid': e['oid'], 'size': e['size'],
                 'mode': '120000' if e['kind'] == 'symlink' else '100755' if e['mode'] & 0o111 else '100644'}
                for path, e in self._paths(revision).items() if e['kind'] != 'dir']

    def blob(self, revision, path, max_bytes=1048576):
        entry = self._paths(revision).get(_safe_path(path))
        if not entry or entry['kind'] == 'dir':
            raise ValueError('归档中没有此文件。')
        if entry['size'] > max_bytes:
            raise ValueError('文件超过预览大小限制，可恢复原始文件。')
        return self.original._run('cat-file', 'blob', entry['oid'], max_output=max_bytes)

    def diff(self, target, base=None):
        sha = self.resolve(target)
        before = self._paths(base) if base else {}
        after = self._paths(sha)
        files, counts = [], dict(added=0, modified=0, deleted=0, renamed=0, copied=0, type_changed=0, other=0, total=0)
        for path in sorted(set(before) | set(after)):
            a, b = before.get(path), after.get(path)
            if (a or b)['kind'] == 'dir' or a == b:
                continue
            if a and b and a.get('sha256') == b.get('sha256') and a['mode'] == b['mode']:
                continue
            status = 'A' if a is None else 'D' if b is None else 'M'
            if len(files) < 200:
                files.append({'path': path, 'status': status})
            counts[{'A': 'added', 'D': 'deleted', 'M': 'modified'}[status]] += 1
        counts['total'] = sum(counts.values())
        return {'target': sha, 'base': self.resolve(base) if base else None,
                'parents': [], 'files': files, 'counts': counts,
                'files_truncated': counts['total'] > len(files)}

    def status(self):
        return {'available': False, 'dirty': False, 'changes': [],
                'reason': '独立归档快照；原项目 Git 元数据在恢复时还原。'}

    def materialize(self, revision, destination, cancel=None, paths=None):
        if paths is not None:
            raise ValueError('旧归档请先完整恢复到新目录，再选择所需文件。')
        if cancel:
            cancel.check()
        sha = self.resolve(revision)
        entry = self.entries[sha]
        report = restore_snapshot(self.group['archive_repository'], entry['commit'], destination)
        return {'files': report['files'], 'object_hashes_verified': True,
                'readback_verified': True, 'warnings': report['metadata_warnings'],
                'submodules': [], 'lfs_pointers': [], 'archive_sha': entry['commit'],
                'view_sha': sha, 'nested_git_restored': True}
