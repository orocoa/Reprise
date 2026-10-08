from pathlib import Path
import tempfile
import threading
import time
import unittest

from reprise.jobs import Jobs
from reprise.storage import write_json


class JobsTests(unittest.TestCase):
    def test_second_service_does_not_interrupt_live_job_and_serializes_project(self):
        with tempfile.TemporaryDirectory() as directory:
            one = Jobs(directory); event = threading.Event()
            job = one.submit('project', 'test', lambda: (event.wait(3), {'ok': True})[1])
            two = Jobs(directory)
            try:
                self.assertIn(two.get(job['id'])['status'], ('queued', 'running'))
                with self.assertRaises(ValueError): two.submit('project', 'other', lambda: {})
                event.set()
                one.close()
                self.assertEqual(two.get(job['id'])['status'], 'complete')
            finally:
                event.set(); two.close()

    def test_interrupted_owner_is_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            identifier = 'a' * 24
            write_json(Path(directory) / 'jobs' / (identifier + '.json'), {'id': identifier, 'status': 'running', 'owner_pid': 999999999, 'owner_identity': 'gone'})
            jobs = Jobs(directory)
            self.assertEqual(jobs.get(identifier)['status'], 'failed')
            jobs.close()
