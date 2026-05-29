from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.drosophila_suzukii_dryad_table_rows import (
    DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID,
    build_drosophila_suzukii_dryad_table_row_records,
)


RETRIEVED_AT = "2026-05-29T00:00:00Z"
PREVIEW = """
document.getElementById('file_preview_box').innerHTML = `<table>
  <tr><th>treatment</th><th>distance_mm</th></tr>
  <tr><td>raspberry</td><td>42</td></tr>
  <tr><td>blueberry</td><td>35</td></tr>
</table>`;
"""


def write_dryad_manifest_fixture(artifact_dir: Path) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.upsert_records(
        [
            EvidenceRecord(
                record_id="swd:dryad:file:doi:test:mean_distance.csv",
                lane="behavior",
                source="drosophila_suzukii_deep_sources",
                title="Drosophila suzukii Dryad table/data file mean_distance.csv",
                text="Dryad file manifest for Drosophila suzukii behavior data.",
                species="Drosophila suzukii",
                url="https://datadryad.org/stash/dataset/doi:test",
                media_url=None,
                provenance=Provenance(
                    source_id="drosophila_suzukii_deep_sources",
                    locator="raw/drosophila_suzukii_deep_sources/dryad/files.json#files/1",
                    retrieved_at=RETRIEVED_AT,
                    license="CC0",
                    source_url="https://datadryad.org/api/v2/files/1064434/download",
                ),
                payload={
                    "record_type": "dryad_file_manifest",
                    "dataset_doi": "doi:test",
                    "file_path": "mean_distance.csv",
                    "mime_type": "text/csv",
                    "byte_size": 1234,
                    "digest": "abc",
                    "digest_type": "md5",
                    "download_url": "https://datadryad.org/api/v2/files/1064434/download",
                    "raw_file": {"_links": {"self": {"href": "/api/v2/files/1064434"}}},
                },
            )
        ]
    )


class DrosophilaSuzukiiDryadTableRowsTests(unittest.TestCase):
    def test_builds_rows_from_public_preview(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_dryad_manifest_fixture(artifact_dir)

            result = build_drosophila_suzukii_dryad_table_row_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                fetch_preview_text_fn=lambda url: PREVIEW,
            )

            self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID)
            self.assertEqual(result.candidate_count, 1)
            self.assertEqual(result.parsed_table_file_count, 1)
            self.assertEqual(result.table_row_count, 2)
            atom_types = {record.payload.get("atom_type") for record in result.records}
            self.assertIn("dryad_table_sheet", atom_types)
            self.assertIn("dryad_table_row", atom_types)
            self.assertIn("dryad_table_gap", atom_types)
            row = [record for record in result.records if record.payload.get("atom_type") == "dryad_table_row"][0]
            self.assertEqual(row.payload["row_values"]["treatment"], "raspberry")
            self.assertEqual(row.payload["row_values"]["distance_mm"], "42")
            self.assertTrue(any(gap["reason"] == "dryad_table_file_download_blocked_preview_used" for gap in result.gaps))

    def test_preview_failures_become_gap_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_dryad_manifest_fixture(artifact_dir)

            def fail_preview(url: str) -> str:
                raise RuntimeError("preview failed")

            result = build_drosophila_suzukii_dryad_table_row_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                fetch_preview_text_fn=fail_preview,
            )

            self.assertEqual(result.table_row_count, 0)
            self.assertTrue(any(gap["reason"] == "dryad_table_preview_fetch_or_parse_failed" for gap in result.gaps))


if __name__ == "__main__":
    unittest.main()
