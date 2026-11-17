import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ci_artifacts', ROOT / 'scripts/collect_ci_artifacts.py')
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


class CiArtifactsTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / 'work/test-artifacts'
        parent.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix='ci-artifacts-', dir=parent))
        self.source = self.root / 'input'
        self.source.mkdir()
        self.output = self.root / 'output'

    def write(self, name, data=b'evidence'):
        target = self.source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def test_success_keeps_reports_and_logs_without_installations_or_test_snapshots(self):
        self.write('ci/python.log')
        self.write('distribution-one/report.json', b'{}')
        self.write('distribution-one/source/report.json', b'private copied input')
        self.write('distribution-one/venv/install.log', b'copied runtime')
        self.write('snapshot.json', b'test fixture state')
        self.write('screen.png', b'not needed on success')
        self.write('ci-artifacts-fixture/input/report.json', b'the collector test fixture')
        report = ci.collect(self.source, self.output, 'success')
        self.assertEqual({f['path'] for f in report['files']},
                         {'ci/python.log', 'distribution-one/report.json'})
        self.assertTrue((self.source / 'screen.png').exists())

    def test_failure_keeps_visual_evidence_and_reports_but_never_recursive_archives(self):
        self.write('failure/screen.png')
        self.write('failure/video.webm')
        self.write('ci/reprise-skill.zip')
        self.write('ci-upload/reprise-diagnostics.tar.gz')
        report = ci.collect(self.source, self.output, 'failure', include_packages=True)
        self.assertEqual({f['path'] for f in report['files']},
                         {'failure/screen.png', 'failure/video.webm'})

    def test_packages_are_explicit_success_only_and_listed_with_hashes(self):
        self.write('ci/reprise-skill.zip')
        self.write('ci/reprise-workbuddy.zip')
        self.write('another.zip')
        report = ci.collect(self.source, self.output, 'success', include_packages=True)
        self.assertEqual(len(report['files']), 2)
        self.assertTrue(all(len(f['sha256']) == 64 for f in report['files']))

    def test_logs_are_preserved_in_full_without_truncation(self):
        path = self.write('ci/python.log', b'a' * (1024 * 1024 + 1) + b'final failure')
        before = path.read_bytes()
        report = ci.collect(self.source, self.output, 'failure')
        self.assertFalse(report['files'][0]['truncated'])
        self.assertEqual((self.output / 'ci/python.log').stat().st_size, len(before))
        self.assertTrue((self.output / 'ci/python.log').read_bytes().endswith(b'final failure'))
        self.assertEqual(path.read_bytes(), before)

    def test_no_task_file_count_or_media_size_limit(self):
        for index in range(205):
            self.write('logs/%03d.log' % index)
        media = b'complete frame' * (400000)
        self.write('failure/large.png', media)
        report = ci.collect(self.source, self.output, 'failure')
        self.assertEqual(len(report['files']), 206)
        self.assertEqual((self.output / 'failure/large.png').read_bytes(), media)
        self.assertNotIn('limitBytes', report)

    def test_symlinks_cannot_copy_data_outside_test_artifacts(self):
        outside = self.root / 'outside.log'
        outside.write_text('private')
        (self.source / 'escape.log').symlink_to(outside)
        (self.source / 'linked').symlink_to(self.root, target_is_directory=True)
        report = ci.collect(self.source, self.output, 'failure')
        self.assertEqual(report['files'], [])
        self.assertEqual(outside.read_text(), 'private')

    def test_output_cannot_overwrite_input_or_a_previous_collection(self):
        for output in [self.source, self.source / 'nested', self.root]:
            with self.assertRaises(ValueError):
                ci.collect(self.source, output, 'success')
        ci.collect(self.source, self.output, 'success')
        before = (self.output / 'ci-artifact-manifest.json').read_bytes()
        with self.assertRaises(FileExistsError):
            ci.collect(self.source, self.output, 'success')
        self.assertEqual((self.output / 'ci-artifact-manifest.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
