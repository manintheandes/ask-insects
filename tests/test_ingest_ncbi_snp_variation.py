import json
import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from scripts.ingest_ncbi_snp_variation import ingest_ncbi_snp_variation


class IngestNCBISnpVariationTests(unittest.TestCase):
    def test_ingest_ncbi_snp_variation_preserves_sources_and_records_gap_metadata(self):
        def fake_fetch_json(url: str):
            return {"esearchresult": {"count": "0", "idlist": []}}

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            result = ingest_ncbi_snp_variation(
                artifact_dir=artifact_dir,
                limit=100,
                page_size=50,
                delay_seconds=0,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-25T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["record_count"], 1)
            self.assertEqual(result["variant_record_count"], 0)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, lane, count(*) as n from records group by source, lane")
            counts = {(row["source"], row["lane"]): row["n"] for row in rows}
            source_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            source_counts = {row["source"]: row["n"] for row in source_rows}
            self.assertEqual(source_counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts[("aedes_ncbi_snp_variation", "genome_features")], 1)
            gaps = json.loads((artifact_dir / "gaps.json").read_text(encoding="utf-8"))
            self.assertEqual([gap["reason"] for gap in gaps if gap.get("source") == "aedes_ncbi_snp_variation"], ["ncbi_snp_no_aedes_records"])
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn("aedes_ncbi_snp_variation", status["sources"])
            self.assertEqual(status["aedes_ncbi_snp_variation"]["reported_total_count"], 0)
            self.assertEqual(status["aedes_ncbi_snp_variation"]["gap_count"], 1)


if __name__ == "__main__":
    unittest.main()
