"""Suggest a new recovery location without reserving it or listing directories."""
import os
from pathlib import Path
import re
import secrets
import unicodedata


_FULL_SHA = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})')


def _project_name(value):
    name = unicodedata.normalize('NFKC', str(value or 'project'))
    name = ''.join(character if character.isalnum() or character in '-_'
                   else '-' for character in name)
    return re.sub('-+', '-', name).strip('-_')[:40] or 'project'


def suggest_destination(recoveries, project_id, sha):
    """Return a suggestion for one registered project and an exact commit.

    The result is not a reservation. The restore operation must still use
    RecoveryStore.destination and exclusive materialization at execution time.
    Only generated siblings of the source are probed; callers cannot browse
    directories. The copy remains outside application data so it can be edited
    and registered as a new folder project.
    """
    if not isinstance(sha, str) or not _FULL_SHA.fullmatch(sha):
        raise ValueError('请选择一个完整版本标识，不能使用 HEAD 或缩写。')
    project = recoveries.projects.record(project_id)
    repository = recoveries.projects.repository(project_id)
    if repository.resolve(sha) != sha:
        raise ValueError('版本标识发生变化，请重新选择确切版本。')

    managed = Path(recoveries.directory)
    if any(path.is_symlink() for path in (managed, *managed.parents)):
        raise ValueError('恢复资料目录不能经过符号链接，请检查本地数据位置。')
    if managed.exists() and not managed.is_dir():
        raise ValueError('恢复资料位置不是文件夹，请检查本地数据位置。')

    source = Path(project['path'])
    root = source.parent
    if any(path.is_symlink() for path in (source, *source.parents)):
        raise ValueError('原项目位置经过符号链接，请在“更改位置”中选择新的文件夹。')
    if not root.is_dir() or not os.access(root, os.W_OK | os.X_OK):
        raise ValueError('原项目的上级目录不可用或不可写，请在“更改位置”中选择新的文件夹。')
    data = Path(recoveries.projects.directory).resolve()
    sources = [Path(record['path']).resolve()
               for record in recoveries.projects.records()]
    name = _project_name(project.get('name'))
    for _ in range(8):
        candidate = root / ('Restored-%s-%s-%s' %
                            (name, sha[:8], secrets.token_hex(4)))
        if os.path.lexists(candidate):
            continue
        resolved = candidate.resolve()
        if (resolved == data or data in resolved.parents or
                resolved in data.parents):
            raise ValueError('恢复副本必须位于 Reprise 数据目录之外，请更改位置。')
        if any(resolved in imported.parents for imported in sources):
            raise ValueError('恢复副本不能包含已登记源目录，请更改位置。')
        try:
            target = recoveries.destination(str(candidate))
        except ValueError:
            # Another operation may have occupied this candidate after the probe.
            if os.path.lexists(candidate):
                continue
            raise
        return {
            'project_id': project_id,
            'sha': sha,
            'to': str(target),
            'display_label': target.name,
            'location': 'source-sibling',
        }
    raise ValueError('暂时无法推荐新的恢复目录，请重试或选择另一个新位置。')
