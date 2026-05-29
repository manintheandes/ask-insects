import gzip
import tempfile
import unittest
from pathlib import Path

from askinsects.sources.drosophila_suzukii_geo_expression_matrices import (
    DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID,
    fetch_drosophila_suzukii_geo_expression_matrices_records,
)


class DrosophilaSuzukiiGeoExpressionMatricesSourceTests(unittest.TestCase):
    def test_fetch_parses_geo_differential_expression_rows(self):
        table = (
            "test_id\tgene_id\tgene\tlocus\tsample_1\tsample_2\tstatus\tvalue_1\tvalue_2\tlog2(fold_change)\ttest_stat\tp_value\tq_value\tsignificant\n"
            "XLOC_1\tXLOC_1\tDS10_00000001\tscaffold1:1-2\tControl\tAcclimated\tOK\t56.4\t40.5\t-0.47\t-1.7\t0.004\t0.02\tyes\n"
            "XLOC_2\tXLOC_2\tDS10_00000002\tscaffold1:3-4\tControl\tAcclimated\tOK\t10\t11\t-inf\t0.2\t0.5\t0.9\tno\n"
            "XLOC_3\tXLOC_3\tDS10_00000003\tscaffold1:5-6\tControl\tAcclimated\tOK\t12\t13\t0.2\t0.3\t0.4\t0.8\tno\n"
        )

        def fake_fetch(url):
            return gzip.compress(table.encode("utf-8"))

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_geo_expression_matrices_records(
                artifact_dir=Path(tmpdir),
                fetch_bytes=fake_fetch,
                retrieved_at="2026-05-29T00:00:00Z",
                max_rows_per_file=2,
            )

        self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID)
        self.assertEqual(result.file_count, 7)
        self.assertEqual(result.parsed_row_count, 14)
        self.assertEqual(result.significant_row_count, 7)
        self.assertEqual(result.records[0].lane, "expression")
        self.assertEqual(result.records[0].source, DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID)
        self.assertEqual(result.records[0].payload["atom_type"], "geo_differential_expression_row")
        self.assertEqual(result.records[0].payload["gene"], "DS10_00000001")
        self.assertTrue(result.records[0].payload["significant"])
        self.assertIsNone(result.records[1].payload["log2_fold_change"])
        self.assertIn("geo_expression_row_limit_applied", {gap["reason"] for gap in result.gaps})


if __name__ == "__main__":
    unittest.main()
