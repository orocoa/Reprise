#!/usr/bin/env python3
"""Portable agent entry point; locates its runtime independently of cwd/agent."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

SKILL = Path(__file__).resolve().parents[1]
BUNDLED = SKILL / 'assets' / 'runtime'
SOURCE = SKILL.parents[1] / 'src'
RUNTIME = BUNDLED if (BUNDLED / 'reprise' / '__init__.py').is_file() else SOURCE


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
    manifest = SKILL / 'package-manifest.json'
    checked = 0
    if manifest.is_file():
        try:
            for name, expected in json.loads(manifest.read_text(encoding='utf-8'))['files'].items():
                path = SKILL / name
                if path.is_symlink() or not path.is_file() or path.resolve().is_relative_to(SKILL) is False:
                    errors.append('Missing or unsafe bundled file: ' + name)
                elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    errors.append('Modified bundled file: ' + name)
                checked += 1
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append('Invalid package manifest: ' + str(error))
    print(json.dumps({'ok': not errors, 'python': sys.version.split()[0], 'git': git,
                      'runtime': str(RUNTIME), 'bundled': RUNTIME == BUNDLED,
                      'checked_files': checked, 'errors': errors}, ensure_ascii=True, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    if sys.argv[1:] == ['doctor']:
        sys.exit(doctor())
    if sys.version_info < (3, 9) or sys.platform not in ('darwin', 'linux'):
        sys.exit('Reprise requires Python 3.9+ on macOS/Linux (Windows: use WSL). Run doctor for details.')
    sys.path.insert(0, str(RUNTIME))
    from reprise.cli import main
    sys.exit(main())
