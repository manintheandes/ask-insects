from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from scripts.ingest_drosophila_suzukii_video_atoms import ingest_drosophila_suzukii_video_atoms
from tests.test_drosophila_suzukii_video_atoms import RETRIEVED_AT, write_swd_video_fixture


class IngestDrosophilaSuzukiiVideoAtomsTests(unittest.TestCase):
    def test_ingest_updates_receipts_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_swd_video_fixture(artifact_dir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="aedes:keep",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes video row to preserve",
                        text="Existing Aedes video atom row.",
                        species="Aedes aegypti",
                        url=None,
                        media_url="raw/video_atoms/aedes.jpg",
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="records#aedes:keep",
                            retrieved_at=RETRIEVED_AT,
                        ),
                    )
                ]
            )

            result = ingest_drosophila_suzukii_video_atoms(
                artifact_dir=artifact_dir,
                retrieved_at=RETRIEVED_AT,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["source"], "drosophila_suzukii_video_atoms")
            self.assertEqual(result["video_asset_count"], 1)
            counts = {
                row["source"]: int(row["n"])
                for row in index.sql("select source, count(*) as n from records group by source", limit=100)
            }
            self.assertGreaterEqual(counts["drosophila_suzukii_deep_sources"], 1)
            self.assertGreaterEqual(counts["drosophila_suzukii_video_atoms"], 2)
            self.assertEqual(counts["aedes_video_atoms"], 1)
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            self.assertIn("drosophila_suzukii_video_atoms", status["sources"])
            self.assertIn("drosophila_suzukii_video_atoms", receipt["sources"])
            self.assertEqual(status["drosophila_suzukii_video_atoms"]["video_asset_count"], 1)


if __name__ == "__main__":
    unittest.main()
