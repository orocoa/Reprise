"""Two explicit version lifecycle choices, restricted to Reprise-owned files."""
import hashlib
import json
from pathlib import Path
import re
import secrets
import os

from .content_lock import content_access
from .environments import _scan, _activity, _delete_output
from .storage import read_json, write_json, now, locked
from .folders import signature
from .backup import _regular, _directory
from .version_actions import cleanup_actions, removal_effect


def _folder(app):
    path = app.directory / 'version-cleanup'
    path.mkdir(mode=0o700, exist_ok=True)
    if path.is_symlink():
        raise ValueError('版本操作目录不能是链接。')
    return path


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def removed_versions(app, project):
    """Local view membership only; original Git objects and parent headers stay intact."""
    folder = app.projects.directory / 'version-cleanup'
    if folder.is_symlink():
        raise ValueError('版本操作目录不能是链接。')
    value = read_json(folder / 'removed-versions.json', {})
    return set(value.get(project, []))


def _remove_from_view(app, project, sha):
    folder = _folder(app)
    with locked(folder / 'removed-versions.lock'):
        path = folder / 'removed-versions.json'
        value = read_json(path, {})
        value[project] = sorted(set(value.get(project, [])) | {sha})
        write_json(path, value, private=True)


def options(app, project, revision):
    repository = app.projects.repository(project)
    sha = repository.resolve(revision)
    kind = app.projects.record(project).get('kind')
    has_environment = any(e['status'] != 'released'
                          for e in app.runtimes.environments.list(project, sha))
    return {'sha': sha, 'source_history_retained': kind != 'folder',
            'has_environment': has_environment, 'actions': cleanup_actions(kind, has_environment)}


def _roots(app, project, sha):
    roots = []
    for runtime in app.runtimes.list():
        if runtime.get('project_id') == project and runtime.get('sha') == sha:
            if runtime.get('running') or runtime.get('status') in ('preparing', 'install', 'build', 'starting', 'cleanup_failed'):
                raise ValueError('请先停止此版本的运行预览。')
            if not re.fullmatch('[0-9a-f]{32}', runtime['id']):
                raise ValueError('运行副本身份无效。')
            roots.append(app.directory / 'runtimes' / runtime['id'])
    for environment in app.runtimes.environments.list(project, sha):
        identifier = environment['environment_id']
        app.runtimes.environments.get(identifier)  # Validate registered ownership.
        roots.append(app.directory / 'environments' / identifier)
    # A capture may contain before/after pictures belonging to different SHAs.
    # Never remove another revision's picture as a side effect.
    for path in (app.directory / 'evidence').glob('*/record.json'):
        record = read_json(path)
        items = record.get('items', [])
        if record.get('project_id') == project and record.get('sha') == sha:
            if all(item.get('sha') == sha for item in items):
                roots.append(path.parent)
    return sorted(set(roots))


def _mixed_media(app, project, sha, whole_roots):
    """Remove only selected-SHA media from before/after comparison captures."""
    result = {}
    for path in (app.directory / 'evidence').glob('*/record.json'):
        if path.parent in whole_roots:
            continue
        record = read_json(path)
        if record.get('project_id') != project:
            continue
        items = record.get('items', [])
        selected = [item for item in items if item.get('sha') == sha]
        if not selected:
            continue
        retained = {item.get('path') for item in items if item.get('sha') != sha}
        files = {}
        for item in selected:
            if not item.get('path') or item['path'] in retained:
                continue
            candidate = Path(item['path'])
            if candidate.parent != path.parent or candidate.is_symlink():
                raise ValueError('截图路径归属不明确，未删除。')
            with _regular(candidate) as stream:
                files[candidate.name] = signature(os.fstat(stream.fileno()))
        result[str(path.parent.relative_to(app.directory))] = {'record': record, 'files': files}
    return result


def plan(app, project, revision, mode):
    if mode not in ('all', 'environment'):
        raise ValueError('请选择删除范围。')
    repository = app.projects.repository(project)
    sha = repository.resolve(revision)
    record = app.projects.record(project)
    result = {'id': secrets.token_hex(16), 'project_id': project, 'sha': sha,
              'mode': mode, 'created_at': now(), 'blockers': [], 'roots': {},
              'effect': removal_effect(record.get('kind')) if mode == 'all' else 'clear-environment',
              'environment_ids': [], 'bytes': 0, 'mixed_media': {},
              'source_history_retained': record.get('kind') != 'folder'}
    result['active_runtime_ids'] = [r['id'] for r in app.runtimes.list()
        if r.get('project_id') == project and r.get('sha') == sha
        and (r.get('running') or r.get('status') in ('preparing', 'install', 'build', 'starting', 'cleanup_failed'))]
    if app.jobs.busy:
        result['blockers'].append('请等待当前任务完成，再核对删除范围。')
    if mode == 'all':
        if record.get('kind') == 'folder':
            content = app.version_delete_plan(project, [sha])
            result['content_plan'] = content['id']
            result['blockers'].extend(content.get('blockers', []))
            result['version_content_bytes'] = content['unique_content_bytes']
        try:
            roots = _roots(app, project, sha)
            for path in roots:
                if _activity(path):
                    raise ValueError('版本副本仍被进程使用，请先停止后再删除。')
                entries = _scan(path, identities=True)
                result['roots'][str(path.relative_to(app.directory))] = entries
                result['bytes'] += sum(e.get('size', 0) for e in entries.values())
            result['mixed_media'] = _mixed_media(app, project, sha, roots)
            result['bytes'] += sum(e[3] for media in result['mixed_media'].values() for e in media['files'].values())
        except (ValueError, OSError) as error:
            result['blockers'].append(str(error))
    else:
        for environment in app.runtimes.environments.list(project, sha):
            if environment['status'] == 'released':
                continue
            check = app.runtimes.environment_check(environment['environment_id'])
            result['blockers'].extend(check.get('blockers', []))
            result['environment_ids'].append(environment['environment_id'])
            result['bytes'] += check.get('output_bytes', 0)
    result['fingerprint'] = _hash(result)
    write_json(_folder(app) / (result['id'] + '.json'), result, private=True)
    return result


def execute(app, project, identifier, confirm):
    if confirm is not True or not isinstance(identifier, str) or not re.fullmatch('[0-9a-f]{32}', identifier):
        raise ValueError('请核对范围并确认删除。')
    path = _folder(app) / (identifier + '.json')
    value = read_json(path, required=True)
    saved = dict(value)
    fingerprint = saved.pop('fingerprint', None)
    if fingerprint != _hash(saved) or value['project_id'] != project or value['blockers']:
        raise ValueError('删除计划无效，请重新核对。')
    receipt = _folder(app) / (identifier + '.receipt.json')
    if receipt.exists():
        previous = read_json(receipt)
        if previous.get('status') == 'complete':
            return previous
        raise ValueError('上次删除未完整完成，请保留回执并检查剩余内容。')
    result = {'project_id': project, 'sha': value['sha'], 'mode': value['mode'],
              'status': 'running', 'removed_files': 0, 'removed_logical_bytes': 0,
              'source_files_removed': False, 'created_at': now(), 'receipt_path': str(receipt)}
    write_json(receipt, result, private=True)
    try:
        with app.request_gate, content_access(app.projects.folders.directory):
            if value['mode'] == 'environment':
                # Each release repeats ownership, activity and input verification.
                result['releases'] = [app.runtimes.release_environment(e) for e in value['environment_ids']]
                result['removed_files'] = sum(r['removed_files'] for r in result['releases'])
                result['removed_logical_bytes'] = sum(r['removed_logical_bytes'] for r in result['releases'])
                result['version_retained'] = True
            else:
                roots = _roots(app, project, value['sha'])
                if {str(p.relative_to(app.directory)) for p in roots} != set(value['roots']):
                    raise ValueError('删除范围已经变化，请重新核对。')
                for target in roots:
                    expected = value['roots'][str(target.relative_to(app.directory))]
                    if _activity(target) or _scan(target, identities=True) != expected:
                        raise ValueError('版本副本已经变化或正在使用，未删除。')
                if _mixed_media(app, project, value['sha'], roots) != value['mixed_media']:
                    raise ValueError('版本截图已经变化，请重新核对。')
                # The canonical operation verifies every retained saved version
                # and keeps complete ordered parent headers for graph boundaries.
                if value.get('content_plan'):
                    result['content'] = app.delete_versions(project, value['content_plan'], True)
                elif not value.get('source_history_retained'):
                    raise ValueError('删除计划缺少版本内容校验，请重新核对。')
                for target in roots:
                    expected = value['roots'][str(target.relative_to(app.directory))]
                    _delete_output(target, expected, result)
                for relative, media in value['mixed_media'].items():
                    target = app.directory / relative
                    with _directory(target) as fd:
                        for name, expected in media['files'].items():
                            if signature(os.stat(name, dir_fd=fd, follow_symlinks=False)) != expected:
                                raise ValueError('截图文件已经变化，剩余文件保留。')
                            os.unlink(name, dir_fd=fd)
                            result['removed_files'] += 1
                            result['removed_logical_bytes'] += expected[3]
                    record = media['record']
                    record['items'] = [item for item in record['items'] if item.get('sha') != value['sha']]
                    record['removed_version_media'] = value['sha']
                    write_json(target / 'record.json', record, private=True)
                if value.get('source_history_retained'):
                    _remove_from_view(app, project, value['sha'])
                    result['removed_from_reprise'] = True
                    result['source_history_retained'] = True
                result['version_retained'] = False
            result.update(status='complete', finished_at=now())
    except Exception as error:
        result.update(status='partial', error=str(error), finished_at=now())
        write_json(receipt, result, private=True)
        raise
    write_json(receipt, result, private=True)
    return result
