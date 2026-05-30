import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from askinsects.sources.drosophila_suzukii_jki_drosomon_trap_captures import FetchBody
from scripts.ingest_drosophila_suzukii_jki_drosomon_trap_captures import (
    ingest_drosophila_suzukii_jki_drosomon_trap_captures,
)
from tests.test_drosophila_suzukii_jki_drosomon_trap_captures_source import DATASET_FIXTURE
from tests.test_drosophila_suzukii_jki_drosomon_trap_captures_source import CAPTURES_CSV_FIXTURE
from tests.test_drosophila_suzukii_jki_drosomon_trap_captures_source import zipped_jki_fixture


class IngestDrosophilaSuzukiiJkiDrosomonTrapCapturesTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        def fetch_body(url):
            return FetchBody(body=b"<html>Security Check</html>", content_type="text/html;charset=UTF-8", status=200)

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            result = ingest_drosophila_suzukii_jki_drosomon_trap_captures(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: DATASET_FIXTURE,
                fetch_body=fetch_body,
                retrieved_at="2026-05-29T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertGreaterEqual(result["record_count"], 5)
            self.assertEqual(result["parsed_trap_row_count"], 0)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            counts = {
                (row["source"], row["lane"]): row["n"]
                for row in index.sql(
                    "select source, lane, count(*) as n from records group by source, lane order by source, lane",
                    limit=100,
                )
            }
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 4)
            self.assertGreaterEqual(counts[("drosophila_suzukii_jki_drosomon_trap_captures", "ecology")], 5)
            payload_rows = index.sql(
                "select payload_json from record_payloads where source='drosophila_suzukii_jki_drosomon_trap_captures'",
                limit=10,
            )
            self.assertTrue(any("openagrar_security_check_blocks_csv_download" in row["payload_json"] for row in payload_rows))
            status = (artifact_dir / "source_status.json").read_text(encoding="utf-8")
            self.assertIn("drosophila_suzukii_jki_drosomon_trap_captures", status)

    def test_ingest_installs_trap_deployment_rows_when_csv_is_available(self):
        def fetch_body(url):
            return FetchBody(body=CAPTURES_CSV_FIXTURE, content_type="text/csv", status=200)

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            result = ingest_drosophila_suzukii_jki_drosomon_trap_captures(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: DATASET_FIXTURE,
                fetch_body=fetch_body,
                retrieved_at="2026-05-29T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["parsed_trap_row_count"], 2)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            rows = index.sql(
                "select payload_json from record_payloads where source='drosophila_suzukii_jki_drosomon_trap_captures' and payload_json like '%jki_drosomon_trap_deployment_row%'",
                limit=10,
            )
            self.assertEqual(len(rows), 2)
            self.assertTrue(any('"adult_captures": 7' in row["payload_json"] for row in rows))

    def test_ingest_installs_trap_location_rows_from_data_zip(self):
        def fetch_body(url):
            return FetchBody(body=zipped_jki_fixture(), content_type="application/zip", status=200)

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            result = ingest_drosophila_suzukii_jki_drosomon_trap_captures(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: DATASET_FIXTURE,
                fetch_body=fetch_body,
                retrieved_at="2026-05-29T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["parsed_trap_row_count"], 2)
            self.assertEqual(result["parsed_trap_location_count"], 1)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            rows = index.sql(
                "select payload_json from record_payloads where source='drosophila_suzukii_jki_drosomon_trap_captures' and payload_json like '%jki_drosomon_trap_location_row%'",
                limit=10,
            )
            self.assertEqual(len(rows), 1)
            self.assertTrue(any('"latitude": 49.800277' in row["payload_json"] for row in rows))


if __name__ == "__main__":
    unittest.main()
