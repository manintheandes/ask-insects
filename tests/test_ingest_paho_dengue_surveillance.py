import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from scripts.ingest_paho_dengue_surveillance import ingest_paho_dengue_surveillance
from tests.test_paho_surveillance_source import DASHBOARD_HTML, REPORT_HTML


class IngestPahoDengueSurveillanceTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        def fake_fetch(url):
            if "dashboard" in url:
                return DASHBOARD_HTML
            return REPORT_HTML

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            result = ingest_paho_dengue_surveillance(
                artifact_dir=artifact_dir,
                report_urls=["https://example.org/report"],
                dashboard_pages=["https://example.org/dashboard"],
                fetch_text=fake_fetch,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertGreaterEqual(result["record_count"], 6)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            counts = {
                (row["source"], row["lane"]): row["n"]
                for row in index.sql(
                    "select source, lane, count(*) as n from records group by source, lane order by source, lane",
                    limit=100,
                )
            }
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 4)
            self.assertGreaterEqual(counts[("aedes_paho_dengue_surveillance", "public_health")], 6)
            payload_rows = index.sql("select payload_json from record_payloads where source='aedes_paho_dengue_surveillance'")
            self.assertIn("Aedes aegypti", payload_rows[0]["payload_json"])
            status = (artifact_dir / "source_status.json").read_text(encoding="utf-8")
            self.assertIn("aedes_paho_dengue_surveillance", status)
            self.assertIn('"fully_parsed": false', status)
            gaps = (artifact_dir / "gaps.json").read_text(encoding="utf-8")
            self.assertIn("paho_dashboard_data_not_yet_cell_queryable", gaps)


if __name__ == "__main__":
    unittest.main()
