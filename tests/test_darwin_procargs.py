"""Darwin procargs races must not turn confirmed exits into cleanup failures."""
import ctypes
import errno
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from reprise import processes


class DarwinProcargsTests(unittest.TestCase):
    def failed_libc(self, code=errno.EIO):
        def fail(*args):
            ctypes.set_errno(code)
            return -1
        return Mock(sysctl=Mock(side_effect=fail))

    def test_exit_during_environment_read_is_confirmed_before_ignoring_eio(self):
        for current in (None, {'zombie': True}):
            with self.subTest(current=current), \
                    patch.object(processes.sys, 'platform', 'darwin'), \
                    patch.object(processes.ctypes, 'CDLL', return_value=self.failed_libc()), \
                    patch.object(processes, '_inspect_or_confirm_exit', return_value=current) as inspect, \
                    patch.object(processes.os, 'killpg') as signal:
                self.assertIsNone(processes._owner_marker(123))
                inspect.assert_called_once_with(123)
                signal.assert_not_called()

    def test_exec_map_race_recovers_the_actual_marker(self):
        marker = 'a' * 32
        raw = (1).to_bytes(4, sys.byteorder) + b'/tool\0\0tool\0' + \
              processes.OWNER_ENV.encode() + b'=' + marker.encode() + b'\0'
        calls = []
        def read(mib, count, data, size, new, newlen):
            calls.append(1)
            if len(calls) == 1:
                ctypes.set_errno(errno.EIO)
                return -1
            ctypes.memmove(data, raw, len(raw))
            ctypes.cast(size, ctypes.POINTER(ctypes.c_size_t)).contents.value = len(raw)
            return 0
        with patch.object(processes.sys, 'platform', 'darwin'), \
                patch.object(processes.ctypes, 'CDLL', return_value=Mock(sysctl=read)), \
                patch.object(processes, '_inspect_or_confirm_exit', return_value={'zombie': False}), \
                patch.object(processes.time, 'sleep'):
            self.assertEqual(processes._owner_marker(123), marker)
        self.assertEqual(len(calls), 2)

    def test_persistent_live_process_read_failure_stays_unconfirmed(self):
        libc = self.failed_libc()
        with patch.object(processes.sys, 'platform', 'darwin'), \
                patch.object(processes.ctypes, 'CDLL', return_value=libc), \
                patch.object(processes, '_inspect_or_confirm_exit', return_value={'zombie': False}), \
                patch.object(processes.time, 'monotonic', side_effect=[0, 1]), \
                patch.object(processes.os, 'killpg') as signal:
            with self.assertRaisesRegex(processes.ProcessObservationError, r'KERN_PROCARGS2.*PID 123.*\[Errno 5\]'):
                processes._owner_marker(123)
            signal.assert_not_called()
        self.assertEqual(libc.sysctl.call_count, 1)

    def test_other_kernel_errors_are_not_treated_as_exits(self):
        with patch.object(processes.sys, 'platform', 'darwin'), \
                patch.object(processes.ctypes, 'CDLL', return_value=self.failed_libc(errno.ENOMEM)), \
                patch.object(processes, '_inspect_or_confirm_exit') as inspect:
            with self.assertRaisesRegex(processes.ProcessObservationError, 'KERN_PROCARGS2'):
                processes._owner_marker(123)
            inspect.assert_not_called()


@unittest.skipUnless(sys.platform == 'darwin', 'Darwin kernel process lifecycle')
class DarwinCleanupRaceTests(unittest.TestCase):
    def test_stale_live_snapshot_of_exited_unrelated_process_does_not_poison_tree(self):
        root = Path(__file__).resolve().parents[1] / 'work/test-artifacts'
        root.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix='darwin-procargs-', dir=root))
        with (folder / 'child.log').open('wb') as log:
            tree = processes.launch_owned([sys.executable, '-c', 'import time; time.sleep(60)'],
                                          folder, dict(os.environ), log, folder / 'ownership.json')
        unrelated = subprocess.Popen(['/usr/bin/true'])
        try:
            tree.close()
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                current = processes._process_info(unrelated.pid)
                if current and current['zombie']:
                    break
                time.sleep(.01)
            self.assertTrue(current and current['zombie'], 'Retain the actual unreaped zombie PID')
            # ps observed it alive; it exits before its environment is read.
            table = processes._process_table()
            table[unrelated.pid] = dict(current, zombie=False)
            libc = ctypes.CDLL(None, use_errno=True)
            failed_reads = []
            def read(mib, *args):
                if mib[2] == unrelated.pid:
                    failed_reads.append(mib[2])
                    ctypes.set_errno(errno.EIO)
                    return -1
                return libc.sysctl(mib, *args)
            with patch.object(processes, '_process_table', return_value=table), \
                    patch.object(processes.ctypes, 'CDLL', return_value=Mock(sysctl=read)):
                self.assertTrue(tree.refresh())
            self.assertTrue(failed_reads, 'The regression must exercise the kernel error')
            self.assertNotIn('observation_error', json.loads(tree.record_path.read_text()))
            tree.terminate(timeout=.1)
            self.assertIsNotNone(tree.process.poll())
            self.assertEqual(json.loads(tree.record_path.read_text())['status'], 'stopped')
        finally:
            unrelated.wait(timeout=3)
            tree.terminate(timeout=.1)
