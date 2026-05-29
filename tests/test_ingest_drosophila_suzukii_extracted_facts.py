from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from scripts.ingest_drosophila_suzukii_extracted_facts import ingest_drosophila_suzukii_extracted_facts
from tests.test_drosophila_suzukii_extracted_facts import write_swd_literature_fixture


class IngestDrosophilaSuzukiiExtractedFactsTests(unittest.TestCase):
    def test_ingest_updates_swd_receipts_without_removing_core_or_aedes_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_swd_literature_fixture(artifact_dir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="aedes:keep",
                        lane="literature",
                        source="aedes_extracted_facts",
                        title="Aedes row to preserve",
                        text="Existing Aedes extracted-fact row.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_extracted_facts",
                            locator="records#aedes:keep",
                            retrieved_at="2026-05-28T00:00:00Z",
                        ),
                    )
                ]
            )

            result = ingest_drosophila_suzukii_extracted_facts(
                artifact_dir=artifact_dir,
                retrieved_at="2026-05-28T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["source"], "drosophila_suzukii_extracted_facts")
            self.assertEqual(result["supplement_audit_record_count"], 2)
            counts = {
                row["source"]: int(row["n"])
                for row in index.sql("select source, count(*) as n from records group by source", limit=100)
            }
            self.assertGreaterEqual(counts["drosophila_suzukii_core"], 2)
            self.assertGreaterEqual(counts["drosophila_suzukii_extracted_facts"], 3)
            self.assertEqual(counts["aedes_extracted_facts"], 1)
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn("drosophila_suzukii_extracted_facts", status["sources"])
            self.assertEqual(
                status["drosophila_suzukii_extracted_facts"]["supplement_audit_record_count"],
                2,
            )

    def test_incremental_merge_deletes_only_requested_swd_paper(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_swd_literature_fixture(artifact_dir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")

            ingest_drosophila_suzukii_extracted_facts(
                artifact_dir=artifact_dir,
                retrieved_at="2026-05-28T00:00:00Z",
            )
            before = {
                row["source_record_id"]: int(row["n"])
                for row in index.sql(
                    """
                    select json_extract(payload_json, '$.source_record_id') as source_record_id, count(*) as n
                    from record_payloads
                    where source='drosophila_suzukii_extracted_facts'
                    group by source_record_id
                    """,
                    limit=10,
                )
            }
            self.assertGreater(before["swd:openalex:W1"], 0)
            self.assertGreater(before["swd:openalex:W2"], 0)

            result = ingest_drosophila_suzukii_extracted_facts(
                artifact_dir=artifact_dir,
                retrieved_at="2026-05-28T01:00:00Z",
                source_record_ids=["swd:openalex:W2"],
                merge_existing=True,
            )

            self.assertTrue(result["ok"])
            self.assertGreater(result["deleted_existing_record_count"], 0)
            after = {
                row["source_record_id"]: int(row["n"])
                for row in index.sql(
                    """
                    select json_extract(payload_json, '$.source_record_id') as source_record_id, count(*) as n
                    from record_payloads
                    where source='drosophila_suzukii_extracted_facts'
                    group by source_record_id
                    """,
                    limit=10,
                )
            }
            self.assertGreater(after["swd:openalex:W1"], 0)
            self.assertGreater(after["swd:openalex:W2"], 0)


if __name__ == "__main__":
    unittest.main()
