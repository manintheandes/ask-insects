import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from askinsects.builder import build_fixture_index
from scripts import ingest_bold_barcodes
from tests.test_bold_barcode_source import FAKE_BOLD_TSV


class IngestBoldBarcodesTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            with mock.patch.object(ingest_bold_barcodes, "fetch_bold_barcode_records") as fetch:
                from askinsects.sources.bold_barcodes import fetch_bold_barcode_records

                fetch.return_value = fetch_bold_barcode_records(
                    species="Aedes aegypti",
                    raw_dir=artifact_dir / "raw" / "bold",
                    limit=2,
                    fetch_text=lambda url: FAKE_BOLD_TSV,
                    retrieved_at="2026-05-24T00:00:00Z",
                )
                result = ingest_bold_barcodes.ingest_bold_barcodes(
                    artifact_dir=artifact_dir,
                    species="Aedes aegypti",
                    limit=2,
                    retrieved_at="2026-05-24T00:00:00Z",
                )

            self.assertTrue(result["ok"])
            self.assertEqual(result["record_count"], 2)
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn("mosquito_v1_fixtures", status["sources"])
            self.assertIn("bold_api", status["sources"])
            self.assertEqual(status["source_counts"]["bold_api"], 2)
            self.assertEqual(status["lanes"]["dna_barcodes"], 2)


if __name__ == "__main__":
    unittest.main()

