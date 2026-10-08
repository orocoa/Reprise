#!/usr/bin/env python3
"""Create new, retained local Git fixtures. Never operates on existing repositories."""
import argparse
import datetime
import json
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--output', default=str(root / 'work' / ('examples-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))))
args = parser.parse_args()
output = Path(args.output).resolve()
output.mkdir(parents=True, exist_ok=False)
projects = []
for name in ('static-web', 'web-game', 'python-cli'):
    path = output / name
    shutil.copytree(root / 'examples' / name, path)
    def git(*args):
        return subprocess.check_output(['git', '-C', str(path), *args], stderr=subprocess.PIPE).decode().strip()
    git('init', '--initial-branch=main')
    git('config', 'user.name', 'Reprise Example')
    git('config', 'user.email', 'example@reprise.local')
    git('add', '.')
    git('commit', '-m', 'Initial ' + name)
    first = git('rev-parse', 'HEAD')
    if name == 'web-game':
        file = path / 'index.html'; file.write_text(file.read_text().replace("ctx.fillStyle='#e9ac61'", "ctx.fillStyle='#89d4be'").replace('x=140,y=210', 'x=220,y=210'))
    elif name == 'static-web':
        file = path / 'index.html'; file.write_text(file.read_text().replace('每个版本，', '每次改变，').replace('background:#c84f2d', 'background:#24786f'))
    else:
        file = path / 'main.py'; file.write_text(file.read_text().replace("'Hello, '", "'Welcome, '"))
    git('add', '.'); git('commit', '-m', 'Improve ' + name)
    projects.append({'name': name, 'path': str(path), 'base': first, 'head': git('rev-parse', 'HEAD')})
(output / 'manifest.json').write_text(json.dumps(projects, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'output': str(output), 'projects': projects}, ensure_ascii=False, indent=2))
