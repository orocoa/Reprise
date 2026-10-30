"""Choose an external recovery location without reserving or creating it."""
from dataclasses import dataclass
import os
from pathlib import Path
import re
import secrets
import unicodedata


_FULL_SHA = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})')


@dataclass(frozen=True)
class DestinationRoot:
    path: Path
    location: str


def _project_name(value):
    name = unicodedata.normalize('NFKC', str(value or 'project'))
    name = ''.join(c if c.isalnum() or c in '-_' else '-' for c in name)
    return re.sub('-+', '-', name).strip('-_')[:40] or 'project'


def _through_link(path):
    return any(p.is_symlink() for p in (path, *path.parents))


def _within(path, root):
    return path == root or root in path.parents


def _roots(project, records, data):
    """The explicit project relation determines provenance, never path guesses."""
    source = Path(project['path'])
    internal = project.get('kind') == 'archive' and _within(source.resolve(), data)
    if not internal:
        return False, [DestinationRoot(source.parent, 'source-sibling')]
    roots = [DestinationRoot(Path(p['path']).parent, 'related-project-sibling')
             for p in records if project['id'] in p.get('history_project_ids', [])]
    roots += [DestinationRoot(Path.home() / 'Documents', 'documents'),
              DestinationRoot(Path.home(), 'home')]
    return True, list(dict.fromkeys(roots))


def _check_root(root):
    if _through_link(root):
        raise ValueError('原项目位置经过符号链接，请在“更改位置”中选择新的文件夹。')
    if not root.is_dir() or not os.access(root, os.W_OK | os.X_OK):
        raise ValueError('原项目的上级目录不可用或不可写，请在“更改位置”中选择新的文件夹。')


def _check_target(recoveries, candidate, data, sources):
    resolved = candidate.resolve()
    if _within(resolved, data) or resolved in data.parents:
        raise ValueError('恢复副本必须位于 Reprise 数据目录之外，请更改位置。')
    if any(resolved in source.parents for source in sources):
        raise ValueError('恢复副本不能包含已登记源目录，请更改位置。')
    # The same validator used by execution protects all registered sources and
    # their common Git directories. Execution repeats it after receipt creation.
    return recoveries.destination(str(candidate))


def suggest_destination(recoveries, project_id, sha):
    """Resolve exact identity, choose roots, then validate a fresh target.

    Ordinary projects retain their source-sibling behavior. An internal archive
    tries its explicit owner's sibling, Documents, then home. Unusable archive
    roots are skipped; ordinary-project failures still ask for another location.
    A returned name is only a suggestion, not a filesystem reservation.
    """
    if not isinstance(sha, str) or not _FULL_SHA.fullmatch(sha):
        raise ValueError('请选择一个完整版本标识，不能使用 HEAD 或缩写。')
    project = recoveries.projects.record(project_id)
    if recoveries.projects.repository(project_id).resolve(sha) != sha:
        raise ValueError('版本标识发生变化，请重新选择确切版本。')
    managed = Path(recoveries.directory)
    if _through_link(managed):
        raise ValueError('恢复资料目录不能经过符号链接，请检查本地数据位置。')
    if managed.exists() and not managed.is_dir():
        raise ValueError('恢复资料位置不是文件夹，请检查本地数据位置。')
    if _through_link(Path(project['path'])):
        raise ValueError('原项目位置经过符号链接，请在“更改位置”中选择新的文件夹。')

    data = Path(recoveries.projects.directory).resolve()
    records = recoveries.projects.records()
    sources = [Path(p['path']).resolve() for p in records]
    fallback, roots = _roots(project, records, data)
    stem = 'Restored-%s-%s-' % (_project_name(project.get('name')), sha[:8])
    for root in roots:
        try:
            _check_root(root.path)
            for _ in range(8):
                candidate = root.path / (stem + secrets.token_hex(4))
                if os.path.lexists(candidate):
                    continue
                try:
                    target = _check_target(recoveries, candidate, data, sources)
                except ValueError:
                    if os.path.lexists(candidate):
                        continue  # Another writer occupied this suggestion.
                    raise
                return {'project_id': project_id, 'sha': sha, 'to': str(target),
                        'display_label': target.name, 'location': root.location}
        except ValueError:
            if not fallback:
                raise
    raise ValueError('暂时无法推荐新的恢复目录，请重试或选择另一个新位置。')
