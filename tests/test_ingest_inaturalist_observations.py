import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from askinsects.builder import build_fixture_index
from scripts import ingest_inaturalist_observations
from tests.test_inaturalist_source import observation_payload


class IngestINaturalistObservationsTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            with mock.patch.object(ingest_inaturalist_observations, "fetch_inaturalist_records") as fetch:
                from askinsects.sources.inaturalist import fetch_inaturalist_records

                fetch.return_value = fetch_inaturalist_records(
                    ["Aedes aegypti"],
                    raw_dir=artifact_dir / "raw" / "inaturalist",
                    place=None,
                    observation_limit=1,
                    page_size=10,
                    delay_seconds=0,
                    fetch_json=lambda url: observation_payload(),
                    retrieved_at="2026-05-24T00:00:00Z",
                )
                result = ingest_inaturalist_observations.ingest_inaturalist_observations(
                    artifact_dir=artifact_dir,
                    species=["Aedes aegypti"],
                    observation_limit=1,
                    page_size=10,
                    delay_seconds=0,
                    retrieved_at="2026-05-24T00:00:00Z",
                )

            self.assertTrue(result["ok"])
            self.assertEqual(result["source_counts"]["mosquito_v1_fixtures"], 7)
            self.assertEqual(result["source_counts"]["inaturalist_api"], 2)
            self.assertEqual(result["lanes"]["media"], 1)
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn("inaturalist_api", status["sources"])
            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["inaturalist"]["record_count"], 2)


if __name__ == "__main__":
    unittest.main()
