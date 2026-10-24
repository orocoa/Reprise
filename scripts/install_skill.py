#!/usr/bin/env python3
"""Install the source-compatible Skill (host Python/Git required), retaining a backup.

The source Skill reuses host tools; the former complete runtime bundle is withdrawn.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from build_skill import build


def install(destination, output, local_candidate=False):
    destination = Path(destination).expanduser().absolute()
    output = Path(output).expanduser().resolve()
    if destination.is_symlink() or output == destination or destination in output.parents:
        raise ValueError('Use a real Skill directory and a separate retained output folder')
    output.mkdir(parents=True, exist_ok=False)
    package = output / 'reprise.zip'
    build(package, local_candidate=local_candidate)
    with zipfile.ZipFile(package) as archive:
        archive.extractall(output / 'candidate')
    candidate = output / 'candidate/reprise'
    checked = subprocess.run([sys.executable, '-I', str(candidate / 'scripts/reprise.py'), 'doctor'],
                             capture_output=True, text=True, check=True)
    report = json.loads(checked.stdout)
    if not report['ok']:
        raise ValueError('Candidate verification failed')
    if destination.exists():
        shutil.copytree(destination, output / 'previous-skill', symlinks=True)
    else:
        destination.mkdir(parents=True)
    tree = report['source_tree_sha256']
    relative = 'assets/runtimes/' + tree[:20]
    runtime = destination / relative
    if runtime.exists():
        raise ValueError('This runtime is already installed; retained candidate can be reviewed')
    runtime.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(candidate / 'assets/runtime', runtime)
    # Do not overwrite assets/runtime: live services may still read those files.
    for path in candidate.rglob('*'):
        name = path.relative_to(candidate).as_posix()
        if not path.is_file() or name.startswith('assets/runtime/') or name == 'package-manifest.json':
            continue
        target = destination / name
        if target.is_symlink() or any(p.is_symlink() for p in target.parents if destination in (p, *p.parents)):
            raise ValueError('Installed Skill path must not follow symlinks')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    pointer = destination / 'runtime-location.json'
    pointer.write_text(json.dumps({'path': relative}, indent=2)+'\n')
    manifest = json.loads((candidate / 'package-manifest.json').read_text())
    manifest['files'] = {(name.replace('assets/runtime/', relative+'/', 1) if name.startswith('assets/runtime/') else name): value
                         for name, value in manifest['files'].items()}
    manifest['files']['runtime-location.json'] = hashlib.sha256(pointer.read_bytes()).hexdigest()
    (destination / 'package-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    installed = subprocess.run([sys.executable, '-I', str(destination / 'scripts/reprise.py'), 'doctor'],
                               capture_output=True, text=True, check=True)
    result = {'destination': str(destination), 'backup': str(output / 'previous-skill'),
              'runtime': str(runtime), 'verification': json.loads(installed.stdout),
              'existing_runtimes_retained': True, 'user_data_modified': False}
    (output / 'installation.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--local-candidate', action='store_true', help='Keep unreleased status in the installed packet')
    args = parser.parse_args()
    print(json.dumps(install(args.destination, args.output, args.local_candidate), indent=2))
