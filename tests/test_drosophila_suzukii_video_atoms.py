from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.drosophila_suzukii_video_atoms import (
    DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID,
    build_drosophila_suzukii_video_atom_records,
)


RETRIEVED_AT = "2026-05-28T00:00:00Z"


def write_swd_video_fixture(artifact_dir: Path, *, license_text: str = "CC BY 4.0") -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.upsert_records(
        [
            EvidenceRecord(
                record_id="swd:figshare:video:27176940:d_suzukii_on_fungus_mcevey.mp4",
                lane="media",
                source="drosophila_suzukii_deep_sources",
                title="Drosophila suzukii Figshare video file D suzukii on fungus, McEvey.mp4",
                text="Figshare moving-image file for Drosophila suzukii behavior on fungus.",
                species="Drosophila suzukii",
                url="https://figshare.com/articles/media/example/27176940",
                media_url="https://ndownloader.figshare.com/files/49633659",
                provenance=Provenance(
                    source_id="drosophila_suzukii_deep_sources",
                    locator="raw/drosophila_suzukii_deep_sources/figshare/figshare_article_27176940.json#files/1",
                    retrieved_at=RETRIEVED_AT,
                    license=license_text,
                    source_url="https://ndownloader.figshare.com/files/49633659",
                ),
                payload={"raw_file": {"name": "D suzukii on fungus, McEvey.mp4", "size": 25}},
            )
        ]
    )


class DrosophilaSuzukiiVideoAtomsTests(unittest.TestCase):
    def test_builds_manifest_video_asset_and_motion_gap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_swd_video_fixture(artifact_dir)

            result = build_drosophila_suzukii_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
            )

            self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID)
            self.assertEqual(result.video_asset_count, 1)
            asset = [record for record in result.records if record.payload.get("atom_type") == "video_asset"][0]
            self.assertEqual(asset.source, DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID)
            self.assertEqual(asset.species, "Drosophila suzukii")
            self.assertEqual(asset.payload["verification_status"], "manifest_only")
            self.assertEqual(result.motion_row_count, 0)
            self.assertTrue(any(gap["reason"] == "source_trajectory_tables_not_available_for_swd" for gap in result.gaps))

    def test_license_unclear_blocks_mirror_but_keeps_queryable_gap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_swd_video_fixture(artifact_dir, license_text="unknown")

            result = build_drosophila_suzukii_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                mirror_videos=True,
            )

            reasons = [gap["reason"] for gap in result.gaps]
            self.assertIn("video_license_unclear", reasons)
            asset = [record for record in result.records if record.payload.get("atom_type") == "video_asset"][0]
            self.assertEqual(asset.payload["verification_status"], "manifest_only_license_unclear")

    def test_mirror_probe_and_artifact_rows_are_queryable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_swd_video_fixture(artifact_dir)

            def fake_fetch(url: str, max_bytes: int) -> bytes:
                self.assertIn("figshare", url)
                return b"fake video bytes"

            def fake_probe(path: Path) -> dict[str, object]:
                return {"duration_seconds": 4.5, "fps": 30.0, "width": 640, "height": 480, "codec": "h264"}

            def fake_artifacts(asset_path: Path, output_dir: Path, probe: dict[str, object]) -> dict[str, object]:
                output_dir.mkdir(parents=True, exist_ok=True)
                thumbnail = output_dir / "thumbnail.jpg"
                keyframe = output_dir / "keyframe_000001.jpg"
                preview = output_dir / "preview.mp4"
                manifest = output_dir / "frames.json"
                for path in (thumbnail, keyframe, preview, manifest):
                    path.write_bytes(b"x")
                return {
                    "thumbnail_path": thumbnail.as_posix(),
                    "keyframe_paths": [keyframe.as_posix()],
                    "preview_clip_path": preview.as_posix(),
                    "frame_manifest_path": manifest.as_posix(),
                }

            result = build_drosophila_suzukii_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                mirror_videos=True,
                generate_artifacts=True,
                fetch_video_bytes_fn=fake_fetch,
                probe_video_file_fn=fake_probe,
                artifact_generator_fn=fake_artifacts,
            )

            self.assertEqual(result.mirrored_video_count, 1)
            self.assertEqual(result.verified_video_count, 1)
            self.assertEqual(result.artifact_count, 4)
            self.assertEqual(result.motion_row_count, 1)
            atom_types = {record.payload.get("atom_type") for record in result.records if record.payload}
            self.assertIn("video_keyframe", atom_types)
            self.assertIn("video_preview_clip", atom_types)
            self.assertIn("video_motion_row", atom_types)
            asset = [record for record in result.records if record.payload.get("atom_type") == "video_asset"][0]
            self.assertEqual(asset.payload["codec"], "h264")
            self.assertTrue(str(asset.payload["mirror_path"]).startswith("raw/drosophila_suzukii_video_atoms/"))
            motion = [record for record in result.records if record.payload.get("atom_type") == "video_motion_row"][0]
            self.assertEqual(motion.lane, "behavior")
            self.assertEqual(motion.payload["source_video_asset_id"], asset.record_id)
            self.assertEqual(motion.payload["time_start_seconds"], 0.0)
            self.assertEqual(motion.payload["time_end_seconds"], 4.5)
            self.assertEqual(motion.payload["frame_start"], 0)
            self.assertEqual(motion.payload["frame_end"], 135)
            self.assertFalse(motion.payload["coordinates_available"])
            self.assertEqual(motion.payload["coordinate_detail"], "source trajectory table not available")
            self.assertEqual(motion.payload["behavior_type"], "feeding")
            self.assertEqual(motion.payload["confidence"], "derived_video_interval_no_tracking_table")


if __name__ == "__main__":
    unittest.main()
