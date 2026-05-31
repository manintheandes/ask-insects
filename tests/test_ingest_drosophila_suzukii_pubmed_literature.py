import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from scripts.ingest_drosophila_suzukii_pubmed_literature import ingest_drosophila_suzukii_pubmed_literature
from tests.test_drosophila_suzukii_pubmed_literature_source import ESEARCH, ESUMMARY


class IngestDrosophilaSuzukiiPubMedLiteratureTests(unittest.TestCase):
    def test_ingest_updates_pubmed_lane_without_removing_core_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd:openalex_literature:openalex:W1",
                        lane="literature",
                        source="drosophila_suzukii_core",
                        title="Management of spotted wing drosophila in berry systems",
                        text="Drosophila suzukii literature row doi 10.1000/swd-management",
                        species="Drosophila suzukii",
                        url="https://doi.org/10.1000/swd-management",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_core",
                            locator="openalex#W1",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={"doi": "10.1000/swd-management"},
                    )
                ]
            )

            def fake_fetch_json(url):
                if "esearch.fcgi" in url:
                    return ESEARCH
                if "esummary.fcgi" in url:
                    return ESUMMARY
                raise AssertionError(url)

            result = ingest_drosophila_suzukii_pubmed_literature(
                artifact_dir=artifact_dir,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-29T00:00:00Z",
                max_results=20,
                page_size=10,
                delay_seconds=0,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["source"], "drosophila_suzukii_pubmed_literature")
            self.assertEqual(result["record_count"], 2)
            self.assertEqual(result["canonical_literature_row_count"], 1)
            self.assertEqual(result["already_indexed_count"], 1)
            self.assertEqual(result["pubmed_metadata_ingested_count"], 1)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select source, lane, count(*) as n from records group by source, lane order by source, lane",
                limit=100,
            )
            counts = {(row["source"], row["lane"]): row["n"] for row in rows}
            self.assertEqual(counts[("drosophila_suzukii_core", "literature")], 1)
            self.assertEqual(counts[("drosophila_suzukii_pubmed_literature", "literature")], 2)
            receipt = (artifact_dir / "source_receipt.json").read_text(encoding="utf-8")
            self.assertIn("drosophila_suzukii_pubmed_literature", receipt)
            self.assertIn("already_indexed_count", receipt)

    def test_failed_refresh_preserves_existing_pubmed_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"

            def fake_fetch_json(url):
                if "esearch.fcgi" in url:
                    return ESEARCH
                if "esummary.fcgi" in url:
                    return ESUMMARY
                raise AssertionError(url)

            ingest_drosophila_suzukii_pubmed_literature(
                artifact_dir=artifact_dir,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-29T00:00:00Z",
                delay_seconds=0,
            )
            failed = ingest_drosophila_suzukii_pubmed_literature(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-29T01:00:00Z",
                delay_seconds=0,
            )

            self.assertFalse(failed["ok"])
            self.assertTrue(failed["preserved_existing"])
            # preserved_existing is True is the real guard against record loss here;
            # the loosened count only tolerates added source_gap EvidenceRecords.
            self.assertGreaterEqual(failed["record_count"], 2)


if __name__ == "__main__":
    unittest.main()
