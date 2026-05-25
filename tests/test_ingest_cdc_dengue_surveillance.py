import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from scripts.ingest_cdc_dengue_surveillance import ingest_cdc_dengue_surveillance
from tests.test_cdc_dengue_surveillance_source import CDC_HTML, CONFIG_JSON, EPI_CSV, JURISDICTION_CSV


class IngestCdcDengueSurveillanceTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        def fake_fetch(url):
            if url.endswith("current-data.html"):
                return CDC_HTML
            if url.endswith("current-year-tabs-updated.json"):
                return CONFIG_JSON
            if url.endswith("Cases_by_Jurisdiction_Current.csv"):
                return JURISDICTION_CSV
            if url.endswith("Epi_Curve_Current.csv"):
                return EPI_CSV
            raise AssertionError(f"unexpected URL {url}")

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            result = ingest_cdc_dengue_surveillance(
                artifact_dir=artifact_dir,
                source_urls=["https://www.cdc.gov/dengue/data-research/facts-stats/current-data.html"],
                fetch_text=fake_fetch,
                retrieved_at="2026-05-25T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["dataset_row_count"], 4)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            counts = {
                (row["source"], row["lane"]): row["n"]
                for row in index.sql(
                    "select source, lane, count(*) as n from records group by source, lane order by source, lane",
                    limit=100,
                )
            }
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 4)
            self.assertGreaterEqual(counts[("aedes_cdc_dengue_surveillance", "public_health")], 8)
            rows = index.sql(
                "select record_id from records where source='aedes_cdc_dengue_surveillance' and record_id like '%Cases_by_Jurisdiction_Current%'",
                limit=10,
            )
            self.assertEqual(len(rows), 2)
            payload_rows = index.sql("select payload_json from record_payloads where source='aedes_cdc_dengue_surveillance'")
            self.assertIn("Aedes aegypti", payload_rows[0]["payload_json"])
            status = (artifact_dir / "source_status.json").read_text(encoding="utf-8")
            self.assertIn("aedes_cdc_dengue_surveillance", status)
            self.assertIn('"dataset_row_count": 4', status)
            self.assertIn('"fully_parsed": true', status)


if __name__ == "__main__":
    unittest.main()
