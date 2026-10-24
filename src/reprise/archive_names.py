"""Local names and pinned versions for Reprise's private archive collection."""
import json
import os
from pathlib import Path
import unicodedata

from reprise.cli import default_directory
from .archive_snapshot import restore_snapshot


def key(value):
    return ''.join(c for c in unicodedata.normalize('NFKC',str(value)).casefold() if c.isalnum())


def registry_path(value=None):
    return Path(value).expanduser().resolve() if value else Path(default_directory())/'named-archives/registry.json'


def load(value=None):
    p=registry_path(value)
    if not p.is_file():raise ValueError('No named archives registered. Registry: '+str(p))
    data=json.loads(p.read_text())
    if data.get('schema')!=1:raise ValueError('Unsupported archive registry')
    labels=[e['label'] for g in data['projects'] for e in g['snapshots']]
    if len(labels)!=len(set(labels)):raise ValueError('Duplicate archive labels')
    return data


def list_projects(value=None):
    data=load(value)
    return {'registry':str(registry_path(value)),'archive_count':sum(len(g['snapshots']) for g in data['projects']),
            'projects':[{'id':g['id'],'name':g['name'],'aliases':g['aliases'],
                         'versions':[{'label':e['label'],'name':e['name'],'sha':e['commit']} for e in g['snapshots']],
                         'available':Path(g['view_repository']).is_dir()} for g in data['projects']]}


def select(project,version=None,value=None):
    data=load(value);needle=key(project);matches=[]
    if not needle:raise ValueError('Project name is empty')
    for g in data['projects']:
        if needle in {key(x) for x in [g['id'],g['name'],*g['aliases']]}:
            matches.append((g,g['snapshots']))
        else:
            entries=[e for e in g['snapshots'] if needle in {key(x) for x in [e['label'],e['name'],*e['aliases']]}]
            if entries:matches.append((g,entries))
    if len(matches)!=1:
        names=[g['name'] for g,_ in matches] or [g['name'] for g in data['projects']]
        raise ValueError(('Ambiguous project name. ' if matches else 'Unknown project name. ')+'Choose: '+', '.join(names))
    group,entries=matches[0]
    if version and version!='--all':
        v=key(version)
        if v in ('latest','最新'):
            if not group.get('latest'):raise ValueError('This project contains different archive components; choose a version or restore all')
            entries=[e for e in entries if e['label']==group['latest']]
        else:
            entries=[e for e in entries if v in {key(x) for x in [e['label'],e['name'],e['commit'],e['view_commit'],*e['version_aliases']]}]
        if len(entries)!=1:raise ValueError('Unknown or ambiguous version. Choose: '+', '.join(e['name'] for e in group['snapshots']))
    return group,entries


def verify_selection(group,entries):
    from reprise.git import Repository
    repository=Repository(group['archive_repository'])
    view=Repository(group['view_repository'])
    for e in entries:
        if repository.resolve('refs/tags/'+e['label'])!=e['commit']:raise ValueError('Archive tag changed: '+e['label'])
        if view.resolve('refs/tags/'+e['label'])!=e['view_commit']:raise ValueError('Archive view changed: '+e['label'])
    return repository,view


def history(group,entries,limit=30,offset=0):
    if not 1<=limit<=200 or not 0<=offset<=1000000:raise ValueError('History limit/offset out of range')
    _,view=verify_selection(group,entries)
    commits={c['sha']:c for c in view.history('--all',200,0)['commits']}
    versions=[]
    for e in entries:
        c=commits[e['view_commit']]
        versions.append({'name':e['name'],'label':e['label'],'sha':e['commit'],'view_sha':e['view_commit'],
                         'files':e['files'],'bytes':e['logical_bytes'],'archived_at':c['committed_at'],
                         'original_path':e['source'],'parents':[]})
    return {'project':group['name'],'history_kind':'archived_snapshots','commits':versions[offset:offset+limit],
            'has_more':offset+limit<len(versions),'total':len(versions),
            'note':'Each entry is an archived directory, not an invented original project commit. Original nested Git metadata is preserved in recovery.'}


def restore(group,entries,dest):
    verify_selection(group,entries)
    dest=Path(dest).resolve()
    if os.path.lexists(dest):raise ValueError('Destination exists; choose a new path')
    for root in [group['archive_repository'],group['view_repository'],*(e['source'] for e in entries)]:
        protected=Path(root).resolve()
        if dest==protected or protected in dest.parents:raise ValueError('Destination is inside an archive or original source')
    if len(entries)>1:dest.mkdir(parents=True)
    results=[]
    for e in entries:
        child=dest/e['restore_name'] if len(entries)>1 else dest
        results.append(restore_snapshot(group['archive_repository'],e['commit'],child))
    return {'project':group['name'],'source_repository':group['archive_repository'],'output':str(dest),
            'verification':'passed','verified_files':sum(r['files'] for r in results),
            'snapshots':results,'nested_git_restored':True}
