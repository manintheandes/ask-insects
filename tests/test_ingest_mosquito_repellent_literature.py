import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from scripts.ingest_mosquito_repellent_literature import ingest_mosquito_repellent_literature
from tests.test_mosquito_repellent_literature_source import CROSSREF, ESEARCH, ESUMMARY


class IngestMosquitoRepellentLiteratureTests(unittest.TestCase):
    def test_ingest_updates_repellent_lane_without_removing_other_literature(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="literature:openalex:W123",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Picaridin repellency in mosquito landing assays",
                        text="Aedes aegypti picaridin repellency paper doi 10.1000/repellent.2",
                        species="Aedes aegypti",
                        url="https://doi.org/10.1000/repellent.2",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_literature_openalex",
                            locator="openalex#W123",
                            retrieved_at="2026-05-25T00:00:00Z",
                        ),
                        payload={"doi": "10.1000/repellent.2"},
                    )
                ]
            )

            def fake_fetch_json(url):
                if "esearch.fcgi" in url:
                    return ESEARCH
                if "esummary.fcgi" in url:
                    return ESUMMARY
                if "api.crossref.org" in url:
                    return CROSSREF
                raise AssertionError(url)

            result = ingest_mosquito_repellent_literature(
                artifact_dir=artifact_dir,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-25T00:00:00Z",
                pubmed_max_results=20,
                crossref_max_results=20,
                page_size=10,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["source"], "mosquito_repellent_literature")
            # record_count includes source_gap records persisted by runner; anchor non-gap
            self.assertGreaterEqual(result["record_count"], 3)
            self.assertEqual(result["refresh_record_count"], 3)
            self.assertEqual(result["canonical_literature_row_count"], 1)
            self.assertEqual(result["already_indexed_count"], 1)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select source, lane, count(*) as n from records group by source, lane order by source, lane",
                limit=100,
            )
            counts = {(row["source"], row["lane"]): row["n"] for row in rows}
            self.assertEqual(counts[("aedes_literature_openalex", "literature")], 1)
            # literature lane has the 3 fetched records; runner may also add source_gap records
            self.assertGreaterEqual(counts[("mosquito_repellent_literature", "literature")], 3)
            receipt = (artifact_dir / "source_receipt.json").read_text(encoding="utf-8")
            self.assertIn("mosquito_repellent_literature", receipt)
            self.assertIn("repellent_terms", receipt)

    def test_failed_refresh_preserves_existing_repellent_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch_json(url):
                if "esearch.fcgi" in url:
                    return ESEARCH
                if "esummary.fcgi" in url:
                    return ESUMMARY
                if "api.crossref.org" in url:
                    return CROSSREF
                raise AssertionError(url)

            ingest_mosquito_repellent_literature(
                artifact_dir=artifact_dir,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-25T00:00:00Z",
            )
            failed = ingest_mosquito_repellent_literature(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-25T01:00:00Z",
            )

            self.assertFalse(failed["ok"])
            self.assertTrue(failed["preserved_existing"])
            # preserved_existing is the guard; record_count includes source_gap rows
            self.assertGreaterEqual(failed["record_count"], 3)


if __name__ == "__main__":
    unittest.main()
