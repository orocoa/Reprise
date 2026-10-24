#!/usr/bin/env python3
"""Create three synthetic website drafts using an already installed Reprise.

Python standard library only. The destination must not exist. By default this
only saves versions. --with-previews explicitly allows Reprise to serve each
saved draft locally and capture it using existing Node.js, Playwright and Chromium.
It never restores, deletes, installs dependencies, or touches real projects.
"""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys


DRAFTS = (
    ('初稿', 'First draft', 'Keep the first idea.', '#fbf3e8', '#a34030', '50%'),
    ('第二稿', 'Second draft', 'Make the direction clear.', '#eef4ff', '#285fc9', '24px'),
    ('当前稿', 'Current draft', 'Keep every step in view.', '#edf5ec', '#33754b', '90px 20px'),
)


def page(title, headline, paper, accent, radius):
    return ('''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reprise recovery sample — ''' + html.escape(title) + '''</title>
<style>*{box-sizing:border-box}body{margin:0;background:''' + paper + ''';color:#172b24;
font-family:system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:60px}
header{display:flex;justify-content:space-between;font-size:16px}section{display:grid;
grid-template-columns:1.5fr 1fr;align-items:center;gap:40px;min-height:460px}
h1{font-size:72px;line-height:1.05;letter-spacing:-.055em;margin:24px 0}
p{font-size:19px;line-height:1.7;max-width:520px}.shape{height:270px;background:''' + accent + ''';
border-radius:''' + radius + ''';display:grid;place-items:center;color:white;font-size:28px}
footer{font-size:15px}@media(max-width:650px){main{padding:28px}section{grid-template-columns:1fr;
padding:30px 0}h1{font-size:48px}.shape{height:180px}}</style>
<main><header><strong>Website recovery sample</strong><span>''' + html.escape(title) + '''</span></header>
<section><div><h1>''' + html.escape(headline) + '''</h1><p>This synthetic website has three saved drafts.
Find the first one, compare its files, and recover index.html into a new folder.</p></div>
<div class="shape">''' + html.escape(title) + '''</div></section>
<footer>Reprise tutorial sample. No personal data or external assets.</footer></main></html>\n''').encode('utf-8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def run_command(argv, destination, env, name, timeout=120):
    """Keep the command and its output even when it fails or cannot start."""
    log = destination / 'commands' / (name + '.json')
    record = dict(argv=argv, command=shlex.join(argv), returncode=None, stdout='', stderr='')
    try:
        result = subprocess.run(argv, cwd=str(destination), env=env,
                                capture_output=True, text=True, timeout=timeout)
        record.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
    except (OSError, subprocess.SubprocessError) as error:
        record['error'] = str(error)
        for field in ('stdout', 'stderr'):
            output = getattr(error, field, '') or ''
            record[field] = output.decode('utf-8', errors='replace') if isinstance(output, bytes) else output
    value = None
    if record['stdout']:
        try:
            value = json.loads(record['stdout'])
            if not isinstance(value, dict):
                raise ValueError('Expected a JSON object from Reprise')
        except ValueError as error:
            record['error'] = 'Invalid Reprise response: ' + str(error)
    if record['returncode'] == 0 and value is None:
        record.setdefault('error', 'Reprise returned no JSON result')
    write_json(log, record)
    return value, record, str(log)


def capture_preview(command, destination, data, env, project, version, number, recipe_file):
    sha = version['sha']
    result = dict(sha=sha, title=version['title'], status='failed', images=[], errors=[], command_logs=[])
    for operation, arguments in (
            ('recipe', [project, str(recipe_file), '--sha', sha]),
            ('capture', [project, '--sha', sha])):
        argv = command + ['--data', str(data), operation] + arguments
        # Capture owns its browser/runtime timeout and cleanup. Killing the outer
        # CLI on a second timeout would bypass that cleanup.
        value, record, log = run_command(argv, destination, env, '%s-%s' % (operation, number),
                                        timeout=None if operation == 'capture' else 120)
        result['command_logs'].append(log)
        if record.get('error') or record['returncode'] != 0 or not value or value.get('status') in ('failed', 'cancelled'):
            result['errors'].append(operation + ' failed; see ' + log)
            # Failed captures can still include useful evidence diagnostics.
            if operation != 'capture' or not isinstance(value, dict):
                return result
        if operation == 'capture':
            capture = value.get('result') if isinstance(value, dict) else None
            if not isinstance(capture, dict):
                result['errors'].append('No capture result; see ' + log)
                return result
            result.update(evidence_id=capture.get('id'), evidence_record=capture.get('record_path'),
                          browser_logs=capture.get('browser_logs', []))
            result['errors'].extend(capture.get('errors', []))
            for item in capture.get('items', []):
                if item.get('diagnostic') or item.get('media_type') != 'image/png':
                    continue
                path = Path(item.get('path', ''))
                if (capture.get('sha') != sha or item.get('sha') != sha or item.get('side') != 'after'
                        or item.get('missing') or item.get('error')):
                    result['errors'].append('Image is missing or is not bound to the requested version')
                    continue
                try:
                    if not path.is_file() or digest(path) != item.get('content_sha256'):
                        raise ValueError('Image content does not match its capture record')
                except (OSError, ValueError) as error:
                    result['errors'].append(str(error))
                    continue
                result['images'].append({key: item[key] for key in ('sha', 'path', 'content_sha256', 'capture_id') if key in item})
            if (capture.get('status') == 'complete' and capture.get('source') == 'automatic'
                    and result['images'] and not result['errors']):
                result['status'] = 'complete'
            elif not result['errors']:
                result['errors'].append('Capture did not produce a complete automatic preview')
    return result


def prepare(destination, entry=None, cli=None, with_previews=False):
    destination = Path(destination).expanduser().resolve()
    if destination.exists():
        raise ValueError('Destination already exists. Choose a new path; existing files are retained.')
    command = [str(Path(cli).expanduser().resolve())] if cli else [sys.executable, str(Path(entry).expanduser().resolve())]
    if not Path(command[-1]).is_file():
        raise ValueError('Installed Reprise entry was not found: ' + command[-1])
    destination.mkdir(parents=True)
    source, data = destination / 'source', destination / 'data'
    expected = destination / 'expected'
    source.mkdir(); expected.mkdir(); (destination / 'commands').mkdir()
    versions = []
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    for number, (zh, en, headline, paper, accent, radius) in enumerate(DRAFTS, 1):
        content = page(en, headline, paper, accent, radius)
        (source / 'index.html').write_bytes(content)
        (source / 'notes.txt').write_text(en + '\n' + headline + '\n', encoding='utf-8')
        (expected / ('draft-%s.html' % number)).write_bytes(content)
        argv = command + ['--data', str(data), 'save', str(source), '--name', 'Website recovery demo', '--title', zh]
        saved, record, log = run_command(argv, destination, env, 'save-%s' % number)
        if record.get('error') or record['returncode'] != 0:
            raise RuntimeError('Reprise save failed; retained logs: ' + str(destination / 'commands'))
        try:
            versions.append(dict(title=zh, title_en=en, sha=saved['result']['sha'], index_sha256=digest(source / 'index.html')))
            project = saved['project_id']
        except (KeyError, TypeError):
            raise RuntimeError('Reprise save returned no version identity; retained log: ' + log) from None
    if (source / '.git').exists():
        raise RuntimeError('Unexpected Git metadata in the source folder')
    summary = dict(schema=1, status='prepared', sample_only=True, project_id=project,
                   source=str(source), data=str(data), versions=versions,
                   source_current_sha256=digest(source / 'index.html'),
                   open_command=shlex.join(command + ['--data', str(data), 'open', str(source), '--folder', '--no-browser']),
                   restore_target=str(destination / 'restored-first-draft'),
                   restore_command=shlex.join(command + ['--data', str(data), 'restore', project, '--sha', versions[0]['sha'], '--path', 'index.html', '--to', str(destination / 'restored-first-draft')]),
                   source_git_initialized=False, restore_executed=False, deletion_executed=False,
                   file_versions=dict(status='complete', saved=len(versions)),
                   previews=dict(requested=with_previews, status='pending' if with_previews else 'not_requested', results=[]))
    write_json(destination / 'summary.json', summary)
    if with_previews:
        recipe_file = destination / 'preview.recipe.json'
        write_json(recipe_file, dict(schema=1, adapter='static-web', root='.', network='local',
            readiness=dict(path='/', selector='h1', timeout_ms=5000),
            captures=[dict(id='tutorial', route='/', viewport=dict(width=1280, height=800, scale=1))]))
        summary['previews']['recipe'] = str(recipe_file)
        summary['previews']['status'] = 'running'
        for number, version in enumerate(versions, 1):
            summary['previews']['results'].append(capture_preview(
                command, destination, data, env, project, version, number, recipe_file))
            write_json(destination / 'summary.json', summary)
        complete = sum(result['status'] == 'complete' for result in summary['previews']['results'])
        summary['previews'].update(complete=complete,
            status='complete' if complete == len(versions) else 'partial' if complete else 'failed')
        write_json(destination / 'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--to', required=True, help='New directory for synthetic source, saved versions, and logs')
    parser.add_argument('--with-previews', action='store_true',
                        help='Explicitly allow local serving and browser capture of all three saved drafts; uses existing capture dependencies')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--entry', help='Extracted Skill: reprise/scripts/reprise.py')
    group.add_argument('--cli', help='Installed reprise executable, for example a venv bin/reprise')
    args = parser.parse_args()
    try:
        summary = prepare(args.to, args.entry, args.cli, args.with_previews)
        if args.with_previews and summary['previews']['status'] != 'complete':
            parser.exit(1, 'All three file versions were saved, but previews are incomplete. See summary.json and commands/ in ' + str(Path(args.to).expanduser().resolve()) + '\n')
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
