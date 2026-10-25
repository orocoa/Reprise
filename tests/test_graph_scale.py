"""Real Git objects for the large-history browser contract; no imported sources."""
import hashlib
import subprocess
from pathlib import Path


def scale_repository(root, waves=20, branches=16):
    source = Path(root) / 'source'
    source.mkdir()
    subprocess.run(['git', '-C', str(source), 'init', '-q', '-b', 'main'], check=True)
    html = b'<!doctype html><title>Scale fixture</title><h1>Synthetic large Git history</h1>'
    payload = bytearray(b'blob\nmark :1\ndata %d\n' % len(html) + html + b'\n')
    commits = []

    def commit(ref, parents, title):
        mark = len(commits) + 2
        message = title.encode()
        payload.extend(('commit refs/heads/%s\nmark :%d\n'
                        'committer Reprise Fixture <fixture@example.invalid> %d +0000\n'
                        'data %d\n' % (ref, mark, 1700000000 + mark, len(message))).encode())
        payload.extend(message + b'\n')
        if parents:
            payload.extend(('from :%d\n' % parents[0]).encode())
            for parent in parents[1:]:
                payload.extend(('merge :%d\n' % parent).encode())
        else:
            payload.extend(b'M 100644 :1 index.html\n')
        payload.extend(b'\n')
        commits.append({'mark': mark, 'parents': parents})
        return mark

    main = commit('main', [], 'Initial synthetic page')
    for wave in range(waves):
        tips = []
        for branch in range(branches):
            tip = main
            for step in range(3):
                tip = commit('topic-%02d' % branch, [tip],
                             'Study %02d / branch %02d / change %d' % (wave, branch, step))
            tips.append(tip)
        main = commit('main', [main], 'Main progress %02d' % wave)
        for branch, tip in enumerate(tips):
            main = commit('main', [main, tip], 'Merge study %02d / branch %02d' % (wave, branch))
    marks = Path(root) / 'fast-import-marks.txt'
    result = subprocess.run(['git', '-C', str(source), 'fast-import', '--quiet',
                             '--export-marks=' + str(marks)], input=payload, capture_output=True)
    (Path(root) / 'fast-import.log').write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace'))
    ids = {int(line.split()[0][1:]): line.split()[1] for line in marks.read_text().splitlines()}
    # Populate only this freshly constructed fixture, before Reprise imports it.
    subprocess.run(['git', '-C', str(source), 'read-tree', 'HEAD'], check=True)
    (source / 'index.html').write_bytes(html)
    expected = [{'id': ids[c['mark']], 'parents': [ids[p] for p in c['parents']]} for c in commits]
    return source, expected


def fingerprint(source):
    return {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(source.rglob('*')) if p.is_file()}
