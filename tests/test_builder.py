import json
import os
import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.builder import build_source_index
from askinsects.sources.neurobiology import NEUROBIOLOGY_SOURCE_ID
from tests.test_ncbi_genome_source import write_fake_ncbi_package
from tests.test_neurobiology_source import write_fake_neurobiology_artifacts


def fake_inaturalist_fetcher(url):
    if "/v1/observations" in url:
        return {
            "total_results": 1,
            "results": [
                {
                    "id": 12345,
                    "uri": "https://www.inaturalist.org/observations/12345",
                    "observed_on": "2021-02-03",
                    "place_guess": "Rio de Janeiro, Brazil",
                    "license_code": "cc-by",
                    "taxon": {"name": "Aedes aegypti"},
                    "photos": [
                        {
                            "id": 99,
                            "url": "https://static.inaturalist.org/photos/1/medium.jpg",
                            "license_code": "cc-by",
                        }
                    ],
                }
            ],
        }
    raise AssertionError(f"unexpected URL: {url}")


def fake_gbif_fetcher(url):
    if "/v1/species/match" in url:
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

    def test_build_source_index_combines_fixture_and_inaturalist_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            result = build_source_index(
                include_fixtures=True,
                include_gbif=False,
                include_inaturalist=True,
                fixture_path=Path("data/fixtures/mosquito_records.json"),
                artifact_dir=artifact_dir,
                inaturalist_species=["Aedes aegypti"],
                inaturalist_place="Brazil",
                observation_limit=1,
                page_size=2,
                delay_seconds=0,
                inaturalist_fetch_json=fake_inaturalist_fetcher,
                retrieved_at="2026-05-23T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertIn("inaturalist_api", result["sources"])
            self.assertEqual(result["source_counts"]["inaturalist_api"], 2)
            self.assertEqual(result["inaturalist"]["requested_species"], ["Aedes aegypti"])
            self.assertEqual(result["inaturalist"]["place"], "Brazil")

            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn("inaturalist_api", status["sources"])

            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["inaturalist"]["observation_limit"], 1)
            self.assertEqual(receipt["inaturalist"]["page_size"], 2)
            self.assertEqual(receipt["inaturalist"]["delay_seconds"], 0)
            self.assertEqual(receipt["inaturalist"]["total_results"]["Aedes aegypti"], 1)
            self.assertTrue(
                (artifact_dir / "raw" / "inaturalist" / "Aedes_aegypti_Brazil_page_001.json").exists()
            )

    def test_build_source_index_combines_fixture_and_ncbi_genome_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            artifact_dir = tmp_path / "mosquito-v1"
            package_dir = write_fake_ncbi_package(tmp_path)

            result = build_source_index(
                include_fixtures=True,
                include_gbif=False,
                include_inaturalist=False,
                include_ncbi_genome=True,
                fixture_path=Path("data/fixtures/mosquito_records.json"),
                artifact_dir=artifact_dir,
                genome_package_dir=package_dir,
                genome_assembly_accession="GCF_002204515.2",
                retrieved_at="2026-05-23T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertIn("ncbi_datasets_genome", result["sources"])
            self.assertEqual(result["ncbi_genome"]["assembly_accession"], "GCF_002204515.2")
            self.assertGreaterEqual(result["source_counts"]["ncbi_datasets_genome"], 6)
            self.assertEqual(result["lanes"]["genome_assemblies"], 1)
            self.assertEqual(result["lanes"]["genes"], 1)
            self.assertEqual(result["lanes"]["transcripts"], 1)
            self.assertGreaterEqual(result["lanes"]["genome_features"], 1)
            self.assertEqual(result["lanes"]["proteins"], 2)

            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn("ncbi_datasets_genome", status["sources"])

            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["ncbi_genome"]["package_dir"], package_dir.as_posix())

    def test_build_source_index_combines_fixture_and_neurobiology_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            artifact_dir = tmp_path / "mosquito-v1"
            neurobiology_artifact_dir = write_fake_neurobiology_artifacts(tmp_path)

            result = build_source_index(
                include_fixtures=True,
                include_gbif=False,
                include_inaturalist=False,
                include_ncbi_genome=False,
                include_neurobiology=True,
                fixture_path=Path("data/fixtures/mosquito_records.json"),
                artifact_dir=artifact_dir,
                neurobiology_artifact_dir=neurobiology_artifact_dir,
                retrieved_at="2026-05-23T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertIn(NEUROBIOLOGY_SOURCE_ID, result["sources"])
            self.assertGreaterEqual(result["source_counts"][NEUROBIOLOGY_SOURCE_ID], 6)
            self.assertGreaterEqual(result["lanes"]["neurobiology"], 6)
            self.assertEqual(result["neurobiology"]["artifact_dir"], neurobiology_artifact_dir.as_posix())
            self.assertGreaterEqual(result["neurobiology"]["gap_count"], 2)

            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn(NEUROBIOLOGY_SOURCE_ID, status["sources"])

            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["neurobiology"]["source_id"], NEUROBIOLOGY_SOURCE_ID)
            self.assertEqual(receipt["neurobiology"]["artifact_dir"], neurobiology_artifact_dir.as_posix())


if __name__ == "__main__":
    unittest.main()
