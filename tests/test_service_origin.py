"""A running service keeps its startup location without gaining shutdown authority."""
import json
import os
import shlex
import sys
import unittest
from unittest.mock import Mock, patch

from reprise import __version__, launcher
from reprise.server import LocalServer
from test_runtime import fixture


class ServiceOriginTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture('service-origin')
        self.bundle = self.root / 'Reprise package with spaces' / 'resources'
        self.bundle.mkdir(parents=True)
        self.data = self.root / 'state'
        self.data.mkdir()
        self.environment = patch.dict(os.environ, {'REPRISE_BUNDLE_RESOURCES': str(self.bundle)})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.record = {'pid': 123, 'identity': 'verified-process', 'instance_id': 'verified-instance',
                       'version': __version__, 'url': 'http://127.0.0.1:12345/',
                       'data_directory': str(self.data)}

    def test_another_bundle_is_rejected_without_starting_or_stopping_it(self):
        record = {**self.record, 'source_id': 'another-bundle'}
        with patch.object(launcher, 'verified_server', return_value=record):
            with patch.object(launcher.subprocess, 'Popen') as spawn:
                with patch.object(launcher, 'shutdown') as stop:
                    with self.assertRaisesRegex(ValueError, 'different location'):
                        launcher._ensure_server(self.data, 0)
        spawn.assert_not_called()
        stop.assert_not_called()

    def test_bundle_does_not_reuse_a_service_without_source_identity(self):
        with patch.object(launcher, 'verified_server', return_value=self.record):
            with patch.object(launcher.subprocess, 'Popen') as spawn:
                with self.assertRaisesRegex(ValueError, 'location cannot be verified') as failure:
                    launcher._ensure_server(self.data, 0)
        spawn.assert_not_called()
        command = str(failure.exception).split('. Run ', 1)[1].split(', then open again;', 1)[0]
        parts = shlex.split(command)
        self.assertEqual(parts[0], sys.executable)
        self.assertTrue(parts[4].endswith('/reprise/server_entry.py'))
        self.assertEqual(parts[5:], ['--data', str(self.data), 'shutdown'])

    def test_concurrent_winner_from_another_bundle_is_rejected_without_killing(self):
        record = {**self.record, 'pid': 456, 'source_id': 'another-bundle'}
        process = Mock(pid=123)
        process.poll.return_value = None
        with patch.object(launcher, 'verified_server', side_effect=[None, record]), \
                patch.object(launcher, 'process_identity', return_value='verified-caller'):
            with patch.object(launcher.subprocess, 'Popen', return_value=process):
                with self.assertRaisesRegex(ValueError, 'different location'):
                    launcher._ensure_server(self.data, 0)
        process.terminate.assert_not_called()
        process.kill.assert_not_called()

    def test_same_bundle_reuses_without_spawning(self):
        record = {**self.record, 'source_id': launcher.service_source_id()}
        with patch.object(launcher, 'verified_server', return_value=record):
            with patch.object(launcher.subprocess, 'Popen') as spawn:
                found, reused = launcher._ensure_server(self.data, 0)
        self.assertEqual(found, record)
        self.assertTrue(reused)
        spawn.assert_not_called()

    def test_canonical_location_is_opaque_and_stable_across_aliases(self):
        original = launcher.service_source_id()
        alias = self.root / 'bundle alias'
        alias.symlink_to(self.bundle, target_is_directory=True)
        with patch.dict(os.environ, {'REPRISE_BUNDLE_RESOURCES': str(alias)}):
            self.assertEqual(launcher.service_source_id(), original)
        self.assertRegex(original, r'^[a-f0-9]{64}$')
        self.assertNotIn(str(self.root), original)

    def test_moved_bundle_does_not_change_the_running_servers_startup_identity(self):
        # No socket or real service: construction captures startup identity;
        # changing the launcher location models a subsequent relocated entry.
        with patch('reprise.server.LoopbackHTTPServer.__init__', return_value=None):
            server = LocalServer(('127.0.0.1', 0), Mock())
        original = server.source_id
        moved = self.root / 'Moved Reprise' / 'resources'
        moved.mkdir(parents=True)
        with patch.dict(os.environ, {'REPRISE_BUNDLE_RESOURCES': str(moved)}):
            self.assertNotEqual(launcher.service_source_id(), original)
            self.assertEqual(server.source_id, original)
            record = {**self.record, 'source_id': server.source_id}
            with patch.object(launcher, 'verified_server', return_value=record):
                with self.assertRaisesRegex(ValueError, 'different location'):
                    launcher._ensure_server(self.data, 0)

    def test_health_source_is_authoritative_not_the_saved_record(self):
        record = {**self.record, 'source_id': 'untrusted-record-only-origin'}
        (self.data / 'server.json').write_text(json.dumps(record))
        for health_source in (None, 'actual-startup-origin'):
            with self.subTest(health_source=health_source):
                health = {'version': __version__, 'instance_id': record['instance_id']}
                if health_source is not None:
                    health['source_id'] = health_source
                with patch.object(launcher, 'process_identity', return_value=record['identity']):
                    with patch.object(launcher, '_request', return_value=health):
                        found = launcher.verified_server(self.data)
                self.assertEqual(found.get('source_id'), health_source)

    def test_legacy_or_other_origin_service_can_be_explicitly_shut_down(self):
        # Exercise real verification as well as shutdown: neither old version
        # nor absent/different origin grants reuse, but both remain stoppable.
        (self.data / 'server.json').write_text(json.dumps(self.record))
        for source in (None, 'another-bundle'):
            with self.subTest(source=source):
                health = {'version': '0.0.0', 'instance_id': self.record['instance_id']}
                if source is not None:
                    health['source_id'] = source
                with patch.object(launcher, 'process_identity', side_effect=[
                        self.record['identity'], self.record['identity'], None, None]):
                    with patch.object(launcher, '_request', side_effect=[
                            health, {'token': 'token'}, {'stopped': True}]) as request:
                        result = launcher.shutdown(self.data, instance_id=self.record['instance_id'])
                self.assertEqual(result, {'stopped': True})
                self.assertEqual([call.args[1] for call in request.call_args_list],
                                 ['/api/health', '/api/bootstrap?include_projects=0', '/api/shutdown'])
                self.assertEqual(request.call_args.args[2:],
                                 ({'instance_id': self.record['instance_id']}, 'token'))

    def test_source_only_location_remains_usable(self):
        environment = dict(os.environ)
        environment.pop('REPRISE_BUNDLE_RESOURCES', None)
        with patch.dict(os.environ, environment, clear=True):
            record = {**self.record, 'source_id': launcher.service_source_id()}
            with patch.object(launcher, 'verified_server', return_value=record):
                _, reused = launcher._ensure_server(self.data, 0)
        self.assertTrue(reused)
