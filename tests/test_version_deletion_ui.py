"""Opt-in browser coverage of explicit managed-version deletion and its receipts."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import threading
import unittest
import zlib

from reprise.server import LocalServer
from reprise.service import Reprise
from test_runtime import fixture, commit_repo, http_server_command


def version_deletion_fixture(root):
    source = root / 'synthetic-source'
    source.mkdir()
    (source / 'index.html').write_text('<!doctype html><title>First layout</title><h1>First layout</h1>')
    (source / 'shared.txt').write_text('Shared by all retained versions.\n' * 500)
    (source / 'large-content.bin').write_bytes(bytes(range(256)) * 800)
    app = Reprise(root / 'data')
    project = app.projects.add(str(source), 'Synthetic website versions', 'folder')
    first = app.projects.snapshot(project['id'], 'First layout')
    # A second full state with identical bytes makes a zero-exclusive-content case.
    stat = (source / 'index.html').stat()
    os.utime(source / 'index.html', ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    second = app.projects.snapshot(project['id'], 'Same layout, later file time')
    (source / 'index.html').write_text('<!doctype html><title>Current layout</title><h1>Current layout</h1>')
    (source / 'large-content.bin').write_bytes(b'Current retained content.\n' * 400)
    third = app.projects.snapshot(project['id'], 'Current layout')
    def chunk(kind, body):
        return struct.pack('!I', len(body)) + kind + body + struct.pack('!I', zlib.crc32(kind + body) & 0xffffffff)
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!IIBBBBB', 160, 100, 8, 2, 0, 0, 0)) +
           chunk(b'IDAT', zlib.compress((b'\0' + b'\x40\x89\xad' * 160) * 100)) + chunk(b'IEND', b''))
    image = root / 'synthetic-preview.png'
    image.write_bytes(png)
    app.evidence.manual(app.projects.repository(project['id']), project['id'],
                        {'sha': first['sha'], 'path': str(image), 'kind': 'image', 'title': 'Synthetic first-version evidence'})
    app.projects.save_recipe(project['id'], {'adapter': 'static-web', 'root': '.', 'readiness': {'path': '/'}}, third['sha'])
    git_repo = commit_repo(root / 'read-only-git')
    git_project = app.projects.add(str(git_repo.work_tree), 'Read-only Git example')
    env_source = root / 'environment-source'
    env_source.mkdir()
    (env_source / 'index.html').write_text('<!doctype html><h1>Rebuilt environment</h1>')
    (env_source / 'requirements.txt').write_text('# synthetic install, no network\n')
    env_project = app.projects.add(str(env_source), 'Synthetic environment', 'folder')
    env_version = app.projects.snapshot(env_project['id'], 'Rebuildable site')
    app.projects.save_recipe(env_project['id'], {'adapter': 'command-web', 'root': '.',
        'environment': {'outputs': ['node_modules'], 'inputs': ['requirements.txt'], 'tools': ['python3']},
        'commands': {'install': [[sys.executable, '-c', "from pathlib import Path; p=Path('node_modules'); p.mkdir(exist_ok=True); (p/'synthetic.txt').write_text('rebuildable output '*1000)"]], 'start': http_server_command()},
        'readiness': {'path': '/', 'timeout_ms': 15000}}, env_version['sha'])
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    values = {'root': str(root), 'source': str(source), 'project': project['id'], 'git_project': git_project['id'],
              'first': first['sha'], 'second': second['sha'], 'retained': third['sha'], 'source_hashes': hashes,
              'environment_project': env_project['id'], 'environment_sha': env_version['sha']}
    (root / 'fixture.json').write_text(json.dumps(values, indent=2))
    return app, values


@unittest.skipUnless(os.environ.get('REPRISE_BROWSER_TESTS') == '1', 'browser tests opt in')
class VersionDeletionBrowserTests(unittest.TestCase):
    def test_selection_zero_exclusive_review_deletion_and_retained_preview(self):
        root = fixture('version-deletion-ui')
        app, values = version_deletion_fixture(root)
        server = LocalServer(('127.0.0.1', 0), app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run([os.environ['REPRISE_NODE'], str(Path(__file__).with_name('version_deletion_acceptance.mjs')),
                                     'http://127.0.0.1:%s/' % server.server_port, str(root / 'fixture.json')],
                                    capture_output=True, text=True, timeout=150)
            (root / 'browser.log').write_text(result.stdout + '\n' + result.stderr)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(values['source_hashes'], {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(values['source']).iterdir()})
        finally:
            for runtime in app.runtime_list():
                if runtime.get('running'):
                    app.runtimes.stop(runtime['id'])
            server.shutdown()
            server.server_close()
            thread.join(2)
            app.close()
