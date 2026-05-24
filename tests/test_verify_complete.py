import subprocess
import sys
import unittest

from scripts import verify_complete


class VerifyCompleteTests(unittest.TestCase):
    def test_literature_source_map_gate_passes_without_network(self):
        verify_complete.check_literature_source_map()
        self.assertIn("tests.test_literature_source", verify_complete.UNIT_TEST_MODULES)

    def test_verify_complete_enforces_atomic_source_replacement(self):
        verify_complete.check_atomic_source_replacement()

    def test_verify_complete_requires_open_source_boundary(self):
        required_files = set(verify_complete.REQUIRED_FILES)

        self.assertIn("LICENSE", required_files)
        self.assertIn("NOTICE", required_files)
        self.assertIn("THIRD_PARTY_DATA.md", required_files)
        verify_complete.check_open_source_boundary()

    def test_verify_complete_requires_open_insects_public_identity(self):
        required_files = set(verify_complete.REQUIRED_FILES)

        self.assertIn(
            "docs/superpowers/specs/2026-05-24-open-insects-public-identity-design.md",
            required_files,
        )
        self.assertIn(
            "docs/superpowers/plans/2026-05-24-open-insects-public-identity.md",
            required_files,
        )
        verify_complete.check_public_identity()

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

    def test_verify_complete_requires_vectorbase_genomics_lane(self):
        required_files = set(verify_complete.REQUIRED_FILES)
        unit_modules = set(verify_complete.UNIT_TEST_MODULES)

        self.assertIn("askinsects/sources/vectorbase_genomics.py", required_files)
        self.assertIn("scripts/ingest_vectorbase_genomics.py", required_files)
        self.assertIn("tests/test_vectorbase_genomics_source.py", required_files)
        self.assertIn("tests/test_ingest_vectorbase_genomics.py", required_files)
        self.assertIn(
            "docs/superpowers/specs/2026-05-24-aedes-vectorbase-genomics-lane-design.md",
            required_files,
        )
        self.assertIn(
            "docs/superpowers/plans/2026-05-24-aedes-vectorbase-genomics-lane.md",
            required_files,
        )
        self.assertIn("tests.test_vectorbase_genomics_source", unit_modules)
        self.assertIn("tests.test_ingest_vectorbase_genomics", unit_modules)

    def test_verify_complete_requires_neurobiology_lane(self):
        required_files = set(verify_complete.REQUIRED_FILES)
        unit_modules = set(verify_complete.UNIT_TEST_MODULES)

        self.assertIn("askinsects/sources/neurobiology.py", required_files)
        self.assertIn("scripts/ingest_neurobiology_sources.py", required_files)
        self.assertIn("tests/test_neurobiology_source.py", required_files)
        self.assertIn(
            "docs/superpowers/specs/2026-05-23-aedes-aegypti-neurobiology-lane-design.md",
            required_files,
        )
        self.assertIn(
            "docs/superpowers/specs/2026-05-24-aedes-neurobiology-deep-source-completion-design.md",
            required_files,
        )
        self.assertIn(
            "docs/superpowers/specs/2026-05-23-neurobiology-gap-closure-design.md",
            required_files,
        )
        self.assertIn(
            "docs/superpowers/plans/2026-05-23-aedes-aegypti-neurobiology-lane.md",
            required_files,
        )
        self.assertIn(
            "docs/superpowers/plans/2026-05-24-aedes-neurobiology-deep-source-completion.md",
            required_files,
        )
        self.assertIn(
            "docs/superpowers/plans/2026-05-23-neurobiology-gap-closure.md",
            required_files,
        )
        self.assertIn("askinsects/voxels.py", required_files)
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
