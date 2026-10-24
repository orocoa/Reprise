import os
from pathlib import Path
import shutil
import subprocess
import threading
import json
import hashlib
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from unittest.mock import patch

from reprise.capture import CaptureService, stop_browser_from_record
from reprise.processes import ProcessCleanupError, ProcessObservationError
from reprise.runtime import RuntimeManager, process_identity
from test_runtime import commit_repo, fixture


class CaptureOwnershipTests(unittest.TestCase):
    def test_failed_observation_is_not_reported_as_an_exited_browser(self):
        root = fixture('capture-observation-denied')
        record = root / 'browser.json'
        record.write_text(json.dumps({'pid': 123, 'process_identity': 'recorded-birth'}))
        with patch('reprise.capture.process_identity', side_effect=ProcessObservationError('cannot observe owned process')), \
                patch('reprise.capture.OwnedProcessTree.adopt') as adopt:
            with self.assertRaisesRegex(ProcessCleanupError, 'cannot observe owned process'):
                stop_browser_from_record(record)
        adopt.assert_not_called()
        self.assertEqual(json.loads(record.read_text())['process_identity'], 'recorded-birth')

    def test_worker_never_publishes_a_null_browser_identity_and_closes_its_handle(self):
        node = os.environ.get('REPRISE_NODE') or shutil.which('node')
        if not node:
            self.skipTest('Node required for browser-worker protocol test')
        root = fixture('worker-missing-identity')
        closed, connected = root / 'closed', root / 'connected'
        module = root / 'fake-playwright.cjs'
        module.write_text('const fs = require("node:fs");\nmodule.exports = {chromium: {'
            'launchServer: async () => ({process: () => ({pid: 2147483647}), '
            'wsEndpoint: () => "ws://127.0.0.1:1/", close: async () => fs.writeFileSync(%s, "closed")}), '
            'connect: async () => {fs.writeFileSync(%s, "unexpected connect"); throw Error("unexpected connect");}'
            '}};\n' % (json.dumps(str(closed)), json.dumps(str(connected))))
        inputs = root / 'input.json'
        ownership, result = root / 'browser.json', root / 'result.json'
        inputs.write_text(json.dumps({'browser_process_path': str(ownership), 'result_path': str(result),
                                     'side': 'after', 'recipe': {'captures': []}}))
        worker = Path(__file__).resolve().parents[1] / 'src/reprise/browser_worker.mjs'
        completed = subprocess.run([node, str(worker), str(inputs)], capture_output=True, text=True,
                                   env={**os.environ, 'REPRISE_PLAYWRIGHT': str(module)}, timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        outcome = json.loads(result.read_text())
        self.assertTrue(any('process identity' in error['error'] for error in outcome['errors']), outcome)
        self.assertEqual(outcome['items'], [])
        self.assertFalse(ownership.exists())
        self.assertFalse(connected.exists())
        self.assertEqual(closed.read_text(), 'closed')


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('capture')
        self.repo = commit_repo(self.root / 'repo')
        self.manager = RuntimeManager(self.root / 'state')
        self.capture = CaptureService(self.root / 'state', self.manager)

    def test_missing_node_is_actionable_and_retained(self):
        with patch.dict(os.environ, {'PATH': '', 'REPRISE_NODE': ''}):
            # Resolve commits before clearing PATH because Git itself is required.
            with patch.object(self.repo, 'resolve', return_value='a' * 40):
                result = self.capture.capture(self.repo, 'example', 'HEAD', {'adapter': 'static-web'})
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(result['ai_used'])
        self.assertIn('Node.js is unavailable', result['errors'][0]['error'])
        self.assertEqual(self.manager.list(), [])
        self.assertEqual(self.capture.list('example')[0]['id'], result['id'])

    def test_manual_adapter_does_not_start_runtime(self):
        with self.assertRaisesRegex(ValueError, 'Manual adapter'):
            self.capture.capture(self.repo, 'native-game', 'HEAD', {'adapter': 'manual'})
        self.assertEqual(self.manager.list(), [])

    @unittest.skipUnless(os.environ.get('REPRISE_BROWSER_TESTS') == '1', 'set REPRISE_BROWSER_TESTS=1 for real Chromium capture')
    def test_paired_canvas_game_dpr_video_cache_and_cleanup(self):
        source = self.root / 'repo'
        html = '''<!doctype html><meta charset="utf-8"><title>Canvas demo</title>
<link rel="icon" href="data:,"><style>body{margin:0;background:#fff;color:#111}canvas{display:block}</style>
<h1>Version: COLOR</h1><input id="name"><button id="start">Start</button><canvas id="game" width="640" height="300" tabindex="0"></canvas>
<script>const c=document.getElementById('game'),ctx=c.getContext('2d');let x=20;
function draw(){ctx.fillStyle='COLOR';ctx.fillRect(0,0,640,300);ctx.fillStyle='white';ctx.fillRect(x,100,80,80)}
document.getElementById('start').onclick=()=>{c.focus();draw()};c.onkeydown=e=>{if(e.key==='ArrowRight'){x+=100;draw()}};draw();</script>'''
        (source / 'index.html').write_text(html.replace('COLOR', 'blue'))
        subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(source), 'commit', '-qm', 'blue game'], check=True)
        before = self.repo.resolve('HEAD')
        (source / 'index.html').write_text(html.replace('COLOR', 'green'))
        subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(source), 'commit', '-qm', 'green game'], check=True)
        after = self.repo.resolve('HEAD')
        recipe = {'adapter': 'static-web', 'readiness': {'selector': 'canvas'}, 'captures': [{'id': 'play',
            'viewport': {'width': 640, 'height': 480, 'scale': 2}, 'steps': [{'action': 'fill', 'selector': '#name', 'value': 'Test'},
                {'action': 'click', 'selector': '#start'}, {'action': 'press', 'selector': '#game', 'key': 'ArrowRight'}],
            'record': True, 'record_ms': 100}]}
        result = self.capture.capture(self.repo, 'game', after, recipe, base=before)
        self.assertEqual(result['status'], 'complete', result['errors'])
        self.assertEqual(len(result['items']), 4)
        images = [item for item in result['items'] if item['media_type'] == 'image/png']
        videos = [item for item in result['items'] if item['media_type'] == 'video/webm']
        self.assertEqual(len(images), 2)
        self.assertEqual(len(videos), 2)
        self.assertTrue(all((i['width'], i['height']) == (1280, 960) for i in images))
        self.assertNotEqual(Path(images[0]['path']).read_bytes(), Path(images[1]['path']).read_bytes())
        self.assertEqual({i['sha'] for i in images}, {before, after})
        self.assertTrue(all(Path(i['path']).stat().st_size > 1000 for i in videos))
        self.assertFalse(any(r['running'] for r in self.manager.list()))
        again = self.capture.capture(self.repo, 'game', after, recipe, base=before)
        self.assertEqual(again['id'], result['id'])
        self.assertTrue(again['cached'])
        for item in result['items']:
            self.assertEqual(item['content_sha256'], hashlib.sha256(Path(item['path']).read_bytes()).hexdigest())
        altered = Path(images[0]['path'])
        original = altered.read_bytes()
        altered.with_suffix('.original.png').write_bytes(original)
        altered.write_bytes(original + b'external edit')
        recaptured = self.capture.capture(self.repo, 'game', after, recipe, base=before)
        self.assertEqual(recaptured['status'], 'complete', recaptured['errors'])
        self.assertNotEqual(recaptured['id'], result['id'])
        self.assertFalse(recaptured['cached'])
        self.assertEqual(altered.read_bytes(), original + b'external edit')

    @unittest.skipUnless(os.environ.get('REPRISE_BROWSER_TESTS') == '1', 'set REPRISE_BROWSER_TESTS=1 for real Chromium capture')
    def test_visible_video_metadata_and_frame_with_preload_none(self):
        # Generate a real local video through the same optional recording runtime;
        # no network downloads, fixture machine paths or extra encoder dependency.
        recorded = self.capture.capture(self.repo, 'video-fixture', 'HEAD', {'adapter': 'static-web',
            'captures': [{'id': 'fixture', 'record': True, 'record_ms': 100,
                          'viewport': {'width': 320, 'height': 240, 'scale': 1}}]})
        self.assertEqual(recorded['status'], 'complete', recorded['errors'])
        video = next(i for i in recorded['items'] if i['media_type'] == 'video/webm')
        source = self.root / 'repo'
        shutil.copyfile(video['path'], source / 'fixture.webm')
        (source / 'index.html').write_text('<!doctype html><link rel="icon" href="data:,"><h1>Video metadata</h1>'
            '<video width="320" height="240" controls preload="none" src="/fixture.webm" '
            'poster="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%27320%27 height=%27240%27%3E%3Crect width=%27320%27 height=%27240%27 fill=%27red%27/%3E%3C/svg%3E"></video>')
        subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(source), 'commit', '-qm', 'video fixture'], check=True)
        result = self.capture.capture(self.repo, 'video-page', 'HEAD', {'adapter': 'static-web', 'readiness': {'timeout_ms': 3000}})
        self.assertEqual(result['status'], 'complete', result['errors'])
        ready = result['items'][0]['media_readiness'][0]
        self.assertEqual((ready['video_width'], ready['video_height']), (320, 240))
        self.assertGreaterEqual(ready['ready_state'], 2)
        self.assertGreater(ready['duration'], 0)
        self.assertTrue(ready['paused'])
        self.assertTrue(ready['source'].endswith('/fixture.webm'))

    @unittest.skipUnless(os.environ.get('REPRISE_BROWSER_TESTS') == '1', 'set REPRISE_BROWSER_TESTS=1 for real Chromium capture')
    def test_missing_and_corrupt_visible_video_are_diagnostic(self):
        source = self.root / 'repo'
        (source / 'corrupt.mp4').write_bytes(b'This is not an actual movie')
        for filename in ['missing.mp4', 'corrupt.mp4']:
            with self.subTest(filename=filename):
                (source / 'index.html').write_text('<!doctype html><link rel="icon" href="data:,"><h1>Video error</h1>'
                    '<video width="320" height="240" controls preload="none" src="/%s"></video>' % filename)
                subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
                subprocess.run(['git', '-C', str(source), 'commit', '-qm', filename], check=True)
                # Diagnose the asset, not a one-second Python startup race.
                result = self.capture.capture(self.repo, 'bad-video', 'HEAD', {'adapter': 'static-web', 'readiness': {'timeout_ms': 3000}})
                self.assertEqual(result['status'], 'partial')
                self.assertTrue(any('video ' in e['error'] and filename in e['error'] for e in result['errors']), result['errors'])
                self.assertTrue(result['items'][0]['diagnostic'])
                self.assertTrue(result['items'][0]['content_sha256'])
                self.assertFalse(any(r['running'] for r in self.manager.list()))

    @unittest.skipUnless(os.environ.get('REPRISE_BROWSER_TESTS') == '1', 'set REPRISE_BROWSER_TESTS=1 for real Chromium capture')
    def test_timeout_stops_worker_and_detached_browser(self):
        recipe = {'adapter': 'static-web', 'captures': [{'id': 'slow', 'steps': [{'action': 'wait', 'ms': 15000}]}]}
        with patch.dict(os.environ, {'REPRISE_CAPTURE_TIMEOUT': '2'}):
            result = self.capture.capture(self.repo, 'timeout', 'HEAD', recipe)
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(any('timed out' in e['error'] for e in result['errors']))
        folder = self.root / 'state' / 'evidence' / result['id']
        for name in ['after-worker.json', 'after-browser-process.json']:
            state = json.loads((folder / name).read_text())
            end = time.monotonic() + 3
            while process_identity(state['pid']) and time.monotonic() < end:
                time.sleep(.05)
            self.assertIsNone(process_identity(state['pid']), name)
        self.assertFalse(any(r['running'] for r in self.manager.list()))

    @unittest.skipUnless(os.environ.get('REPRISE_BROWSER_TESTS') == '1', 'set REPRISE_BROWSER_TESTS=1 for real Chromium capture')
    def test_local_network_does_not_reach_other_host_services(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                self.send_response(200)
                self.end_headers()
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            source = self.root / 'repo'
            (source / 'index.html').write_text('<!doctype html><link rel="icon" href="data:,"><h1>Isolation</h1><img src="http://127.0.0.1:%s/private">' % server.server_port)
            subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(source), 'commit', '-qm', 'network fixture'], check=True)
            result = self.capture.capture(self.repo, 'local-isolation', 'HEAD', {'adapter': 'static-web', 'readiness': {'timeout_ms': 3000}})
            self.assertEqual(result['status'], 'partial')
            self.assertTrue(any('Blocked external request' in e['error'] for e in result['errors']))
            self.assertEqual(requests, [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    @unittest.skipUnless(os.environ.get('REPRISE_BROWSER_TESTS') == '1', 'set REPRISE_BROWSER_TESTS=1 for real Chromium capture')
    def test_missing_assets_report_partial_evidence(self):
        source = self.root / 'repo'
        (source / 'index.html').write_text('<!doctype html><link rel="icon" href="data:,"><h1>Missing asset</h1><img src="/missing.png">')
        subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(source), 'commit', '-qm', 'missing asset'], check=True)
        result = self.capture.capture(self.repo, 'broken-web', 'HEAD', {'adapter': 'static-web', 'readiness': {'timeout_ms': 3000}})
        self.assertEqual(result['status'], 'partial')
        self.assertTrue(any('missing.png' in e['error'] for e in result['errors']))
        self.assertTrue(result['items'][0]['diagnostic'])
        self.assertFalse(any(r['running'] for r in self.manager.list()))
        again = self.capture.capture(self.repo, 'broken-web', 'HEAD', {'adapter': 'static-web', 'readiness': {'timeout_ms': 3000}})
        self.assertNotEqual(again['id'], result['id'])


if __name__ == '__main__':
    unittest.main()
