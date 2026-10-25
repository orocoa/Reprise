#!/usr/bin/env python3
"""Build and smoke-test offline distributions; retain every test environment."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ASSETS = tuple(str(p.relative_to(ROOT / 'web')) for p in sorted((ROOT / 'web').rglob('*')) if p.is_file())
CANDIDATE_DOCS = frozenset({
    'ARCHITECTURE.md', 'RECIPES.md', 'GIT-GRAPH.md', 'PRIVACY.md',
    'BACKUP-AND-MIGRATION.md', 'AGENT-SKILL.md', 'VERSION-LIFECYCLE.md',
    'RELEASE-CHECKLIST.md', 'implementation-contract.md', 'VALIDATION.md',
    'QUICKSTART.md', 'FAQ.md', 'ROADMAP.md', 'USER-GUIDE.zh-CN.md',
    'REFERENCE.zh-CN.md', 'REFERENCE.en.md', 'WORKSPACE-TASKS.md', 'PRODUCT-DIRECTION.md',
    'FEATURES.md', 'FEATURES.en.md', 'FOLDER-IMPORTS.md',
})
PUBLIC_SITE_TYPES = frozenset({'.md', '.json', '.css', '.js', '.html', '.svg',
                               '.png', '.jpg', '.webp', '.webm', '.mp4', '.vtt', '.zip'})


def public_site_file(relative):
    path = Path(relative)
    return (relative.startswith('site/') and path.suffix in PUBLIC_SITE_TYPES
            and not any(part.startswith('.') for part in path.parts)
            and (relative.startswith(('site/content/', 'site/assets/'))
                 or relative in ('site/README.md', 'site/PUBLISH-CHECKLIST.md',
                                 'site/metadata.json', 'site/recovery-demo.json')))


def candidate_documents(source):
    """Export a declared documentation surface without copying internal notebooks."""
    target = source / 'docs'
    target.mkdir()
    policy = {'schema': 1, 'release_status': 'LOCAL CANDIDATE',
              'policy': 'Only declared user/developer documents are exported; originals stay unchanged.',
              'allowlist': sorted(CANDIDATE_DOCS), 'included': [], 'omitted': []}
    for path in sorted((ROOT / 'docs').rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT / 'docs').as_posix()
        original = path.read_bytes()
        row = {'path': 'docs/' + relative, 'source_sha256': hashlib.sha256(original).hexdigest()}
        if relative not in CANDIDATE_DOCS and not public_site_file(relative):
            row['reason'] = 'Outside the explicit public-document allowlist; internal material is retained at source.'
            policy['omitted'].append(row)
            continue
        if public_site_file(relative) and path.suffix not in ('.md', '.json', '.css', '.js', '.html', '.svg', '.vtt'):
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(original)
            row.update(export_sha256=row['source_sha256'], transformations=[])
            policy['included'].append(row)
            continue
        content = original.decode('utf-8')
        changes = []
        if relative == 'VALIDATION.md':
            content = ('# Reproduce validation for this local candidate\n\n'
                       'Historical internal reports and screenshots are not included in this source package. '
                       'Their omission does not assert that a new package has passed those historical checks.\n\n'
                       'Run `PYTHONPATH=src python3 -m unittest discover -s tests -v` for the core regressions. '
                       'Run `node --test tests/*.test.cjs` for the Node contracts. Browser tests opt in with '
                       '`REPRISE_BROWSER_TESTS=1` and require an explicitly available browser/runtime.\n\n'
                       'Use `python3 scripts/check_distribution.py --local-candidate` for a new retained '
                       'installation check when building from a Git source checkout. This command needs '
                       'the documented offline Python build tools. A source archive alone has no Git identity.\n\n'
                       'See [release checks](RELEASE-CHECKLIST.md), [Git graph contracts](GIT-GRAPH.md), '
                       'and [the source export policy](../SOURCE-EXPORT-POLICY.json). Report the actual '
                       'platform, source hashes, passes, failures and skipped checks for each new run.\n')
            changes.append('Replace private historical validation log with reproducible verification instructions.')
        elif relative == 'BACKUP-AND-MIGRATION.md':
            content = re.sub(r'^## 本轮验收要求\n.*?(?=^## )', '', content, flags=re.MULTILINE | re.DOTALL)
            content = re.sub(r'^## 最终验收[^\n]*\n.*\Z', '', content, flags=re.MULTILINE | re.DOTALL)
            changes.append('Omit internal implementation/acceptance history; retain user workflow and limitations.')
        elif relative == 'RELEASE-CHECKLIST.md':
            content = '\n'.join(line for line in content.split('\n')
                                if not line.startswith(('已有多组 PersonalWeb demo', '本次本机审计的基准')))
            changes.append('Omit private project anecdotes and unavailable local report locations.')
        if changes and relative != 'VALIDATION.md':
            content = content.rstrip() + ('\n\n> Source-package note: internal acceptance notes and local '
                'evidence locations are omitted. This document does not substitute for validation '
                'of the exact candidate you installed.\n')
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding='utf-8')
        row.update(export_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(), transformations=changes)
        policy['included'].append(row)
    return policy


def audit_export_text(files):
    """Check every UTF-8 payload, including provenance; never exempt source receipts."""
    findings, scanned = [], 0
    home = re.compile(r'/(?:Users|home)/([A-Za-z0-9_.-]+)/')
    # A real deep link starts with an identifier/route. Do not mistake a scanner's
    # own regex alternative ("thread://|...") for an exported conversation link.
    private_chat = re.compile(r'''(?:thread|codex)://[A-Za-z0-9][^\s)'"\\|]*''')
    private_link = re.compile(r'\]\((?:\.\./)*(?:work|outputs?)/[^)]+\)')
    dated_evidence = re.compile(r'work/(?:test-artifacts|qa|visual-references)/[^\s`)]*[0-9]{8}')
    for name, data in sorted(files.items()):
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            continue
        scanned += 1
        for number, line in enumerate(text.splitlines(), 1):
            reasons = []
            if any(match.group(1).lower() not in ('you', 'user', 'username', 'example') for match in home.finditer(line)):
                reasons.append('machine-specific home path')
            if private_chat.search(line):
                reasons.append('private chat link')
            if name.endswith('.md') and (private_link.search(line) or dated_evidence.search(line)):
                reasons.append('unavailable private evidence reference')
            if reasons:
                findings.append({'path': name, 'line': number, 'reasons': reasons})
    return {'status': 'passed' if not findings else 'failed', 'utf8_files_scanned': scanned,
            'provenance_included_in_scan': True, 'findings': findings}


def audit_archive(path):
    if path.suffix == '.whl':
        with zipfile.ZipFile(path) as archive:
            files = {name: archive.read(name) for name in archive.namelist() if not name.endswith('/')}
    else:
        with tarfile.open(path) as archive:
            files = {member.name: archive.extractfile(member).read() for member in archive.getmembers() if member.isfile()}
    return audit_export_text(files)


def clean_environment():
    env = dict(os.environ)
    for name in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONUSERBASE', 'PYTHONNOUSERSITE'):
        env.pop(name, None)
    env.update(PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1',
               PIP_CONFIG_FILE=os.devnull, PYTHONUNBUFFERED='1')
    return env


def command(argv, cwd, log, env=None):
    with log.open('wb') as stream:
        result = subprocess.run([str(arg) for arg in argv], cwd=str(cwd),
                                env=env or clean_environment(), stdout=stream,
                                stderr=subprocess.STDOUT, timeout=180)
    if result.returncode:
        raise RuntimeError('Command failed (%s); see %s' % (result.returncode, log))


def build(source, output, kind, log):
    output.mkdir()
    code = ('import setuptools.build_meta as backend, sys; '
            'print(backend.build_%s(sys.argv[1]))' % kind)
    command([sys.executable, '-c', code, output], source, log)
    suffix = '*.whl' if kind == 'wheel' else '*.tar.gz'
    files = list(output.glob(suffix))
    if len(files) != 1:
        raise RuntimeError('Expected one %s in %s' % (kind, output))
    return files[0]


def check_wheel(wheel, expected):
    with zipfile.ZipFile(wheel) as archive:
        for name, digest in expected.items():
            actual = hashlib.sha256(archive.read('reprise/web/' + name)).hexdigest()
            if actual != digest:
                raise AssertionError('Wheel asset differs from canonical web/' + name)
        if 'reprise/browser_worker.mjs' not in archive.namelist():
            raise AssertionError('Wheel lacks browser worker')
        for notice in ('LICENSE', 'THIRD-PARTY-NOTICES.md'):
            bundled = [name for name in archive.namelist()
                       if '.dist-info/' in name and name.endswith('/' + notice)]
            if len(bundled) != 1 or archive.read(bundled[0]) != (ROOT / notice).read_bytes():
                raise AssertionError('Wheel lacks the canonical license notice: ' + notice)


def unpack_sdist(archive_path, target):
    target.mkdir()
    with tarfile.open(archive_path) as archive:
        members = archive.getmembers()
        for member in members:
            destination = (target / member.name).resolve()
            if target.resolve() not in destination.parents or member.issym() or member.islnk():
                raise ValueError('Unexpected source archive entry: ' + member.name)
        if hasattr(tarfile, 'data_filter'):
            archive.extractall(target, filter='data')
        else:
            archive.extractall(target)
    roots = list(target.iterdir())
    if len(roots) != 1:
        raise AssertionError('Source archive must have one root')
    source = roots[0]
    for name in ('run.py', 'package.json', 'README.md', 'MANIFEST.in',
                 'docs/RECIPES.md', 'examples/command-web.recipe.json',
                 'scripts/import_legacy_evidence.py', 'scripts/check_distribution.py',
                 'scripts/start_workbench.py', 'Reprise.command'):
        if not (source / name).is_file():
            raise AssertionError('Source archive lacks ' + name)
    return source


def smoke_install(wheel, case, mode, expected, caller):
    case.mkdir()
    env = clean_environment()
    if mode == 'venv':
        prefix = case / 'venv'
        command([sys.executable, '-m', 'venv', prefix], caller, case / 'venv.log', env)
        python = prefix / 'bin/python'
        command([python, '-m', 'pip', 'install', '--no-index', '--no-deps', wheel],
                caller, case / 'install.log', env)
    else:
        prefix = case / 'userbase'
        env['PYTHONUSERBASE'] = str(prefix)
        python = Path(sys.executable)
        command([python, '-m', 'pip', 'install', '--user', '--ignore-installed', '--no-index', '--no-deps', wheel],
                caller, case / 'install.log', env)
    executable = prefix / 'bin/reprise'
    command([executable, '--help'], caller, case / 'cli-help.log', env)
    command([python, '-m', 'reprise', '--help'], caller, case / 'module-help.log', env)
    probe = ('import json,reprise,reprise.server; '
             'print(json.dumps({"package":reprise.__file__,"web":str(reprise.server.WEB)}))')
    command([python, '-c', probe], caller, case / 'package-location.json', env)
    locations = json.loads((case / 'package-location.json').read_text())
    for name in ('package', 'web'):
        if prefix.resolve() not in Path(locations[name]).resolve().parents:
            raise AssertionError('%s loaded outside isolated install: %s' % (name, locations[name]))
    data = case / 'data'
    requests = {}
    with (case / 'server.log').open('wb') as log:
        process = subprocess.Popen([str(executable), '--data', str(data), 'serve', '--port', '0'],
                                   cwd=str(caller), env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 15
            while not (data / 'server.json').is_file():
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('Server did not start; see ' + str(case / 'server.log'))
                time.sleep(.05)
            url = json.loads((data / 'server.json').read_text())['url']
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for route in ('/', *('/' + name for name in expected if name != 'index.html'), '/api/health', '/api/bootstrap'):
                with opener.open(url.rstrip('/') + route, timeout=10) as response:
                    content = response.read()
                    requests[route] = {'status': response.status, 'bytes': len(content)}
                    if response.status != 200:
                        raise AssertionError('%s returned %s' % (route, response.status))
                if route == '/' or route[1:] in expected:
                    filename = 'index.html' if route == '/' else route[1:]
                    digest = hashlib.sha256(content).hexdigest()
                    requests[route]['sha256'] = digest
                    if digest != expected[filename]:
                        raise AssertionError('Served wrong asset: ' + route)
                elif route == '/api/health' and not json.loads(content)['ok']:
                    raise AssertionError('Unhealthy server')
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=10)
    return {'mode': mode, 'wheel': str(wheel), 'locations': locations,
            'requests': requests, 'artifacts': str(case)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'work/test-artifacts',
                        help='Parent for a new retained test directory')
    parser.add_argument('--local-candidate', action='store_true',
                        help='Label build artifacts as local candidates without changing package versions')
    args = parser.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = args.output.expanduser().resolve() / ('distribution-' + stamp + '-' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True)
    report = {'status': 'running', 'python': sys.executable, 'artifacts': str(output), 'cases': []}
    try:
        import setuptools
        import wheel  # noqa: F401: validate offline build prerequisites
        if int(setuptools.__version__.split('.')[0]) < 61:
            raise RuntimeError('Build checks require setuptools >= 61; installed ' + setuptools.__version__)
        if sys.prefix != sys.base_prefix:
            raise RuntimeError('Run with a base Python interpreter so --user installation can be checked.')
        source = output / 'source'
        source.mkdir()
        for name in ('pyproject.toml', 'MANIFEST.in', 'README.md', 'CHANGELOG.md', 'AGENTS.md',
                     'LICENSE', 'THIRD-PARTY-NOTICES.md', 'run.py', 'package.json', 'Reprise.command'):
            shutil.copy2(ROOT / name, source / name)
        for path in sorted(ROOT.glob('README*.md')):
            if path.name != 'README.md':
                shutil.copy2(path, source / path.name)
        if (ROOT / 'CONTRIBUTING.md').is_file():
            shutil.copy2(ROOT / 'CONTRIBUTING.md', source / 'CONTRIBUTING.md')
        for name in ('src', 'web', 'tests', 'examples', 'docs', 'scripts', 'skills'):
            if args.local_candidate and name == 'docs':
                continue
            shutil.copytree(ROOT / name, source / name,
                            ignore=shutil.ignore_patterns('__pycache__', '*.egg-info', '*.pyc', '.DS_Store'))
        export_policy = candidate_documents(source) if args.local_candidate else None
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                capture_output=True, text=True, check=True).stdout.strip()
        status = subprocess.run(['git', 'status', '--porcelain=v1', '--untracked-files=normal'],
                                cwd=ROOT, capture_output=True, check=True).stdout
        if args.local_candidate:
            notice = ('# LOCAL CANDIDATE\n\nThis is a local validation build, not a public release. '
                      'It includes the copied working-tree source, which may differ from its recorded Git commit. '
                      'See SOURCE-PROVENANCE.json for the exact build-input hashes.\n\n')
            (output / 'LOCAL-CANDIDATE.md').write_text(notice)
            (source / 'README.md').write_text(notice + (source / 'README.md').read_text())
        # This manifest identifies the frozen inputs, not just their possibly dirty base commit.
        # It intentionally excludes itself and build-generated files created later.
        with (source / 'MANIFEST.in').open('a') as stream:
            stream.write('\ninclude SOURCE-PROVENANCE.json\n')
            if args.local_candidate:
                stream.write('include SOURCE-EXPORT-POLICY.json\n')
        if export_policy is not None:
            policy_payload = json.dumps(export_policy, ensure_ascii=False, indent=2) + '\n'
            (source / 'SOURCE-EXPORT-POLICY.json').write_text(policy_payload)
            (output / 'SOURCE-EXPORT-POLICY.json').write_text(policy_payload)
        inputs = {str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in sorted(source.rglob('*')) if path.is_file()}
        provenance = {'source_commit': commit, 'source_dirty': bool(status.strip()),
                      'source_status_sha256': hashlib.sha256(status).hexdigest(),
                      'source_tree_sha256': hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(),
                      'scope': 'frozen distribution inputs, excluding this manifest and later build outputs',
                      'files': inputs,
                      'packaging_overlays': ['MANIFEST.in: include SOURCE-PROVENANCE.json']}
        if args.local_candidate:
            provenance['release_status'] = 'LOCAL CANDIDATE'
            provenance['packaging_overlays'].append('README.md: prepend LOCAL CANDIDATE notice')
            provenance['packaging_overlays'].append('docs/: explicit allowlist and documented internal-evidence omissions; see SOURCE-EXPORT-POLICY.json')
            report['release_status'] = 'LOCAL CANDIDATE'
        payload = json.dumps(provenance, ensure_ascii=False, indent=2) + '\n'
        (output / 'SOURCE-PROVENANCE.json').write_text(payload)
        (source / 'SOURCE-PROVENANCE.json').write_text(payload)
        report['source_provenance'] = str(output / 'SOURCE-PROVENANCE.json')
        if args.local_candidate:
            audit = audit_export_text({str(path.relative_to(source)): path.read_bytes()
                                       for path in source.rglob('*') if path.is_file()})
            report['source_export_audit'] = audit
            (output / 'source-export-audit.json').write_text(json.dumps(audit, indent=2) + '\n')
            if audit['status'] != 'passed':
                raise RuntimeError('Candidate source export contains private references; see source-export-audit.json')
        caller = output / 'outside-source'
        caller.mkdir()
        expected = {name: hashlib.sha256((source / 'web' / name).read_bytes()).hexdigest() for name in ASSETS}
        direct = build(source, output / 'wheel', 'wheel', output / 'build-wheel.log')
        archive = build(source, output / 'sdist', 'sdist', output / 'build-sdist.log')
        unpacked = unpack_sdist(archive, output / 'unpacked-sdist')
        rebuilt = build(unpacked, output / 'sdist-wheel', 'wheel', output / 'build-sdist-wheel.log')
        if args.local_candidate:
            report['archive_export_audits'] = {}
            for label, artifact in (('wheel', direct), ('sdist', archive), ('sdist-wheel', rebuilt)):
                audit = audit_archive(artifact)
                report['archive_export_audits'][label] = audit
                if audit['status'] != 'passed':
                    raise RuntimeError('Candidate %s contains private references; see report.json' % label)
        for label, artifact in (('wheel', direct), ('sdist', rebuilt)):
            check_wheel(artifact, expected)
            for mode in ('venv', 'user'):
                print('Checking %s → %s' % (label, mode), flush=True)
                report['cases'].append(smoke_install(artifact, output / (label + '-' + mode), mode, expected, caller))
        report['status'] = 'passed'
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print('Retained distribution checks: ' + str(output), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
