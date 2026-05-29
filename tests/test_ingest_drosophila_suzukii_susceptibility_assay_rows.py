from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from scripts.ingest_drosophila_suzukii_susceptibility_assay_rows import (
    ingest_drosophila_suzukii_susceptibility_assay_rows,
)
from tests.test_drosophila_suzukii_susceptibility_assay_rows import write_swd_susceptibility_fixture


class IngestDrosophilaSuzukiiSusceptibilityAssayRowsTests(unittest.TestCase):
    def test_ingest_updates_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_swd_susceptibility_fixture(artifact_dir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="fixture:swd",
                        lane="taxonomy",
                        source="drosophila_suzukii_core",
                        title="Drosophila suzukii",
                        text="Fixture taxonomy row.",
                        species="Drosophila suzukii",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_core",
                            locator="fixture#swd",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                    )
                ]
            )

            result = ingest_drosophila_suzukii_susceptibility_assay_rows(
                artifact_dir=artifact_dir,
                retrieved_at="2026-05-29T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["source"], "drosophila_suzukii_susceptibility_assay_rows")
            self.assertEqual(result["record_count"], 2)
            self.assertEqual(result["parsed_table_row_count"], 1)
            self.assertEqual(result["candidate_fact_count"], 1)
            counts = {
                (row["source"], row["lane"]): int(row["n"])
                for row in index.sql("select source,lane,count(*) as n from records group by source,lane", limit=100)
            }
            self.assertEqual(counts[("drosophila_suzukii_susceptibility_assay_rows", "resistance")], 2)
            self.assertEqual(counts[("drosophila_suzukii_core", "taxonomy")], 1)
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn("drosophila_suzukii_susceptibility_assay_rows", status["sources"])
            self.assertEqual(status["drosophila_suzukii_susceptibility_assay_rows"]["record_count"], 2)


if __name__ == "__main__":
    unittest.main()
