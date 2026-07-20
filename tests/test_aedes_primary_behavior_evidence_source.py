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

        self.assertEqual(len(records), 7)
        self.assertEqual(
            {record.record_id for record in records},
            {
                "aedes_primary_behavior:pubmed:544697",
                "aedes_primary_behavior:pubmed:469272",
                "aedes_primary_behavior:pmc:PMC3794971",
                "aedes_primary_behavior:pmc:PMC9866038:table8",
                "aedes_primary_behavior:pmc:PMC3577799",
                "aedes_primary_behavior:plosntds:e0003726",
                "aedes_primary_behavior:pmc:PMC8816903",
            },
        )
        spectral_gating = next(
            record for record in records if record.record_id.endswith("PMC8816903")
        )
        self.assertEqual(
            spectral_gating.title,
            "The olfactory gating of visual preferences to human skin and visible "
            "spectra in mosquitoes",
        )
        self.assertEqual(
            spectral_gating.url,
            "https://doi.org/10.1038/s41467-022-28195-x",
        )
        for fragment in (
            "1-4%",
            "600 and 660 nm",
            "496 nm",
            "437, 452, 510, and 520 nm",
            "heat, water vapor, or skin volatiles",
            "landing or biting",
        ):
            self.assertIn(fragment, spectral_gating.text)
        self.assertEqual(
            spectral_gating.provenance.locator,
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC8816903/#Sec3 "
            "(Results paragraphs 7-9, Figure 1e-i, and Supplementary Figure S1); "
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC8816903/#Sec9 "
            "(Discussion paragraph 26)",
        )
        self.assertEqual(
            spectral_gating.provenance.source_id,
            "doi:10.1038/s41467-022-28195-x",
        )
        table = next(record for record in records if record.record_id.endswith("table8"))
        self.assertIn("4.0 +/- 0.0 hours", table.text)
        self.assertIn("0.3 +/- 0.5 hours", table.text)
        self.assertIn("Table 8 labels N=6", table.text)
        self.assertIn("three participants", table.text)
        self.assertIn("sample size is unresolved", table.text)
        self.assertTrue(table.provenance.locator.endswith("#life-13-00141-t008"))
        prior_deet = next(
            record for record in records if record.record_id.endswith("PMC3577799")
        )
        self.assertIn("three hours", prior_deet.text)
        self.assertIn("electroantennogram", prior_deet.text)
        heritable_transfluthrin = next(
            record for record in records if record.record_id.endswith("e0003726")
        )
        self.assertIn("nine generations", heritable_transfluthrin.text)
        self.assertIn("experimental cross", heritable_transfluthrin.text)
        for record in records:
            with self.subTest(record_id=record.record_id):
                self.assertEqual(
                    record.source,
                    AEDES_PRIMARY_BEHAVIOR_EVIDENCE_SOURCE_ID,
                )
                expected_source_id = (
                    "doi:10.1038/s41467-022-28195-x"
                    if record.record_id.endswith("PMC8816903")
                    else AEDES_PRIMARY_BEHAVIOR_EVIDENCE_SOURCE_ID
                )
                self.assertEqual(record.provenance.source_id, expected_source_id)
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
        self.assertEqual(len(rows), 7)
        self.assertEqual(searchable_count, 7)
        self.assertTrue(all(row["title"] for row in rows))
        self.assertTrue(all(str(row["url"]).startswith("https://") for row in rows))
        self.assertEqual(
            status["source_counts"][AEDES_PRIMARY_BEHAVIOR_EVIDENCE_SOURCE_ID],
            7,
        )
        self.assertEqual(status["record_count"], 7)
        self.assertEqual(status["lanes"]["literature"], 7)


if __name__ == "__main__":
    unittest.main()
