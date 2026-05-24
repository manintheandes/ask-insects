import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.builder import build_source_index
from tests.test_ncbi_genome_source import write_fake_ncbi_package


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


def fake_literature_fetcher(url):
    if "/topics" in url:
        return {
            "results": [
                {
                    "id": "https://openalex.org/T-AEDES",
                    "display_name": "Aedes aegypti vector biology",
                    "description": "Aedes aegypti mosquito papers",
                    "keywords": ["Aedes aegypti"],
                }
            ]
        }
    if "esearch.fcgi" in url:
        return {"esearchresult": {"idlist": ["123"]}}
    if "esummary.fcgi" in url:
        return {
            "result": {
                "uids": ["123"],
                "123": {
                    "uid": "123",
                    "title": "Aedes aegypti open literature record",
                    "elocationid": "doi: 10.1000/aedes-builder",
                },
            }
        }
    if "api.unpaywall.org" in url:
        return {
            "doi": "10.1000/aedes-builder",
            "is_oa": True,
            "best_oa_location": {
                "url_for_pdf": "https://example.org/aedes-builder.pdf",
                "license": "cc-by",
            },
        }
    if "/works" in url:
        return {
            "meta": {"count": 1, "next_cursor": None},
            "results": [
                {
                    "id": "https://openalex.org/WBUILDER",
                    "doi": "https://doi.org/10.1000/aedes-builder",
                    "display_name": "Aedes aegypti open literature record",
                    "publication_date": "2024-03-01",
                    "type": "article",
                    "abstract_inverted_index": {"Aedes": [0], "aegypti": [1], "builder": [2]},
                    "primary_location": {"source": {"display_name": "Journal of Mosquito Work"}},
                    "ids": {
                        "openalex": "https://openalex.org/WBUILDER",
                        "doi": "https://doi.org/10.1000/aedes-builder",
                    },
                    "primary_topic": {
                        "id": "https://openalex.org/T-AEDES",
                        "display_name": "Aedes aegypti vector biology",
                    },
                    "topics": [
                        {
                            "id": "https://openalex.org/T-AEDES",
                            "display_name": "Aedes aegypti vector biology",
                        }
                    ],
                }
            ],
        }
    raise AssertionError(f"unexpected URL: {url}")


def fake_literature_fetcher_without_pubmed(url):
    if "esearch.fcgi" in url or "esummary.fcgi" in url:
        raise AssertionError(f"unexpected PubMed URL: {url}")
    if "/topics" in url:
        return {"results": []}
    if "api.unpaywall.org" in url:
        return {"doi": "10.1000/aedes-skip-builder", "is_oa": False, "best_oa_location": None}
    if "/works" in url:
        return {
            "meta": {"count": 1, "next_cursor": None},
            "results": [
                {
                    "id": "https://openalex.org/WSKIPBUILDER",
                    "doi": "https://doi.org/10.1000/aedes-skip-builder",
                    "display_name": "Aedes aegypti skip PubMed builder record",
                    "publication_date": "2024-03-01",
                    "type": "article",
                    "abstract_inverted_index": {"Aedes": [0], "aegypti": [1], "builder": [2]},
                    "primary_location": {"source": {"display_name": "Journal of Mosquito Work"}},
                    "ids": {
                        "openalex": "https://openalex.org/WSKIPBUILDER",
                        "doi": "https://doi.org/10.1000/aedes-skip-builder",
                    },
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

    def test_builds_literature_source_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            result = build_source_index(
                include_fixtures=False,
                include_gbif=False,
                include_inaturalist=False,
                include_literature=True,
                artifact_dir=artifact_dir,
                literature_species="Aedes aegypti",
                literature_from_date="2020-01-01",
                literature_to_date="2026-05-23",
                literature_work_type="article",
                include_topic_discovery=True,
                literature_page_size=25,
                literature_delay_seconds=0,
                literature_max_works=1,
                literature_fetch_json=fake_literature_fetcher,
                literature_fetch_text=lambda url: "Aedes aegypti legal open full text",
                unpaywall_email="test@example.com",
                retrieved_at="2026-05-23T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertIn("aedes_literature_openalex", result["sources"])
            self.assertEqual(result["source_counts"]["aedes_literature_openalex"], 1)
            self.assertEqual(result["literature"]["species"], "Aedes aegypti")
            self.assertEqual(result["literature"]["from_date"], "2020-01-01")
            self.assertEqual(result["literature"]["to_date"], "2026-05-23")
            self.assertEqual(result["literature"]["work_type"], "article")
            self.assertEqual(result["literature"]["record_count"], 1)
            self.assertEqual(result["literature"]["fulltext_unit_count"], 1)
            self.assertEqual(result["literature"]["gap_count"], 0)
            self.assertIn("gaps_path", result["literature"])
            self.assertNotIn("gaps", result["literature"])
            self.assertTrue(result["literature"]["raw_artifacts"])
            self.assertTrue(result["literature"]["topic_search_results"])
            self.assertEqual(result["literature"]["accepted_topic_ids"], ["T-AEDES"])
            self.assertEqual(result["literature"]["inclusion_path_counts"]["title"], 1)
            self.assertEqual(result["literature"]["inclusion_path_counts"]["abstract"], 1)
            self.assertEqual(result["literature"]["inclusion_path_counts"]["topic"], 1)
            self.assertEqual(result["literature"]["doi_count"], 1)
            self.assertEqual(result["literature"]["unpaywall_queried_count"], 1)
            self.assertEqual(result["literature"]["open_fulltext_count"], 1)

            conn = sqlite3.connect(artifact_dir / "source_index.sqlite")
            record_row = conn.execute(
                "select record_id, source, lane from records where source = ?",
                ("aedes_literature_openalex",),
            ).fetchone()
            unit_row = conn.execute(
                "select record_id, text from literature_fulltext_units where record_id = ?",
                ("openalex:WBUILDER",),
            ).fetchone()
            conn.close()

            self.assertEqual(record_row, ("openalex:WBUILDER", "aedes_literature_openalex", "literature"))
            self.assertIsNotNone(unit_row)
            self.assertIn("legal open full text", unit_row[1])

            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            self.assertIn("aedes_literature_openalex", receipt["sources"])
            self.assertEqual(receipt["literature"]["page_count"], 1)
            self.assertEqual(receipt["literature"]["gaps_path"], (artifact_dir / "gaps.json").as_posix())
            self.assertNotIn("gaps", receipt["literature"])

    def test_live_literature_build_defaults_to_current_generated_at(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            result = build_source_index(
                include_fixtures=False,
                include_gbif=False,
                include_inaturalist=False,
                include_literature=True,
                artifact_dir=artifact_dir,
                include_topic_discovery=True,
                literature_page_size=25,
                literature_delay_seconds=0,
                literature_max_works=1,
                literature_fetch_json=fake_literature_fetcher,
                literature_fetch_text=lambda url: "Aedes aegypti legal open full text",
                unpaywall_email="test@example.com",
            )

            self.assertNotEqual(result["generated_at"], "2026-05-23T00:00:00Z")
            self.assertEqual(result["literature"]["to_date"], result["generated_at"].split("T", 1)[0])

    def test_build_source_index_passes_skip_pubmed_to_literature_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            result = build_source_index(
                include_fixtures=False,
                include_gbif=False,
                include_inaturalist=False,
                include_literature=True,
                artifact_dir=artifact_dir,
                literature_species="Aedes aegypti",
                literature_from_date="2020-01-01",
                literature_to_date="2026-05-23",
                literature_delay_seconds=0,
                literature_fetch_json=fake_literature_fetcher_without_pubmed,
                unpaywall_email="test@example.com",
                skip_pubmed=True,
                retrieved_at="2026-05-23T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertTrue(result["literature"]["skip_pubmed"])
            self.assertEqual(result["literature"]["pubmed_skipped_count"], 1)

            gaps = json.loads((artifact_dir / "gaps.json").read_text(encoding="utf-8"))
            self.assertEqual(
                [gap["reason"] for gap in gaps if gap.get("reason") == "pubmed_skipped"],
                ["pubmed_skipped"],
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


if __name__ == "__main__":
    unittest.main()
