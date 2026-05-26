import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from scripts.ingest_ncvbdc_dengue_surveillance import ingest_ncvbdc_dengue_surveillance
from tests.test_ncvbdc_dengue_surveillance_source import NCVBDC_HTML


class IngestNcvbdcDengueSurveillanceTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            result = ingest_ncvbdc_dengue_surveillance(
                artifact_dir=artifact_dir,
                source_urls=["https://ncvbdc.example/dengue"],
                fetch_text=lambda url: NCVBDC_HTML,
                retrieved_at="2026-05-26T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["record_count"], 14)
            self.assertEqual(result["gap_count"], 0)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            counts = {
                (row["source"], row["lane"]): row["n"]
                for row in index.sql(
                    "select source, lane, count(*) as n from records group by source, lane order by source, lane",
                    limit=100,
                )
            }
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 4)
            self.assertEqual(counts[("aedes_ncvbdc_dengue_surveillance", "public_health")], 14)
            rows = index.sql(
                "select record_id, text from records where source='aedes_ncvbdc_dengue_surveillance' and record_id like '%last_two_complete_years%'",
                limit=1,
            )
            self.assertIn("Total dengue deaths: 428", rows[0]["text"])
            payload_rows = index.sql("select payload_json from record_payloads where source='aedes_ncvbdc_dengue_surveillance'")
            self.assertIn('"total_deaths": 428', "\n".join(row["payload_json"] for row in payload_rows))
            status = (artifact_dir / "source_status.json").read_text(encoding="utf-8")
            self.assertIn("aedes_ncvbdc_dengue_surveillance", status)
            self.assertIn('"fully_parsed": true', status)


if __name__ == "__main__":
    unittest.main()
