import tempfile
import unittest
from pathlib import Path

from askinsects.sources.ncbi_snp_variation import NCBI_SNP_VARIATION_SOURCE_ID, fetch_ncbi_snp_variation_records


def snp_summary_payload() -> dict[str, object]:
    return {
        "result": {
            "uids": ["123"],
            "123": {
                "uid": "123",
                "chr": "2",
                "allele": "A/G",
                "fxn_class": "intron_variant",
                "genes": "AAEL000001",
                "assembly": "AaegL5",
            },
        }
    }


class NCBISnpVariationSourceTests(unittest.TestCase):
    def test_fetch_ncbi_snp_variation_records_writes_queryable_gap_when_no_records(self):
        calls = []

        def fake_fetch_json(url: str):
            calls.append(url)
            return {"esearchresult": {"count": "0", "idlist": []}}

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_ncbi_snp_variation_records(
                raw_dir=Path(tmpdir) / "raw",
                limit=100,
                page_size=50,
                delay_seconds=0,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-25T00:00:00Z",
            )

        self.assertEqual(result.source_id, NCBI_SNP_VARIATION_SOURCE_ID)
        self.assertEqual(result.total_count, 0)
        self.assertEqual(result.fetched_count, 0)
        self.assertEqual(result.gaps[0]["reason"], "ncbi_snp_no_aedes_records")
        self.assertEqual(len(result.records), 1)
        record = result.records[0]
        self.assertEqual(record.source, NCBI_SNP_VARIATION_SOURCE_ID)
        self.assertEqual(record.lane, "genome_features")
        self.assertIn("zero records", record.text)
        self.assertEqual(record.payload["gap"]["reason"], "ncbi_snp_no_aedes_records")
        self.assertTrue(result.raw_artifacts)
        self.assertTrue(any("esearch.fcgi" in call for call in calls))

    def test_fetch_ncbi_snp_variation_records_normalizes_summary_records(self):
        def fake_fetch_json(url: str):
            if "esearch.fcgi" in url:
                return {"esearchresult": {"count": "1", "idlist": ["123"]}}
            return snp_summary_payload()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_ncbi_snp_variation_records(
                species="Aedes aegypti",
                raw_dir=Path(tmpdir) / "raw",
                limit=1,
                page_size=1,
                delay_seconds=0,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-25T00:00:00Z",
            )

        self.assertEqual(result.total_count, 1)
        self.assertEqual(result.fetched_count, 1)
        self.assertEqual(result.gaps, [])
        self.assertEqual(len(result.records), 1)
        record = result.records[0]
        self.assertEqual(record.record_id, "ncbi_snp_variation:rs123")
        self.assertEqual(record.source, NCBI_SNP_VARIATION_SOURCE_ID)
        self.assertEqual(record.lane, "genome_features")
        self.assertEqual(record.species, "Aedes aegypti")
        self.assertIn("AAEL000001", record.text)
        self.assertEqual(record.payload["rsid"], "rs123")


if __name__ == "__main__":
    unittest.main()
