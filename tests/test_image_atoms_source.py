from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.image_atoms import IMAGE_ATOMS_SOURCE_ID, build_image_atom_records


RETRIEVED_AT = "2026-05-25T00:00:00Z"


def write_image_fixture(artifact_dir: Path) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.upsert_records(
        [
            EvidenceRecord(
                record_id="inat:media:99",
                lane="media",
                source="inaturalist_api",
                title="Aedes aegypti iNaturalist still image 99",
                text="iNaturalist still image for Aedes aegypti.",
                species="Aedes aegypti",
                url="https://www.inaturalist.org/observations/12345",
                media_url="https://static.inaturalist.org/photos/99/medium.jpg",
                provenance=Provenance(
                    source_id="inaturalist_api",
                    locator="raw/inaturalist/page.json#observations/12345/photos/99",
                    retrieved_at=RETRIEVED_AT,
                    license="cc-by",
                    source_url="https://www.inaturalist.org/observations/12345",
                ),
                payload={
                    "raw_observation": {
                        "id": 12345,
                        "observed_on": "2026-05-01",
                        "place_guess": "Brazil",
                        "quality_grade": "research",
                        "geojson": {"type": "Point", "coordinates": [-43.2, -22.9]},
                        "annotations": [{"controlled_attribute_id": 1, "controlled_value_id": 2, "concatenated_attr_val": "1|2"}],
                    },
                    "raw_photo": {
                        "id": 99,
                        "url": "https://static.inaturalist.org/photos/99/medium.jpg",
                        "license_code": "cc-by",
                        "attribution": "(c) Example Observer",
                    },
                },
            ),
            EvidenceRecord(
                record_id="mosquito_alert:media:4909387174:image",
                lane="media",
                source="mosquito_alert_gbif",
                title="Aedes aegypti Mosquito Alert still image 4909387174",
                text="Mosquito Alert still image for Aedes aegypti.",
                species="Aedes aegypti",
                url="https://www.gbif.org/occurrence/4909387174",
                media_url="http://webserver.mosquitoalert.com/media/tigapics/example.jpg",
                provenance=Provenance(
                    source_id="mosquito_alert_gbif",
                    locator="raw/mosquito_alert/page.json#occurrence/4909387174/media/1",
                    retrieved_at=RETRIEVED_AT,
                    license="Anonymous, CC by Mosquito Alert",
                    source_url="http://webserver.mosquitoalert.com/media/tigapics/example.jpg",
                ),
                payload={
                    "raw_occurrence": {
                        "key": 4909387174,
                        "species": "Aedes aegypti",
                        "country": "Brazil",
                        "eventDate": "2023-01-24",
                        "basisOfRecord": "HUMAN_OBSERVATION",
                        "identifiedBy": "Example expert",
                        "lifeStage": "Adult",
                        "occurrenceStatus": "PRESENT",
                    },
                    "raw_media": {
                        "type": "StillImage",
                        "format": "image/jpeg",
                        "license": "Anonymous, CC by Mosquito Alert",
                        "rightsHolder": "Mosquito Alert",
                        "creator": "Anonymous Mosquito Alert citizen scientist",
                    },
                },
            ),
        ]
    )


class ImageAtomsSourceTests(unittest.TestCase):
    def test_builds_image_assets_labels_and_structured_label_gaps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_image_fixture(artifact_dir)

            result = build_image_atom_records(artifact_dir, retrieved_at=RETRIEVED_AT)

            self.assertEqual(result.source_id, IMAGE_ATOMS_SOURCE_ID)
            self.assertEqual(result.image_asset_count, 2)
            self.assertGreaterEqual(result.image_label_count, 6)
            self.assertTrue(any(gap["reason"] == "image_label_missing" for gap in result.gaps))
            labels = [record for record in result.records if record.payload and record.payload.get("atom_type") == "image_label"]
            label_pairs = {(record.payload["label_type"], record.payload["label_value"]) for record in labels}
            self.assertIn(("life_stage", "adult"), label_pairs)
            self.assertIn(("life_stage", "Adult"), label_pairs)
            self.assertIn(("quality_grade", "research"), label_pairs)
            self.assertIn(("media_format", "image/jpeg"), label_pairs)
            asset = next(record for record in result.records if record.payload and record.payload.get("atom_type") == "image_asset")
            self.assertEqual(asset.source, IMAGE_ATOMS_SOURCE_ID)
            self.assertIn("records#inat:media:99", asset.provenance.locator)
            self.assertEqual(asset.payload["latitude"], -22.9)

    def test_ignores_non_aedes_or_missing_media_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="inat:media:no-url",
                        lane="media",
                        source="inaturalist_api",
                        title="Aedes aegypti no media",
                        text="no media",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(source_id="inaturalist_api", locator="raw#1", retrieved_at=RETRIEVED_AT),
                    ),
                    EvidenceRecord(
                        record_id="inat:media:culex",
                        lane="media",
                        source="inaturalist_api",
                        title="Culex image",
                        text="not Aedes",
                        species="Culex pipiens",
                        url=None,
                        media_url="https://example.org/culex.jpg",
                        provenance=Provenance(source_id="inaturalist_api", locator="raw#2", retrieved_at=RETRIEVED_AT),
                    ),
                ]
            )

            result = build_image_atom_records(artifact_dir, retrieved_at=RETRIEVED_AT)

            self.assertEqual(result.image_asset_count, 0)
            self.assertEqual(result.records, [])
            self.assertEqual(result.gaps, [])


if __name__ == "__main__":
    unittest.main()
