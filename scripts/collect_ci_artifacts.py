#!/usr/bin/env python3
"""Copy purpose-selected CI evidence without truncating or deleting originals."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path

STATUSES = {'success', 'failure', 'cancelled'}
PRUNED = {'.git', '.venv', 'venv', 'env', 'user-site', 'site-packages',
          'node_modules', '__pycache__', '.cache', 'source', 'unpacked-sdist',
          'ci-upload', 'ci-artifact'}
REPORTS = {'report.json', 'SOURCE-PROVENANCE.json', 'source-export-audit.json',
           'SOURCE-EXPORT-POLICY.json', 'package-location.json'}
PACKAGES = {'ci/reprise-skill.zip', 'ci/reprise-workbuddy.zip'}
MEDIA = {'.png', '.jpg', '.jpeg', '.webp', '.webm', '.mp4'}


def collect(root, output, status, include_packages=False):
    if status not in STATUSES:
        raise ValueError('Unknown job status')
    root, output = Path(root).resolve(), Path(output).resolve()
    if output == root or root in output.parents or output in root.parents:
        raise ValueError('Evidence output must be separate from the input tree')
    output.mkdir(parents=True, exist_ok=False)
    selected, candidates, counts, examples = [], [], Counter(), []

    def omit(path, reason):
        counts[reason] += 1
        if len(examples) < 25:
            examples.append({'path': str(path), 'reason': reason})

    for folder, dirs, files in os.walk(root, followlinks=False):
        base = Path(folder)
        dirs[:] = sorted(d for d in dirs if d not in PRUNED and
                         not d.startswith(('.', 'ci-artifacts-')) and not (base / d).is_symlink())
        for name in sorted(files):
            path = base / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink() or not path.is_file():
                omit(relative, 'not a regular file')
                continue
            if relative in PACKAGES and status == 'success' and include_packages:
                kind, order = 'package', 1
            elif path.suffix == '.log':
                kind, order = 'log', 0
            elif name in REPORTS:
                kind, order = 'report', 0
            elif status != 'success' and path.suffix.lower() in MEDIA:
                kind, order = 'failure-media', 2
            else:
                omit(relative, 'outside the evidence allowlist')
                continue
            candidates.append((order, relative, path, kind))

    total = 0
    for _, relative, path, kind in sorted(candidates):
        size = path.stat().st_size
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        copied = 0
        with path.open('rb') as source, target.open('wb') as destination:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                destination.write(chunk)
                digest.update(chunk)
                copied += len(chunk)
        selected.append({'path': relative, 'kind': kind, 'sourceBytes': size,
                         'bytes': copied, 'truncated': False,
                         'sha256': digest.hexdigest()})
        total += copied

    report = {'schema': 1, 'jobStatus': status,
              'sourceCommit': os.environ.get('GITHUB_SHA', ''),
              'runId': os.environ.get('GITHUB_RUN_ID', ''),
              'runnerOS': os.environ.get('RUNNER_OS', ''),
              'payloadBytes': total, 'files': selected,
              'omittedCounts': dict(counts), 'omittedExamples': examples,
              'policy': 'CI evidence only; official releases and rollback packages remain in GitHub Releases. Originals are never modified.'}
    manifest = (json.dumps(report, indent=2) + '\n').encode()
    (output / 'ci-artifact-manifest.json').write_bytes(manifest)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--status', choices=sorted(STATUSES), required=True)
    parser.add_argument('--include-packages', action='store_true')
    args = parser.parse_args()
    report = collect(args.root, args.out, args.status, args.include_packages)
    summary = ('### CI evidence\n\nJob status: %s. Copied %s files, %s bytes in full. '
               'Omitted counts: `%s`.\n\n'
               'No custom size, file-count, truncation or expiry limits. '
               'Superseded artifacts are cleaned only after a verified replacement; '
               'GitHub platform retention still applies. Release downloads are unchanged.\n' %
               (report['jobStatus'], len(report['files']), report['payloadBytes'],
                json.dumps(report['omittedCounts'], sort_keys=True)))
    print(summary, flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write(summary)


if __name__ == '__main__':
    main()
