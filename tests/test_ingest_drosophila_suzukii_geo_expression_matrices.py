import tempfile
import unittest
from pathlib import Path

from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.drosophila_suzukii_geo_expression_matrices import (
    DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID,
    DrosophilaSuzukiiGeoExpressionMatricesResult,
)
from scripts.ingest_drosophila_suzukii_geo_expression_matrices import ingest_drosophila_suzukii_geo_expression_matrices


class IngestDrosophilaSuzukiiGeoExpressionMatricesTests(unittest.TestCase):
    def test_ingest_preserves_sources_and_updates_metadata(self):
        record = EvidenceRecord(
            record_id="swd_geo_expression:GSE1:file:r1",
            lane="expression",
            source=DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID,
            title="Drosophila suzukii GEO differential expression",
            text="GEO differential-expression row for Drosophila suzukii gene DS10_00000001.",
            species="Drosophila suzukii",
            url="https://example.org/file.txt.gz",
            media_url=None,
            provenance=Provenance(
                source_id=DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID,
                locator="raw/geo/file.txt.gz#row/1",
                retrieved_at="2026-05-29T00:00:00Z",
            ),
            payload={"atom_type": "geo_differential_expression_row", "gene": "DS10_00000001", "significant": True},
        )

        def fake_fetch_records(**kwargs):
            return DrosophilaSuzukiiGeoExpressionMatricesResult(
                source_id=DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID,
                records=[record],
                gaps=[],
                raw_artifacts=["raw/geo/file.txt.gz"],
                requested_urls=["https://example.org/file.txt.gz"],
                file_count=1,
                parsed_row_count=1,
                significant_row_count=1,
                accessions=["GSE1"],
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            from unittest.mock import patch

            with patch(
                "scripts.ingest_drosophila_suzukii_geo_expression_matrices.fetch_drosophila_suzukii_geo_expression_matrices_records",
                fake_fetch_records,
            ):
                result = ingest_drosophila_suzukii_geo_expression_matrices(
                    artifact_dir=artifact_dir,
                    retrieved_at="2026-05-29T00:00:00Z",
                )
            self.assertTrue(result["ok"])
            self.assertEqual(result["record_count"], 1)
            self.assertEqual(result["significant_row_count"], 1)
            rows = result["source_counts"]
            self.assertEqual(rows[DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID], 1)
            status = (artifact_dir / "source_status.json").read_text(encoding="utf-8")
            self.assertIn(DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID, status)


if __name__ == "__main__":
    unittest.main()
