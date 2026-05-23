import json
import os
import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index


class BuilderTests(unittest.TestCase):
    def test_build_fixture_index_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            result = build_fixture_index(
                fixture_path=Path("data/fixtures/mosquito_records.json"),
                artifact_dir=artifact_dir,
            )

            self.assertTrue(result["ok"])
            self.assertTrue((artifact_dir / "source_index.sqlite").exists())
            self.assertTrue((artifact_dir / "source_status.json").exists())
            self.assertTrue((artifact_dir / "source_receipt.json").exists())
            self.assertTrue((artifact_dir / "gaps.json").exists())

            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["source_id"], "mosquito_v1_fixtures")
            self.assertTrue(status["fully_parsed"])
            self.assertEqual(status["gap_count"], 0)

    def test_build_fixture_index_defaults_work_from_other_cwd(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            artifact_dir = tmp_path / "artifacts"
            try:
                os.chdir(tmp_path)
                result = build_fixture_index(artifact_dir=artifact_dir)
            finally:
                os.chdir(original_cwd)

            self.assertTrue(result["ok"])
            self.assertTrue((artifact_dir / "source_index.sqlite").exists())
            self.assertTrue((artifact_dir / "source_status.json").exists())


if __name__ == "__main__":
    unittest.main()
