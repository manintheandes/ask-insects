import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from scripts.ingest_who_dengue_surveillance import ingest_who_dengue_surveillance
from tests.test_who_dengue_surveillance_source import DASHBOARD_HTML, WER_HTML, WPRO_HTML


class IngestWhoDengueSurveillanceTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        def fake_fetch(url):
            if "wer" in url:
                return WER_HTML
            if "dashboard" in url:
                return DASHBOARD_HTML
            return WPRO_HTML

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            result = ingest_who_dengue_surveillance(
                artifact_dir=artifact_dir,
                source_urls=[
                    "https://www.who.int/westernpacific/wpro-emergencies/surveillance/dengue",
                    "https://www.who.int/publications/i/item/who-wer10052-665-678",
                    "https://data.wpro.who.int/dashboard",
                ],
                fetch_text=fake_fetch,
                retrieved_at="2026-05-25T00:00:00Z",
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
            self.assertGreaterEqual(counts[("aedes_who_dengue_surveillance", "public_health")], 6)
            payload_rows = index.sql("select payload_json from record_payloads where source='aedes_who_dengue_surveillance'")
            self.assertIn("Aedes aegypti", payload_rows[0]["payload_json"])
            status = (artifact_dir / "source_status.json").read_text(encoding="utf-8")
            self.assertIn("aedes_who_dengue_surveillance", status)
            self.assertIn('"publication_count": 1', status)
            self.assertIn('"fully_parsed": false', status)
            gaps = (artifact_dir / "gaps.json").read_text(encoding="utf-8")
            self.assertIn("who_dengue_dashboard_export_not_machine_readable", gaps)


if __name__ == "__main__":
    unittest.main()
