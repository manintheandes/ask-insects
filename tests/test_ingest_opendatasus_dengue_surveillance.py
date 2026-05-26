from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from scripts.ingest_opendatasus_dengue_surveillance import ingest_opendatasus_dengue_surveillance
from tests.test_opendatasus_dengue_surveillance_source import zip_bytes


class IngestOpenDataSusDengueSurveillanceTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            result = ingest_opendatasus_dengue_surveillance(
                artifact_dir=artifact_dir,
                years=[2025],
                file_urls=["https://opendatasus.example/DENGBR25.csv.zip"],
                fetch_bytes=lambda url: zip_bytes(),
                retrieved_at="2026-05-26T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["record_count"], 9)
            self.assertEqual(result["gap_count"], 0)
            self.assertEqual(result["input_csv_row_count"], 3)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            counts = {
                (row["source"], row["lane"]): row["n"]
                for row in index.sql(
                    "select source, lane, count(*) as n from records group by source, lane order by source, lane",
                    limit=100,
                )
            }
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 4)
            self.assertEqual(counts[("aedes_opendatasus_dengue_surveillance", "public_health")], 9)
            rows = index.sql(
                "select record_id, text from records where source='aedes_opendatasus_dengue_surveillance' and record_id like '%country:brazil:2025'",
                limit=1,
            )
            self.assertIn("Deaths coded as death by disease in EVOLUCAO=2: 1", rows[0]["text"])
            payload_rows = index.sql("select payload_json from record_payloads where source='aedes_opendatasus_dengue_surveillance'")
            self.assertIn('"residence_state": "Sao Paulo"', "\n".join(row["payload_json"] for row in payload_rows))
            status = (artifact_dir / "source_status.json").read_text(encoding="utf-8")
            self.assertIn("aedes_opendatasus_dengue_surveillance", status)
            self.assertIn('"fully_parsed": true', status)


if __name__ == "__main__":
    unittest.main()
