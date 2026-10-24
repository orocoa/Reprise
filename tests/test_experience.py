"""Ordinary draft tasks preserve content, exact media identity, and consent."""
from contextlib import contextmanager
import http.client
import json
import threading
import time
import unittest
from unittest.mock import patch

from reprise.cancellation import Cancelled
from reprise.experience import capture_draft, queue_capture, visual_history, plan_draft_preview
from reprise.server import LocalServer
from reprise.service import Reprise
from test_runtime import fixture


class ExperienceTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('draft-experience')
        self.source = self.root / 'webpage'
        self.source.mkdir()
        (self.source / 'index.html').write_text('<h1>First saved draft</h1>')
        self.app = Reprise(self.root / 'data')
        self.project = self.app.projects.add(
            str(self.source), 'Drafts', kind='folder')['id']
        self.first = self.app.projects.snapshot(self.project, 'First')['sha']

    def tearDown(self):
        self.app.close()

    def wait(self, job):
        deadline = time.monotonic() + 10
        while job['status'] in ('queued', 'running', 'cancelling'):
            self.assertLess(time.monotonic(), deadline, job)
            time.sleep(.01)
            job = self.app.jobs.get(job['id'])
        self.assertEqual(job['status'], 'complete', job)
        return job['result']

    def second_version(self):
        (self.source / 'index.html').write_text('<h1>Second saved draft</h1>')
        return self.app.projects.snapshot(self.project, 'Second')['sha']

    def test_quick_capture_saves_exact_static_recipe_before_capture(self):
        self.second_version()
        (self.source / 'index.html').write_text('Unsaved work must remain')

        def capture(repository, project, sha, recipe, **options):
            self.assertEqual(project, self.project)
            self.assertEqual(sha, self.first)
            self.assertEqual(repository.blob(sha, 'index.html'),
                             b'<h1>First saved draft</h1>')
            saved = self.app.projects.record(project)['version_recipes'][sha]['recipe']
            self.assertEqual(saved, recipe)
            self.assertEqual(recipe['adapter'], 'static-web')
            self.assertEqual(recipe['commands'], {})
            self.assertEqual(recipe['network'], 'local')
            self.assertTrue(options['approved'])
            return {'id': 'synthetic', 'sha': sha, 'status': 'complete'}

        with patch.object(self.app.captures, 'capture', side_effect=capture):
            result = self.wait(queue_capture(
                self.app, self.project, {'sha': self.first}))
        self.assertEqual(result['sha'], self.first)
        self.assertEqual((self.source / 'index.html').read_text(),
                         'Unsaved work must remain')
        self.assertFalse((self.source / '.git').exists())

    def test_existing_exact_recipe_is_not_overwritten_by_quick_capture(self):
        custom = {'schema': 1, 'adapter': 'static-web', 'root': '.',
                  'captures': [{'id': 'custom', 'route': '/?mode=review',
                                'viewport': {'width': 800, 'height': 600}}]}
        self.app.projects.save_recipe(self.project, custom, self.first)
        before = (self.app.directory / 'projects.json').read_bytes()
        with patch.object(self.app.captures, 'capture') as capture:
            result = capture_draft(self.app, self.project, self.first)
        self.assertNotEqual(result['status'], 'complete')
        capture.assert_not_called()
        self.assertEqual((self.app.directory / 'projects.json').read_bytes(),
                         before)

    def test_recapture_does_not_duplicate_saved_recipe_history(self):
        result = {'id': 'synthetic', 'sha': self.first, 'status': 'complete'}
        with patch.object(self.app.captures, 'capture', return_value=result) as capture:
            capture_draft(self.app, self.project, self.first)
            before = (self.app.directory / 'projects.json').read_bytes()
            capture_draft(self.app, self.project, self.first)
        self.assertEqual(capture.call_count, 2)
        self.assertEqual((self.app.directory / 'projects.json').read_bytes(),
                         before)

    def test_invalid_revision_cannot_enqueue_or_save_configuration(self):
        before = (self.app.directory / 'projects.json').read_bytes()
        with patch.object(self.app.captures, 'capture') as capture:
            for sha in ('HEAD', self.first[:8], 'f' * 40, None):
                with self.subTest(sha=sha), self.assertRaises(ValueError):
                    queue_capture(self.app, self.project, {'sha': sha})
        capture.assert_not_called()
        self.assertEqual(self.app.jobs.list(), [])
        self.assertEqual((self.app.directory / 'projects.json').read_bytes(),
                         before)

    def test_default_save_and_false_capture_flag_do_not_run_webpage(self):
        with patch.object(self.app.captures, 'capture') as capture:
            for body in ({}, {'capture_static': False}):
                (self.source / 'index.html').write_text(str(body))
                result = self.wait(self.app.execute(
                    self.project, 'snapshot', body))
                self.assertTrue(result['saved'])
                self.assertEqual(result['preview']['mode'], 'remind')
        capture.assert_not_called()

    def test_vite_save_returns_reviewable_plan_without_approving_or_executing(self):
        from test_vite_preview import manifest, lock
        package = manifest()
        (self.source / 'package.json').write_text(json.dumps(package))
        (self.source / 'package-lock.json').write_text(json.dumps(lock(package)))
        with patch.object(self.app.captures, 'capture') as capture:
            result = self.wait(self.app.execute(self.project, 'snapshot', {'capture_static': True}))
            capture.assert_not_called()
        self.assertTrue(result['saved'])
        self.assertEqual(result['preview']['status'], 'needs-approval')
        sha = result['sha']
        plan = result['preview']['plan']
        self.assertEqual(plan['sha'], sha)
        self.assertEqual(plan['recipe']['adapter'], 'command-web')
        self.assertNotIn(sha, self.app.projects.record(self.project).get('version_recipes', {}))
        with self.assertRaises(ValueError):
            queue_capture(self.app, self.project, {'sha': sha})
        self.app.projects.save_recipe(self.project, plan['recipe'], sha)
        self.assertEqual(plan_draft_preview(self.app, self.project, sha)['reason'], 'existing-settings')
        self.assertTrue(self.app.projects.get(self.project, sha)['recipe_approved'])

    def test_explicit_static_capture_flag_runs_only_after_snapshot_is_saved(self):
        (self.source / 'index.html').write_text('<h1>Explicit new draft</h1>')

        def capture(repository, project, sha, recipe, **options):
            self.assertNotEqual(sha, self.first)
            self.assertEqual(repository.blob(sha, 'index.html'),
                             b'<h1>Explicit new draft</h1>')
            return {'id': 'synthetic', 'sha': sha, 'status': 'complete'}

        with patch.object(self.app.captures, 'capture', side_effect=capture):
            result = self.wait(self.app.execute(
                self.project, 'snapshot', {'capture_static': True}))
        self.assertTrue(result['saved'])
        self.assertEqual(result['preview']['mode'], 'quick')
        self.assertEqual(result['preview']['evidence']['sha'], result['sha'])
        self.assertNotIn('preview_preferences',
                         self.app.projects.record(self.project))

    def test_non_boolean_capture_flag_is_rejected_before_snapshot(self):
        for value in ('true', 1, None, []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.app.execute(self.project, 'snapshot',
                                 {'capture_static': value})
        self.assertEqual(self.app.projects.repository(self.project).resolve('HEAD'),
                         self.first)
        self.assertEqual(self.app.jobs.list(), [])

    def test_quick_capture_failure_or_cancel_cannot_undo_saved_files(self):
        for error, status in ((RuntimeError('Browser unavailable'), 'failed'),
                              (Cancelled(), 'cancelled')):
            with self.subTest(status=status):
                content = '<h1>Saved even when capture is %s</h1>' % status
                (self.source / 'index.html').write_text(content)
                with patch.object(self.app.captures, 'capture', side_effect=error):
                    result = self.wait(self.app.execute(
                        self.project, 'snapshot', {'capture_static': True}))
                self.assertTrue(result['saved'])
                self.assertEqual(result['preview']['status'], status)
                self.assertEqual(self.app.projects.repository(self.project).blob(
                    result['sha'], 'index.html'), content.encode())

    def test_unavailable_quick_preview_still_keeps_saved_version(self):
        (self.source / 'index.html').write_text(
            '<h1>Online image</h1><img src="https://example.invalid/photo.png">')
        with patch.object(self.app.captures, 'capture') as capture:
            result = self.wait(self.app.execute(
                self.project, 'snapshot', {'capture_static': True}))
        self.assertTrue(result['saved'])
        self.assertEqual(result['preview']['status'], 'needs-configuration')
        self.assertEqual(result['preview']['plan']['reason'], 'remote-assets')
        capture.assert_not_called()

    def evidence_record(self, identifier, sha, created_at, **values):
        return {'id': identifier, 'project_id': self.project, 'sha': sha,
                'base': None, 'created_at': created_at, 'status': 'complete',
                'source': 'capture', 'items': [], **values}

    def image(self, sha, url, **values):
        return {'sha': sha, 'side': 'target', 'media_type': 'image/png',
                'url': url, **values}

    def test_visual_history_does_not_borrow_other_version_or_invalid_media(self):
        second = self.second_version()
        records = [self.evidence_record('pair', second, '2026-10-24',
            base=self.first, items=[
                self.image(self.first, '/artifacts/old.png', side='before'),
                self.image(second, '/artifacts/current.png'),
            ]), self.evidence_record('bad', self.first, '2026-10-25', items=[
                self.image(second, '/artifacts/wrong-sha.png'),
                self.image(self.first, '/artifacts/missing.png', missing=True),
                self.image(self.first, '/artifacts/error.png', error='Invalid'),
                self.image(self.first, '/artifacts/movie.mp4', media_type='video/mp4'),
                self.image(self.first, ''),
            ])]
        with patch.object(self.app.evidence, 'list', return_value=records):
            images = visual_history(self.app, self.project)['images']
        self.assertEqual(set(images), {self.first, second})
        self.assertEqual(images[self.first]['url'], '/artifacts/old.png')
        self.assertEqual(images[second]['url'], '/artifacts/current.png')

    def test_visual_history_retains_manual_and_partial_capture_provenance(self):
        second = self.second_version()
        records = [self.evidence_record('manual', self.first, '2026-10-24',
            source='manual', verification='user-supplied',
            items=[self.image(self.first, '/artifacts/manual.png')]),
            self.evidence_record('partial', second, '2026-10-24',
                status='partial', errors=['Missing local image'],
                items=[self.image(second, '/artifacts/diagnostic.png')])]
        with patch.object(self.app.evidence, 'list', return_value=records):
            images = visual_history(self.app, self.project)['images']
        self.assertEqual(images[self.first]['source'], 'manual')
        self.assertEqual(images[self.first]['verification'], 'user-supplied')
        self.assertEqual(images[second]['status'], 'partial')

    def test_newer_failed_capture_does_not_replace_a_complete_image(self):
        records = [self.evidence_record('complete', self.first, '2026-10-23',
            items=[self.image(self.first, '/artifacts/complete.png')]),
            self.evidence_record('failed', self.first, '2026-10-24',
                status='failed', errors=['Browser crashed'],
                items=[self.image(self.first, '/artifacts/failed.png')])]
        for ordered in (records, records[::-1]):
            with patch.object(self.app.evidence, 'list', return_value=ordered):
                image = visual_history(self.app, self.project)['images'][self.first]
            self.assertEqual(image['url'], '/artifacts/complete.png')
            self.assertTrue(image['complete'])

    @contextmanager
    def api(self):
        server = LocalServer(('127.0.0.1', 0), self.app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def request(method, path, body=None, headers=None):
            connection = http.client.HTTPConnection(
                '127.0.0.1', server.server_port, timeout=5)
            try:
                connection.request(method, path,
                    json.dumps(body) if body is not None else None,
                    headers or {})
                response = connection.getresponse()
                return response.status, json.loads(response.read())
            finally:
                connection.close()

        try:
            yield server, request
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_preview_and_destination_gets_are_read_only_and_post_needs_token(self):
        prefix = '/api/projects/' + self.project
        before = (self.app.directory / 'projects.json').read_bytes()
        with self.api() as (server, request):
            with patch.object(self.app.captures, 'capture') as capture:
                for route in ('/quick-preview?sha=' + self.first,
                              '/recovery-destination?sha=' + self.first,
                              '/visual-history'):
                    status, response = request('GET', prefix + route)
                    self.assertEqual(status, 200, response)
                self.assertEqual((self.app.directory / 'projects.json').read_bytes(),
                                 before)
                self.assertFalse(self.app.recovery.directory.exists())
                self.assertEqual(self.app.jobs.list(), [])
                capture.assert_not_called()

            good = {'Content-Type': 'application/json',
                    'X-Reprise-Token': server.token}
            invalid = [
                {'Content-Type': 'application/json'},
                {**good, 'X-Reprise-Token': 'wrong'},
                {**good, 'Origin': 'https://example.invalid'},
                {**good, 'Host': 'example.invalid'},
            ]
            with patch.object(self.app.captures, 'capture') as capture:
                for headers in invalid:
                    status, response = request('POST', prefix + '/quick-preview',
                        {'sha': self.first}, headers)
                    self.assertEqual(status, 403, response)
                capture.assert_not_called()
                self.assertEqual(self.app.jobs.list(), [])

            capture_result = {'id': 'synthetic', 'sha': self.first,
                              'status': 'complete'}
            with patch.object(self.app.captures, 'capture', return_value=capture_result):
                status, job = request('POST', prefix + '/quick-preview',
                    {'sha': self.first}, good)
                self.assertEqual(status, 202, job)
                self.assertEqual(self.wait(job)['sha'], self.first)


if __name__ == '__main__':
    unittest.main()
