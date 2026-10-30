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
        git_history = bool(record and record.get('archive_git_history', record.get('kind', 'git') == 'git'))
        if record is None:
            record = {'id': group.get('native_project_id') or hashlib.sha256(
                group['view_repository'].encode()).hexdigest()[:20],
                'path': group['view_repository']}
            result.append(record)
        aliases = list(group.get('aliases', []))
        for entry in group['snapshots']:
            aliases.extend([entry['label'], entry['name'], *entry.get('aliases', [])])
        record.update(kind='archive', name=group['name'], aliases=list(dict.fromkeys(aliases)),
                      archive_group=group['id'], archive_git_history=git_history)
    return result


class ArchiveRepository(Repository):
    def __init__(self, group, *, git_history=False):
        archive_names.verify_selection(group, group['snapshots'])
        self.group = group
        self.original = Repository(group['archive_repository'])
        self.entries = {e['view_commit']: e for e in group['snapshots']}
        self.manifests = {}
        # A view explicitly registered as Git can also retain original source
        # commits. Snapshot content still comes only from its pinned manifest.
        self.git_history = git_history
        super().__init__(group['view_repository'])

    def resolve(self, revision):
        revision = next((e['view_commit'] for e in self.entries.values()
                         if e['commit'] == revision), revision)
        sha = super().resolve(revision)
        if sha not in self.entries and not self.git_history:
            raise ValueError('版本不在已登记归档中。')
        return sha

    def info(self):
        return {**super().info(), 'kind': 'archive',
                'history_kind': 'git_and_archived_snapshots' if self.git_history else 'archived_snapshots'}

    def refs(self):
        refs = super().refs()
        return refs if self.git_history else [r for r in refs if r['sha'] in self.entries]

    def _history(self, *args, **kwargs):
        result = super()._history(*args, **kwargs)
        for commit in result['commits']:
            commit['history_kind'] = 'archived_snapshots' if commit['sha'] in self.entries else 'git'
        return result

    def _snapshot_history(self, limit):
        # Read one exact node per registered snapshot, retaining its real parent
        # SHAs as boundaries. Do not walk unregistered view metadata as content.
        refs = self.refs()
        commits = [self._history(sha, 1, 0, refs)['commits'][0] for sha in self.entries]
        commits.sort(key=lambda c: (c['committed_at'], c['sha']), reverse=True)
        return commits[:limit], len(commits) > limit

    def history(self, ref='--all', limit=50, offset=0):
        if self.git_history or ref != '--all':
            return super().history(ref, limit, offset)
        limit, offset = int(limit), int(offset)
        if not 1 <= limit <= 200 or not 0 <= offset <= 1000000:
            raise ValueError('History limit must be 1–200 and offset 0–1000000')
        commits, more = self._snapshot_history(offset + limit)
        return {'commits': commits[offset:], 'has_more': more,
                'next_offset': offset + limit if more else None}

    def history_tips(self, tips, limit=2000, *, refs=None, shallow=None):
        if self.git_history:
            return super().history_tips(tips, limit, refs=refs, shallow=shallow)
        if not isinstance(limit, int) or not 1 <= limit <= 2000:
            raise ValueError('History tip limit must be 1–2000')
        commits, more = self._snapshot_history(limit)
        return {'commits': commits, 'truncated_tips': tips[:1] if more else []}

    def manifest(self, revision):
        sha = self.resolve(revision)
        if sha not in self.entries:
            raise ValueError('此版本是原 Git 提交，不是目录归档快照。')
        if sha not in self.manifests:
            commit = self.entries[sha]['commit']
            self.manifests[sha] = read_manifest(self.original, commit)
        return self.manifests[sha]

    def _paths(self, revision):
        sha = self.resolve(revision)
        if sha not in self.entries:
            return {e['path']: {**e, 'mode': int(e['mode'], 8) & 0o777,
                               'kind': 'symlink' if e['mode'] == '120000' else 'file'}
                    for e in super().tree(sha) if e['type'] == 'blob'}
        manifest = self.manifest(revision)
        return {(Path(manifest['source']).name if e['path'] == '.' else e['path']): e
                for e in manifest['entries'] if e['path'] != '.' or e['kind'] != 'dir'}

    def tree(self, revision):
        sha = self.resolve(revision)
        if sha not in self.entries:
            return super().tree(sha)
        return [{'path': path, 'type': 'blob', 'oid': e['oid'], 'size': e['size'],
                 'mode': '120000' if e['kind'] == 'symlink' else '100755' if e['mode'] & 0o111 else '100644'}
                for path, e in self._paths(revision).items() if e['kind'] != 'dir']

    def blob(self, revision, path, max_bytes=1048576):
        sha = self.resolve(revision)
        if sha not in self.entries:
            return super().blob(sha, path, max_bytes)
        entry = self._paths(revision).get(_safe_path(path))
        if not entry or entry['kind'] == 'dir':
            raise ValueError('归档中没有此文件。')
        if entry['size'] > max_bytes:
            raise ValueError('文件超过预览大小限制，可恢复原始文件。')
        return self.original._run('cat-file', 'blob', entry['oid'], max_output=max_bytes)

    def diff(self, target, base=None):
        sha = self.resolve(target)
        if sha not in self.entries and (base is None or self.resolve(base) not in self.entries):
            return super().diff(sha, base)
        before = self._paths(base) if base else {}
        after = self._paths(sha)
        files, counts = [], dict(added=0, modified=0, deleted=0, renamed=0, copied=0, type_changed=0, other=0, total=0)
        for path in sorted(set(before) | set(after)):
            a, b = before.get(path), after.get(path)
            if (a or b)['kind'] == 'dir' or a == b:
                continue
            if a and b and a['mode'] == b['mode'] and a['kind'] == b['kind'] and (
                    (a.get('sha256') is not None and a.get('sha256') == b.get('sha256')) or
                    (a.get('oid') is not None and a.get('oid') == b.get('oid'))):
                continue
            status = 'A' if a is None else 'D' if b is None else 'M'
            if len(files) < 200:
                files.append({'path': path, 'status': status})
            counts[{'A': 'added', 'D': 'deleted', 'M': 'modified'}[status]] += 1
        counts['total'] = sum(counts.values())
        return {'target': sha, 'base': self.resolve(base) if base else None,
                'parents': self._parents(sha), 'files': files, 'counts': counts,
                'files_truncated': counts['total'] > len(files)}

    def status(self):
        return {'available': False, 'dirty': False, 'changes': [],
                'reason': '独立归档快照；原项目 Git 元数据在恢复时还原。'}

    def materialize(self, revision, destination, cancel=None, paths=None):
        sha = self.resolve(revision)
        if sha not in self.entries:
            return super().materialize(sha, destination, cancel=cancel, paths=paths)
        if paths is not None:
            raise ValueError('旧归档请先完整恢复到新目录，再选择所需文件。')
        if cancel:
            cancel.check()
        entry = self.entries[sha]
        report = restore_snapshot(self.group['archive_repository'], entry['commit'], destination)
        return {'files': report['files'], 'object_hashes_verified': True,
                'readback_verified': True, 'warnings': report['metadata_warnings'],
                'submodules': [], 'lfs_pointers': [], 'archive_sha': entry['commit'],
                'view_sha': sha, 'nested_git_restored': True}
