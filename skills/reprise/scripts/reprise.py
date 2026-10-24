#!/usr/bin/env python3
"""Portable agent entry point; locates its runtime independently of cwd/agent."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

SKILL = Path(__file__).resolve().parents[1]
location = SKILL / 'runtime-location.json'
relative = json.loads(location.read_text())['path'] if location.is_file() else 'assets/runtime'
BUNDLED = (SKILL / relative).resolve()
if not BUNDLED.is_relative_to(SKILL):
    raise ValueError('Bundled runtime must be inside this Skill')
SOURCE = SKILL.parents[1] / 'src'
RUNTIME = BUNDLED if (BUNDLED / 'reprise' / '__init__.py').is_file() else SOURCE


def runtime_version():
    """Read the version declaration without importing or executing runtime code."""
    source = ast.parse((RUNTIME / 'reprise' / '__init__.py').read_text(encoding='utf-8'))
    for statement in source.body:
        if (isinstance(statement, ast.Assign) and
                any(isinstance(target, ast.Name) and target.id == '__version__' for target in statement.targets)):
            value = ast.literal_eval(statement.value)
            if isinstance(value, str) and value:
                return value
            break
    raise ValueError('Runtime __version__ must be a literal, non-empty string')


def doctor_requested(arguments):
    """Find the command without treating a --data value as a command name."""
    position = 0
    while position < len(arguments):
        argument = arguments[position]
        if argument == '--data':
            position += 2
        elif argument.startswith('--data='):
            position += 1
        else:
            return argument == 'doctor'
    return False


def doctor_arguments(arguments):
    parser = argparse.ArgumentParser(prog='reprise doctor',
        description='Check the Skill runtime and package without reading or creating a data directory')
    parser.add_argument('command', choices=('doctor',))
    def data_path(value):
        if not value.strip():
            raise argparse.ArgumentTypeError('--data requires a non-empty path')
        return value
    parser.add_argument('--data', type=data_path, help='Accepted for CLI consistency; diagnosis does not access this path')
    return parser.parse_args(arguments)


def doctor():
    errors = []
    if sys.version_info < (3, 9):
        errors.append('Python 3.9+ is required')
    if sys.platform not in ('darwin', 'linux'):
        errors.append('Use macOS, Linux, or WSL; native Windows is not supported')
    if not (RUNTIME / 'reprise' / '__init__.py').is_file():
        errors.append('Runtime missing: extract the entire release ZIP, including assets/')
    git = shutil.which('git')
    if not git:
        errors.append('Git is not on PATH')
    else:
        try:
            subprocess.run([git, '--version'], check=True, capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            errors.append('Git could not run')
    try:
        version = runtime_version()
    except (OSError, ValueError, SyntaxError) as error:
        version = None
        errors.append('Runtime version unavailable: ' + str(error))
    manifest = SKILL / 'package-manifest.json'
    checked = 0
    integrity_scope = 'package-manifest' if manifest.is_file() else ('unverified-bundle' if RUNTIME == BUNDLED else 'source-only')
    if manifest.is_file():
        try:
            files = json.loads(manifest.read_text(encoding='utf-8'))['files']
            if not isinstance(files, dict) or not files:
                raise ValueError('files must be a non-empty object')
            for name, expected in files.items():
                if not isinstance(name, str) or not isinstance(expected, str):
                    raise ValueError('file paths and SHA-256 values must be strings')
                path = SKILL / name
                if path.is_symlink() or not path.is_file() or path.resolve().is_relative_to(SKILL) is False:
                    errors.append('Missing or unsafe bundled file: ' + name)
                elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    errors.append('Modified bundled file: ' + name)
                checked += 1
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append('Invalid package manifest: ' + str(error))
    elif RUNTIME == BUNDLED:
        errors.append('Package manifest missing: bundled files have not been integrity-checked')
    provenance = RUNTIME / 'provenance.json'
    source = {}
    if provenance.is_file():
        try:
            source = json.loads(provenance.read_text(encoding='utf-8'))
            if not isinstance(source, dict):
                raise ValueError('provenance must be an object')
            if source.get('version') != version:
                errors.append('Runtime version differs from package provenance')
        except (OSError, ValueError) as error:
            source = {}
            errors.append('Invalid runtime provenance: ' + str(error))
    print(json.dumps({'ok': not errors, 'python': sys.version.split()[0], 'git': git,
                      'runtime': str(RUNTIME), 'bundled': RUNTIME == BUNDLED,
                      'version': version, 'source_commit': source.get('source_commit'),
                      'source_tree_sha256': source.get('source_tree_sha256'),
                      'integrity_scope': integrity_scope,
                      'package_integrity_verified': integrity_scope == 'package-manifest' and checked > 0 and not errors,
                      'checked_files': checked, 'errors': errors}, ensure_ascii=True, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    if doctor_requested(sys.argv[1:]):
        doctor_arguments(sys.argv[1:])
        sys.exit(doctor())
    if sys.version_info < (3, 9) or sys.platform not in ('darwin', 'linux'):
        sys.exit('Reprise requires Python 3.9+ on macOS/Linux (Windows: use WSL). Run doctor for details.')
    sys.path.insert(0, str(RUNTIME))
    from reprise.cli import main
    sys.exit(main())
