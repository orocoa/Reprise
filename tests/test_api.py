import base64
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from reprise.server import LocalServer
from reprise.service import Reprise
from test_git import git


class APITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        git(self.source, 'init', '-b', 'main')
        git(self.source, 'config', 'user.name', 'Test')
        git(self.source, 'config', 'user.email', 'test@example.invalid')
        self.app = Reprise(self.root / 'state')
        self.server = LocalServer(('127.0.0.1', 0), self.app)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.token = self.server.token
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.app.close()
        self.tmp.cleanup()

    def request(self, method, path, body=None, headers=None, authorized=True, raw=False):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        request_headers = dict(headers or {})
        if body is not None:
            body = json.dumps(body).encode('utf-8')
            request_headers.setdefault('Content-Type', 'application/json')
        if authorized and method not in ('GET', 'HEAD'):
            request_headers.setdefault('X-Reprise-Token', self.token)
            request_headers.setdefault('Origin', self.origin)
        conn.request(method, path, body=body, headers=request_headers)
        response = conn.getresponse()
        data = response.read()
        status, response_headers = response.status, dict(response.getheaders())
        conn.close()
        if not raw and data and 'application/json' in response_headers.get('Content-Type', ''):
            data = json.loads(data)
        return status, response_headers, data

    def commit(self, files):
        for name, data in files.items():
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(data)
        git(self.source, 'add', '.')
        git(self.source, 'commit', '-m', 'fixture')
        return git(self.source, 'rev-parse', 'HEAD')

    def import_project(self):
        status, _, project = self.request('POST', '/api/projects', {'path': str(self.source)})
        self.assertEqual(status, 201, project)
        return project

    def test_all_workspace_assets_are_available_and_notes_are_revision_bound(self):
        for path in ('/', '/app.js', '/styles.css', '/locale.js', '/shell.js', '/paper-grid.css', '/workspace-grid.css', '/browse-motion.js'):
            status, headers, data = self.request('GET', path, raw=True)
            self.assertEqual(status, 200, path)
            self.assertTrue(data)
        from test_ai import NOTES
        sha = self.commit({'index.html': '<h1>Fixture</h1>'})
        project = self.import_project()
        prefix = '/api/projects/' + project['id']
        self.assertEqual(self.request('PUT', prefix + '/notes', {'sha': sha, 'localizations': NOTES}, authorized=False)[0], 403)
        self.assertEqual(self.request('PUT', prefix + '/notes', {'sha': sha, 'localizations': {'zh': NOTES['zh']}})[0], 400)
        self.assertEqual(self.request('PUT', prefix + '/notes', {'sha': sha[:9], 'localizations': NOTES})[0], 200)
        status, _, version = self.request('GET', prefix + '/versions/' + sha)
        self.assertEqual(version['notes']['localizations'], NOTES)
        self.assertEqual(version['commit']['sha'], sha)
        self.assertFalse(version['recipe_approved'])

    def test_host_origin_token_and_content_type_boundaries(self):
        status, _, _ = self.request('GET', '/api/bootstrap', headers={'Host': 'evil.invalid'})
        self.assertEqual(status, 403)
        status, _, bootstrap = self.request('GET', '/api/bootstrap')
        self.assertEqual(status, 200)
        self.assertEqual(bootstrap['token'], self.token)
        status, _, _ = self.request('POST', '/api/projects', {'path': str(self.source)}, authorized=False)
        self.assertEqual(status, 403)
        status, _, _ = self.request('POST', '/api/projects', {'path': str(self.source)}, headers={'Origin': 'http://evil.invalid'})
        self.assertEqual(status, 403)
        status, _, _ = self.request('POST', '/api/projects', {'path': str(self.source)}, headers={'Content-Type': 'text/plain'})
        self.assertEqual(status, 415)
        self.assertEqual(self.app.projects.records(), [])

    def test_import_refresh_unknown_and_empty_history(self):
        empty = self.import_project()
        status, _, history = self.request('GET', '/api/projects/' + empty['id'] + '/history')
        self.assertEqual(status, 200)
        self.assertEqual(history['commits'], [])
        sha = self.commit({'unknown.custom': 'content'})
        status, _, project = self.request('GET', '/api/projects/' + empty['id'])
        self.assertEqual(status, 200)
        self.assertEqual(project['head'], sha)
        status, _, version = self.request('GET', '/api/projects/' + empty['id'] + '/versions/' + sha)
        self.assertEqual(status, 200, version)
        self.assertEqual(version['diff']['counts']['added'], 1)
        self.assertEqual(version['detection']['kind'], 'unknown')
        status, _, result = self.request('POST', '/api/projects/' + empty['id'] + '/run', {'sha': sha})
        self.assertEqual(status, 400)
        self.assertTrue(result['error'])

    def test_merge_api_uses_actual_parent_and_allows_second_parent(self):
        self.commit({'common': 'one'})
        git(self.source, 'checkout', '-b', 'feature')
        feature = self.commit({'feature': 'one'})
        git(self.source, 'checkout', 'main')
        main = self.commit({'main': 'one'})
        git(self.source, 'merge', '--no-ff', 'feature', '-m', 'merge')
        merge = git(self.source, 'rev-parse', 'HEAD')
        project = self.import_project()
        prefix = '/api/projects/' + project['id']
        status, _, version = self.request('GET', prefix + '/versions/' + merge)
        self.assertEqual(status, 200, version)
        self.assertEqual(version['commit']['parents'], [main, feature])
        self.assertEqual(version['diff']['base'], main)
        status, _, diff = self.request('GET', prefix + '/diff?target=' + merge + '&base=' + feature)
        self.assertEqual(status, 200)
        self.assertEqual(diff['base'], feature)
        self.assertEqual([f['path'] for f in diff['files']], ['main'])

    def test_committed_recipe_read_does_not_authorize_command(self):
        recipe = {'adapter': 'command-web', 'commands': {'start': ['touch', 'MUST_NOT_EXIST']}}
        sha = self.commit({'package.json': '{"scripts":{"start":"touch MUST_NOT_EXIST"}}', '.reprise.json': json.dumps(recipe)})
        project = self.import_project()
        self.assertFalse(project['recipe_approved'])
        status, _, result = self.request('POST', '/api/projects/' + project['id'] + '/run', {'sha': sha})
        self.assertEqual(status, 400, result)
        self.assertFalse((self.source / 'MUST_NOT_EXIST').exists())
        self.assertEqual(self.app.runtimes.list(), [])
        status, _, result = self.request('PUT', '/api/projects/' + project['id'] + '/recipe', {'recipe': recipe})
        self.assertEqual(status, 200, result)
        self.assertTrue(result['recipe_approved'])
        self.assertEqual(self.app.runtimes.list(), [])

    def test_manual_evidence_is_copied_bound_to_sha_and_served_with_ranges(self):
        sha = self.commit({'opaque.dat': 'unknown'})
        project = self.import_project()
        payload = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+kL9sAAAAASUVORK5CYII=')
        original = self.root / 'manual.png'
        original.write_bytes(payload)
        status, _, evidence = self.request('POST', '/api/projects/' + project['id'] + '/evidence/manual',
                                            {'sha': sha, 'path': str(original), 'kind': 'image', 'title': 'Manual proof'})
        self.assertEqual(status, 201, evidence)
        self.assertEqual(original.read_bytes(), payload)
        self.assertEqual(evidence['source'], 'manual')
        self.assertEqual(evidence['sha'], sha)
        self.assertEqual(evidence['verification'], 'user-supplied')
        url = evidence['items'][0]['url']
        status, headers, data = self.request('GET', url, headers={'Range': 'bytes=2-10'}, raw=True)
        self.assertEqual(status, 206)
        self.assertEqual(data, payload[2:11])
        self.assertEqual(headers['Content-Range'], 'bytes 2-10/' + str(len(payload)))
        self.assertEqual(headers['Content-Type'], 'image/png')
        etag = headers['ETag']
        status, _, data = self.request('GET', url, headers={'Range': 'bytes=-5'}, raw=True)
        self.assertEqual(status, 206)
        self.assertEqual(data, payload[-5:])
        status, headers, data = self.request('HEAD', url, headers={'Range': 'bytes=0-3'}, raw=True)
        self.assertEqual(status, 206)
        self.assertEqual(headers['Content-Length'], '4')
        self.assertEqual(data, b'')
        status, _, data = self.request('GET', url, headers={'If-None-Match': etag}, raw=True)
        self.assertEqual(status, 304)
        self.assertEqual(data, b'')
        status, headers, data = self.request('GET', url, headers={'Range': 'bytes=9999-'}, raw=True)
        self.assertEqual(status, 416)
        status, _, _ = self.request('GET', '/artifacts/../projects.json')
        self.assertEqual(status, 404)
        status, _, _ = self.request('GET', url.rsplit('/', 1)[0] + '/record.json')
        self.assertEqual(status, 404)


if __name__ == '__main__':
    unittest.main()
