from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from askinsects.index import SourceIndex
from askinsects.sources.swd_primary_field_evidence import (
    ECOTROL_FIELD_RECORD_ID,
    SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID,
    build_swd_primary_field_evidence_records,
)
from scripts.ingest_swd_primary_field_evidence import (
    ingest_swd_primary_field_evidence,
)


class SwdPrimaryFieldEvidenceSourceTests(unittest.TestCase):
    def test_record_preserves_greenhouse_to_field_results_and_exact_source(self):
        records = build_swd_primary_field_evidence_records(
            retrieved_at="2026-07-19T00:00:00Z"
        )

        self.assertEqual(len(records), 2)
        record = next(item for item in records if item.record_id != ECOTROL_FIELD_RECORD_ID)
        self.assertEqual(
            record.record_id,
            "swd_primary_field:doi:10.1016/j.cropro.2019.05.033",
        )
        self.assertEqual(record.source, SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID)
        self.assertEqual(record.species, "Drosophila suzukii")
        self.assertEqual(
            record.title,
            "Evaluation of hop (Humulus lupulus) as a repellent for the management of Drosophila suzukii",
        )
        self.assertEqual(
            record.url,
            "https://doi.org/10.1016/j.cropro.2019.05.033",
        )
        self.assertEqual(
            record.provenance.locator,
            "https://bio.kuleuven.be/ento/pdfs/reher_etal_cropprot_2019.pdf#page=4",
        )
        for fragment in (
            "24-hour greenhouse cage",
            "ratio 0.392",
            "neither the hop treatment nor dispenser-applied positive controls significantly reduced infestation",
            "commercial raspberry and blackberry",
            "larvae in fruit",
            "hypotheses rather than demonstrated causes",
        ):
            self.assertIn(fragment, record.text)

    def test_record_preserves_ecotrol_crop_specific_results_and_limits(self):
        records = build_swd_primary_field_evidence_records(
            retrieved_at="2026-07-20T00:00:00Z"
        )

        record = next(
            item for item in records if item.record_id == ECOTROL_FIELD_RECORD_ID
        )
        self.assertEqual(record.source, SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID)
        self.assertEqual(record.species, "Drosophila suzukii")
        self.assertEqual(
            record.url,
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC7469169/",
        )
        for fragment in (
            "rosemary oil (10%)",
            "3.5 L/ha",
            "sentinel raspberries",
            "0.06 plus or minus 0.01",
            "equivalence or noninferiority",
            "half-high Vaccinium corymbosum cv. Chippewa",
            "P=0.909",
            "does not support transferring",
        ):
            self.assertIn(fragment, record.text)

    def test_ingest_is_idempotent_and_keeps_one_searchable_row(self):
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
                first = ingest_swd_primary_field_evidence(
                    artifact_dir=artifact_dir,
                    retrieved_at="2026-07-19T00:00:00Z",
                )
                repeated = ingest_swd_primary_field_evidence(
                    artifact_dir=artifact_dir,
                    retrieved_at="2026-07-20T00:00:00Z",
                )

            index = SourceIndex(artifact_dir / "source_index.sqlite")
            with index.connect() as connection:
                record_count = int(
                    connection.execute(
                        "select count(*) as n from records where source=?",
                        (SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID,),
                    ).fetchone()["n"]
                )
                searchable_count = int(
                    connection.execute(
                        "select count(*) as n from records_fts f "
                        "join records r on r.record_id=f.record_id where r.source=?",
                        (SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID,),
                    ).fetchone()["n"]
                )
            status = json.loads(
                (artifact_dir / "source_status.json").read_text(encoding="utf-8")
            )

        self.assertTrue(first["ok"])
        self.assertTrue(repeated["ok"])
        self.assertEqual(record_count, 2)
        self.assertEqual(searchable_count, 2)
        self.assertEqual(
            status["source_counts"][SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID], 2
        )
        self.assertEqual(status["record_count"], 2)
        self.assertEqual(status["lanes"]["literature"], 2)


if __name__ == "__main__":
    unittest.main()
