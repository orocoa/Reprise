#!/usr/bin/env python3
"""Run a small, reproducible folder-version workflow using the real CLI.

Only synthetic files in a new caller-selected directory are used. Nothing is
deleted, no server is started, and every command/output is retained on failure.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def run_demo(destination, entry):
    destination = Path(destination).expanduser().absolute()
    entry = Path(entry).expanduser().resolve(strict=True)
    # Refuse reuse, including dangling symlinks. All inputs are made below this
    # fresh directory; never infer an existing user's project from the cwd.
    destination.mkdir(parents=True, exist_ok=False)
    source = destination / 'sample-folder'
    source.mkdir()
    data = destination / 'reprise-data'
    commands = destination / 'commands'
    commands.mkdir()
    started = time.monotonic()
    steps = []

    def call(label, *arguments):
        argv = [sys.executable, str(entry), '--data', str(data), *map(str, arguments)]
        tick = time.monotonic()
        try:
            result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=120)
        except (subprocess.TimeoutExpired, OSError) as error:
            def text(value):
                return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value or ''
            record = dict(argv=argv, returncode=None,
                          elapsed_seconds=round(time.monotonic() - tick, 3),
                          timed_out=isinstance(error, subprocess.TimeoutExpired),
                          stdout=text(getattr(error, 'stdout', None)),
                          stderr=text(getattr(error, 'stderr', None)), error=str(error))
            write_json(commands / (label + '.json'), record)
            steps.append(dict(step=label, elapsed_seconds=record['elapsed_seconds'], failed=True))
            raise
        record = dict(argv=argv, returncode=result.returncode,
                      elapsed_seconds=round(time.monotonic() - tick, 3),
                      stdout=result.stdout, stderr=result.stderr)
        write_json(commands / (label + '.json'), record)
        steps.append(dict(step=label, elapsed_seconds=record['elapsed_seconds']))
        print(label, flush=True)
        if result.returncode:
            raise RuntimeError('CLI failed at ' + label + '; retained output: ' + str(commands))
        value = json.loads(result.stdout)
        if isinstance(value, dict) and value.get('status') in ('failed', 'cancelled', 'partial'):
            raise RuntimeError('Incomplete result at ' + label)
        return value

    try:
        first = b'Launch notes\nPublish the first draft.\n'
        second = b'Launch notes\nReview the second draft before publishing.\n'
        shared = b'This exact illustration placeholder is reused.\n' * 1024
        (source / 'draft.txt').write_bytes(first)
        (source / 'illustration.txt').write_bytes(shared)
        (source / 'illustration-copy.txt').write_bytes(shared)
        (source / 'empty-folder').mkdir()
        saved1 = call('01-save-first', 'save', source, '--name', 'Reprise sample', '--title', 'First draft')
        sha1 = saved1['result']['sha']
        project = saved1['project_id']
        (source / 'draft.txt').write_bytes(second)
        saved2 = call('02-save-second', 'save', source, '--title', 'Reviewed draft')
        sha2 = saved2['result']['sha']
        history = call('03-history', 'history', project)
        compared = call('04-compare', 'compare', project, '--base', sha1, '--target', sha2)
        checked = call('05-integrity', 'verify', project, '--sha', sha1)
        preflight = call('06-organize-check', 'organize', project, '--sha', sha2, '--check')
        before = call('07-storage-before-review', 'storage')
        restored = destination / 'restored-first-draft'
        call('08-restore-first-file', 'restore', project, '--sha', sha1, '--path', 'draft.txt', '--to', restored)
        if (restored / 'draft.txt').read_bytes() != first:
            raise RuntimeError('Restored first-draft bytes do not match the original')
        if (source / 'draft.txt').read_bytes() != second or (source / '.git').exists():
            raise RuntimeError('Source folder unexpectedly changed')
        reviewed = call('09-verified-review', 'organize', project, '--sha', sha2)
        plan = call('10-review-details', 'review', reviewed['result']['id'], '--details')
        # Show an explicit choice made only on this synthetic sample. It saves a
        # pending list, not a deletion request for any real user content.
        candidate = next(c for c in plan['candidates'] if c['selectable'])
        selected = call('11-save-choice', 'select', plan['id'], '--path', candidate['path'])
        after = call('12-storage-after-review', 'storage')
        if selected['source_files_removed'] or not (source / candidate['path']).is_file():
            raise RuntimeError('Review unexpectedly removed a source file')
        if len(history['commits']) != 2 or compared['diff']['counts']['total'] != 1:
            raise RuntimeError('Expected two versions with one changed file')
        if saved2['result']['stats']['new_bytes'] != len(second):
            raise RuntimeError('Unchanged duplicate content was stored again')
        summary = dict(schema=1, status='passed', sample_only=True,
            elapsed_seconds=round(time.monotonic() - started, 3), steps=steps,
            project_id=project, versions=[sha1, sha2], changed_files=1,
            restored_file_sha256=hashlib.sha256(first).hexdigest(),
            restored_file_matches_original=True, source_second_draft_unchanged=True,
            source_git_initialized=False, source_files_removed=False,
            snapshot_stats=[saved1['result']['stats'], saved2['result']['stats']],
            integrity=checked['result'], organization_preview=preflight['result'],
            organization_review=reviewed['result'], selected_count=selected['selected_count'],
            storage_before_review=before, storage_after_review=after,
            actual_reclaimed_bytes=0,
            limitations=['Synthetic sample; not a large-directory performance benchmark.',
                         'No originals were removed, so this run did not reclaim space.',
                         'Logical duplicate bytes are not exclusive filesystem blocks.',
                         'Review retains a complete restored copy and increases local storage.',
                         'Integrity and readback do not test application execution or independent media.'])
        write_json(destination / 'summary.json', summary)
        open_command = shlex.join([sys.executable, str(entry), '--data', str(data), 'open', str(source), '--folder', '--no-browser'])
        (destination / 'README-local.txt').write_text(
            'Reprise workflow completed using synthetic files only.\n'
            'Two versions saved; one changed file; first draft restored byte-for-byte.\n'
            'The live second draft and both duplicate files remain. No space was reclaimed.\n'
            'summary.json records timings, content-byte accounting and retained recovery cost.\n'
            'commands/ retains every CLI invocation and output.\n\n'
            'To inspect this sample in the workbench, run:\n' + open_command + '\n'
            'Then open the returned local URL. This script did not start a service.\n', encoding='utf-8')
        return summary
    except Exception as error:
        write_json(destination / 'failure.json', dict(status='failed', error=str(error), steps=steps))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--to', required=True, help='New directory for all synthetic inputs, state and retained results')
    parser.add_argument('--entry', default=str(ROOT / 'run.py'), help='Optional source or installed Skill Python CLI entry')
    args = parser.parse_args()
    try:
        result = run_demo(args.to, args.entry)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps({k: result[k] for k in ('status', 'elapsed_seconds', 'restored_file_matches_original', 'actual_reclaimed_bytes')}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
