from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.drosophila_suzukii import DROSOPHILA_SUZUKII_SOURCE_ID
from askinsects.sources.drosophila_suzukii_occurrence_ecology import (
    DROSOPHILA_SUZUKII_OCCURRENCE_ECOLOGY_SOURCE_ID,
    build_drosophila_suzukii_occurrence_ecology_records,
)


def swd_observation_record(record_id: str, payload: dict[str, object], *, country_text: str) -> EvidenceRecord:
    return EvidenceRecord(
        record_id=record_id,
        lane="observations",
        source=DROSOPHILA_SUZUKII_SOURCE_ID,
        title=f"Drosophila suzukii observation in {country_text}",
        text=f"Drosophila suzukii occurrence observation in {country_text}.",
        species="Drosophila suzukii",
        url=f"https://example.test/{record_id}",
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_SOURCE_ID,
            locator=f"raw/drosophila_suzukii#{record_id}",
            retrieved_at="2026-05-28T00:00:00Z",
            license="test",
            source_url=f"https://example.test/{record_id}",
        ),
        payload=payload,
    )


def write_swd_occurrence_ecology_fixture(artifact_dir: Path) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.upsert_records(
        [
            swd_observation_record(
                "swd:gbif:1",
                {
                    "upstream_source": "gbif",
                    "raw_occurrence": {
                        "country": "United States",
                        "eventDate": "2025-08-14",
                        "decimalLatitude": 45.52,
                        "decimalLongitude": -122.67,
                        "datasetName": "GBIF test dataset",
                        "occurrenceRemarks": "raspberry field edge",
                    },
                },
                country_text="United States",
            ),
            swd_observation_record(
                "swd:gbif:2",
                {
                    "upstream_source": "gbif",
                    "raw_occurrence": {
                        "country": "United States",
                        "eventDate": "2025-09-02",
                        "decimalLatitude": 44.05,
                        "decimalLongitude": -123.09,
                        "datasetName": "GBIF test dataset",
                    },
                },
                country_text="United States",
            ),
            swd_observation_record(
                "swd:inat:1",
                {
                    "upstream_source": "inaturalist",
                    "raw_observation": {
                        "observed_on": "2026-05-24",
                        "observed_on_details": {"month": 5},
                        "place_guess": "St. Tammany Parish, LA, USA",
                        "quality_grade": "research",
                        "geojson": {"coordinates": [-90.06, 30.38]},
                        "ofvs": [{"name": "Habitat", "value": "Berry garden"}],
                    },
                },
                country_text="United States",
            ),
        ]
    )


class DrosophilaSuzukiiOccurrenceEcologyTests(unittest.TestCase):
    def test_builds_country_month_and_habitat_ecology_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_swd_occurrence_ecology_fixture(artifact_dir)

            result = build_drosophila_suzukii_occurrence_ecology_records(
                artifact_dir,
                retrieved_at="2026-05-28T00:00:00Z",
            )

            self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_OCCURRENCE_ECOLOGY_SOURCE_ID)
            self.assertEqual(result.observation_count, 3)
            self.assertEqual(result.country_count, 1)
            self.assertEqual(result.country_month_count, 3)
            self.assertEqual(result.habitat_count, 1)
            self.assertFalse(result.gaps)
            by_id = {record.record_id: record for record in result.records}
            self.assertIn("swd_occurrence_ecology:country:United_States_of_America", by_id)
            self.assertIn("swd_occurrence_ecology:country_month:United_States_of_America:08", by_id)
            self.assertIn("swd_occurrence_ecology:habitat:United_States_of_America:Berry_garden", by_id)
            country = by_id["swd_occurrence_ecology:country:United_States_of_America"]
            self.assertEqual(country.source, DROSOPHILA_SUZUKII_OCCURRENCE_ECOLOGY_SOURCE_ID)
            self.assertEqual(country.lane, "ecology")
            self.assertIn("country summary for United States of America", country.text)
            self.assertEqual(country.payload["observation_count"], 3)
            self.assertEqual(country.payload["input_source_counts"]["gbif"], 2)

    def test_reports_gap_when_observation_inputs_are_absent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            SourceIndex(artifact_dir / "source_index.sqlite").initialize()

            result = build_drosophila_suzukii_occurrence_ecology_records(
                artifact_dir,
                retrieved_at="2026-05-28T00:00:00Z",
            )

            self.assertEqual(result.records, [])
            self.assertEqual(result.gaps[0]["reason"], "no_indexed_drosophila_suzukii_observation_records")


if __name__ == "__main__":
    unittest.main()
