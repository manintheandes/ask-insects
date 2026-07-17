from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from askinsects.index import SourceIndex
from askinsects.sources.aedes_primary_behavior_evidence import (
    AEDES_PRIMARY_BEHAVIOR_EVIDENCE_SOURCE_ID,
    build_aedes_primary_behavior_evidence_records,
)
from scripts.ingest_aedes_primary_behavior_evidence import (
    ingest_aedes_primary_behavior_evidence,
)


class AedesPrimaryBehaviorEvidenceSourceTests(unittest.TestCase):
    def test_records_point_to_exact_primary_papers_and_table(self):
        records = build_aedes_primary_behavior_evidence_records(
            retrieved_at="2026-07-17T00:00:00Z"
        )

        self.assertEqual(len(records), 4)
        self.assertEqual(
            {record.record_id for record in records},
            {
                "aedes_primary_behavior:pubmed:544697",
                "aedes_primary_behavior:pubmed:469272",
                "aedes_primary_behavior:pmc:PMC3794971",
                "aedes_primary_behavior:pmc:PMC9866038:table8",
            },
        )
        table = next(record for record in records if record.record_id.endswith("table8"))
        self.assertIn("4.0 +/- 0.0 hours", table.text)
        self.assertIn("0.3 +/- 0.5 hours", table.text)
        self.assertIn("Table 8 labels N=6", table.text)
        self.assertIn("three participants", table.text)
        self.assertIn("sample size is unresolved", table.text)
        self.assertTrue(table.provenance.locator.endswith("#life-13-00141-t008"))
        for record in records:
            with self.subTest(record_id=record.record_id):
                self.assertEqual(
                    record.source,
                    AEDES_PRIMARY_BEHAVIOR_EVIDENCE_SOURCE_ID,
                )
                self.assertEqual(
                    record.provenance.source_id,
                    AEDES_PRIMARY_BEHAVIOR_EVIDENCE_SOURCE_ID,
                )
                self.assertTrue(record.title)
                self.assertTrue(str(record.url).startswith("https://"))
                self.assertTrue(record.provenance.locator.startswith("https://"))
                self.assertNotIn("config/", record.provenance.locator)
                self.assertEqual(record.provenance.source_url, record.url)

    def test_ingest_is_idempotent_and_preserves_search_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            with (
                patch.object(
                    SourceIndex,
                    "summary",
                    side_effect=AssertionError("full index summary is not allowed"),
                ),
                patch.object(
                    SourceIndex,
                    "sql",
                    side_effect=AssertionError("broad index SQL is not allowed"),
                ),
            ):
                result = ingest_aedes_primary_behavior_evidence(
                    artifact_dir=artifact_dir,
                    retrieved_at="2026-07-17T00:00:00Z",
                )
                repeated = ingest_aedes_primary_behavior_evidence(
                    artifact_dir=artifact_dir,
                    retrieved_at="2026-07-18T00:00:00Z",
                )
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            with index.connect() as connection:
                rows = connection.execute(
                    "select record_id, title, url from records where source=? "
                    "order by record_id",
                    (AEDES_PRIMARY_BEHAVIOR_EVIDENCE_SOURCE_ID,),
                ).fetchall()
                searchable_count = int(
                    connection.execute(
                        "select count(*) as n from records_fts f "
                        "join records r on r.record_id=f.record_id where r.source=?",
                        (AEDES_PRIMARY_BEHAVIOR_EVIDENCE_SOURCE_ID,),
                    ).fetchone()["n"]
                )
            status = json.loads(
                (artifact_dir / "source_status.json").read_text(encoding="utf-8")
            )

        self.assertTrue(result["ok"])
        self.assertTrue(repeated["ok"])
        self.assertEqual(len(rows), 4)
        self.assertEqual(searchable_count, 4)
        self.assertTrue(all(row["title"] for row in rows))
        self.assertTrue(all(str(row["url"]).startswith("https://") for row in rows))
        self.assertEqual(
            status["source_counts"][AEDES_PRIMARY_BEHAVIOR_EVIDENCE_SOURCE_ID],
            4,
        )
        self.assertEqual(status["record_count"], 4)
        self.assertEqual(status["lanes"]["literature"], 4)


if __name__ == "__main__":
    unittest.main()
