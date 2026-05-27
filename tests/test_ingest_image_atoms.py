from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from scripts.ingest_image_atoms import ingest_image_atoms
from tests.test_image_atoms_source import PNG_1X1, RETRIEVED_AT, write_image_fixture


class IngestImageAtomsTests(unittest.TestCase):
    def test_ingest_updates_image_atoms_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_image_fixture(artifact_dir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="fixture:taxonomy:aedes",
                        lane="taxonomy",
                        source="mosquito_v1_fixtures",
                        title="Aedes aegypti",
                        text="Aedes aegypti taxonomy fixture.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(source_id="mosquito_v1_fixtures", locator="fixture#taxonomy", retrieved_at=RETRIEVED_AT),
                    )
                ]
            )

            result = ingest_image_atoms(artifact_dir=artifact_dir, retrieved_at=RETRIEVED_AT)

            self.assertTrue(result["ok"])
            self.assertEqual(result["source"], "aedes_image_atoms")
            self.assertEqual(result["image_asset_count"], 2)
            self.assertGreater(result["image_label_count"], 0)
            rows = index.sql("select source, lane, count(*) as n from records group by source, lane", limit=100)
            counts = {(row["source"], row["lane"]): int(row["n"]) for row in rows}
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 1)
            self.assertGreater(counts[("aedes_image_atoms", "media")], 2)
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn("aedes_image_atoms", status["sources"])
            self.assertEqual(status["aedes_image_atoms"]["image_asset_count"], 2)
            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["aedes_image_atoms"]["record_count"], result["record_count"])
            gaps = json.loads((artifact_dir / "gaps.json").read_text(encoding="utf-8"))
            self.assertTrue(any(gap.get("source") == "aedes_image_atoms" for gap in gaps))
            alive_rows = index.search("alive", lane="media", limit=5)
            self.assertTrue(any(row.source == "aedes_image_atoms" for row in alive_rows))
            organism_rows = index.search("organism", lane="media", limit=5)
            self.assertTrue(any(row.source == "aedes_image_atoms" for row in organism_rows))

    def test_ingest_records_mirrored_image_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_image_fixture(artifact_dir)

            result = ingest_image_atoms(
                artifact_dir=artifact_dir,
                retrieved_at=RETRIEVED_AT,
                mirror_images=True,
                max_image_bytes=10_000,
                allowed_licenses=("cc-by",),
                fetch_image_bytes_fn=lambda url, max_bytes: (PNG_1X1, "image/png"),
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["mirrored_image_count"], 2)
            self.assertEqual(result["verified_image_count"], 2)
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["aedes_image_atoms"]["mirrored_image_count"], 2)
            self.assertEqual(status["aedes_image_atoms"]["verified_image_count"], 2)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select count(*) as n from record_payloads where source='aedes_image_atoms' and json_extract(payload_json, '$.raw_asset_path') is not null",
                limit=5,
            )
            self.assertEqual(rows[0]["n"], 2)


if __name__ == "__main__":
    unittest.main()
