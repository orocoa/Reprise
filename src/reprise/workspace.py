"""Read-only workspace history, related archives and file comparisons."""
import hashlib
import json
import re


def repository_snapshot(service, identifier):
    repository = service.projects.repository(identifier)
    project = service.projects.get(identifier, repository=repository)
    refs = repository.refs()
    tips = list(dict.fromkeys(([project['head']] if project['head'] else []) +
                [r['sha'] for r in refs if r.get('target_type') == 'commit']))
    warnings = []
    if len(tips) > 64:
        tips = tips[:64]
        warnings.append('引用较多，本次最多读取 64 个不同引用顶点。')
    history = repository.history_tips(tips, refs=refs, shallow=project['repository']['shallow'])
    if history['truncated_tips']:
        warnings.append('部分引用超过 2000 个提交，未加载的父节点作为边界显示。')
    for commit in history['commits']:
        commit['notes'] = project.get('version_notes', {}).get(commit['sha'])
        commit['source_project_id'] = identifier
    ordered = sorted(history['commits'], key=lambda c: (c['committed_at'], c['sha']), reverse=True)
    fingerprint = hashlib.sha256(json.dumps([ordered, refs], sort_keys=True).encode()).hexdigest()
    return {'project': project, 'refs': refs, 'commits': ordered, 'snapshot': fingerprint,
            'warnings': warnings + project['repository'].get('warnings', []),
            'status': repository.status()}


def snapshot(service, identifier, history_identifiers=(), history_catalog=None):
    result = repository_snapshot(service, identifier)
    commits = {c['sha']: c for c in result['commits']}
    refs = {r['name']: r for r in result['refs']}
    sources = [{'id': identifier, 'kind': 'current', 'path': result['project']['path'],
                'count': len(commits), 'unique_commits': len(commits)}]
    fingerprints = [result['snapshot']]
    for history_id in history_identifiers:
        archive = repository_snapshot(service, history_id)
        if not set(commits).intersection(c['sha'] for c in archive['commits']):
            raise ValueError('历史存档与当前仓库没有共同提交，不能合并展示。')
        extra = 0
        visible = 0
        for commit in archive['commits']:
            if history_catalog is not None and commit['sha'] not in history_catalog:
                continue
            visible += 1
            if commit['sha'] not in commits:
                commit['archived'] = True
                commits[commit['sha']] = commit
                extra += 1
        for ref in archive['refs']:
            if ref['name'] not in refs and ref['sha'] in commits:
                refs[ref['name']] = {**ref, 'source_project_id': history_id}
        sources.append({'id': history_id, 'kind': 'archive', 'path': archive['project']['path'],
                        'count': len(archive['commits']), 'visible_commits': visible,
                        'metadata_commits': len(archive['commits']) - visible, 'unique_commits': extra})
        result['warnings'].extend(archive['warnings'])
        fingerprints.append(archive['snapshot'])
    result['commits'] = sorted(commits.values(), key=lambda c: (c['committed_at'], c['sha']), reverse=True)
    # Explicitly removed read-only versions must not reappear through another
    # linked archive. Keep every retained commit's original ordered parent SHAs;
    # omitted parents remain graph boundaries rather than invented connections.
    from .version_cleanup import removed_versions
    removed = set().union(*(removed_versions(service, source['id']) for source in sources))
    result['commits'] = [c for c in result['commits'] if c['sha'] not in removed]
    for source in sources:
        visible = [c for c in result['commits'] if c['source_project_id'] == source['id']]
        source['unique_commits'] = len(visible)
        if source['kind'] == 'current':
            source['count'] = len(visible)
    result['refs'] = list(refs.values())
    result['history_sources'] = sources
    # Catalog membership and provenance can change without moving a Git tip.
    result['snapshot'] = hashlib.sha256(json.dumps(
        [fingerprints, result['commits'], result['refs']], sort_keys=True).encode()).hexdigest()
    return result


def search_index(service, identifier, shas):
    """Return only changed names; never build runtime or evidence details."""
    from .git import Repository
    if (not isinstance(shas, list) or len(shas) > 128 or
            any(not isinstance(s, str) or not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', s) for s in shas)):
        raise ValueError('Expected at most 128 full commit SHAs')
    repository = service.projects.repository(identifier)
    if type(repository) is Repository:
        paths = repository.search_index(shas)
    else:
        paths = {sha: [p for f in repository.diff(sha)['files']
                       for p in (f['path'], f.get('old_path')) if p] for sha in dict.fromkeys(shas)}
    return {'paths': paths}


def comparison_repository(service, identifier, history_identifiers, base, target):
    for project_id in [identifier, *history_identifiers]:
        repository = service.projects.repository(project_id)
        try:
            repository.resolve(base)
            repository.resolve(target)
        except ValueError:
            continue
        return project_id, repository
    raise ValueError('两个版本没有可同时读取的 Git 来源，不能比较。')


def context(service, identifier=None):
    if not identifier:
        records = service.projects.records()
        identifier = records[0]['id'] if len(records) == 1 else None
    record = service.projects.record(identifier) if identifier else {}
    return {'project_id': identifier,
            'history_project_ids': record.get('history_project_ids', [])}


def project_snapshot(service, identifier):
    record = service.projects.record(identifier)
    return snapshot(service, identifier, record.get('history_project_ids', []),
                    set(record['history_catalog']) if record.get('history_catalog') is not None else None)


def file_comparison(service, identifier, sha, path, base=None):
    repository = service.projects.repository(identifier)
    target = repository.resolve(sha)
    diff = repository.diff(target, base=base)
    item = next((f for f in diff['files'] if f['path'] == path), None)
    if item is None:
        raise ValueError('该文件不在当前比较的变化清单中。')

    def content(revision, name, absent=False):
        if not revision or absent:
            return {'text': '', 'absent': True}
        try:
            data = repository.blob(revision, name, max_bytes=65536)
            if b'\0' in data:
                return {'text': '', 'binary': True, 'error': '二进制文件，请查看变化清单。'}
            return {'text': data.decode('utf-8')}
        except (ValueError, UnicodeError) as error:
            return {'text': '', 'error': str(error)}

    return {'sha': target, 'path': path, 'base_path': item.get('old_path', path), 'base': diff['base'],
            'before': content(diff['base'], item.get('old_path', path), item['status'].startswith('A')),
            'after': content(target, path, item['status'].startswith('D'))}
