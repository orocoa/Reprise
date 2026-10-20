#!/usr/bin/env python3
"""Build and smoke-test offline distributions; retain every test environment."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
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
                 'scripts/import_legacy_evidence.py', 'scripts/check_distribution.py'):
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
                     'LICENSE', 'THIRD-PARTY-NOTICES.md', 'run.py', 'package.json'):
            shutil.copy2(ROOT / name, source / name)
        for name in ('src', 'web', 'tests', 'examples', 'docs', 'scripts', 'skills'):
            shutil.copytree(ROOT / name, source / name,
                            ignore=shutil.ignore_patterns('__pycache__', '*.egg-info', '*.pyc', '.DS_Store'))
        caller = output / 'outside-source'
        caller.mkdir()
        expected = {name: hashlib.sha256((source / 'web' / name).read_bytes()).hexdigest() for name in ASSETS}
        direct = build(source, output / 'wheel', 'wheel', output / 'build-wheel.log')
        archive = build(source, output / 'sdist', 'sdist', output / 'build-sdist.log')
        unpacked = unpack_sdist(archive, output / 'unpacked-sdist')
        rebuilt = build(unpacked, output / 'sdist-wheel', 'wheel', output / 'build-sdist-wheel.log')
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
