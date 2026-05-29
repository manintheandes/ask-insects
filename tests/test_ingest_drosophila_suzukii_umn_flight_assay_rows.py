import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from askinsects.sources.drosophila_suzukii_umn_flight_assay_rows import (
    BITSTREAM_API_URL,
    CSV_CONTENT_URL,
    ITEM_API_URL,
)
from scripts.ingest_drosophila_suzukii_umn_flight_assay_rows import ingest_drosophila_suzukii_umn_flight_assay_rows
from tests.test_drosophila_suzukii_umn_flight_assay_rows_source import BITSTREAM_FIXTURE, CSV_FIXTURE, ITEM_FIXTURE


class IngestDrosophilaSuzukiiUmnFlightAssayRowsTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        def fetch_json(url):
            if url == ITEM_API_URL:
                return ITEM_FIXTURE
            if url == BITSTREAM_API_URL:
                return BITSTREAM_FIXTURE
            raise AssertionError(url)

        def fetch_bytes(url):
            self.assertEqual(url, CSV_CONTENT_URL)
            return CSV_FIXTURE.encode("utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            result = ingest_drosophila_suzukii_umn_flight_assay_rows(
                artifact_dir=artifact_dir,
                fetch_json=fetch_json,
                fetch_bytes=fetch_bytes,
                retrieved_at="2026-05-29T00:00:00Z",
                max_rows=3,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["parsed_row_count"], 3)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            counts = {
                (row["source"], row["lane"]): row["n"]
                for row in index.sql(
                    "select source, lane, count(*) as n from records group by source, lane order by source, lane",
                    limit=100,
                )
            }
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 4)
            self.assertEqual(counts[("drosophila_suzukii_umn_flight_assay_rows", "behavior")], 5)
            payload_rows = index.sql(
                "select payload_json from record_payloads where source='drosophila_suzukii_umn_flight_assay_rows'",
                limit=10,
            )
            self.assertTrue(any("umn_flight_assay_row" in row["payload_json"] for row in payload_rows))
            status = (artifact_dir / "source_status.json").read_text(encoding="utf-8")
            self.assertIn("drosophila_suzukii_umn_flight_assay_rows", status)


if __name__ == "__main__":
    unittest.main()
