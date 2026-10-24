#!/usr/bin/env python3
"""Build source-compatible Agent Skills; host Python/Git are still required."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def source_skill_instructions(body):
    """Ship the canonical source Skill instructions."""
    return body


def build(destination, profile='standard', local_candidate=False):
    if profile not in ('standard', 'workbuddy'):
        raise ValueError('Unknown Skill profile: ' + str(profile))
    destination = Path(destination).expanduser().resolve()
    files = {}
    skill = ROOT / 'skills' / 'reprise'
    for path in sorted(skill.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            files[path.relative_to(skill).as_posix()] = path.read_bytes()
    files['SKILL.md'] = source_skill_instructions(files['SKILL.md'].decode('utf-8')).encode('utf-8')
    for path in sorted((ROOT / 'src' / 'reprise').iterdir()):
        if path.is_file() and path.suffix in ('.py', '.mjs'):
            files['assets/runtime/reprise/' + path.name] = path.read_bytes()
    for path in sorted((ROOT / 'web').rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.name != '.DS_Store' and path.suffix != '.pyc':
            files['assets/runtime/reprise/web/' + path.relative_to(ROOT / 'web').as_posix()] = path.read_bytes()
    for name in ('LICENSE', 'THIRD-PARTY-NOTICES.md'):
        files[name] = (ROOT / name).read_bytes()
    version = (ROOT / 'src/reprise/__init__.py').read_text().split("__version__ = ")[1].strip().strip("'\"")
    source_files = {name: hashlib.sha256(value).hexdigest() for name, value in files.items()
                    if name.startswith('assets/runtime/')}
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    status = subprocess.run(['git', 'status', '--porcelain=v1', '--untracked-files=normal'],
                            cwd=ROOT, capture_output=True, check=True).stdout
    provenance = {'version': version, 'source_commit': commit,
                  'source_dirty': bool(status.strip()),
                  'source_status_sha256': hashlib.sha256(status).hexdigest(),
                  'source_tree_sha256': hashlib.sha256(json.dumps(source_files, sort_keys=True).encode()).hexdigest(),
                  'source_tree_scope': 'packaged canonical runtime and web files; paths prefixed assets/runtime/',
                  'scope': 'canonical local source, including uncommitted changes; no user state',
                  'files': [{'path': name.removeprefix('assets/runtime/'), 'sha256': value}
                            for name, value in sorted(source_files.items())]}
    if local_candidate:
        provenance['release_status'] = 'LOCAL CANDIDATE'
        files['LOCAL-CANDIDATE.md'] = (
            '# LOCAL CANDIDATE\n\nReprise ' + version + ' is a local validation build, not a public release.\n'
            'It may include uncommitted source changes. The source commit alone does not identify this package.\n'
            'Use package-manifest.json and assets/runtime/provenance.json for file hashes and source scope.\n'
        ).encode('utf-8')
    files['assets/runtime/provenance.json'] = (json.dumps(provenance, indent=2) + '\n').encode()
    if profile == 'workbuddy':
        # WorkBuddy Open Platform requires these provider-specific metadata keys.
        body = files['SKILL.md'].decode('utf-8')
        body = body.replace('license: MIT\n', 'license: MIT\ndisplay_name: "倒带 / Reprise"\ndisplay_name_en: "Reprise"\ndescription_zh: 打开倒带，保存本地网页稿、按画面找回旧版并取出新副本。\ndescription_en: Open Reprise, save local webpage drafts and recover a chosen version.\nversion: "' + version + '"\nauthor: orocoa\n')
        files['SKILL.md'] = body.encode('utf-8')
    manifest = {'schema': 1, 'version': version, 'profile': profile,
                'files': {name: hashlib.sha256(value).hexdigest() for name, value in sorted(files.items())}}
    if local_candidate:
        manifest['release_status'] = 'LOCAL CANDIDATE'
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
    parser.add_argument('--local-candidate', action='store_true', help='Label this package as a local validation candidate, without changing its version')
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.profile, args.local_candidate), indent=2))
