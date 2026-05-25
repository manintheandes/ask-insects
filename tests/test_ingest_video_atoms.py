from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources import video_atoms
from scripts.ingest_video_atoms import ingest_video_atoms
from tests.test_mendeley_behavior_media_source import tiny_xlsx
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

    def test_ingest_discovers_default_mendeley_xlsx_motion_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)
            table_path = artifact_dir / "raw" / "mendeley_behavior_media" / "table_files" / "movement.xlsx"
            table_path.parent.mkdir(parents=True, exist_ok=True)
            table_path.write_bytes(
                tiny_xlsx(
                    [
                        ["Behavioural_Activity", "Trial", "Subject", "Zone", "Species", "Velocity.center.point.Mean.cm.s"],
                        ["Walking", "Trial 7", "Subject 9", "In Arena", "Aedes aegypti", "3.25"],
                    ]
                )
            )

            result = ingest_video_atoms(artifact_dir=artifact_dir, retrieved_at=RETRIEVED_AT)

            self.assertTrue(result["ok"])
            self.assertEqual(result["motion_row_count"], 1)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select payload_json, provenance_json from record_payloads where source='aedes_video_atoms' and lane='behavior'",
                limit=5,
            )
            payload = json.loads(rows[0]["payload_json"])
            self.assertEqual(payload["behavior_type"], "Walking")
            self.assertEqual(payload["velocity_mean_cm_s"], 3.25)
            self.assertIn("raw/mendeley_behavior_media/table_files/movement.xlsx#sheet/1/row/2", rows[0]["provenance_json"])

    def test_ingest_writes_video_discovery_sweep_receipts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)
            discovery_clients = {
                repository: (lambda repository=repository: [
                    {
                        "title": f"Aedes aegypti {repository} video",
                        "download_url": f"https://example.org/{repository}.mp4",
                        "source_url": f"https://example.org/{repository}",
                        "license": "CC-BY",
                        "repository": repository,
                        "species_scope": "Aedes aegypti",
                    }
                ])
                for repository in video_atoms.DISCOVERY_REPOSITORIES
            }

            result = ingest_video_atoms(
                artifact_dir=artifact_dir,
                retrieved_at=RETRIEVED_AT,
                discover_sources=True,
                discovery_clients=discovery_clients,
            )

            self.assertTrue(result["ok"])
            self.assertEqual({receipt["repository"] for receipt in result["discovery_sweep_receipts"]}, set(video_atoms.DISCOVERY_REPOSITORIES))
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(
                {item["repository"] for item in status["aedes_video_atoms"]["discovery_sweep_receipts"]},
                set(video_atoms.DISCOVERY_REPOSITORIES),
            )
            self.assertEqual(
                {item["repository"] for item in receipt["aedes_video_atoms"]["discovery_sweep_receipts"]},
                set(video_atoms.DISCOVERY_REPOSITORIES),
            )
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select json_extract(payload_json, '$.repository') as repository from record_payloads where source='aedes_video_atoms' and json_extract(payload_json, '$.atom_type')='video_sweep'",
                limit=20,
            )
            self.assertEqual({row["repository"] for row in rows}, set(video_atoms.DISCOVERY_REPOSITORIES))

    def test_ingest_preserves_existing_mirror_and_artifact_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)
            safe_id = video_atoms._safe_id("pmc:video:PMC123:video1.mp4")
            asset_path = artifact_dir / "raw" / "video_atoms" / "assets" / f"{safe_id}_existing.mp4"
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            asset_path.write_bytes(b"existing-video-bytes")
            probe = {
                "duration_seconds": 4.0,
                "fps": 24.0,
                "width": 640,
                "height": 480,
                "codec": "h264",
            }
            first = video_atoms.build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                probe_video_file_fn=lambda path: probe,
            )
            asset = next(record for record in first.records if record.payload["source_video_record_id"] == "pmc:video:PMC123:video1.mp4")
            output_dir = artifact_dir / "raw" / "video_atoms" / "artifacts" / video_atoms._safe_id(asset.record_id)
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "thumbnail.jpg").write_bytes(b"jpg")
            (output_dir / "preview.mp4").write_bytes(b"mp4")
            (output_dir / "frames.json").write_text(json.dumps({"probe": probe}), encoding="utf-8")

            result = ingest_video_atoms(
                artifact_dir=artifact_dir,
                retrieved_at=RETRIEVED_AT,
                probe_video_file_fn=lambda path: probe,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["mirrored_video_count"], 1)
            self.assertEqual(result["verified_video_count"], 1)
            self.assertEqual(result["artifact_count"], 4)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                """
                select json_extract(payload_json, '$.atom_type') as atom_type,
                       json_extract(payload_json, '$.verification_status') as status,
                       count(*) as n
                from record_payloads
                where source='aedes_video_atoms'
                group by atom_type, status
                """,
                limit=20,
            )
            counts = {(row["atom_type"], row["status"]): int(row["n"]) for row in rows}
            self.assertEqual(counts[("video_asset", "verified")], 1)
            self.assertEqual(counts[("video_thumbnail", None)], 1)
            self.assertEqual(counts[("video_keyframe", None)], 1)
            self.assertEqual(counts[("video_preview_clip", None)], 1)
            self.assertEqual(counts[("video_frame_manifest", None)], 1)


if __name__ == "__main__":
    unittest.main()
