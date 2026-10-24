import base64
import http.client
import json
import threading
import unittest
from pathlib import Path

from reprise.server import LocalServer
from reprise.service import Reprise
from test_git import git
from test_runtime import fixture


class APITests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('api')
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

    def test_workbench_bootstrap_does_not_create_or_read_legacy_ai_settings(self):
        ai_directory = self.app.directory / 'ai'
        self.assertFalse(ai_directory.exists())
        ai_directory.mkdir()
        settings = ai_directory / 'settings.json'
        settings.write_text('invalid legacy settings must not block drafts')
        before = settings.read_bytes()
        status, _, bootstrap = self.request('GET', '/api/bootstrap?include_projects=0')
        self.assertEqual(status, 200, bootstrap)
        self.assertNotIn('ai', bootstrap)
        self.assertIsNone(self.app._ai)
        self.assertEqual(settings.read_bytes(), before)

    def test_desktop_shutdown_cannot_stop_a_different_service_instance(self):
        status, _, result = self.request('POST', '/api/shutdown', {'instance_id': 'a-previous-service'})
        self.assertEqual(status, 200)
        self.assertEqual(result, {'stopped': False, 'reason': 'different-instance'})
        status, _, health = self.request('GET', '/api/health')
        self.assertEqual(status, 200)
        self.assertEqual(health['instance_id'], self.server.instance_id)
        self.assertTrue(self.thread.is_alive())

    def test_health_reports_fixed_startup_origin_without_a_private_path(self):
        from unittest.mock import patch
        status, _, initial = self.request('GET', '/api/health')
        self.assertEqual(status, 200)
        self.assertRegex(initial['source_id'], r'^[a-f0-9]{64}$')
        self.assertEqual(initial['source_id'], self.server.source_id)
        self.assertNotIn(str(Path(__file__).resolve().parents[1]), json.dumps(initial))
        with patch('reprise.server.service_source_id', return_value='moved-after-startup') as current:
            status, _, later = self.request('GET', '/api/health')
        self.assertEqual(status, 200)
        self.assertEqual(later, initial)
        current.assert_not_called()

    def test_folder_snapshot_files_duplicates_and_selected_recovery(self):
        import time
        folder = self.root / 'ordinary-folder'
        folder.mkdir()
        (folder / 'first.md').write_text('Shared paragraph')
        (folder / 'second.md').write_text('Shared paragraph')
        status, _, project = self.request('POST', '/api/projects', {'path': str(folder), 'kind': 'folder'})
        self.assertEqual(status, 201, project)
        prefix = '/api/projects/' + project['id']
        self.assertEqual(self.request('POST', prefix + '/snapshot', {'title': 'Draft'}, authorized=False)[0], 403)
        status, _, job = self.request('POST', prefix + '/snapshot', {'title': 'Draft'})
        self.assertEqual(status, 202, job)
        while job['status'] in ('queued', 'running', 'cancelling'):
            time.sleep(.02)
            _, _, job = self.request('GET', '/api/jobs/' + job['id'])
        self.assertEqual(job['status'], 'complete', job)
        sha = job['result']['sha']
        status, _, files = self.request('GET', prefix + '/files?sha=' + sha + '&limit=1')
        self.assertEqual(status, 200, files)
        self.assertEqual(files['total'], 2)
        self.assertEqual(files['next_offset'], 1)
        status, _, content = self.request('GET', prefix + '/file-content?sha=' + sha + '&path=first.md')
        self.assertEqual(status, 200, content)
        self.assertEqual(content['text'], 'Shared paragraph')
        self.assertEqual(self.request('GET', prefix + '/file-content?sha=' + sha + '&path=../escape')[0], 400)
        _, _, duplicates = self.request('GET', prefix + '/duplicates?sha=' + sha)
        self.assertEqual(duplicates['total'], 1)
        self.assertEqual(len(duplicates['groups'][0]['paths']), 2)
        _, _, privacy = self.request('GET', '/api/privacy')
        self.assertFalse(privacy['local_operations_upload'])
        self.assertFalse(privacy['local_operations_use_ai'])
        self.assertEqual(self.request('POST', prefix + '/organize', {'sha': sha}, authorized=False)[0], 403)
        status, _, organizing = self.request('POST', prefix + '/organize', {'sha': sha})
        self.assertEqual(status, 202, organizing)
        while organizing['status'] in ('queued', 'running', 'cancelling'):
            time.sleep(.02)
            _, _, organizing = self.request('GET', '/api/jobs/' + organizing['id'])
        self.assertEqual(organizing['status'], 'complete', organizing)
        plan_id = organizing['result']['id']
        _, _, plan = self.request('GET', '/api/organization/' + plan_id)
        self.assertTrue(plan['verification']['readback_verified'])
        self.assertEqual(plan['selected_paths'], [])
        self.assertEqual(self.request('POST', '/api/organization/' + plan_id + '/selection', {'paths': []}, authorized=False)[0], 403)
        self.assertEqual(self.request('POST', '/api/organization/' + plan_id + '/selection', {'paths': []})[0], 200)
        self.assertTrue((folder / 'second.md').exists())
        target = self.root / 'selected-restoration'
        status, _, recovery = self.request('POST', prefix + '/restore', {'sha': sha, 'paths': ['second.md'], 'to': str(target)})
        self.assertEqual(status, 202, recovery)
        while recovery['status'] in ('queued', 'running', 'cancelling'):
            time.sleep(.02)
            _, _, recovery = self.request('GET', '/api/jobs/' + recovery['id'])
        self.assertEqual(recovery['status'], 'complete', recovery)
        self.assertEqual((target / 'second.md').read_text(), 'Shared paragraph')
        self.assertFalse((target / 'first.md').exists())
        self.assertEqual(self.request('POST', prefix + '/restore', {'sha': sha, 'paths': ['../escape'], 'to': str(self.root / 'invalid')})[0], 400)
        self.assertFalse((folder / '.git').exists())

    def test_backup_verify_and_restore_jobs_preserve_offline_history(self):
        import time
        from reprise.backup import create_backup
        data, folder = self.root / 'offline-data', self.root / 'backup-folder'
        folder.mkdir()
        (folder / 'draft.md').write_text('saved before backup')
        offline = Reprise(data)
        try:
            project = offline.projects.add(str(folder), kind='folder')
            version = offline.projects.snapshot(project['id'], 'Saved')
        finally:
            offline.close()
        backup, restored = self.root / 'backup', self.root / 'restored-data'
        create_backup(data, backup)
        data.rename(self.root / 'original-data-unavailable')
        folder.rename(self.root / 'original-source-unavailable')
        def finish(job):
            deadline = time.monotonic() + 10
            while job['status'] in ('queued', 'running', 'cancelling') and time.monotonic() < deadline:
                time.sleep(.02)
                _, _, job = self.request('GET', '/api/jobs/' + job['id'])
            self.assertEqual(job['status'], 'complete', job)
            return job['result']
        for operation, body in [('backup-check', {'backup': str(backup)}),
                                ('data-restore', {'backup': str(backup), 'to': str(restored)})]:
            self.assertEqual(self.request('POST', '/api/' + operation, body, authorized=False)[0], 403)
            status, _, job = self.request('POST', '/api/' + operation, body)
            self.assertEqual(status, 202, job)
            result = finish(job)
            self.assertIn(result['status'], ('verified', 'complete'))
        recovered = Reprise(restored)
        try:
            target = self.root / 'restored-history'
            result = recovered.recovery.create(recovered.projects.repository(project['id']),
                project['id'], version['sha'], 'restore', str(target))
            self.assertEqual((target / 'draft.md').read_text(), 'saved before backup')
            self.assertTrue(result)
        finally:
            recovered.close()
        self.assertFalse(data.exists())
        self.assertFalse(folder.exists())

    def test_recovery_download_is_registered_and_writes_require_local_token(self):
        import io
        import time
        import zipfile
        sha = self.commit({'index.html': '<h1>Exact historical content</h1>'})
        project = self.import_project()
        prefix = '/api/projects/' + project['id']
        self.assertEqual(self.request('POST', prefix + '/export', {'sha': sha}, authorized=False)[0], 403)
        status, _, job = self.request('POST', prefix + '/export', {'sha': sha})
        self.assertEqual(status, 202)
        deadline = time.monotonic() + 10
        while job['status'] in ('queued', 'running') and time.monotonic() < deadline:
            time.sleep(.03)
            job = self.request('GET', '/api/jobs/' + job['id'])[2]
        self.assertEqual(job['status'], 'complete', job)
        status, headers, data = self.request('GET', job['result']['download_url'], raw=True)
        self.assertEqual(status, 200)
        self.assertIn('attachment', headers['Content-Disposition'])
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(archive.read('index.html'), b'<h1>Exact historical content</h1>')
        self.assertEqual(self.request('GET', '/downloads/' + 'g'*32)[0], 404)
        self.assertEqual(self.request('POST', prefix + '/restore', {'sha': sha, 'to': str(self.source / 'nested')})[0], 400)
        self.assertFalse((self.source / 'nested').exists())

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

    def test_workspace_bootstrap_does_not_inspect_other_repositories(self):
        # A moved source should not prevent the launch workspace from obtaining
        # its token, runtime controls and per-record recovery warnings.
        project = self.import_project()
        from reprise.storage import write_json
        records = self.app.projects.records()
        records[0]['path'] = str(self.root / 'unavailable-source')
        write_json(self.app.projects.file, {'schema': 1, 'projects': records})
        status, _, bootstrap = self.request('GET', '/api/bootstrap?include_projects=0')
        self.assertEqual(status, 200)
        self.assertEqual(bootstrap['projects'], [])
        self.assertEqual(bootstrap['token'], self.token)
        self.assertEqual(self.request('GET', '/api/projects/' + project['id'])[0], 400)

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
        private = Path(evidence['items'][0]['path']).parent / 'capture-input.json'
        private.write_text('{"private": "retained input"}')
        for method in ('GET', 'HEAD'):
            status, _, _ = self.request(method, url.rsplit('/', 1)[0] + '/' + private.name)
            self.assertEqual(status, 404)
        self.assertTrue(private.exists(), 'Private diagnostics remain available locally')


    def test_storage_and_integrity_are_explicit_authenticated_jobs(self):
        import time

        def finish(job, expected='complete'):
            deadline = time.monotonic() + 15
            while job['status'] in ('queued', 'running', 'cancelling'):
                self.assertLess(time.monotonic(), deadline, job)
                time.sleep(.02)
                status, _, job = self.request('GET', '/api/jobs/' + job['id'])
                self.assertEqual(status, 200)
            self.assertEqual(job['status'], expected, job)
            return job

        self.assertEqual(self.request('POST', '/api/storage', {}, authorized=False)[0], 403)
        self.assertEqual(self.request('GET', '/api/storage')[0], 404)
        status, _, job = self.request('POST', '/api/storage', {})
        self.assertEqual(status, 202)
        result = finish(job)['result']
        self.assertIsNone(result['reclaimable_bytes'])
        self.assertEqual(result['storage_path'], str(self.app.directory))

        folder = self.root / 'content-to-check'
        folder.mkdir()
        (folder / 'a.txt').write_text('version one')
        project = self.app.projects.add(str(folder), kind='folder')
        first = self.app.projects.snapshot(project['id'], 'one')['sha']
        (folder / 'a.txt').write_text('version two')
        self.app.projects.snapshot(project['id'], 'two')
        endpoint = '/api/projects/' + project['id'] + '/verify'
        self.assertEqual(self.request('POST', endpoint, {'sha': first}, authorized=False)[0], 403)
        status, _, job = self.request('POST', endpoint, {'sha': first})
        self.assertEqual(status, 202)
        self.assertEqual(job['request']['sha'], first)
        result = finish(job)['result']
        self.assertEqual(result['sha'], first)
        self.assertEqual(result['status'], 'verified')
        self.assertEqual((folder / 'a.txt').read_text(), 'version two')

        # A bounded accounting scan remains a usable partial report, rather
        # than becoming a capture failure which hides its counts and warnings.
        from unittest.mock import patch
        with patch('reprise.storage_report._MAX_DEPTH', 1):
            status, _, job = self.request('POST', '/api/storage', {})
            self.assertEqual(status, 202)
            partial = finish(job)
        self.assertEqual(partial['result']['status'], 'partial')
        self.assertTrue(partial['result']['warnings'])
        self.assertNotIn('error', partial)

        from reprise.integrity import IntegrityError
        report = {'status': 'failed', 'sha': first, 'checked_objects': 0,
                  'limitations': ['Library check only'], 'errors': ['Object missing']}
        with patch('reprise.integrity.verify_project', side_effect=IntegrityError('Object missing', report)):
            status, _, job = self.request('POST', endpoint, {'sha': first})
            self.assertEqual(status, 202)
            failed = finish(job, 'failed')
        self.assertEqual(failed['result']['sha'], first)
        self.assertEqual(failed['result']['status'], 'failed')
        self.assertEqual(failed['result']['errors'], ['Object missing'])


    def test_directory_migration_relinks_same_identity_and_has_authenticated_empty_safe_entry(self):
        import time
        def finish(job, expected='complete'):
            deadline = time.monotonic() + 20
            while job['status'] in ('queued', 'running', 'cancelling'):
                self.assertLess(time.monotonic(), deadline)
                time.sleep(.02)
                _, _, job = self.request('GET', '/api/jobs/' + job['id'])
            self.assertEqual(job['status'], expected, job)
            return job
        folder = self.root / 'relocate-source'; folder.mkdir()
        (folder / 'draft.txt').write_text('saved draft')
        project = self.app.projects.add(str(folder), kind='folder')
        sha = self.app.projects.snapshot(project['id'])['sha']
        target = self.root / 'relocated'
        endpoint = '/api/projects/' + project['id']
        self.assertEqual(self.request('POST', endpoint + '/migrate', {'to': str(target)}, authorized=False)[0], 403)
        status, _, job = self.request('POST', endpoint + '/migrate', {'to': str(target)})
        self.assertEqual(status, 202); finish(job)
        self.assertEqual(self.app.projects.record(project['id'])['path'], str(target))
        self.assertTrue((folder / 'draft.txt').is_file())
        self.assertEqual(self.app.projects.repository(project['id']).resolve('HEAD'), sha)
        self.assertEqual(self.app.projects.add(str(target), kind='folder')['id'], project['id'])
        _, _, info = self.request('GET', '/api/transfer')
        self.assertTrue(info['backup_requires_offline'])
        self.assertIn('backup', info['backup_command_prefix'])
        self.assertEqual(self.request('POST', '/api/backup-check', {'backup': '/missing'}, authorized=False)[0], 403)
        self.assertEqual(self.request('POST', '/api/data-restore', {'backup': '/missing', 'to': str(self.app.directory / 'nested')})[0], 400)


if __name__ == '__main__':
    unittest.main()
