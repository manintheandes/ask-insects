import subprocess
import sys
import unittest

from scripts import verify_complete


class VerifyCompleteTests(unittest.TestCase):
    def test_literature_source_map_gate_passes_without_network(self):
        verify_complete.check_literature_source_map()
        self.assertIn("tests.test_literature_source", verify_complete.UNIT_TEST_MODULES)

    def test_verify_complete_gate_passes(self):
        result = subprocess.run(
            [sys.executable, "scripts/verify_complete.py"],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("verify_complete ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
