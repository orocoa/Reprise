"""Compare stream estimates to retained reference libraries; never delete a version."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch
import urllib.request

from reprise.cancellation import Cancellation, Cancelled
from reprise.content_lock import content_access
from reprise.packing import stream_pack
from reprise.service import Reprise
from reprise.server import LocalServer
from reprise.version_deletion import sizes, VersionDeletion
from test_runtime import fixture


def files(path):
    return {str(p.relative_to(path)): (hashlib.sha256(p.read_bytes()).hexdigest(),
            p.stat().st_mtime_ns, p.stat().st_mode) for p in path.rglob('*') if p.is_file()}


def sample(root, mode):
    source, other = root / 'source', root / 'other'
    source.mkdir(); other.mkdir()
    common = hashlib.shake_256(b'shared').digest(128 * 1024)
    (source / 'shared.bin').write_bytes(common)
    if mode == 'compressible':
        old, new = b'old-content\n' * 50000, b'new-content\n' * 50000
    elif mode == 'similar':
        old = hashlib.shake_256(b'almost-same').digest(512 * 1024)
        new = old[:10000] + b'changed!' + old[10008:]
    else:
        old, new = (hashlib.shake_256(seed).digest(512 * 1024) for seed in (b'old', b'new'))
    (source / 'payload.bin').write_bytes(old)
    app = Reprise(root / 'data')
    project = app.projects.add(str(source), 'Synthetic versions', kind='folder')['id']
    a = app.projects.snapshot(project, 'Old')['sha']
    (source / 'payload.bin').write_bytes(new)
    b = app.projects.snapshot(project, 'New')['sha']
    selected = [a]
    if mode == 'zero':
        value = (source / 'payload.bin').stat()
        os.utime(source / 'payload.bin', ns=(value.st_atime_ns, value.st_mtime_ns + 1_000_000_000))
        selected = [app.projects.snapshot(project, 'Same bytes, different historical state')['sha']]
    other_project = app.projects.add(str(other), 'Shared content', kind='folder')['id']
    if mode != 'empty':
        (other / 'shared.bin').write_bytes(common)
        app.projects.snapshot(other_project, 'Kept shared content')
    else:
        selected = [a, b]
    return app, project, selected, source, other


class SpaceEstimationTests(unittest.TestCase):
    def test_replacement_metadata_rejects_unsafe_reference_names_before_writing(self):
        root = fixture('space-estimation-reference-safety')
        target = type('Target', (), {'path': root})()
        for catalog in ({'../outside': ['a'*40]}, {'a'*20: ['../../outside']}, {'a'*20: ['b'*39]}):
            with self.assertRaisesRegex(ValueError, '未写入引用'):
                VersionDeletion._metadata(target, catalog, set(), {})
        self.assertEqual(list(root.iterdir()), [])

    def test_reference_measurement_protects_unpublished_diagnostic_ancestry(self):
        root = fixture('space-estimation-diagnostics')
        app, project, selected, _, _ = sample(root, 'compressible')
        try:
            engine, store = app.version_deletions, app.projects.folders
            blob = store.run('hash-object', '-w', '--stdin', input=b'Keep failed-save diagnostic')
            tree = store.run('mktree', input=('100644 blob ' + blob + '\tdiagnostic.txt\n').encode())
            orphan = store.run('commit-tree', tree, '-p', selected[0], input=b'Unpublished diagnostic\n')
            plan = engine.plan(project, selected)
            self.assertEqual(plan['unique_content_bytes'], 0)
            before = files(store.path)
            estimate = engine.estimate(project, plan['id'])
            with content_access(store.directory):
                records, catalog, _, _, _, protected, objects = engine._state()
                reference = engine._build_replacement(root / 'kept-reference', records,
                              engine._retained(catalog, plan), protected, objects)
            self.assertEqual(reference.run('cat-file', '-p', blob), 'Keep failed-save diagnostic')
            self.assertIn(selected[0], reference.run('cat-file', '-p', orphan))
            self.assertEqual(estimate['runs'][0]['store_bytes_min'], sizes(reference.path)[0])
            self.assertEqual(before, files(store.path))
        finally:
            app.close()

    def test_api_estimate_job_uses_frozen_plan_without_a_delete_confirmation(self):
        root = fixture('space-estimation-api')
        app, project, selected, source, other = sample(root, 'compressible')
        server = LocalServer(('127.0.0.1', 0), app)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def request(route, body=None):
            req = urllib.request.Request('http://127.0.0.1:%d%s' % (server.server_port, route),
                data=json.dumps(body).encode() if body is not None else None,
                headers={'Content-Type': 'application/json', 'X-Reprise-Token': server.token,
                         'Origin': 'http://127.0.0.1:%d' % server.server_port})
            with opener.open(req, timeout=30) as response:
                return json.load(response)
        try:
            before = files(app.projects.folders.path), files(source), files(other)
            plan = request('/api/projects/%s/version-delete-plan' % project, {'shas': selected})
            with patch.object(app.version_deletions, 'execute', side_effect=AssertionError('No deletion allowed')):
                job = request('/api/projects/%s/version-estimate' % project, {'plan_id': plan['id']})
                deadline = time.monotonic() + 30
                while job['status'] in ('queued', 'running', 'cancelling') and time.monotonic() < deadline:
                    time.sleep(.05)
                    job = request('/api/jobs/' + job['id'])
            self.assertEqual(job['status'], 'complete', job)
            self.assertEqual(job['request'], {'plan_id': plan['id']})
            self.assertTrue(job['cancellable'])
            self.assertEqual(job['result']['plan_id'], plan['id'])
            self.assertEqual(before, (files(app.projects.folders.path), files(source), files(other)))
        finally:
            server.shutdown(); server.server_close(); thread.join(2); app.close()

    def test_stream_model_matches_independent_verified_kept_libraries(self):
        root = fixture('space-estimation-matrix')
        results = []
        for mode in ('compressible', 'random', 'similar', 'zero', 'empty'):
            case = root / mode; case.mkdir()
            app, project, selected, source, other = sample(case, mode)
            try:
                engine = app.version_deletions
                plan = engine.plan(project, selected)
                before = files(engine.store.path), files(source), files(other)
                history = {c['sha'] for c in app.projects.repository(project).history()['commits']}
                with patch.object(engine, 'execute', side_effect=AssertionError('Deletion forbidden in this test')):
                    estimate = engine.estimate(project, plan['id'])
                with content_access(engine.store.directory):
                    records, catalog, _, _, _, protected, objects = engine._state()
                    kept = engine._build_replacement(case / 'reference-kept', records,
                                engine._retained(catalog, plan), protected, objects)
                    baseline = engine._build_replacement(case / 'reference-all', records,
                                catalog, protected, objects)
                actual, actual_allocated = sizes(kept.path)
                actual_baseline = sizes(baseline.path)[0]
                expected = estimate['current_store_bytes'] - actual
                self.assertLessEqual(estimate['estimated_store_reduction_min_bytes'], expected, mode)
                self.assertGreaterEqual(estimate['estimated_store_reduction_max_bytes'], expected, mode)
                self.assertEqual(estimate['runs'][0]['store_bytes_min'], actual, mode)
                self.assertEqual(estimate['runs'][0]['allocated_bytes_min'], actual_allocated, mode)
                self.assertEqual(estimate['baseline']['store_bytes_min'], actual_baseline, mode)
                self.assertEqual(before, (files(engine.store.path), files(source), files(other)))
                self.assertEqual(history, {c['sha'] for c in app.projects.repository(project).history()['commits']})
                self.assertIsNone(estimate['actual_deletion_error_bytes'])
                self.assertIsNone(estimate['physical_free_delta_estimate_bytes'])
                self.assertEqual(estimate['observed_repeat_spread_bytes'], 0)
                artifacts = Path(estimate['artifact_directory'])
                self.assertFalse(list(artifacts.rglob('*.pack')))
                self.assertFalse(list(artifacts.rglob('*.idx')))
                self.assertEqual(sizes(artifacts)[0], estimate['retained_artifact_bytes'])
                self.assertFalse(list(engine.directory.glob('*.receipt.json')))
                packs = list(kept.path.glob('objects/pack/*.pack'))
                if packs:
                    self.assertEqual(packs[0].stem.removeprefix('pack-'), estimate['runs'][0]['pack_sha1'])
                if mode == 'zero':
                    self.assertEqual(plan['unique_content_bytes'], 0)
                    self.assertTrue(plan['history_state_loss'])
                results.append(dict(case=mode, unique_uncompressed_bytes=plan['unique_content_bytes'],
                    predicted_store_reduction=estimate['estimated_store_reduction_min_bytes'],
                    reference_store_reduction=expected, reference_construction_error_bytes=estimate['estimated_store_reduction_min_bytes']-expected,
                    allocation_model_error_bytes=estimate['runs'][0]['allocated_bytes_min']-actual_allocated,
                    retained_artifact_bytes=estimate['retained_artifact_bytes'], estimate=estimate))
            finally:
                app.close()
        (root / 'matrix.json').write_text(json.dumps({'results': results,
            'actual_deletions': 0, 'error_scope': 'Verified reference construction, not actual deletion or volume free space'}, indent=2))
        print('\nEstimation matrix retained at ' + str(root / 'matrix.json'))

    def test_layout_or_config_change_invalidates_estimate_before_output(self):
        root = fixture('space-estimation-stale')
        app, project, selected, _, _ = sample(root, 'compressible')
        try:
            engine = app.version_deletions
            plan = engine.plan(project, selected)
            config = engine.store.path / 'config'
            with config.open('a') as stream:
                stream.write('\n')
            with self.assertRaisesRegex(ValueError, '已失效'):
                engine.estimate(project, plan['id'])
            self.assertFalse((engine.directory / 'estimates').exists())
        finally:
            app.close()

    def test_small_free_space_is_rejected_without_partial_output(self):
        root = fixture('space-estimation-low-space')
        app, project, selected, _, _ = sample(root, 'compressible')
        try:
            engine = app.version_deletions
            plan = engine.plan(project, selected)
            usage = __import__('shutil').disk_usage(root)
            with patch('reprise.version_deletion.shutil.disk_usage', return_value=type(usage)(usage.total, usage.used, 1)):
                with self.assertRaisesRegex(ValueError, '空间不足'):
                    engine.estimate(project, plan['id'])
            self.assertFalse((engine.directory / 'estimates').exists())
        finally:
            app.close()

    def test_stream_cancellation_stops_only_its_own_child_and_keeps_diagnostics(self):
        root = fixture('space-estimation-cancel')
        cancel = Cancellation(root / 'cancel.json')
        real_popen, owned = subprocess.Popen, []
        def slow_child(command, **kwargs):
            process = real_popen([sys.executable, '-c', 'import sys,time;sys.stdout.buffer.write(b"PACK");sys.stdout.flush();time.sleep(60)'], **kwargs)
            owned.append(process)
            return process
        def request():
            while not owned:
                time.sleep(.01)
            cancel.request_path.write_text('{}')
        thread = threading.Thread(target=request, daemon=True); thread.start()
        began = time.monotonic()
        with patch('reprise.packing.subprocess.Popen', side_effect=slow_child):
            with self.assertRaises(Cancelled):
                stream_pack(type('Store', (), {'path': root})(), {'a'*40}, root / 'stream', cancel)
        thread.join(2)
        self.assertLess(time.monotonic()-began, 5)
        self.assertIsNotNone(owned[0].poll())
        self.assertTrue((root / 'stream/object-ids.txt').is_file())
        self.assertTrue((root / 'stream/pack.stderr.log').is_file())

    def test_truncated_or_wrong_count_stream_is_never_a_success(self):
        root = fixture('space-estimation-invalid-pack')
        real_popen = subprocess.Popen
        def invalid(command, **kwargs):
            return real_popen([sys.executable, '-c', 'import sys;sys.stdout.buffer.write(b"PACK"+b"x"*40)'], **kwargs)
        with patch('reprise.packing.subprocess.Popen', side_effect=invalid):
            with self.assertRaisesRegex(ValueError, '校验和不一致'):
                stream_pack(type('Store', (), {'path': root})(), {'a'*40}, root / 'stream')
