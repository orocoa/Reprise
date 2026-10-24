#!/usr/bin/env python3
"""Build a local offline macOS candidate from pinned upstream archives.

This is a maintainer command. End users run the resulting `reprise` entry.
No downloads, host dependency copies, installation or publication occur here.
Every output and extraction directory must be new; diagnostics are retained.
"""
import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def inside(root, relative):
    path = root / relative
    if path.resolve() != root and root not in path.resolve().parents:
        raise ValueError('Path escapes its root: ' + str(relative))
    return path


def extract(archive, destination):
    destination.mkdir(parents=True, exist_ok=False)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as stream:
            for item in stream.infolist():
                target = inside(destination, item.filename)
                mode = item.external_attr >> 16
                if (mode & 0o170000) == 0o120000:
                    raise ValueError('Unexpected symlink in ZIP: ' + item.filename)
                stream.extract(item, destination)
                if not item.is_dir() and mode:
                    target.chmod(mode & 0o777)
    else:
        with tarfile.open(archive) as stream:
            members = stream.getmembers()
            for item in members:
                target = inside(destination, item.name)
                if item.issym():
                    inside(destination, target.parent.relative_to(destination) / item.linkname)
                elif item.islnk():
                    inside(destination, item.linkname)
                elif not (item.isfile() or item.isdir()):
                    raise ValueError('Unsupported archive entry: ' + item.name)
            stream.extractall(destination, members=members)


def copy_tree(source, destination):
    shutil.copytree(source, destination, symlinks=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store'))


def copy_selected(source, destination, includes, excludes=()):
    destination.mkdir(parents=True, exist_ok=False)
    for path in sorted(source.rglob('*')):
        relative = path.relative_to(source).as_posix()
        if any(fnmatch.fnmatchcase(relative, pattern) for pattern in excludes):
            continue
        if not any(fnmatch.fnmatchcase(relative, pattern) for pattern in includes):
            continue
        target = destination / relative
        if path.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(os.readlink(path))
        elif path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def inventory(folder):
    result = {}
    for path in sorted(folder.rglob('*')):
        name = path.relative_to(folder).as_posix()
        if path.is_symlink():
            inside(folder, name)  # reject links into the build machine
            if not path.exists():
                raise ValueError('Dangling bundled link: ' + name)
            result[name] = {'symlink': os.readlink(path)}
        elif path.is_file():
            result[name] = {'sha256': digest(path), 'bytes': path.stat().st_size,
                            'mode': oct(path.stat().st_mode & 0o777)}
    return result


def build(cache, output, archive=False, lock_path=None):
    cache = Path(cache).expanduser().resolve(strict=True)
    output = Path(output).expanduser().resolve()
    lock_path = Path(lock_path or ROOT / 'desktop/macos/runtime-lock.json')
    lock = json.loads(lock_path.read_text())
    stage = output.with_name(output.name + '-inputs')
    zip_path = output.with_suffix('.zip')
    if output.exists() or stage.exists() or (archive and zip_path.exists()):
        raise ValueError('Use a new output path; previous builds are retained')
    min_macos = lock.get('min_macos')
    if (not isinstance(min_macos, str) or
            re.fullmatch(r'[0-9]+\.[0-9]+(?:\.[0-9]+)?', min_macos) is None):
        raise ValueError('runtime-lock.json requires min_macos as major.minor[.patch]')
    # Validate all locked inputs before extracting or writing the candidate.
    extra_inputs = lock.get('license_files', []) + lock.get('source_archives', [])
    inputs = [item['archive'] for item in lock['components'].values()] + extra_inputs
    for record in inputs:
        relative = record['cache_file']
        path = inside(cache, relative)
        if not path.is_file() or digest(path) != record['sha256']:
            raise ValueError('Missing or changed pinned input: ' + relative)
    output.mkdir(parents=True)
    stage.mkdir(parents=True)
    for name, component in lock['components'].items():
        extracted = stage / name
        extract(cache / component['archive']['cache_file'], extracted)
        source = inside(extracted, component['archive_top_level'])
        copy_selected(source, inside(output, component['destination']),
                      component['include'], component.get('exclude', ()))
    for item in extra_inputs:
        target = inside(output, item['destination'])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cache / item['cache_file'], target)
    app = output / 'app/reprise'
    app.mkdir(parents=True)
    for path in sorted((ROOT / 'src/reprise').iterdir()):
        if path.is_file() and path.suffix in ('.py', '.mjs'):
            shutil.copy2(path, app / path.name)
    copy_tree(ROOT / 'web', app / 'web')
    copy_tree(ROOT / 'skills/reprise', output / 'skills/reprise')
    for name in ('LICENSE', 'THIRD-PARTY-NOTICES.md'):
        shutil.copy2(ROOT / name, output / name)
    shutil.copy2(ROOT / 'desktop/macos/reprise', output / 'reprise')
    (output / 'reprise').chmod(0o755)
    shutil.copy2(ROOT / 'desktop/macos/Prepare Skill.command', output / 'Prepare Skill.command')
    (output / 'Prepare Skill.command').chmod(0o755)
    skill_entry = output / 'skills/reprise/scripts/reprise'
    if skill_entry.exists():
        skill_entry.chmod(0o755)
    (output / 'Reprise.command').write_text(
        '#!/bin/sh\nset -eu\nROOT=$(CDPATH= cd -- "$(/usr/bin/dirname -- "$0")" && /bin/pwd -P)\n'
        'exec "$ROOT/reprise" "$@"\n')
    (output / 'Reprise.command').chmod(0o755)
    for source, name in (('docs/MACOS-BUNDLE.md', 'START-HERE.md'),):
        shutil.copy2(ROOT / source, output / name)
    manifest = {'schema': 1, 'platform': 'darwin-arm64', 'min_macos': min_macos, 'paths': lock['paths'],
                'capabilities': {'screenshots': True, 'video_recording': False}}
    (output / 'runtime/manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    shutil.copy2(lock_path, output / 'runtime/upstream-lock.json')
    (output / 'LOCAL-CANDIDATE.md').write_text(
        '# Local candidate / 本地候选\n\nNot a public release. No Developer ID signing or '
        'notarization has been established. 本包尚未公开发布，也未完成签名和公证。\n')
    files = inventory(output)
    package_manifest = {'schema': 1, 'release_status': 'LOCAL CANDIDATE',
                        'platform': 'darwin-arm64', 'min_macos': min_macos, 'files': files}
    (output / 'package-manifest.json').write_text(json.dumps(package_manifest, indent=2) + '\n')
    result = {'path': str(output), 'min_macos': min_macos, 'files': len(files),
              'regular_bytes': sum(item.get('bytes', 0) for item in files.values()),
              'manifest_sha256': digest(output / 'package-manifest.json')}
    if archive:
        subprocess.run(['/usr/bin/ditto', '-c', '-k', '--keepParent', '--norsrc',
                        str(output), str(zip_path)], check=True)
        result.update(archive=str(zip_path), archive_bytes=zip_path.stat().st_size,
                      archive_sha256=digest(zip_path))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--zip', action='store_true')
    args = parser.parse_args()
    print(json.dumps(build(args.cache, args.output, args.zip), indent=2))
