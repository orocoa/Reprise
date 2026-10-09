"""Retained integration fixtures for cancellation and revision-specific workflows."""
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from reprise.cancellation import Cancelled
from reprise.jobs import Jobs
from reprise.recipes import recipe_hash
from reprise.runtime import process_identity
from reprise.server import LocalServer
from reprise.service import Reprise
from reprise.storage import write_json
from test_git import git
from test_runtime import fixture


class VersionWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('version-workflows')
        self.source = self.root / 'source'
        self.source.mkdir()
        git(self.source, 'init', '-b', 'main')
        git(self.source, 'config', 'user.name', 'Reprise workflow test')
        git(self.source, 'config', 'user.email', 'test@example.invalid')
        self.app = Reprise(self.root / 'state')

    def tearDown(self):
        self.app.close()
        for runtime in self.app.runtimes.list():
            if runtime['running']:
                self.app.runtimes.stop(runtime['id'])

    def commit(self, content, name='index.html'):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        git(self.source, 'add', '.')
        git(self.source, 'commit', '-m', content[:30])
        return git(self.source, 'rev-parse', 'HEAD')

    def until(self, callback, timeout=10):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = callback()
            if value:
                return value
            time.sleep(.05)
        self.fail('Condition not reached within %s seconds' % timeout)

    def finished(self, job):
        return self.until(lambda: (value if value['status'] in ('complete', 'failed', 'cancelled') else None)
                          if (value := self.app.jobs.get(job['id'])) else None)

    def test_corrupt_job_files_are_preserved_and_reported_individually(self):
        directory = self.root / 'recovery'
        records = directory / 'jobs'
        records.mkdir(parents=True)
        bad = {'a' * 24: b'{broken', 'b' * 24: b'[]', 'c' * 24: b'{}',
               'd' * 24: json.dumps({'id': 'd' * 24, 'status': 'complete', 'created_at': 3}).encode(),
               'e' * 24: b'\xff'}
        for name, content in bad.items():
            (records / (name + '.json')).write_bytes(content)
        good = 'f' * 24
        write_json(records / (good + '.json'), {'id': good, 'status': 'complete'})
        recovered = Jobs(directory)
        try:
            self.assertEqual([j['id'] for j in recovered.list()], [good])
            self.assertEqual(len(recovered.warnings()), len(bad))
            for name, content in bad.items():
                self.assertEqual((records / (name + '.json')).read_bytes(), content)
            with self.assertRaisesRegex(ValueError, '原文件已保留'):
                recovered.get('a' * 24)
            new = recovered.submit('usable', 'test', lambda: {'ok': True})
            self.until(lambda: recovered.get(new['id'])['status'] == 'complete')
        finally:
            recovered.close()

    def test_recipes_bind_exact_sha_and_preserve_legacy_configuration(self):
        first = self.commit('<h1>first</h1>')
        second = self.commit('<h1>second</h1>')
        project = self.app.projects.add(str(self.source))
        recipe1 = {'adapter': 'static-web', 'captures': [{'id': 'old-scene'}]}
        recipe2 = {'adapter': 'static-web', 'captures': [{'id': 'new-scene'}]}
        self.app.projects.save_recipe(project['id'], recipe1, first)
        self.app.projects.save_recipe(project['id'], recipe2, 'HEAD')
        self.assertEqual(self.app.projects.get(project['id'], first)['recipe']['captures'][0]['id'], 'old-scene')
        self.assertEqual(self.app.projects.get(project['id'], second)['recipe']['captures'][0]['id'], 'new-scene')
        third = self.commit('<h1>third</h1>')
        self.assertEqual(self.app.projects.get(project['id'], third)['recipe_source'], 'detected')
        self.app.projects.save_recipe(project['id'], None, first)
        self.assertEqual(self.app.projects.get(project['id'], first)['recipe_source'], 'detected')
        self.assertEqual(self.app.projects.get(project['id'], second)['recipe_source'], 'version')
        records = self.app.projects.records()
        legacy = {'adapter': 'command-web', 'commands': {'start': ['must-not-run']}}
        records[0]['recipe'] = legacy
        write_json(self.app.projects.file, {'schema': 1, 'projects': records})
        state = self.app.projects.get(project['id'], third)
        self.assertEqual(state['legacy_recipe'], legacy)
        self.assertEqual(state['recipe']['adapter'], 'static-web')
        self.assertFalse(state['recipe_approved'])
        self.assertEqual(len(self.app.projects.record(project['id'])['recipe_history']), 3)

    def test_cancel_queued_job_from_another_instance_releases_lock(self):
        owner = Jobs(self.root / 'queue', workers=1)
        other = Jobs(self.root / 'queue')
        started, release = threading.Event(), threading.Event()
        called = []
        try:
            one = owner.submit('one', 'test', lambda: (started.set(), release.wait(10), {})[-1])
            self.assertTrue(started.wait(2))
            queued = owner.submit('two', 'capture', lambda cancel: called.append('ran'), cancellable=True)
            other.cancel(queued['id'])
            self.until(lambda: other.get(queued['id'])['status'] == 'cancelled')
            self.assertEqual(called, [])
            retry = other.submit('two', 'test', lambda: {'ok': True})
            self.until(lambda: other.get(retry['id'])['status'] == 'complete')
            self.assertEqual(other.cancel(retry['id'])['status'], 'complete')
        finally:
            release.set()
            owner.close()
            other.close()

    def test_cancel_build_stops_process_group_and_retains_logs(self):
        sha = self.commit('<h1>build fixture</h1>')
        project = self.app.projects.add(str(self.source))
        build = 'import subprocess,sys,time; child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); print(child.pid,flush=True); time.sleep(60)'
        recipe = {'adapter': 'command-web', 'commands': {'build': [[sys.executable, '-c', build]], 'start': [sys.executable, '-m', 'http.server', '{port}']}}
        self.app.projects.save_recipe(project['id'], recipe, sha)
        job = self.app.execute(project['id'], 'run', {'sha': sha})
        def building():
            for runtime in self.app.runtimes.list():
                log = Path(runtime['log_path'])
                if runtime['status'] == 'build' and log.exists() and log.read_text().strip():
                    return runtime
        runtime = self.until(building)
        child = int(Path(runtime['log_path']).read_text().strip())
        other = Jobs(self.app.directory)
        try:
            other.cancel(job['id'])
        finally:
            other.close()
        result = self.finished(job)
        self.assertEqual(result['status'], 'cancelled', result)
        self.until(lambda: process_identity(runtime['pid']) is None)
        self.until(lambda: process_identity(child) is None)
        self.assertTrue(Path(runtime['path']).is_dir())
        self.assertIn(str(child), Path(runtime['log_path']).read_text())
        self.assertEqual(self.app.runtimes.list()[0]['status'], 'cancelled')
        self.assertEqual(git(self.source, 'status', '--porcelain'), '')

    def test_cancel_during_readiness_and_do_not_stop_completed_preview(self):
        sha = self.commit('<h1>readiness fixture</h1>')
        project = self.app.projects.add(str(self.source))
        recipe = {'adapter': 'command-web', 'commands': {'start': [sys.executable, '-c', 'import time; time.sleep(60)']}, 'readiness': {'timeout_ms': 60000}}
        self.app.projects.save_recipe(project['id'], recipe, sha)
        job = self.app.execute(project['id'], 'run', {'sha': sha})
        self.until(lambda: any(r['status'] == 'starting' for r in self.app.runtimes.list()))
        pending_runtime = next(r for r in self.app.runtimes.list() if r['status'] == 'starting')
        with self.assertRaisesRegex(ValueError, '取消任务'):
            self.app.runtimes.stop(pending_runtime['id'])
        self.app.jobs.cancel(job['id'])
        self.assertEqual(self.finished(job)['status'], 'cancelled')
        self.app.projects.save_recipe(project['id'], {'adapter': 'static-web'}, sha)
        success = self.app.execute(project['id'], 'run', {'sha': sha})
        result = self.finished(success)
        self.assertEqual(result['status'], 'complete', result)
        self.assertEqual(self.app.jobs.cancel(success['id'])['status'], 'complete')
        self.assertIsNotNone(process_identity(result['result']['pid']))

    def test_capture_uses_two_saved_recipes_and_resolves_refs_before_queue(self):
        first = self.commit('<h1>old</h1>', 'old/index.html')
        second = self.commit('<h1>new</h1>')
        project = self.app.projects.add(str(self.source))
        old_recipe = {'adapter': 'command-web', 'root': 'old', 'commands': {'start': [sys.executable, '-m', 'http.server', '{port}']}}
        self.app.projects.save_recipe(project['id'], old_recipe, first)
        self.app.projects.save_recipe(project['id'], {'adapter': 'static-web'}, second)
        git(self.source, 'tag', 'baseline', first)
        seen = {}
        def capture(*args, **kwargs):
            seen.update(kwargs)
            return {'status': 'complete', 'items': []}
        with patch.object(self.app.captures, 'capture', side_effect=capture):
            job = self.app.execute(project['id'], 'capture', {'sha': second, 'base': 'baseline'})
            self.assertEqual(self.finished(job)['status'], 'complete')
        self.assertEqual(seen['base'], first)
        self.assertEqual(seen['base_recipe']['root'], 'old')
        self.assertTrue(seen['base_approved'])
        self.assertEqual(self.app.jobs.get(job['id'])['request']['base'], first)
        self.app.projects.save_recipe(project['id'], {'adapter': 'manual'}, first)
        with self.assertRaisesRegex(ValueError, '比较基准'):
            self.app.execute(project['id'], 'capture', {'sha': second, 'base': first})

    def test_api_compares_nonadjacent_versions_and_scopes_recipe(self):
        first = self.commit('first')
        self.commit('second')
        third = self.commit('third', 'another.txt')
        project = self.app.projects.add(str(self.source))
        server = LocalServer(('127.0.0.1', 0), self.app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def request(method, path, body=None):
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            headers = {'X-Reprise-Token': server.token, 'Content-Type': 'application/json'}
            conn.request(method, path, json.dumps(body) if body is not None else None, headers)
            response = conn.getresponse()
            status, value = response.status, json.loads(response.read())
            conn.close()
            return status, value
        try:
            prefix = '/api/projects/' + project['id']
            status, diff = request('GET', prefix + '/diff?base=' + first + '&target=' + third)
            self.assertEqual(status, 200)
            self.assertEqual((diff['base'], diff['target']), (first, third))
            self.assertEqual({f['path'] for f in diff['files']}, {'index.html', 'another.txt'})
            status, result = request('PUT', prefix + '/recipe', {'sha': first, 'recipe': {'adapter': 'manual'}})
            self.assertEqual(status, 200)
            self.assertEqual(result['revision'], first)
            self.assertEqual(self.app.projects.get(project['id'], third)['recipe_source'], 'detected')
            stop = threading.Event()
            def running(cancel):
                while not stop.wait(.02):
                    cancel.check()
            job = self.app.jobs.submit(project['id'], 'capture', running, cancellable=True)
            status, result = request('POST', '/api/jobs/' + job['id'] + '/cancel', {})
            self.assertEqual(status, 202)
            self.assertEqual(self.finished(job)['status'], 'cancelled')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)

    @unittest.skipUnless(os.environ.get('REPRISE_BROWSER_TESTS') == '1', 'Browser tests opt in')
    def test_real_capture_cancellation_stops_worker_browser_and_preview(self):
        sha = self.commit('<h1>cancel browser</h1>')
        project = self.app.projects.add(str(self.source))
        recipe = {'adapter': 'static-web', 'captures': [{'id': 'long', 'steps': [{'action': 'wait', 'ms': 60000}], 'record': True}]}
        self.app.projects.save_recipe(project['id'], recipe, sha)
        job = self.app.execute(project['id'], 'capture', {'sha': sha})
        record_path = self.until(lambda: next(iter((self.app.directory / 'evidence').glob('*/after-browser-process.json')), None), 20)
        self.until(lambda: 'Capture step started: wait' in record_path.with_name('after-browser.log').read_text(), 10)
        browser = json.loads(record_path.read_text())
        worker = json.loads(record_path.with_name('after-worker.json').read_text())
        self.app.jobs.cancel(job['id'])
        result = self.finished(job)
        self.assertEqual(result['status'], 'cancelled', result)
        self.assertEqual(result['result']['status'], 'cancelled')
        self.until(lambda: process_identity(browser['pid']) is None)
        self.until(lambda: process_identity(worker['pid']) is None)
        self.assertFalse(any(r['running'] for r in self.app.runtimes.list()))
        self.assertTrue(record_path.with_name('after-browser.log').exists())

    @unittest.skipUnless(os.environ.get('REPRISE_BROWSER_TESTS') == '1', 'Browser tests opt in')
    def test_real_compare_uses_revision_roots_and_shared_scenarios(self):
        first = self.commit('<body style="background:red">before</body>', 'old/index.html')
        second = self.commit('<body style="background:blue">after</body>')
        project = self.app.projects.add(str(self.source))
        self.app.projects.save_recipe(project['id'], {'adapter': 'static-web', 'root': 'old'}, first)
        self.app.projects.save_recipe(project['id'], {'adapter': 'static-web', 'captures': [{'id': 'shared'}]}, second)
        job = self.app.execute(project['id'], 'capture', {'sha': second, 'base': first})
        result = self.until(lambda: self.app.jobs.get(job['id']) if self.app.jobs.get(job['id'])['status'] in ('complete','failed') else None, 40)
        self.assertEqual(result['status'], 'complete', result)
        record = result['result']
        self.assertEqual(record['base_recipe']['root'], 'old')
        self.assertEqual(record['base_recipe']['captures'], record['recipe']['captures'])
        self.assertEqual(record['base_recipe_hash'], recipe_hash(record['base_recipe']))
        self.assertEqual({item['sha'] for item in record['items']}, {first, second})
        self.assertEqual({item['capture_id'] for item in record['items']}, {'shared'})
        self.assertEqual(len({item['content_sha256'] for item in record['items']}), 2)
