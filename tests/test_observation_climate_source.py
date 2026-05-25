from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.observation_climate import (
    DEFAULT_WORLDCLIM_ZIP_RELATIVE_PATH,
    OBSERVATION_CLIMATE_SOURCE_ID,
    build_observation_climate_records,
)
from tests.test_aedes_deep_sources import fake_worldclim_zip


def observation_record(record_id: str, source: str, payload: dict[str, object]) -> EvidenceRecord:
    return EvidenceRecord(
        record_id=record_id,
        lane="observations",
        source=source,
        title=f"Aedes aegypti observation {record_id}",
        text="Aedes aegypti occurrence observation with source coordinates.",
        species="Aedes aegypti",
        url=f"https://example.test/{record_id}",
        media_url=None,
        provenance=Provenance(
            source_id=source,
            locator=f"{source}#{record_id}",
            retrieved_at="2026-05-25T00:00:00Z",
            license="test",
            source_url=f"https://example.test/{record_id}",
        ),
        payload=payload,
    )


def write_observation_climate_fixture(artifact_dir: Path) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.upsert_records(
        [
            observation_record(
                "gbif:occurrence:1",
                "gbif_api",
                {
                    "raw_occurrence": {
                        "country": "Brazil",
                        "eventDate": "2023-01-24",
                        "decimalLatitude": -15.36,
                        "decimalLongitude": -44.25,
                        "datasetName": "GBIF test dataset",
                    }
                },
            ),
            observation_record(
                "inat:observation:1",
                "inaturalist_api",
                {
                    "raw_observation": {
                        "observed_on": "2026-05-22",
                        "place_guess": "Rio de Janeiro, Brazil",
                        "quality_grade": "research",
                        "geojson": {"coordinates": [-43.17, -22.90]},
                    }
                },
            ),
            observation_record(
                "gbif:occurrence:no-coordinates",
                "gbif_api",
                {"raw_occurrence": {"country": "Brazil", "eventDate": "2023-01-25"}},
            ),
        ]
    )
    zip_path = artifact_dir / DEFAULT_WORLDCLIM_ZIP_RELATIVE_PATH
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    zip_path.write_bytes(fake_worldclim_zip())


class ObservationClimateSourceTests(unittest.TestCase):
    def test_builds_worldclim_samples_for_coordinate_observations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_observation_climate_fixture(artifact_dir)

            result = build_observation_climate_records(
                artifact_dir,
                limit=10,
                retrieved_at="2026-05-25T00:00:00Z",
            )

            self.assertEqual(result.source_id, OBSERVATION_CLIMATE_SOURCE_ID)
            self.assertEqual(result.observation_count, 3)
            self.assertEqual(result.sampled_count, 2)
            self.assertEqual(result.skipped_no_coordinate_count, 1)
            self.assertFalse(result.gaps)
            by_id = {record.record_id: record for record in result.records}
            self.assertIn("ecology:observation_climate:gbif_api:gbif:occurrence:1", by_id)
            self.assertIn("ecology:observation_climate:inaturalist_api:inat:observation:1", by_id)
            sample = by_id["ecology:observation_climate:gbif_api:gbif:occurrence:1"]
            self.assertEqual(sample.lane, "ecology")
            self.assertEqual(sample.source, OBSERVATION_CLIMATE_SOURCE_ID)
            self.assertEqual(sample.payload["source_observation_record_id"], "gbif:occurrence:1")
            self.assertEqual(sample.payload["bio1_annual_mean_temperature_c"], 24.0)
            self.assertEqual(sample.payload["bio12_annual_precipitation_mm"], 1432.0)
            self.assertIn("Annual mean temperature: 24.0 deg C", sample.text)

    def test_reports_gap_when_worldclim_zip_is_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            SourceIndex(artifact_dir / "source_index.sqlite").initialize()

            result = build_observation_climate_records(
                artifact_dir,
                worldclim_zip_path=artifact_dir / "missing.zip",
                retrieved_at="2026-05-25T00:00:00Z",
            )

            self.assertEqual(result.sampled_count, 0)
            self.assertEqual(result.gaps[0]["reason"], "observation_climate_worldclim_zip_missing")
            self.assertEqual(result.records[0].source, OBSERVATION_CLIMATE_SOURCE_ID)

    def test_records_limit_gap_for_bounded_sampling(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_observation_climate_fixture(artifact_dir)

            result = build_observation_climate_records(
                artifact_dir,
                limit=1,
                retrieved_at="2026-05-25T00:00:00Z",
            )

            self.assertEqual(result.sampled_count, 1)
            self.assertTrue(any(gap["reason"] == "observation_climate_limit_applied" for gap in result.gaps))


if __name__ == "__main__":
    unittest.main()
