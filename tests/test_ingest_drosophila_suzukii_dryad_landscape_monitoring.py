import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from scripts.ingest_drosophila_suzukii_dryad_landscape_monitoring import (
    ingest_drosophila_suzukii_dryad_landscape_monitoring,
)
from tests.test_drosophila_suzukii_dryad_landscape_monitoring_source import (
    RETRIEVED_AT,
    landscape_fetch_json,
    landscape_fetch_text,
)


def _failing_fetch_text(url: str) -> str:
    raise RuntimeError("public preview blocked")


class IngestDrosophilaSuzukiiDryadLandscapeMonitoringTests(unittest.TestCase):
    def test_ingest_installs_landscape_monitoring_rows_and_receipt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            result = ingest_drosophila_suzukii_dryad_landscape_monitoring(
                artifact_dir=artifact_dir,
                fetch_json=landscape_fetch_json,
                fetch_text=landscape_fetch_text,
                retrieved_at=RETRIEVED_AT,
            )
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            rows = index.sql(
                """
                select json_extract(payload_json, '$.atom_type') as atom_type, count(*) as n
                from record_payloads
                where source='drosophila_suzukii_dryad_landscape_monitoring'
                group by atom_type
                """,
                limit=100,
            )
            counts = {str(row["atom_type"]): int(row["n"]) for row in rows}
            receipt_text = (artifact_dir / "source_receipt.json").read_text(encoding="utf-8")

        self.assertTrue(result["ok"])
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(counts["dryad_landscape_monitoring_row"], 2)
        self.assertEqual(counts["dryad_landscape_file_manifest"], 1)
        self.assertEqual(counts["dryad_landscape_dataset_manifest"], 1)
        self.assertEqual(counts["source_gap"], 1)
        self.assertIn("drosophila_suzukii_dryad_landscape_monitoring", receipt_text)

    def test_preview_failure_persists_queryable_gap(self):
        # When the public preview cannot be parsed, the lane still fetched dataset
        # and file manifests plus an honest gap. Those records must reach the
        # queryable index, not be silently dropped, per the source contract.
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            ingest_drosophila_suzukii_dryad_landscape_monitoring(
                artifact_dir=artifact_dir,
                fetch_json=landscape_fetch_json,
                fetch_text=_failing_fetch_text,
                retrieved_at=RETRIEVED_AT,
            )
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            gap_rows = index.sql(
                """
                select count(*) as n
                from record_payloads
                where source='drosophila_suzukii_dryad_landscape_monitoring'
                  and payload_json like '%dryad_landscape_preview_fetch_or_parse_failed%'
                """
            )

        self.assertGreater(int(gap_rows[0]["n"]), 0)


if __name__ == "__main__":
    unittest.main()
