import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from askinsects.builder import build_fixture_index
from scripts import ingest_vectornet_surveillance
from tests.test_vectornet_surveillance_source import vectornet_archive_bytes


class IngestVectorNetSurveillanceTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            with mock.patch.object(ingest_vectornet_surveillance, "fetch_vectornet_surveillance_records") as fetch:
                from askinsects.sources.vectornet_surveillance import fetch_vectornet_surveillance_records

                fetch.return_value = fetch_vectornet_surveillance_records(
                    raw_dir=artifact_dir / "raw" / "vectornet_surveillance",
                    fetch_bytes=lambda url: vectornet_archive_bytes(),
                    retrieved_at="2026-05-25T00:00:00Z",
                )
                result = ingest_vectornet_surveillance.ingest_vectornet_surveillance(
                    artifact_dir=artifact_dir,
                    retrieved_at="2026-05-25T00:00:00Z",
                )

            self.assertTrue(result["ok"])
            self.assertEqual(result["source_counts"]["mosquito_v1_fixtures"], 7)
            self.assertEqual(result["source_counts"]["vectornet_aedes_surveillance"], result["record_count"])
            self.assertEqual(result["matched_row_count"], 2)
            self.assertGreaterEqual(result["ecology_record_count"], 2)
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn("vectornet_aedes_surveillance", status["sources"])
            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["vectornet_surveillance"]["matched_row_count"], 2)


if __name__ == "__main__":
    unittest.main()
