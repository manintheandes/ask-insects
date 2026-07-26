from __future__ import annotations

import unittest

from askinsects.sources.anopheles_primary_evidence import (
    KNOWLESI_DIRUS_RECORD_ID,
    TANZANIA_INFECTIOUS_BITING_RECORD_ID,
    ZANZIBAR_INFECTIOUS_BITING_RECORD_ID,
    build_anopheles_primary_evidence_records,
)


class AnophelesPrimaryEvidenceSourceTests(unittest.TestCase):
    def test_builds_exact_public_primary_records(self) -> None:
        records = build_anopheles_primary_evidence_records(
            retrieved_at="2026-07-25T00:00:00Z"
        )
        by_id = {record.record_id: record for record in records}

        self.assertEqual(
            set(by_id),
            {
                ZANZIBAR_INFECTIOUS_BITING_RECORD_ID,
                TANZANIA_INFECTIOUS_BITING_RECORD_ID,
                KNOWLESI_DIRUS_RECORD_ID,
            },
        )
        self.assertIn("n=10", by_id[ZANZIBAR_INFECTIOUS_BITING_RECORD_ID].text)
        self.assertIn("17 of 7,442", by_id[TANZANIA_INFECTIOUS_BITING_RECORD_ID].text)
        self.assertIn("2 of 745", by_id[KNOWLESI_DIRUS_RECORD_ID].text)
        self.assertTrue(
            all(record.provenance.source_url for record in records)
        )


if __name__ == "__main__":
    unittest.main()
