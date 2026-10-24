"""An optional screenshot bundle rejects video before running project code."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from reprise.capture import CaptureService


class BundleCaptureCapabilityTests(unittest.TestCase):
    def setUp(self):
        artifacts = Path(__file__).resolve().parents[1] / 'work/test-artifacts'
        artifacts.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix='bundle-capture-capabilities-', dir=artifacts))
        self.resources = self.root / 'Resources'
        (self.resources / 'runtime').mkdir(parents=True)
        (self.resources / 'runtime/manifest.json').write_text(json.dumps({
            'schema': 1, 'paths': {}, 'capabilities': {'video_recording': False},
        }))
        self.runtime = Mock()
        self.capture = CaptureService(self.root / 'state', self.runtime)
        self.repository = Mock()
        self.repository.resolve.return_value = 'a' * 40

    def test_video_is_rejected_before_repository_runtime_or_worker_is_used(self):
        with patch.dict(os.environ, {'REPRISE_BUNDLE_RESOURCES': str(self.resources)}), \
                patch('reprise.capture.launch_owned') as worker, \
                patch('reprise.desktop_bundle.os.walk', side_effect=AssertionError('No tree scan')):
            with self.assertRaises(ValueError) as raised:
                self.capture.capture(self.repository, 'project', 'HEAD', {
                    'adapter': 'static-web', 'captures': [{'id': 'main', 'record': True}],
                })
        message = str(raised.exception)
        self.assertIn('不包含录像组件', message)
        self.assertIn('does not include video recording', message)
        self.assertNotIn('npx', message)
        self.repository.resolve.assert_not_called()
        self.runtime.start.assert_not_called()
        worker.assert_not_called()
        self.assertEqual(list(self.capture.directory.iterdir()), [])

    def test_screenshots_and_unbundled_video_keep_the_capture_path(self):
        cases = [('bundled screenshot', str(self.resources), False),
                 ('source video', '', True)]
        for name, resources, record in cases:
            with self.subTest(name=name):
                self.runtime.reset_mock()
                self.runtime.start.side_effect = RuntimeError('Reached existing runtime path')
                with patch.dict(os.environ, {'REPRISE_BUNDLE_RESOURCES': resources, 'REPRISE_NODE': '/test/node'}):
                    result = self.capture.capture(self.repository, name, 'HEAD', {
                        'adapter': 'static-web', 'captures': [{'id': 'main', 'record': record}],
                    })
                self.runtime.start.assert_called_once()
                self.assertEqual(result['status'], 'failed')
                self.assertEqual(result['errors'][0]['error'], 'Reached existing runtime path')


if __name__ == '__main__':
    unittest.main()
