import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from scripts.ingest_public_health_guidance import ingest_public_health_guidance


HTML = """
<html>
  <head><title>Aedes vector control guidance</title></head>
  <body>Aedes aegypti dengue vector control surveillance and source reduction.</body>
</html>
"""


class IngestPublicHealthGuidanceTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            result = ingest_public_health_guidance(
                artifact_dir=artifact_dir,
                source_urls=["https://www.cdc.gov/example"],
                fetch_text=lambda url: HTML,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["record_count"], 1)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            counts = {
                (row["source"], row["lane"]): row["n"]
                for row in index.sql(
                    "select source, lane, count(*) as n from records group by source, lane order by source, lane",
                    limit=100,
                )
            }
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 4)
            self.assertEqual(counts[("aedes_public_health_guidance", "public_health")], 1)
            payload_rows = index.sql("select record_id from record_payloads where source='aedes_public_health_guidance'")
            self.assertTrue(payload_rows[0]["record_id"].startswith("public_health:guidance:"))
            status = (artifact_dir / "source_status.json").read_text(encoding="utf-8")
            self.assertIn("aedes_public_health_guidance", status)


if __name__ == "__main__":
    unittest.main()
