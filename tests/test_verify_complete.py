import subprocess
import sys
import unittest

from scripts import verify_complete


class VerifyCompleteTests(unittest.TestCase):
    def test_literature_source_map_gate_passes_without_network(self):
        verify_complete.check_literature_source_map()
        self.assertIn("tests.test_literature_source", verify_complete.UNIT_TEST_MODULES)

    def test_verify_complete_requires_ncbi_genome_lane(self):
        required_files = set(verify_complete.REQUIRED_FILES)
        unit_modules = set(verify_complete.UNIT_TEST_MODULES)

        self.assertIn("askinsects/sources/ncbi_genome.py", required_files)
        self.assertIn("tests/test_ncbi_genome_source.py", required_files)
        self.assertIn(
            "docs/superpowers/specs/2026-05-23-aedes-aegypti-genomics-lane-design.md",
            required_files,
        )
        self.assertIn(
            "docs/superpowers/plans/2026-05-23-aedes-aegypti-genomics-lane.md",
            required_files,
        )
        self.assertIn("tests.test_ncbi_genome_source", unit_modules)

    def test_verify_complete_requires_neurobiology_lane(self):
        required_files = set(verify_complete.REQUIRED_FILES)
        unit_modules = set(verify_complete.UNIT_TEST_MODULES)

        self.assertIn("askinsects/sources/neurobiology.py", required_files)
        self.assertIn("tests/test_neurobiology_source.py", required_files)
        self.assertIn(
            "docs/superpowers/specs/2026-05-23-aedes-aegypti-neurobiology-lane-design.md",
            required_files,
        )
        self.assertIn(
            "docs/superpowers/plans/2026-05-23-aedes-aegypti-neurobiology-lane.md",
            required_files,
        )
        self.assertIn("tests.test_neurobiology_source", unit_modules)

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
