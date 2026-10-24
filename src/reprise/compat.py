#!/usr/bin/env python3
"""Portable Reprise with read-only Git history and new-path recovery/export."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tarfile
import uuid
import zipfile

from .git import Repository, _environment
from .cli import default_directory


def emit(value):
    print(json.dumps(value,ensure_ascii=True,indent=2))


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def manifest(root):
    result=[]
    for parent,dirs,files in os.walk(root,followlinks=False):
        for name in files+[n for n in dirs if (Path(parent)/n).is_symlink()]:
            p=Path(parent)/name
            if p.is_symlink():
                data=os.fsencode(os.readlink(p));sha=hashlib.sha256(data).hexdigest();size=len(data)
            else:sha=digest(p);size=p.stat().st_size
            result.append({'path':p.relative_to(root).as_posix(),'type':'symlink' if p.is_symlink() else 'file','bytes':size,'sha256':sha})
    return sorted(result,key=lambda x:x['path'])


def output_path(repository,value):
    requested=Path(value).expanduser()
    if os.path.lexists(requested):raise ValueError('Destination exists; choose a new path')
    dest=requested.resolve()
    outside_source(repository,dest)
    receipt=dest.with_name(dest.name+'.reprise.json')
    if os.path.lexists(receipt):raise ValueError('Receipt already exists; choose a new path')
    return dest,receipt


def outside_source(repository,dest):
    raw=os.fsdecode(repository._run('rev-parse','--git-common-dir').rstrip(b'\n'))
    common=Path(raw)
    common=(common if common.is_absolute() else repository.path/common).resolve()
    for protected in (repository.work_tree,repository.git_dir,common):
        if protected and (dest==protected or protected in dest.parents):raise ValueError('Output must be outside source repository and .git')


def select(root,subdir):
    if not subdir:return root
    p=PurePosixPath(subdir)
    if p.is_absolute() or any(x in ('..','.') for x in p.parts) or not p.parts:raise ValueError('Invalid subdir')
    selected=root.joinpath(*p.parts)
    if selected.is_symlink() or not selected.is_dir() or root not in selected.resolve().parents:raise ValueError('subdir is not an internal directory')
    for parent,dirs,files in os.walk(selected,followlinks=False):
        for name in dirs+files:
            link=Path(parent)/name
            if link.is_symlink():
                target=link.resolve(strict=False)
                if target!=selected and selected not in target.parents:raise ValueError('Symlink escapes selected subdir')
    return selected


def archive(root,dest,kind):
    paths=sorted(root.rglob('*'))
    if kind=='zip':
        with dest.open('xb') as stream,zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED,allowZip64=True,strict_timestamps=False) as z:
            for p in paths:
                name=p.relative_to(root).as_posix()
                if p.is_symlink():
                    info=zipfile.ZipInfo(name);info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
                    z.writestr(info,os.fsencode(os.readlink(p)))
                else:z.write(p,name+'/' if p.is_dir() else name)
        with zipfile.ZipFile(dest) as z:
            if z.testzip() is not None:raise ValueError('ZIP integrity failed')
    else:
        with dest.open('xb') as stream,tarfile.open(fileobj=stream,mode='w:gz',dereference=False) as t:
            for p in paths:t.add(p,arcname=p.relative_to(root).as_posix(),recursive=False)
        expected={f['path']:f for f in manifest(root)}
        with tarfile.open(dest,'r:gz') as t:
            for f in t:
                if f.isfile():
                    h=hashlib.sha256();stream=t.extractfile(f)
                    for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
                    if h.hexdigest()!=expected[f.name]['sha256']:raise ValueError('tar.gz content mismatch')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--data');commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('doctor')
    p=commands.add_parser('projects');p.add_argument('--registry')
    for name in ['open','history','refs','compare','restore','export','bundle']:
        p=commands.add_parser(name)
        source=p.add_mutually_exclusive_group(required=True);source.add_argument('--repo');source.add_argument('--project')
        p.add_argument('--registry')
        if name=='open':p.add_argument('--no-browser',action='store_true');p.add_argument('--lang',choices=['zh','en'],default='zh')
        if name=='history':p.add_argument('--ref');p.add_argument('--limit',type=int,default=30);p.add_argument('--offset',type=int,default=0)
        if name=='compare':p.add_argument('--base',required=True);p.add_argument('--target',required=True)
        if name in ['restore','export']:
            p.add_argument('--ref');p.add_argument('--to',required=True);p.add_argument('--subdir');p.add_argument('--work')
        if name=='bundle':p.add_argument('--to',required=True)
    p=commands.add_parser('shutdown')
    a=parser.parse_args(argv)
    data=Path(getattr(a,'data',None) or default_directory()).expanduser().resolve()
    if a.command=='shutdown':
        from reprise.launcher import shutdown
        emit(shutdown(data));return 0
    if a.command=='projects':
        from . import archive_names
        emit(archive_names.list_projects(a.registry or str(data/'named-archives/registry.json')));return 0
    if not a.registry:a.registry=str(data/'named-archives/registry.json')
    named=bool(a.project)
    if a.command=='open' and not named:
        from .launcher import open_repository
        emit(open_repository(data,a.repo,browser=False,language=a.lang));return 0
    if named:
        from . import archive_names
        group,entries=archive_names.select(a.project,getattr(a,'ref',None),a.registry)
        original,repository=archive_names.verify_selection(group,entries)
    else:repository=Repository(a.repo)
    if a.command=='open':
        from reprise.launcher import open_repository
        result=open_repository(data,str(repository.path),browser=False,language=a.lang)
        if named:result.update(named_project=group['name'],archive_versions=[e['name'] for e in entries])
        emit(result);return 0
    if a.command=='history':
        emit(archive_names.history(group,entries,a.limit,a.offset) if named else {'repository':repository.info(),**repository.history(a.ref or '--all',a.limit,a.offset)});return 0
    if a.command=='refs':
        emit({'project':group['name'],'versions':[{'name':e['name'],'label':e['label'],'sha':e['commit'],'view_sha':e['view_commit']} for e in entries]} if named else {'repository':repository.info(),'refs':repository.refs()});return 0
    if a.command=='compare':
        if named:
            _,b=archive_names.select(a.project,a.base,a.registry);_,t=archive_names.select(a.project,a.target,a.registry)
            base=b[0]['view_commit'];target=t[0]['view_commit']
        else:base=repository.resolve(a.base);target=repository.resolve(a.target)
        emit({'repository':repository.info(),'base':base,'target':target,'diff':repository.diff(target,base)});return 0
    # Legacy exports keep their staging in this data root as well. Protect the
    # whole operation with the same lease as native CLI and service writes.
    from .maintenance import DataLease
    outside_source(repository, data)
    if named:
        outside_source(original, data)
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    with DataLease(data):
        return _recover(a, data, named, repository, group if named else None,
                        entries if named else None, original if named else None)


def _recover(a, data, named, repository, group, entries, original):
    from . import archive_names
    dest,receipt=output_path(repository,a.to);kind=None
    if a.command=='export':
        kind='zip' if dest.name.endswith('.zip') else 'tar.gz' if dest.name.endswith(('.tgz','.tar.gz')) else None
        if not kind:raise ValueError('Choose .zip, .tar.gz or .tgz')
    special=False
    if not named and a.command in ['restore','export']:
        if not a.ref:raise ValueError('--repo restore/export requires --ref')
        from .archive_snapshot import is_snapshot,restore_snapshot
        sha=repository.resolve(a.ref);special=is_snapshot(repository,sha)
        if special:original=repository
    if (named or special) and a.command in ['restore','export']:
        if a.subdir:raise ValueError('Named archive recovery already unwraps the original files; omit --subdir')
        outside_source(original,dest)
        dest.parent.mkdir(parents=True,exist_ok=True)
        if a.command=='restore':root=dest;job=None
        else:
            parent=Path(a.work).expanduser().resolve() if a.work else data/'skill-exports'
            outside_source(repository,parent);outside_source(original,parent)
            job=parent/('reprise-'+uuid.uuid4().hex);job.mkdir(parents=True,exist_ok=False);root=job/'restored'
        if named:result=archive_names.restore(group,entries,root)
        else:
            recovered=restore_snapshot(str(repository.path),sha,root)
            result={'source_repository':str(repository.path),'output':str(root),'verification':'passed','verified_files':recovered['files'],'snapshots':[recovered],'nested_git_restored':True}
        if a.command=='export':archive(root,dest,kind)
        result.update(output=str(dest),format='directory' if a.command=='restore' else kind,retained_staging=str(job) if job else None)
        if dest.is_file():result.update(archive_sha256=digest(dest),archive_bytes=dest.stat().st_size)
        with receipt.open('x',encoding='utf-8') as stream:
            os.chmod(receipt,0o600);json.dump(result,stream,ensure_ascii=True,indent=2);stream.write('\n')
        emit({**result,'receipt':str(receipt)});return 0
    if not named and a.command in ['restore','export'] and not a.ref:raise ValueError('--repo restore/export requires --ref')
    sha=None if a.command=='bundle' else repository.resolve(a.ref)
    parent=None
    if a.command in ['restore','export'] and (a.command=='export' or a.subdir):
        parent=Path(a.work).expanduser().resolve() if a.work else data/'skill-exports'
        outside_source(repository,parent)
    dest.parent.mkdir(parents=True,exist_ok=True)
    if a.command=='bundle':
        tips=['refs/tags/'+e['label'] for e in entries] if named else ['--all']
        with dest.open('xb') as stream:
            r=subprocess.run(repository._command('bundle','create','-',*tips),stdout=stream,stderr=subprocess.PIPE,env=_environment(),timeout=300)
        if r.returncode:raise ValueError(r.stderr[:8192].decode(errors='replace'))
        repository._run('bundle','verify',str(dest),max_output=1024*1024,timeout=300)
        result={'source_repository':str(repository.path),'output':str(dest),'format':'git-bundle','verification':'passed','scope':'all local refs; uncommitted files and external LFS/submodule objects are not included'}
        if named:result.update(project=group['name'],scope='selected registered archive snapshots, including original nested Git bytes mapped by snapshot.json',archive_versions=[{'label':e['label'],'sha':e['commit'],'view_sha':e['view_commit']} for e in entries])
    else:
        if a.command=='restore' and not a.subdir:
            materialized=repository.materialize(sha,dest);root=dest;job=None
        else:
            job=parent/('reprise-'+uuid.uuid4().hex);job.mkdir(parents=True,exist_ok=False)
            materialized=repository.materialize(sha,job/'snapshot');root=select(job/'snapshot',a.subdir)
            if a.command=='restore':shutil.copytree(root,dest,symlinks=True);root=dest
            else:archive(root,dest,kind)
        result={'source_repository':str(repository.path),'sha':sha,'output':str(dest),'subdir':a.subdir,'format':'directory' if a.command=='restore' else kind,
                'git_object_hashes_verified':materialized['object_hashes_verified'],'warnings':materialized['warnings'],
                'submodules':materialized['submodules'],'lfs_pointers':materialized['lfs_pointers'],'retained_staging':str(job) if job else None,
                'files':manifest(root),'verification':'passed'}
    if dest.is_file():result.update(archive_sha256=digest(dest),archive_bytes=dest.stat().st_size)
    with receipt.open('x',encoding='utf-8') as stream:
        os.chmod(receipt,0o600);json.dump(result,stream,ensure_ascii=True,indent=2);stream.write('\n')
    public={k:v for k,v in result.items() if k!='files'};public.update(manifest_files=len(result.get('files',[])),receipt=str(receipt));emit(public)
    return 0


if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,OSError,KeyError,subprocess.SubprocessError) as error:
        print(json.dumps({'error':str(error),'partial_outputs_retained':True}),file=sys.stderr);sys.exit(1)
