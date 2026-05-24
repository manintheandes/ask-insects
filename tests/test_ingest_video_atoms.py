from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from scripts.ingest_video_atoms import ingest_video_atoms
from tests.test_video_atoms_source import RETRIEVED_AT, write_video_fixture


class IngestVideoAtomsTests(unittest.TestCase):
    def test_ingest_updates_video_atoms_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)
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
                        provenance=Provenance(
                            source_id="mosquito_v1_fixtures",
                            locator="fixture#taxonomy",
                            retrieved_at=RETRIEVED_AT,
                        ),
                    )
                ]
            )

            result = ingest_video_atoms(
                artifact_dir=artifact_dir,
                retrieved_at=RETRIEVED_AT,
                mirror_videos=True,
                max_video_bytes=100,
                fetch_video_bytes_fn=lambda url, max_bytes: b"video-bytes",
                probe_video_file_fn=lambda path: {
                    "duration_seconds": 3.0,
                    "fps": 25.0,
                    "width": 320,
                    "height": 240,
                    "codec": "h264",
                },
                allowed_licenses=("Creative Commons Attribution License",),
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["source"], "aedes_video_atoms")
            self.assertEqual(result["video_asset_count"], 2)
            self.assertEqual(result["mirrored_video_count"], 1)
            self.assertEqual(result["verified_video_count"], 1)
            self.assertEqual(result["artifact_count"], 0)
            self.assertGreaterEqual(result["gap_count"], 1)
            rows = index.sql("select source, lane, count(*) as n from records group by source, lane", limit=100)
            counts = {(row["source"], row["lane"]): int(row["n"]) for row in rows}
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 1)
            self.assertEqual(counts[("aedes_video_atoms", "media")], 4)
            payload_rows = index.sql("select count(*) as n from record_payloads where source='aedes_video_atoms'")
            self.assertEqual(payload_rows[0]["n"], 4)
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn("aedes_video_atoms", status["sources"])
            self.assertEqual(status["aedes_video_atoms"]["video_asset_count"], 2)
            self.assertEqual(status["aedes_video_atoms"]["mirrored_video_count"], 1)
            self.assertEqual(status["aedes_video_atoms"]["verified_video_count"], 1)
            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["aedes_video_atoms"]["record_count"], 4)
            gaps = json.loads((artifact_dir / "gaps.json").read_text(encoding="utf-8"))
            self.assertTrue(any(gap.get("reason") == "video_license_unclear" for gap in gaps))

    def test_ingest_resolves_relative_motion_tables_against_artifact_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)
            table_path = artifact_dir / "raw" / "video_atoms" / "motion.csv"
            table_path.parent.mkdir(parents=True, exist_ok=True)
            table_path.write_text(
                "video_id,track_id,frame,time_seconds,x,y,behavior\n"
                "pmc:video:PMC123:video1.mp4,track-1,7,0.28,10.5,20.5,flight\n",
                encoding="utf-8",
            )

            result = ingest_video_atoms(
                artifact_dir=artifact_dir,
                retrieved_at=RETRIEVED_AT,
                motion_table_paths=[Path("raw/video_atoms/motion.csv")],
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["motion_row_count"], 1)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='aedes_video_atoms' and lane='behavior'",
                limit=5,
            )
            self.assertIn("raw/video_atoms/motion.csv#row/1", rows[0]["provenance_json"])


if __name__ == "__main__":
    unittest.main()
