import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from askinsects.builder import build_fixture_index
from scripts import ingest_mosquito_alert_observations
from tests.test_mosquito_alert_source import FakeMosquitoAlertFetcher


class IngestMosquitoAlertObservationsTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            with mock.patch.object(ingest_mosquito_alert_observations, "fetch_mosquito_alert_records") as fetch:
                from askinsects.sources.mosquito_alert import fetch_mosquito_alert_records

                fetch.return_value = fetch_mosquito_alert_records(
                    raw_dir=artifact_dir / "raw" / "mosquito_alert",
                    occurrence_limit=1,
                    occurrence_page_size=1,
                    fetch_json=FakeMosquitoAlertFetcher(),
                    retrieved_at="2026-05-24T00:00:00Z",
                )
                result = ingest_mosquito_alert_observations.ingest_mosquito_alert_observations(
                    artifact_dir=artifact_dir,
                    occurrence_limit=1,
                    occurrence_page_size=1,
                    retrieved_at="2026-05-24T00:00:00Z",
                )

            self.assertTrue(result["ok"])
            self.assertEqual(result["source_counts"]["mosquito_v1_fixtures"], 7)
            self.assertEqual(result["source_counts"]["mosquito_alert_gbif"], 2)
            self.assertEqual(result["lanes"]["observations"], 2)
            self.assertEqual(result["lanes"]["media"], 1)
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn("mosquito_alert_gbif", status["sources"])
            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["mosquito_alert"]["record_count"], 2)


if __name__ == "__main__":
    unittest.main()
