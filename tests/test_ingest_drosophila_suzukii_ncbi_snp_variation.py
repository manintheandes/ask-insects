import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from scripts.ingest_drosophila_suzukii_ncbi_snp_variation import ingest_drosophila_suzukii_ncbi_snp_variation


class IngestDrosophilaSuzukiiNcbiSnpVariationTests(unittest.TestCase):
    def test_ingest_installs_queryable_zero_result_gap(self):
        def fake_fetch(url):
            return {"esearchresult": {"count": "0", "idlist": []}}

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            result = ingest_drosophila_suzukii_ncbi_snp_variation(
                artifact_dir=artifact_dir,
                fetch_json=fake_fetch,
                retrieved_at="2026-05-29T00:00:00Z",
                limit=10,
                page_size=10,
                delay_seconds=0,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["record_count"], 1)
            self.assertEqual(result["variant_record_count"], 0)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select source, lane, title from records where source='drosophila_suzukii_ncbi_snp_variation'",
                limit=10,
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["lane"], "genome_features")


if __name__ == "__main__":
    unittest.main()
