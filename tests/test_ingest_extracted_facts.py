from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from scripts.ingest_extracted_facts import ingest_extracted_facts
from tests.test_extracted_facts_source import write_extracted_facts_fixture


class IngestExtractedFactsTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_extracted_facts_fixture(artifact_dir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="fixture:aedes",
                        lane="taxonomy",
                        source="mosquito_v1_fixtures",
                        title="Aedes aegypti",
                        text="Fixture taxonomy row.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="mosquito_v1_fixtures",
                            locator="fixture#1",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                    )
                ]
            )

            result = ingest_extracted_facts(
                artifact_dir=artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertGreaterEqual(result["record_count"], 6)
            self.assertEqual(result["max_fulltext_units"], 5000)
            self.assertEqual(result["max_candidate_text_chars"], 50000)
            self.assertEqual(result["selected_fulltext_unit_count"], 1)
            self.assertEqual(result["selected_record_text_count"], 0)
            counts = {
                (row["source"], row["lane"]): int(row["n"])
                for row in index.sql("select source,lane,count(*) as n from records group by source,lane", limit=100)
            }
            self.assertGreaterEqual(counts[("aedes_extracted_facts", "vector_competence")], 1)
            self.assertGreaterEqual(counts[("aedes_extracted_facts", "resistance")], 1)
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 1)
            payload_rows = index.sql(
                "select count(*) as n from record_payloads where source='aedes_extracted_facts'"
            )
            self.assertGreaterEqual(payload_rows[0]["n"], 6)
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn("aedes_extracted_facts", status["sources"])
            self.assertEqual(status["aedes_extracted_facts"]["record_count"], result["record_count"])
            self.assertEqual(status["aedes_extracted_facts"]["max_fulltext_units"], 5000)
            self.assertEqual(status["aedes_extracted_facts"]["selected_record_text_count"], 0)


if __name__ == "__main__":
    unittest.main()
