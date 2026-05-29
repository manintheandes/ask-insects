import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from scripts.ingest_drosophila_suzukii_extension_guidance import (
    ingest_drosophila_suzukii_extension_guidance,
)


HTML = """
<html>
  <head><title>Spotted wing drosophila IPM</title></head>
  <body>Drosophila suzukii monitoring, trapping, sanitation, and management.</body>
</html>
"""


class IngestDrosophilaSuzukiiExtensionGuidanceTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            result = ingest_drosophila_suzukii_extension_guidance(
                artifact_dir=artifact_dir,
                source_urls=["https://extension.example/swd"],
                fetch_text=lambda url: HTML,
                retrieved_at="2026-05-29T00:00:00Z",
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
            self.assertEqual(counts[("drosophila_suzukii_extension_guidance", "management")], 1)
            payload_rows = index.sql("select record_id from record_payloads where source='drosophila_suzukii_extension_guidance'")
            self.assertTrue(payload_rows[0]["record_id"].startswith("swd_extension_guidance:"))
            status = (artifact_dir / "source_status.json").read_text(encoding="utf-8")
            self.assertIn("drosophila_suzukii_extension_guidance", status)


if __name__ == "__main__":
    unittest.main()
