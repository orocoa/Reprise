"""Fail-closed process observation, service, and launch boundaries."""
import json
import os
import subprocess
import unittest
from unittest.mock import Mock, patch

from reprise import launcher, processes, server
from test_runtime import fixture


class ObservationBoundaryTests(unittest.TestCase):
    def test_strict_identity_does_not_turn_inspection_denial_into_exit(self):
        with patch.object(processes, '_process_info', side_effect=processes.ProcessObservationError('denied')):
            self.assertIsNone(processes.process_identity(os.getpid()))
            with self.assertRaisesRegex(processes.ProcessObservationError, 'denied'):
                processes.strict_process_identity(os.getpid())

    def test_strict_identity_returns_none_only_for_confirmed_exit_or_zombie(self):
        with patch.object(processes, '_process_info', return_value=None):
            with patch.object(processes.os, 'kill', side_effect=ProcessLookupError):
                self.assertIsNone(processes.strict_process_identity(123))
            with patch.object(processes.os, 'kill', return_value=None):
                with patch.object(processes.time, 'monotonic', side_effect=[0, 1]):
                    with self.assertRaisesRegex(processes.ProcessObservationError, 'possibly living'):
                        processes.strict_process_identity(123)
        with patch.object(processes, '_process_info', return_value={'identity': 'ps:confirmed', 'zombie': True}):
            self.assertIsNone(processes.strict_process_identity(123))

    def test_owned_launch_checks_observation_before_creating_a_pipe_or_child(self):
        for failing in ('boot', 'identity', 'table'):
            with self.subTest(failing=failing):
                identity = 'ps:verified'
                failure = processes.ProcessObservationError('inspection denied')
                with patch.object(processes, 'boot_identity', side_effect=failure if failing == 'boot' else None, return_value='boot'), \
                        patch.object(processes, 'strict_process_identity', side_effect=failure if failing == 'identity' else None, return_value=identity), \
                        patch.object(processes, '_uncached_process_table', side_effect=failure if failing == 'table' else None, return_value={os.getpid(): {'identity': identity}}), \
                        patch.object(processes.os, 'pipe') as pipe, \
                        patch.object(processes.subprocess, 'Popen') as spawn:
                    with self.assertRaisesRegex(processes.ProcessObservationError, 'command was not started'):
                        processes.launch_owned(['/usr/bin/true'], '/unused', {}, None, '/unused/record')
                pipe.assert_not_called()
                spawn.assert_not_called()

    def test_live_server_with_unobservable_identity_does_not_spawn_or_claim_shutdown(self):
        directory = fixture('unobservable-server')
        record = {'pid': os.getpid(), 'identity': 'retained-identity'}
        (directory / 'server.json').write_text(json.dumps(record))
        with patch.object(launcher, 'process_identity', side_effect=processes.ProcessObservationError('inspection denied')), \
                patch.object(launcher.subprocess, 'Popen') as spawn, patch.object(launcher, '_request') as request:
            for operation in (lambda: launcher._ensure_server(directory, 0), lambda: launcher.shutdown(directory)):
                with self.assertRaisesRegex(processes.ProcessObservationError, 'inspection denied'):
                    operation()
        spawn.assert_not_called()
        request.assert_not_called()
        self.assertEqual(json.loads((directory / 'server.json').read_text()), record)

    def test_fresh_open_checks_caller_before_starting_a_server(self):
        directory = fixture('fresh-open-observation')
        with patch.object(launcher, 'process_identity', side_effect=processes.ProcessObservationError('inspection denied')), \
                patch.object(launcher.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(processes.ProcessObservationError, 'no new Reprise service was started'):
                launcher._ensure_server(directory, 0)
        spawn.assert_not_called()
        self.assertFalse((directory / 'server.json').exists())
        self.assertFalse((directory / 'server.log').exists())

    def test_post_spawn_observation_failure_reaps_only_the_started_child(self):
        directory = fixture('post-spawn-observation')
        child = Mock(pid=123)
        child.poll.return_value = None
        with patch.object(launcher, 'verified_server', side_effect=[None, processes.ProcessObservationError('new inspection denial')]), \
                patch.object(launcher, 'process_identity', return_value='verified-caller'), \
                patch.object(launcher.subprocess, 'Popen', return_value=child), \
                patch.object(launcher, 'shutdown') as shutdown:
            with self.assertRaisesRegex(processes.ProcessObservationError, 'new inspection denial'):
                launcher._ensure_server(directory, 0)
        child.terminate.assert_called_once_with()
        child.wait.assert_called_once_with(timeout=2)
        child.kill.assert_not_called()
        shutdown.assert_not_called()

    def test_startup_timeout_bounds_child_cleanup_and_keeps_the_original_error(self):
        directory = fixture('startup-timeout-observation')
        child = Mock(pid=123)
        child.poll.return_value = None
        child.wait.side_effect = [subprocess.TimeoutExpired('owned child', 2), 0]
        with patch.object(launcher, 'verified_server', return_value=None), \
                patch.object(launcher, 'process_identity', return_value='verified-caller'), \
                patch.object(launcher.subprocess, 'Popen', return_value=child), \
                patch.object(launcher.time, 'monotonic', side_effect=[0, 16]), \
                patch.object(launcher, 'shutdown') as shutdown:
            with self.assertRaisesRegex(ValueError, 'Reprise did not start; inspect'):
                launcher._ensure_server(directory, 0)
        child.terminate.assert_called_once_with()
        child.kill.assert_called_once_with()
        self.assertEqual(child.wait.call_args_list, [unittest.mock.call(timeout=2), unittest.mock.call(timeout=2)])
        shutdown.assert_not_called()

    def test_concurrent_winner_is_returned_without_cleanup_or_shutdown(self):
        directory = fixture('verified-concurrent-winner')
        child = Mock(pid=123)
        child.poll.return_value = None
        record = {'pid': 456, 'version': launcher.__version__, 'source_id': launcher.service_source_id()}
        with patch.object(launcher, 'verified_server', side_effect=[None, record]), \
                patch.object(launcher, 'process_identity', return_value='verified-caller'), \
                patch.object(launcher.subprocess, 'Popen', return_value=child), \
                patch.object(launcher, 'shutdown') as shutdown:
            self.assertEqual(launcher._ensure_server(directory, 0), (record, True))
        child.terminate.assert_not_called()
        child.kill.assert_not_called()
        shutdown.assert_not_called()

    def test_alive_server_with_missing_retained_identity_is_not_trusted_or_restarted(self):
        directory = fixture('missing-server-identity')
        (directory / 'server.json').write_text(json.dumps({'pid': os.getpid(), 'identity': None}))
        with patch.object(launcher, 'process_identity', return_value='ps:verified-live'), \
                patch.object(launcher.subprocess, 'Popen') as spawn, patch.object(launcher, '_request') as request:
            with self.assertRaisesRegex(ValueError, 'identity cannot be verified'):
                launcher._ensure_server(directory, 0)
        spawn.assert_not_called()
        request.assert_not_called()

    def test_server_cannot_publish_null_identity_or_start_serving(self):
        directory = fixture('server-start-observation')
        original = {'original-record': 'retained'}
        (directory / 'server.json').write_text(json.dumps(original))
        for failure in (None, processes.ProcessObservationError('inspection denied')):
            with self.subTest(failure=failure):
                with patch.object(processes, 'strict_process_identity', return_value=None, side_effect=failure), \
                        patch.object(server, 'Reprise') as app, patch.object(server, 'LocalServer') as listener:
                    with self.assertRaises(processes.ProcessObservationError):
                        server.serve(directory, port=0)
                app.assert_not_called()
                listener.assert_not_called()
                self.assertEqual(json.loads((directory / 'server.json').read_text()), original)

    def test_shutdown_cannot_confirm_exit_after_observation_becomes_unavailable(self):
        record = {'pid': 123, 'identity': 'known', 'instance_id': 'known-instance'}
        with patch.object(launcher, 'verified_server', return_value=record), \
                patch.object(launcher, '_request', side_effect=[{'token': 'token'}, {'stopped': True}]), \
                patch.object(launcher, 'process_identity', side_effect=processes.ProcessObservationError('inspection denied')):
            with self.assertRaisesRegex(processes.ProcessObservationError, 'inspection denied'):
                launcher.shutdown('/unused')

