from pathlib import Path
import threading
import time
import unittest

from reprise.jobs import Jobs
from reprise.storage import write_json
from test_runtime import fixture


class JobsTests(unittest.TestCase):
    def test_second_service_does_not_interrupt_live_job_and_serializes_project(self):
        directory = fixture('jobs-shared')
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
        directory = fixture('jobs-interrupted')
        identifier = 'a' * 24
        write_json(Path(directory) / 'jobs' / (identifier + '.json'), {'id': identifier, 'status': 'running', 'owner_pid': 999999999, 'owner_identity': 'gone'})
        jobs = Jobs(directory)
        try:
            self.assertEqual(jobs.get(identifier)['status'], 'failed')
        finally:
            jobs.close()

    def test_active_jobs_are_not_hidden_by_recent_completed_history(self):
        directory = fixture('jobs-history')
        jobs = Jobs(directory)
        event = threading.Event()
        job = jobs.submit('project', 'test', lambda: event.wait(5))
        try:
            for n in range(35):
                identifier = '%024x' % n
                write_json(jobs.directory / (identifier + '.json'), {
                    'id': identifier, 'status': 'complete', 'created_at': '9999-%02d' % n})
            visible = jobs.list()
            self.assertIn(job['id'], [item['id'] for item in visible])
            self.assertEqual(len(visible), 31)
            # A long-running old job finishing now must be reviewable.
            identifier = 'f' * 24
            write_json(jobs.directory / (identifier + '.json'), {
                'id': identifier, 'status': 'complete', 'created_at': '2000', 'finished_at': '9999-99'})
            self.assertIn(identifier, [item['id'] for item in jobs.list()])
        finally:
            event.set()
            jobs.close()
        self.assertFalse(jobs.watcher.is_alive())
