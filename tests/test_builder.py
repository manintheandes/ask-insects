import json
import os
import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.builder import build_source_index


def fake_gbif_fetcher(url):
    if "/v2/species/match" in url:
        return {
            "usageKey": 1651891,
            "canonicalName": "Aedes aegypti",
            "rank": "SPECIES",
            "status": "ACCEPTED",
            "family": "Culicidae",
            "genus": "Aedes",
            "species": "Aedes aegypti",
        }
    if "/v1/occurrence/search" in url:
        return {
            "count": 1,
            "results": [
                {
                    "key": 444,
                    "species": "Aedes aegypti",
                    "country": "Brazil",
                    "eventDate": "2020-01-02",
                    "datasetName": "Example mosquito dataset",
                    "license": "CC_BY_4_0",
                }
            ],
        }
    raise AssertionError(f"unexpected URL: {url}")


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

    def test_build_source_index_combines_fixture_and_gbif_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            result = build_source_index(
                include_fixtures=True,
                include_gbif=True,
                fixture_path=Path("data/fixtures/mosquito_records.json"),
                artifact_dir=artifact_dir,
                gbif_species=["Aedes aegypti"],
                occurrence_limit=1,
                gbif_fetch_json=fake_gbif_fetcher,
                retrieved_at="2026-05-23T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertIn("mosquito_v1_fixtures", result["sources"])
            self.assertIn("gbif_api", result["sources"])
            self.assertGreaterEqual(result["record_count"], 9)
            self.assertEqual(result["gbif"]["taxon_keys"]["Aedes aegypti"], 1651891)

            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn("gbif_api", status["sources"])
            self.assertEqual(status["source_counts"]["gbif_api"], 2)

            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["gbif"]["requested_species"], ["Aedes aegypti"])
            self.assertTrue((artifact_dir / "raw" / "gbif" / "Aedes_aegypti_match.json").exists())


if __name__ == "__main__":
    unittest.main()
