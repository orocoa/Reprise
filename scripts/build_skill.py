#!/usr/bin/env python3
"""Build self-contained Agent Skills from canonical source, with no local state."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build(destination, profile='standard'):
    destination = Path(destination).expanduser().resolve()
    files = {}
    skill = ROOT / 'skills' / 'reprise'
    for path in sorted(skill.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            files[path.relative_to(skill).as_posix()] = path.read_bytes()
    for path in sorted((ROOT / 'src' / 'reprise').iterdir()):
        if path.is_file() and path.suffix in ('.py', '.mjs'):
            files['assets/runtime/reprise/' + path.name] = path.read_bytes()
    for path in sorted((ROOT / 'web').rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.name != '.DS_Store' and path.suffix != '.pyc':
            files['assets/runtime/reprise/web/' + path.relative_to(ROOT / 'web').as_posix()] = path.read_bytes()
    for name in ('LICENSE', 'THIRD-PARTY-NOTICES.md'):
        files[name] = (ROOT / name).read_bytes()
    version = (ROOT / 'src/reprise/__init__.py').read_text().split("__version__ = ")[1].strip().strip("'\"")
    if profile == 'workbuddy':
        # WorkBuddy Open Platform requires these provider-specific metadata keys.
        body = files['SKILL.md'].decode('utf-8')
        body = body.replace('license: MIT\n', 'license: MIT\ndescription_zh: 查看 Git 历史、预览旧版并恢复到新目录。\ndescription_en: Browse Git history, preview revisions and recover into new folders.\nversion: "' + version + '"\nauthor: orocoa\n')
        files['SKILL.md'] = body.encode('utf-8')
    manifest = {'schema': 1, 'version': version, 'profile': profile,
                'files': {name: hashlib.sha256(value).hexdigest() for name, value in sorted(files.items())}}
    files['package-manifest.json'] = (json.dumps(manifest, ensure_ascii=True, indent=2) + '\n').encode()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream, zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, value in sorted(files.items()):
            entry = zipfile.ZipInfo('reprise/' + name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, value)
    return {'path': str(destination), 'profile': profile, 'version': version,
            'files': len(files), 'bytes': destination.stat().st_size,
            'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--profile', choices=('standard', 'workbuddy'), default='standard')
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.profile), indent=2))
