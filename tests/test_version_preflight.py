"""Impact checks preserve every synthetic version; no deletion is executed."""
import os
import unittest

import test_version_deletion as deletion_fixture


class VersionPreflightTests(unittest.TestCase):
    def setUp(self):
        self.sample = deletion_fixture.VersionDeletionTests()
        self.sample.setUp()

    def tearDown(self):
        self.sample.assert_sources_unchanged()
        self.sample.tearDown()

    def test_project_and_other_project_counts_have_distinct_scopes(self):
        s = self.sample
        plan = s.plan(s.versions[0])
        self.assertEqual(plan['project_versions_before'], 3)
        self.assertEqual(plan['project_versions_retained'], 2)
        self.assertEqual(plan['other_versions_retained'], 1)
        self.assertEqual(plan['other_projects_protected'], 1)
        self.assertEqual(plan['retained_versions'], 3)

    def test_joint_check_keeps_project_and_library_totals_consistent(self):
        s = self.sample
        plan = s.plan(*s.versions[:2])
        self.assertEqual(plan['project_versions_retained'], 1)
        self.assertEqual(plan['other_versions_retained'], 1)
        self.assertEqual(plan['retained_versions'], 2)
        self.assertEqual(set(s.versions), {c['sha'] for c in s.app.projects.repository(s.project).history()['commits']})
        self.assertFalse(list((s.app.directory / 'version-deletions').glob('*.receipt.json')))

    def test_all_selected_still_protects_other_projects(self):
        s = self.sample
        plan = s.plan(*s.versions)
        self.assertEqual(plan['project_versions_retained'], 0)
        self.assertEqual(plan['other_versions_retained'], 1)
        self.assertEqual(plan['retained_versions'], 1)
        self.assertGreater(plan['shared_content_bytes'], 0)
        self.assertEqual(len(s.app.projects.repository(s.project).history()['commits']), 3)

    def test_zero_exclusive_content_still_reports_history_state_loss(self):
        s = self.sample
        path = s.source / 'shared.bin'
        stamp = path.stat()
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 1_000_000_000))
        duplicate = s.app.projects.snapshot(s.project, 'Same contents, different file time')['sha']
        # The fixture source-change expectation includes this deliberate synthetic edit.
        s.source_before = deletion_fixture.source_state(s.source)
        plan = s.plan(duplicate)
        self.assertEqual(plan['unique_content_bytes'], 0)
        self.assertTrue(plan['history_state_loss'])
        self.assertEqual(plan['project_versions_retained'], 3)
        self.assertEqual(len(s.app.projects.repository(s.project).history()['commits']), 4)
