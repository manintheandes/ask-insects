from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from scripts.ingest_vector_competence_assays import ingest_vector_competence_assays
from tests.test_vector_competence_assays_source import write_assay_literature_fixture


class IngestVectorCompetenceAssaysTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_assay_literature_fixture(artifact_dir)
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

            result = ingest_vector_competence_assays(
                artifact_dir=artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["record_count"], 1)
            counts = {
                (row["source"], row["lane"]): int(row["n"])
                for row in index.sql("select source,lane,count(*) as n from records group by source,lane", limit=100)
            }
            self.assertEqual(counts[("aedes_vector_competence_assays", "vector_competence")], 1)
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 1)
            payload_rows = index.sql(
                "select count(*) as n from record_payloads where source='aedes_vector_competence_assays'"
            )
            self.assertEqual(payload_rows[0]["n"], 1)
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn("aedes_vector_competence_assays", status["sources"])
            self.assertEqual(status["aedes_vector_competence_assays"]["record_count"], 1)


if __name__ == "__main__":
    unittest.main()
