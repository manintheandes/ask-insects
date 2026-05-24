from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.occurrence_ecology import (
    OCCURRENCE_ECOLOGY_SOURCE_ID,
    build_occurrence_ecology_records,
)


def observation_record(record_id: str, source: str, payload: dict[str, object], *, country_text: str) -> EvidenceRecord:
    return EvidenceRecord(
        record_id=record_id,
        lane="observations",
        source=source,
        title=f"Aedes aegypti observation in {country_text}",
        text=f"Aedes aegypti occurrence observation in {country_text}.",
        species="Aedes aegypti",
        url=f"https://example.test/{record_id}",
        media_url=None,
        provenance=Provenance(
            source_id=source,
            locator=f"{source}#{record_id}",
            retrieved_at="2026-05-24T00:00:00Z",
            license="test",
            source_url=f"https://example.test/{record_id}",
        ),
        payload=payload,
    )


def write_occurrence_ecology_fixture(artifact_dir: Path) -> None:
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
                country_text="Brazil",
            ),
            observation_record(
                "gbif:occurrence:2",
                "gbif_api",
                {
                    "raw_occurrence": {
                        "country": "Brazil",
                        "eventDate": "2023-02-11",
                        "decimalLatitude": -12.0,
                        "decimalLongitude": -38.5,
                        "datasetName": "GBIF test dataset",
                    }
                },
                country_text="Brazil",
            ),
            observation_record(
                "mosquito_alert:observation:1",
                "mosquito_alert_gbif",
                {
                    "raw_occurrence": {
                        "country": "Argentina",
                        "eventDate": "2023-01-24",
                        "decimalLatitude": -34.58,
                        "decimalLongitude": -58.40,
                        "datasetName": "Mosquito Alert",
                    }
                },
                country_text="Argentina",
            ),
            observation_record(
                "inat:observation:1",
                "inaturalist_api",
                {
                    "raw_observation": {
                        "observed_on": "2026-05-22",
                        "observed_on_details": {"month": 5},
                        "place_guess": "Rio de Janeiro, Brazil",
                        "quality_grade": "research",
                        "geojson": {"coordinates": [-43.17, -22.90]},
                        "ofvs": [
                            {
                                "name": "Habitat",
                                "value": "Gardens",
                            }
                        ],
                    }
                },
                country_text="Brazil",
            ),
        ]
    )


class OccurrenceEcologySourceTests(unittest.TestCase):
    def test_builds_country_month_and_habitat_ecology_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_occurrence_ecology_fixture(artifact_dir)

            result = build_occurrence_ecology_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertEqual(result.source_id, OCCURRENCE_ECOLOGY_SOURCE_ID)
            self.assertEqual(result.observation_count, 4)
            self.assertEqual(result.country_count, 2)
            self.assertEqual(result.country_month_count, 4)
            self.assertEqual(result.habitat_count, 1)
            self.assertFalse(result.gaps)
            by_id = {record.record_id: record for record in result.records}
            self.assertIn("occurrence_ecology:country:Brazil", by_id)
            self.assertIn("occurrence_ecology:country_month:Brazil:01", by_id)
            self.assertIn("occurrence_ecology:habitat:Brazil:Gardens", by_id)
            brazil = by_id["occurrence_ecology:country:Brazil"]
            self.assertEqual(brazil.lane, "ecology")
            self.assertEqual(brazil.source, OCCURRENCE_ECOLOGY_SOURCE_ID)
            self.assertIn("range summary for Brazil", brazil.text)
            self.assertEqual(brazil.payload["observation_count"], 3)
            self.assertEqual(brazil.payload["input_source_counts"]["gbif_api"], 2)

    def test_reports_gap_when_observation_inputs_are_absent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            SourceIndex(artifact_dir / "source_index.sqlite").initialize()

            result = build_occurrence_ecology_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertEqual(result.records, [])
            self.assertEqual(result.gaps[0]["reason"], "no_indexed_aedes_observation_records")


if __name__ == "__main__":
    unittest.main()
