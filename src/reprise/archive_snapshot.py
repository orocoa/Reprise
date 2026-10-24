#!/usr/bin/env python3
"""Restore the selected-snapshot format, without hooks, filters or path overwrite."""
import base64, ctypes, hashlib, json, os, subprocess, sys
from pathlib import Path, PurePosixPath
from reprise.git import Repository, _environment

REPO=None
ENV=_environment()

def git(*args):
    return subprocess.check_output(['git','--git-dir',str(REPO),*args],env=ENV)

def safe(rel):
    p=PurePosixPath(rel)
    if p.is_absolute() or '..' in p.parts or '\0' in rel:raise ValueError('Unsafe path')
    return p

def is_snapshot(repository,sha):
    rows=repository._run('ls-tree',sha,'--','snapshot.json').splitlines()
    if not rows:return False
    info=rows[0].split(b'\t',1)[0].split()
    if len(info)!=3 or info[1]!=b'blob':return False
    proc=subprocess.Popen(repository._command('cat-file','blob',info[2].decode()),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=ENV)
    try:
        prefix=proc.stdout.read(512)
        return b'"format":"reprise-selected-snapshot-v1"' in b''.join(prefix.split())
    finally:
        if proc.poll() is None:proc.terminate()
        proc.wait();proc.stdout.close()

def read_manifest(repository,commit):
    """Read an explicitly selected legacy manifest without the preview blob cap.

    Some existing directory archives have manifests larger than 100 MiB. They
    are local structured recovery data, not text previews or model input.
    """
    sha=repository.resolve(commit)
    oid=repository._run('rev-parse',sha+':snapshot.json').decode().strip()
    proc=subprocess.Popen(repository._command('cat-file','blob',oid),stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL,env=_environment())
    try:
        value=json.load(proc.stdout)
        if proc.wait()!=0 or not isinstance(value,dict) or value.get('format')!='reprise-selected-snapshot-v1':
            raise ValueError('Invalid legacy snapshot manifest')
        return value
    finally:
        if proc.poll() is None:proc.terminate();proc.wait()
        proc.stdout.close()

def restore_snapshot(repo,commit,dest):
    repository=Repository(repo)
    REPO=repository.git_dir
    def git(*args):
        return repository._run(*args, max_output=64 * 1024 * 1024, timeout=300)
    if len(commit)!=40 or any(c not in '0123456789abcdef' for c in commit):raise ValueError('Expected pinned archive SHA')
    commit=git('rev-parse',commit+'^{commit}').decode().strip()
    manifest=read_manifest(repository,commit)
    dest=Path(dest).expanduser().absolute()
    if os.path.lexists(dest):raise ValueError('Destination must be new')
    for forbidden in [REPO,repository.work_tree,Path(manifest['source'])]:
        if forbidden and dest.resolve().is_relative_to(forbidden.resolve()):raise ValueError('Destination is inside source/archive')
    entries=manifest['entries'];warnings=[];restored=0
    paths={}
    for e in entries:
        rel=str(safe(e['path']))
        if rel in paths or e['kind'] not in ('dir','file','symlink'):raise ValueError('Invalid or duplicate snapshot entry')
        paths[rel]=e
    if '.' not in paths:raise ValueError('Missing root entry')
    for rel,e in paths.items():
        for p in PurePosixPath(rel).parents:
            if str(p) in paths and paths[str(p)]['kind']!='dir':raise ValueError('Non-directory ancestor in snapshot')
    dest.mkdir(parents=True)
    def target(e):return dest/Path(manifest['source']).name if e['path']=='.' and e['kind']!='dir' else dest/str(safe(e['path']))
    for e in entries:
        if e['kind']=='dir':target(e).mkdir(exist_ok=e['path']=='.')
    proc=subprocess.Popen(['git','--git-dir',str(REPO),'cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,env=ENV)
    try:
        for e in entries:
            if e['kind']=='dir':continue
            proc.stdin.write((e['oid']+'\n').encode());proc.stdin.flush()
            header=proc.stdout.readline().split()
            assert len(header)==3 and header[0].decode()==e['oid'] and header[1]==b'blob'
            size=int(header[2]);assert size==e['size']
            h=hashlib.sha256();p=target(e)
            if e['kind']=='symlink':
                data=proc.stdout.read(size);assert len(data)==size;h.update(data)
                assert data==os.fsencode(e['target'])
            else:
                with p.open('xb') as f:
                    remaining=size
                    while remaining:
                        b=proc.stdout.read(min(1024*1024,remaining));assert b
                        h.update(b);f.write(b);remaining-=len(b)
            assert proc.stdout.read(1)==b'\n' and h.hexdigest()==e['sha256']
            restored+=1
        proc.stdin.close();assert proc.wait()==0
    finally:
        if proc.poll() is None:proc.terminate();proc.wait()
        if proc.stdout:proc.stdout.close()
        if proc.stdin and not proc.stdin.closed:proc.stdin.close()
    # Links are created last; no subsequent payload write follows a restored link.
    for e in entries:
        if e['kind']=='symlink':os.symlink(e['target'],target(e))
    lib=ctypes.CDLL('/usr/lib/libSystem.B.dylib',use_errno=True) if sys.platform=='darwin' else None
    for e in reversed(entries):
        p=target(e)
        if lib:
            for k,v in e['xattrs'].items():
                b=base64.b64decode(v);rc=lib.setxattr(os.fsencode(p),os.fsencode(k),b,len(b),0,1)
                if rc:
                    if k=='com.apple.ResourceFork':raise OSError(ctypes.get_errno(),'Resource fork restore failed')
                    warnings.append({'path':e['path'],'xattr':k,'errno':ctypes.get_errno()})
        if e['kind']!='symlink':os.chmod(p,e['mode'])
        os.utime(p,ns=(e['atime_ns'],e['mtime_ns']),follow_symlinks=False)
    # Verify restored filesystem bytes, rather than only the bytes sent to disk.
    for e in entries:
        if e['kind']=='dir':continue
        p=target(e);h=hashlib.sha256()
        if e['kind']=='symlink':h.update(os.fsencode(os.readlink(p)))
        else:
            with p.open('rb') as f:
                for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
        assert h.hexdigest()==e['sha256'],'Restore readback mismatch: '+str(p)
    result={'label':manifest['label'],'commit':commit,'source':manifest['source'],'destination':str(dest),'files':restored,'verified':True,'metadata_warnings':warnings}
    return result

