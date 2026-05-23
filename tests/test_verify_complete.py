import subprocess
import sys
import unittest


class VerifyCompleteTests(unittest.TestCase):
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
