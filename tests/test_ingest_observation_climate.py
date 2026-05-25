from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.observation_climate import OBSERVATION_CLIMATE_SOURCE_ID
from scripts.ingest_observation_climate import ingest_observation_climate
from tests.test_observation_climate_source import write_observation_climate_fixture


class IngestObservationClimateTests(unittest.TestCase):
    def test_ingest_adds_climate_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_observation_climate_fixture(artifact_dir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="ecology:observation_climate:stale",
                        lane="ecology",
                        source=OBSERVATION_CLIMATE_SOURCE_ID,
                        title="stale climate row",
                        text="stale",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id=OBSERVATION_CLIMATE_SOURCE_ID,
                            locator="stale",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="test",
                            source_url=None,
                        ),
                        payload={"record_type": "stale"},
                    )
                ]
            )

            result = ingest_observation_climate(
                artifact_dir=artifact_dir,
                limit=10,
                retrieved_at="2026-05-25T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["source"], OBSERVATION_CLIMATE_SOURCE_ID)
            self.assertEqual(result["sampled_count"], 2)
            rows = index.sql(
                "select source, lane, count(*) as n from records group by source, lane",
                limit=20,
            )
            counts = {(row["source"], row["lane"]): row["n"] for row in rows}
            self.assertEqual(counts[(OBSERVATION_CLIMATE_SOURCE_ID, "ecology")], 2)
            self.assertEqual(counts[("gbif_api", "observations")], 2)
            self.assertEqual(counts[("inaturalist_api", "observations")], 1)
            stale = index.sql(
                "select count(*) as n from records where record_id='ecology:observation_climate:stale'"
            )
            self.assertEqual(stale[0]["n"], 0)
            payload_rows = index.sql(
                f"select count(*) as n from record_payloads where source='{OBSERVATION_CLIMATE_SOURCE_ID}'"
            )
            self.assertEqual(payload_rows[0]["n"], 2)
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            self.assertIn(OBSERVATION_CLIMATE_SOURCE_ID, status["sources"])
            self.assertEqual(status[OBSERVATION_CLIMATE_SOURCE_ID]["sampled_count"], 2)
            self.assertEqual(receipt[OBSERVATION_CLIMATE_SOURCE_ID]["observation_count"], 3)


if __name__ == "__main__":
    unittest.main()
