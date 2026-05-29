from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from scripts.ingest_drosophila_suzukii_occurrence_ecology import ingest_drosophila_suzukii_occurrence_ecology
from tests.test_drosophila_suzukii_occurrence_ecology import write_swd_occurrence_ecology_fixture


class IngestDrosophilaSuzukiiOccurrenceEcologyTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_swd_occurrence_ecology_fixture(artifact_dir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="fixture:swd",
                        lane="taxonomy",
                        source="mosquito_v1_fixtures",
                        title="Drosophila suzukii",
                        text="Fixture taxonomy row.",
                        species="Drosophila suzukii",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="mosquito_v1_fixtures",
                            locator="fixture#swd",
                            retrieved_at="2026-05-28T00:00:00Z",
                        ),
                    )
                ]
            )

            result = ingest_drosophila_suzukii_occurrence_ecology(
                artifact_dir=artifact_dir,
                retrieved_at="2026-05-28T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["record_count"], 5)
            counts = {
                (row["source"], row["lane"]): int(row["n"])
                for row in index.sql("select source,lane,count(*) as n from records group by source,lane", limit=100)
            }
            self.assertEqual(counts[("drosophila_suzukii_occurrence_ecology", "ecology")], 5)
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 1)
            payload_rows = index.sql(
                "select count(*) as n from record_payloads where source='drosophila_suzukii_occurrence_ecology'"
            )
            self.assertEqual(payload_rows[0]["n"], 5)
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn("drosophila_suzukii_occurrence_ecology", status["sources"])
            self.assertEqual(status["drosophila_suzukii_occurrence_ecology"]["observation_count"], 3)


if __name__ == "__main__":
    unittest.main()
