import tempfile
import unittest
from pathlib import Path

from askinsects.sources.drosophila_suzukii_jki_drosomon_trap_captures import (
    DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID,
    FetchBody,
    fetch_drosophila_suzukii_jki_drosomon_trap_capture_records,
)


DATASET_FIXTURE = {
    "result": {
        "title": {"en": "Trap captures data from the 7-year Drosophila suzukii monitoring program in southwest Germany"},
        "description": {
            "en": (
                "The JKI monitoring program ran from 2011 to February 2018. "
                "The trap_description table lists 100 traps that were set during the monitoring period. "
                "The captures_data table contains 9967 records, each record representing a trap deployment. "
                "These deployments account for a total of 116,602 days and captured 756,717 adult D. suzukii individuals."
            )
        },
        "distributions": [
            {
                "id": "d0b494c0-398d-4855-b489-1bcf802e9c26",
                "media_type": "text/csv",
                "access_url": ["https://www.openagrar.de/servlets/MCRFileNodeServlet/openagrar_derivate_00016480/captures_data.csv"],
                "format": {"label": "CSV"},
                "license": {"label": "http://dcat-ap.de/def/licenses/cc-by/4.0"},
                "issued": "2026-01-21T01:25:23.399364",
                "modified": "2026-01-23T01:26:40.208115",
            }
        ],
        "page": [{"resource": "https://www.openagrar.de/servlets/MCRFileNodeServlet/openagrar_derivate_00016482/parameter_description.pdf"}],
    }
}


class DrosophilaSuzukiiJkiDrosomonTrapCapturesSourceTests(unittest.TestCase):
    def test_dataset_and_blocked_csv_become_ecology_records_and_gaps(self):
        def fetch_body(url):
            return FetchBody(body=b"<html><title>Sicherheitsueberpruefung</title>Security Check</html>", content_type="text/html", status=200)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_jki_drosomon_trap_capture_records(
                raw_dir=Path(tmpdir),
                fetch_json=lambda url: DATASET_FIXTURE,
                fetch_body=fetch_body,
                retrieved_at="2026-05-29T00:00:00Z",
            )

        self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID)
        self.assertGreaterEqual(len(result.records), 5)
        dataset_record = result.records[0]
        self.assertEqual(dataset_record.source, DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID)
        self.assertEqual(dataset_record.lane, "ecology")
        self.assertEqual(dataset_record.payload["atom_type"], "jki_drosomon_trap_dataset")
        self.assertEqual(dataset_record.payload["deployment_count_reported"], 9967)
        self.assertEqual(dataset_record.payload["adult_captures_reported"], 756717)
        reasons = {gap["reason"] for gap in result.gaps}
        self.assertIn("openagrar_security_check_blocks_csv_download", reasons)
        self.assertIn("jki_trap_deployment_rows_not_queryable", reasons)
        self.assertTrue(any(path.endswith("captures_data_security_check.html") for path in result.raw_artifacts))

    def test_metadata_failure_is_structured_gap(self):
        def fail(url):
            raise RuntimeError("offline")

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_jki_drosomon_trap_capture_records(
                raw_dir=Path(tmpdir),
                fetch_json=fail,
                retrieved_at="2026-05-29T00:00:00Z",
            )

        self.assertEqual(result.records, [])
        self.assertEqual(result.gaps[0]["reason"], "jki_drosomon_metadata_fetch_failed")


if __name__ == "__main__":
    unittest.main()
