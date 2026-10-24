#!/usr/bin/env python3
"""Demonstrate version selection, local preview, joint deletion and verified recovery.

Only a new synthetic fixture and its managed Reprise versions are modified.
Original fixture inputs, source folders, previews and command receipts are kept.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect_source(source):
    return {str(path.relative_to(source)): {'sha256': digest(path.read_bytes()),
            'mode': path.stat().st_mode, 'mtime_ns': path.stat().st_mtime_ns}
            for path in sorted(source.rglob('*')) if path.is_file()}


def run_demo(destination, entry):
    destination = Path(destination).expanduser().absolute()
    entry = Path(entry).expanduser().resolve(strict=True)
    destination.mkdir(parents=True, exist_ok=False)
    source, other = destination / 'sample-project', destination / 'other-project'
    source.mkdir()
    other.mkdir()
    data, commands, inputs = destination / 'reprise-data', destination / 'commands', destination / 'inputs'
    commands.mkdir()
    inputs.mkdir()
    started = time.monotonic()
    steps, active, previews, versions = [], [], [], []

    def call(label, *arguments):
        argv = [sys.executable, str(entry), '--data', str(data), *map(str, arguments)]
        tick = time.monotonic()
        try:
            process = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=120)
        except (subprocess.TimeoutExpired, OSError) as error:
            def decode(value):
                return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value or ''
            record = {'argv': argv, 'returncode': None, 'timed_out': isinstance(error, subprocess.TimeoutExpired),
                      'stdout': decode(getattr(error, 'stdout', None)), 'stderr': decode(getattr(error, 'stderr', None)),
                      'error': str(error), 'elapsed_seconds': round(time.monotonic() - tick, 3)}
            write_json(commands / (label + '.json'), record)
            steps.append({'step': label, 'failed': True})
            raise
        record = {'argv': argv, 'returncode': process.returncode, 'stdout': process.stdout,
                  'stderr': process.stderr, 'elapsed_seconds': round(time.monotonic() - tick, 3)}
        write_json(commands / (label + '.json'), record)
        steps.append({'step': label, 'elapsed_seconds': record['elapsed_seconds']})
        print(label, flush=True)
        if process.returncode:
            raise RuntimeError('CLI failed at %s; output retained in %s' % (label, commands))
        value = json.loads(process.stdout)
        if isinstance(value, dict) and value.get('status') in ('failed', 'cancelled', 'partial'):
            raise RuntimeError('Incomplete CLI result at ' + label)
        return value

    def result(value):
        return value['result'] if isinstance(value, dict) and 'result' in value else value

    try:
        payloads = {name: hashlib.shake_256(name.encode()).digest(size) for name, size in
                    [('S', 65536), ('A', 524288), ('J', 786432), ('X', 524288), ('Y', 524288), ('B', 524288)]}
        recipe = destination / 'preview-recipe.json'
        write_json(recipe, {'schema': 1, 'adapter': 'static-web', 'root': '.', 'network': 'local'})
        states = []
        for number, labels in enumerate((('A', 'J', 'X'), ('B', 'J', 'Y'), ('B', 'S', 'S')), 1):
            html = ('<!doctype html><html lang="en"><meta charset="utf-8">'
                    '<title>Reprise lifecycle — version %d</title>'
                    '<h1>Version %d</h1><p>Synthetic local fixture. Confirm this exact version before deletion.</p>'
                    '<p>The source files remain. Only selected managed snapshots are deleted.</p></html>'
                    % (number, number)).encode('utf-8')
            values = {'index.html': html, 'shared.bin': payloads['S'], 'draft.bin': payloads[labels[0]],
                      'joint.bin': payloads[labels[1]], 'cross.bin': payloads[labels[2]]}
            saved_input = inputs / ('version-%d' % number)
            saved_input.mkdir()
            for name, value in values.items():
                (source / name).write_bytes(value)
                (saved_input / name).write_bytes(value)
            saved = call('save-version-%d' % number, 'save', source, '--name', 'Version lifecycle sample',
                         '--title', 'Version %d' % number)
            project, sha = saved['project_id'], result(saved)['sha']
            versions.append(sha)
            states.append(values)
        for name, label in (('shared.bin', 'S'), ('protected.bin', 'X')):
            (other / name).write_bytes(payloads[label])
        other_saved = call('save-other-project', 'save', other, '--name', 'Shared asset keeper', '--title', 'Keep shared content')
        other_project, other_sha = other_saved['project_id'], result(other_saved)['sha']
        source_before, other_before = inspect_source(source), inspect_source(other)

        # A real loopback HTTP preview, pinned to each selected historical ID.
        # No screenshot/browser-render claim is made by this stdlib-only demo.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for number, sha in enumerate(versions[:2], 1):
            call('save-preview-recipe-%d' % number, 'recipe', project, recipe, '--sha', sha)
            runtime = result(call('run-version-%d' % number, 'run', project, '--sha', sha))
            active.append(runtime['id'])
            if runtime['sha'] != sha:
                raise RuntimeError('Preview was not bound to the selected version')
            with opener.open(runtime['url'], timeout=10) as response:
                served = response.read()
            (destination / ('served-version-%d.html' % number)).write_bytes(served)
            if served != states[number - 1]['index.html']:
                raise RuntimeError('Preview bytes do not match the selected historical page')
            previews.append({'sha': sha, 'runtime_id': runtime['id'], 'url': runtime['url'],
                             'http_readback_verified': True, 'sha256': digest(served),
                             'browser_render_verified': False, 'screenshot_captured': False})
            call('stop-version-%d' % number, 'stop', runtime['id'])
            active.remove(runtime['id'])

        single = [result(call('plan-single-%d' % number, 'version-delete-plan', project, '--sha', sha))
                  for number, sha in enumerate(versions[:2], 1)]
        joint = result(call('plan-joint', 'version-delete-plan', project,
                            '--sha', versions[0], '--sha', versions[1]))
        expected = sum(len(payloads[key]) for key in ('A', 'J', 'Y')) + sum(len(state['index.html']) for state in states[:2])
        if joint['unique_content_bytes'] != expected:
            raise RuntimeError('Joint content accounting does not match the fixture')
        if joint['unique_content_bytes'] <= sum(plan['unique_content_bytes'] for plan in single):
            raise RuntimeError('Joint-only shared content was not accounted for')
        before = call('storage-before-delete', 'storage')
        receipt = result(call('delete-selected-versions', 'version-delete', project, '--plan', joint['id'], '--confirm'))
        if receipt['status'] != 'verified' or receipt['source_files_removed'] or not receipt['verification']['ok']:
            raise RuntimeError('Deletion did not return a verified, source-preserving receipt')
        history = call('retained-history', 'history', project)
        if [row['sha'] for row in history['commits']] != [versions[2]]:
            raise RuntimeError('Retained history does not match the explicit selection')
        restored = destination / 'restored-retained-version'
        other_restored = destination / 'restored-other-project'
        call('restore-retained-version', 'restore', project, '--sha', versions[2], '--to', restored)
        call('restore-other-project', 'restore', other_project, '--sha', other_sha, '--to', other_restored)
        for name, value in states[2].items():
            if (restored / name).read_bytes() != value:
                raise RuntimeError('Retained version readback failed: ' + name)
        if (other_restored / 'protected.bin').read_bytes() != payloads['X']:
            raise RuntimeError('Cross-project shared content was lost')
        if inspect_source(source) != source_before or inspect_source(other) != other_before:
            raise RuntimeError('A source folder changed during version deletion')
        after = call('storage-after-restore', 'storage')
        summary = {'schema': 1, 'status': 'passed', 'sample_only': True,
                   'elapsed_seconds': round(time.monotonic() - started, 3), 'steps': steps,
                   'project_id': project, 'versions_before': versions, 'retained_sha': versions[2],
                   'other_project_id': other_project, 'other_project_sha': other_sha,
                   'previews': previews, 'single_plans': single, 'joint_plan': joint,
                   'expected_joint_content_bytes': expected, 'deletion_receipt': receipt,
                   'source_files_removed': False, 'source_content_and_metadata_unchanged': True,
                   'retained_version_readback_verified': True, 'other_project_readback_verified': True,
                   'storage_before_delete': before, 'storage_after_restore': after,
                   'limitations': ['Synthetic sample; no real user project or snapshot was deleted.',
                       'HTTP byte readback is not a browser screenshot or JavaScript interaction check.',
                       'Static preview needs no downloaded dependencies; dependency rebuild is not tested here.',
                       'Fixture inputs, runtime materializations and restored copies are intentionally retained.',
                       'Logical unreferenced content, repository bytes, allocated blocks and volume free space differ.',
                       'Whole-data-directory usage may increase because this demo retains previews and recoveries.']}
        write_json(destination / 'summary.json', summary)
        return summary
    except Exception as error:
        write_json(destination / 'failure.json', {'status': 'failed', 'error': str(error), 'steps': steps,
                                                 'versions': versions, 'previews': previews})
        raise
    finally:
        for rid in active:
            try:
                call('cleanup-stop-' + rid, 'stop', rid)
            except Exception as error:
                write_json(destination / ('cleanup-failed-' + rid + '.json'), {'runtime_id': rid, 'error': str(error)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--to', required=True, help='New directory for all synthetic inputs and retained evidence')
    parser.add_argument('--entry', default=str(ROOT / 'run.py'), help='Source or installed Skill Python CLI entry')
    args = parser.parse_args()
    try:
        summary = run_demo(args.to, args.entry)
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps({key: summary[key] for key in ('status', 'elapsed_seconds', 'retained_sha',
                     'source_files_removed', 'retained_version_readback_verified')}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
