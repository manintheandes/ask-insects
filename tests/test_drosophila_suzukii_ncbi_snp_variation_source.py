import tempfile
import unittest
from pathlib import Path

from askinsects.sources.drosophila_suzukii_ncbi_snp_variation import (
    DROSOPHILA_SUZUKII_NCBI_SNP_VARIATION_SOURCE_ID,
    fetch_drosophila_suzukii_ncbi_snp_variation_records,
)


class DrosophilaSuzukiiNcbiSnpVariationSourceTests(unittest.TestCase):
    def test_zero_db_snp_result_becomes_queryable_gap_record(self):
        def fake_fetch(url):
            return {"esearchresult": {"count": "0", "idlist": []}}

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_ncbi_snp_variation_records(
                raw_dir=Path(tmpdir),
                fetch_json=fake_fetch,
                retrieved_at="2026-05-29T00:00:00Z",
                limit=10,
                page_size=10,
                delay_seconds=0,
            )

        self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_NCBI_SNP_VARIATION_SOURCE_ID)
        self.assertEqual(result.total_count, 0)
        self.assertEqual(result.gaps[0]["reason"], "ncbi_snp_no_swd_records")
        self.assertEqual(result.records[0].source, DROSOPHILA_SUZUKII_NCBI_SNP_VARIATION_SOURCE_ID)
        self.assertEqual(result.records[0].lane, "genome_features")
        self.assertIn("Drosophila suzukii", result.records[0].text)

    def test_nonzero_db_snp_result_is_retargeted_to_swd_source(self):
        def fake_fetch(url):
            if "esearch.fcgi" in url:
                return {"esearchresult": {"count": "1", "idlist": ["123"]}}
            return {"result": {"uids": ["123"], "123": {"uid": "123", "chr": "2L", "allele": "A/G"}}}

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_ncbi_snp_variation_records(
                raw_dir=Path(tmpdir),
                fetch_json=fake_fetch,
                retrieved_at="2026-05-29T00:00:00Z",
                limit=1,
                page_size=1,
                delay_seconds=0,
            )

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].source, DROSOPHILA_SUZUKII_NCBI_SNP_VARIATION_SOURCE_ID)
        self.assertTrue(result.records[0].record_id.startswith("swd_ncbi_snp_variation:"))


if __name__ == "__main__":
    unittest.main()
