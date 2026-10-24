"""The onboarding example must retain diagnostics when a CLI is interrupted."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from test_runtime import fixture


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('reprise_demo', ROOT / 'scripts/demo_workflow.py')
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


class DemoWorkflowTests(unittest.TestCase):
    def test_timeout_retains_the_command_partial_output_and_generated_inputs(self):
        destination = fixture('demo-timeout') / 'sample'
        error = subprocess.TimeoutExpired(['python3', 'run.py'], 120,
                                          output=b'partial stdout\n', stderr=b'partial stderr\n')
        with patch.object(demo.subprocess, 'run', side_effect=error):
            with self.assertRaises(subprocess.TimeoutExpired):
                demo.run_demo(destination, ROOT / 'run.py')
        receipt = json.loads((destination / 'commands/01-save-first.json').read_text())
        self.assertTrue(receipt['timed_out'])
        self.assertIsNone(receipt['returncode'])
        self.assertEqual(receipt['stdout'], 'partial stdout\n')
        self.assertEqual(receipt['stderr'], 'partial stderr\n')
        self.assertIn(str(destination / 'reprise-data'), receipt['argv'])
        failure = json.loads((destination / 'failure.json').read_text())
        self.assertEqual(failure['steps'][0]['step'], '01-save-first')
        self.assertTrue((destination / 'sample-folder/draft.txt').is_file())
        self.assertFalse((destination / 'summary.json').exists())


if __name__ == '__main__':
    unittest.main()
