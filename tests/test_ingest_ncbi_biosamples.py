import json
import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from scripts.ingest_ncbi_biosamples import ingest_ncbi_biosamples
from tests.test_ncbi_biosample_source import biosample_summary_payload


class IngestNCBIBioSamplesTests(unittest.TestCase):
    def test_ingest_ncbi_biosamples_preserves_existing_sources_and_updates_metadata(self):
        def fake_fetch_json(url: str):
            if "esearch.fcgi" in url:
                return {"esearchresult": {"count": "1", "idlist": ["59867395"]}}
            return biosample_summary_payload()

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            result = ingest_ncbi_biosamples(
                artifact_dir=artifact_dir,
                limit=1,
                page_size=1,
                delay_seconds=0,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["record_count"], 1)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, lane, count(*) as n from records group by source, lane")
            counts = {(row["source"], row["lane"]): row["n"] for row in rows}
            source_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            source_counts = {row["source"]: row["n"] for row in source_rows}
            self.assertEqual(source_counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts[("ncbi_biosamples", "biosamples")], 1)
            payload_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select payload_json from record_payloads where source='ncbi_biosamples'",
            )
            payload = json.loads(payload_rows[0]["payload_json"])
            self.assertEqual(payload["accession"], "SAMN59867395")
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn("ncbi_biosamples", status["sources"])
            self.assertEqual(status["ncbi_biosamples"]["reported_total_count"], 1)


if __name__ == "__main__":
    unittest.main()
