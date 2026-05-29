from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from scripts.ingest_drosophila_suzukii_dryad_table_rows import ingest_drosophila_suzukii_dryad_table_rows
from tests.test_drosophila_suzukii_dryad_table_rows import PREVIEW, write_dryad_manifest_fixture


class IngestDrosophilaSuzukiiDryadTableRowsTests(unittest.TestCase):
    def test_ingest_updates_records_and_receipts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_dryad_manifest_fixture(artifact_dir)

            result = ingest_drosophila_suzukii_dryad_table_rows(
                artifact_dir=artifact_dir,
                retrieved_at="2026-05-29T00:00:00Z",
                fetch_preview_text_fn=lambda url: PREVIEW,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["table_row_count"], 2)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            rows = index.sql(
                "select json_extract(payload_json, '$.atom_type') as atom_type, count(*) as n from record_payloads where source='drosophila_suzukii_dryad_table_rows' group by atom_type",
                limit=20,
            )
            counts = {row["atom_type"]: int(row["n"]) for row in rows}
            self.assertEqual(counts["dryad_table_row"], 2)
            self.assertIn("drosophila_suzukii_dryad_table_rows", (artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
