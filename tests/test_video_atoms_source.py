from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlparse
import zipfile

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources import video_atoms
from askinsects.sources.video_atoms import (
    AedesVideoAtomsResult,
    DISCOVERY_REPOSITORIES,
    DiscoverySweepResult,
    VIDEO_ATOMS_SOURCE_ID,
    VideoDownloadNotVideoError,
    build_video_atom_records,
    default_discovery_clients,
)
from tests.test_mendeley_behavior_media_source import tiny_xlsx


RETRIEVED_AT = "2026-05-24T00:00:00Z"


def write_video_fixture(artifact_dir: Path) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    records = [
        EvidenceRecord(
            record_id="pmc:video:PMC123:video1.mp4",
            lane="media",
            source="pmc_open_access_videos",
            title="Aedes aegypti PMC supplementary video video1.mp4",
            text="BiteOscope Aedes aegypti mosquito biting behavior video file video1.mp4.",
            species="Aedes aegypti",
            url="https://pmc.ncbi.nlm.nih.gov/articles/PMC123/",
            media_url="https://example.org/video1.mp4",
            provenance=Provenance(
                source_id="pmc_open_access_videos",
                locator="raw/pmc_videos/PMC123.html#video/1",
                retrieved_at=RETRIEVED_AT,
                license="Creative Commons Attribution License",
                source_url="https://pmc.ncbi.nlm.nih.gov/articles/PMC123/",
            ),
            payload={
                "article_title": "BiteOscope",
                "filename": "video1.mp4",
                "video_url": "https://example.org/video1.mp4",
            },
        ),
        EvidenceRecord(
            record_id="osf:flighttrackai:file:VIDEOA",
            lane="media",
            source="osf_flighttrackai_aedes_videos",
            title="Aedes aegypti OSF FlightTrackAI video file Video A.mp4",
            text="Flight tracking video. File: Video A.mp4. Size bytes: 200.",
            species="Aedes aegypti",
            url="https://osf.io/cx762/",
            media_url="https://osf.io/download/video-a/",
            provenance=Provenance(
                source_id="osf_flighttrackai_aedes_videos",
                locator="raw/osf/file.json#files/1",
                retrieved_at=RETRIEVED_AT,
                license="CC-BY",
                source_url="https://api.osf.io/v2/files/video-a/",
            ),
            payload={
                "name": "Video A.mp4",
                "materialized_path": "/PROCESSED VIDEOS/Video A.mp4",
                "size": 200,
                "download_url": "https://osf.io/download/video-a/",
            },
        ),
        EvidenceRecord(
            record_id="inaturalist:photo:1",
            lane="media",
            source="inaturalist_api",
            title="Still image",
            text="Aedes aegypti still image.",
            species="Aedes aegypti",
            url="https://example.org/photo",
            media_url="https://example.org/photo.jpg",
            provenance=Provenance(
                source_id="inaturalist_api",
                locator="raw/inat/page.json#photo/1",
                retrieved_at=RETRIEVED_AT,
                license="CC-BY",
            ),
            payload={"photo_url": "https://example.org/photo.jpg"},
        ),
    ]
    index.upsert_records(records)


class VideoAtomsSourceTests(unittest.TestCase):
    def test_builds_video_candidates_from_existing_media(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)

            result = build_video_atom_records(artifact_dir, retrieved_at=RETRIEVED_AT)

        self.assertIsInstance(result, AedesVideoAtomsResult)
        self.assertEqual(result.source_id, VIDEO_ATOMS_SOURCE_ID)
        self.assertEqual(result.video_asset_count, 2)
        self.assertEqual(result.mirrored_video_count, 0)
        self.assertEqual(result.artifact_count, 0)
        self.assertEqual(result.motion_row_count, 0)
        assets = [record for record in result.records if record.payload["atom_type"] == "video_asset"]
        self.assertEqual(len(assets), 2)
        pmc = next(record for record in assets if record.payload["source_video_record_id"] == "pmc:video:PMC123:video1.mp4")
        self.assertEqual(pmc.source, VIDEO_ATOMS_SOURCE_ID)
        self.assertEqual(pmc.lane, "media")
        self.assertEqual(pmc.media_url, "https://example.org/video1.mp4")
        self.assertEqual(pmc.payload["source_dataset"], "BiteOscope")
        self.assertEqual(pmc.payload["download_url"], "https://example.org/video1.mp4")
        self.assertEqual(pmc.payload["license"], "Creative Commons Attribution License")
        self.assertEqual(pmc.payload["verification_status"], "candidate")
        self.assertEqual(pmc.payload["source_video_provenance"]["source_id"], "pmc_open_access_videos")

    def test_builds_video_candidates_from_figshare_source_lane(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="figshare:aedes-video:101:oviposition_mp4",
                        lane="media",
                        source="figshare_aedes_videos",
                        title="Aedes aegypti Figshare oviposition video file oviposition.mp4",
                        text="Figshare video file for Aedes aegypti oviposition behavior.",
                        species="Aedes aegypti",
                        url="https://figshare.com/articles/dataset/101",
                        media_url="https://ndownloader.figshare.com/files/202",
                        provenance=Provenance(
                            source_id="figshare_aedes_videos",
                            locator="raw/figshare_aedes_videos/article_101.json#files/1",
                            retrieved_at=RETRIEVED_AT,
                            license="CC BY 4.0",
                            source_url="https://ndownloader.figshare.com/files/202",
                        ),
                        payload={
                            "filename": "oviposition.mp4",
                            "source_byte_size": 123456,
                            "source_hashes": {"md5": "a" * 32},
                        },
                    )
                ]
            )

            result = build_video_atom_records(artifact_dir, retrieved_at=RETRIEVED_AT)

        asset = next(record for record in result.records if record.payload.get("source_video_record_id") == "figshare:aedes-video:101:oviposition_mp4")
        self.assertEqual(asset.payload["repository"], "figshare")
        self.assertEqual(asset.payload["source_byte_size"], 123456)
        self.assertEqual(asset.payload["source_hashes"]["md5"], "a" * 32)
        self.assertEqual(asset.payload["source_video_provenance"]["source_id"], "figshare_aedes_videos")

    def test_mirrors_and_probes_downloadable_videos(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)
            video_bytes = b"fake-video-bytes"

            def fake_fetch(url: str, max_bytes: int) -> bytes:
                self.assertEqual(url, "https://example.org/video1.mp4")
                self.assertGreaterEqual(max_bytes, len(video_bytes))
                return video_bytes

            def fake_probe(path: Path) -> dict[str, object]:
                self.assertTrue(path.exists())
                return {
                    "duration_seconds": 12.4,
                    "fps": 30.0,
                    "width": 1920,
                    "height": 1080,
                    "codec": "h264",
                }

            result = build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                mirror_videos=True,
                max_video_bytes=10_000,
                fetch_video_bytes_fn=fake_fetch,
                probe_video_file_fn=fake_probe,
                allowed_licenses=("Creative Commons Attribution License",),
            )

            asset = next(record for record in result.records if record.payload["source_video_record_id"] == "pmc:video:PMC123:video1.mp4")
            digest = hashlib.sha256(video_bytes).hexdigest()
            self.assertEqual(asset.payload["verification_status"], "verified")
            self.assertEqual(asset.payload["sha256"], digest)
            self.assertEqual(asset.payload["byte_size"], len(video_bytes))
            self.assertEqual(asset.payload["duration_seconds"], 12.4)
            self.assertEqual(asset.payload["fps"], 30.0)
            self.assertEqual(asset.payload["width"], 1920)
            self.assertEqual(asset.payload["height"], 1080)
            self.assertEqual(asset.payload["codec"], "h264")
            self.assertTrue(asset.payload["raw_asset_path"].startswith("raw/video_atoms/assets/"))
            self.assertTrue((artifact_dir / asset.payload["raw_asset_path"]).exists())
            self.assertEqual(result.mirrored_video_count, 1)
            self.assertEqual(result.verified_video_count, 1)

    def test_uses_existing_mirrored_asset_when_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)
            video_bytes = b"existing-video-bytes"
            safe_id = video_atoms._safe_id("pmc:video:PMC123:video1.mp4")
            asset_path = artifact_dir / "raw" / "video_atoms" / "assets" / f"{safe_id}_existing.mp4"
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            asset_path.write_bytes(video_bytes)

            result = build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                mirror_videos=False,
                probe_video_file_fn=lambda path: {
                    "duration_seconds": 8.5,
                    "fps": 60.0,
                    "width": 1280,
                    "height": 720,
                    "codec": "h264",
                },
            )

        asset = next(record for record in result.records if record.payload["source_video_record_id"] == "pmc:video:PMC123:video1.mp4")
        self.assertEqual(asset.payload["verification_status"], "verified")
        self.assertEqual(asset.payload["sha256"], hashlib.sha256(video_bytes).hexdigest())
        self.assertEqual(asset.payload["byte_size"], len(video_bytes))
        self.assertEqual(asset.payload["duration_seconds"], 8.5)
        self.assertEqual(asset.payload["fps"], 60.0)
        self.assertEqual(asset.payload["width"], 1280)
        self.assertEqual(asset.payload["height"], 720)
        self.assertEqual(asset.payload["codec"], "h264")
        self.assertTrue(asset.payload["raw_asset_path"].endswith("_existing.mp4"))
        self.assertEqual(result.mirrored_video_count, 1)
        self.assertEqual(result.verified_video_count, 1)

    def test_mirrored_video_with_failed_probe_is_not_counted_as_verified(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)

            def fake_probe(path: Path) -> dict[str, object]:
                raise RuntimeError("not parseable as a video")

            def fail_artifacts(asset_path: Path, output_dir: Path, probe: dict[str, object]) -> dict[str, object]:
                raise AssertionError("unverified video should not generate artifacts")

            result = build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                mirror_videos=True,
                generate_artifacts=True,
                max_video_bytes=10_000,
                fetch_video_bytes_fn=lambda url, max_bytes: b"not-a-real-video",
                probe_video_file_fn=fake_probe,
                artifact_generator_fn=fail_artifacts,
                allowed_licenses=("Creative Commons Attribution License",),
            )

            asset = next(record for record in result.records if record.payload["source_video_record_id"] == "pmc:video:PMC123:video1.mp4")
            self.assertEqual(asset.payload["verification_status"], "mirrored_unverified")
            self.assertEqual(result.mirrored_video_count, 1)
            self.assertEqual(result.verified_video_count, 0)
            self.assertEqual(result.artifact_count, 0)
            self.assertTrue(any(gap["reason"] == "video_probe_failed" for gap in result.gaps))
            self.assertFalse(any(gap["reason"] == "video_artifact_generation_failed" for gap in result.gaps))

    def test_non_video_download_payload_becomes_gap_not_mirror(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)

            def fake_fetch(url: str, max_bytes: int) -> bytes:
                raise VideoDownloadNotVideoError("download content-type is not video: text/html")

            result = build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                mirror_videos=True,
                max_video_bytes=10_000,
                fetch_video_bytes_fn=fake_fetch,
                allowed_licenses=("Creative Commons Attribution License",),
            )

            asset = next(record for record in result.records if record.payload["source_video_record_id"] == "pmc:video:PMC123:video1.mp4")
            self.assertEqual(asset.payload["verification_status"], "gapped_download_not_video")
            self.assertNotIn("raw_asset_path", asset.payload)
            self.assertEqual(result.mirrored_video_count, 0)
            self.assertTrue(any(gap["reason"] == "video_download_not_video" for gap in result.gaps))

    def test_records_video_gaps_for_large_or_unclear_assets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="dryad:file:oversized",
                        lane="media",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti oversized video.mp4",
                        text="Video file. Size bytes: 999999.",
                        species="Aedes aegypti",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/example",
                        media_url="https://example.org/oversized.mp4",
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad/file.json#files/1",
                            retrieved_at=RETRIEVED_AT,
                            license="https://spdx.org/licenses/CC0-1.0.html",
                        ),
                        payload={"size": 999_999},
                    ),
                    EvidenceRecord(
                        record_id="osf:unclear:video.mp4",
                        lane="media",
                        source="osf_flighttrackai_aedes_videos",
                        title="Aedes aegypti unclear video.mp4",
                        text="Video file. Size bytes: 999999.",
                        species="Aedes aegypti",
                        url="https://osf.io/cx762/",
                        media_url="https://example.org/unclear.mp4",
                        provenance=Provenance(
                            source_id="osf_flighttrackai_aedes_videos",
                            locator="raw/osf/file.json#files/2",
                            retrieved_at=RETRIEVED_AT,
                            license="OSF project license not supplied",
                        ),
                        payload={
                            "size": 999_999,
                            "raw_file": {
                                "attributes": {
                                    "extra": {
                                        "hashes": {
                                            "md5": "0123456789abcdef0123456789abcdef",
                                            "sha256": "a" * 64,
                                        }
                                    }
                                }
                            },
                        },
                    )
                ]
            )

            result = build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                mirror_videos=True,
                max_video_bytes=100,
                fetch_video_bytes_fn=lambda url, max_bytes: b"x" * 200,
            )

        reasons = {gap["reason"] for gap in result.gaps}
        self.assertIn("video_license_unclear", reasons)
        self.assertIn("video_too_large", reasons)
        asset_statuses = {
            record.payload["source_video_record_id"]: record.payload["verification_status"]
            for record in result.records
            if record.payload and record.payload.get("atom_type") == "video_asset"
        }
        self.assertEqual(asset_statuses["dryad:file:oversized"], "gapped_too_large")
        self.assertEqual(asset_statuses["osf:unclear:video.mp4"], "gapped_license_unclear")
        osf_asset = next(
            record
            for record in result.records
            if record.payload
            and record.payload.get("atom_type") == "video_asset"
            and record.payload["source_video_record_id"] == "osf:unclear:video.mp4"
        )
        self.assertEqual(osf_asset.payload["source_byte_size"], 999_999)
        self.assertEqual(osf_asset.payload["source_hashes"]["sha256"], "a" * 64)
        osf_license_gap = next(
            gap
            for gap in result.gaps
            if gap["reason"] == "video_license_unclear" and gap["record_id"] == "osf:unclear:video.mp4"
        )
        self.assertEqual(osf_license_gap["download_url"], "https://example.org/unclear.mp4")
        self.assertEqual(osf_license_gap["source_byte_size"], 999_999)
        self.assertEqual(osf_license_gap["source_hashes"]["md5"], "0123456789abcdef0123456789abcdef")
        self.assertEqual(osf_license_gap["license"], "OSF project license not supplied")
        gap_records = [record for record in result.records if record.payload and record.payload.get("atom_type") == "video_gap"]
        self.assertEqual({record.payload["reason"] for record in gap_records}, reasons)
        self.assertTrue(all(record.source == VIDEO_ATOMS_SOURCE_ID for record in gap_records))
        osf_gap_record = next(record for record in gap_records if record.payload["record_id"] == "osf:unclear:video.mp4" and record.payload["reason"] == "video_license_unclear")
        self.assertIn("Download URL: https://example.org/unclear.mp4", osf_gap_record.text)
        self.assertIn("Source byte size: 999999", osf_gap_record.text)
        self.assertIn("Source SHA-256: " + "a" * 64, osf_gap_record.text)
        self.assertIn("License: OSF project license not supplied", osf_gap_record.text)

    def test_promotes_upstream_zenodo_figshare_manifest_gaps_to_queryable_atom_gaps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            gaps_path = artifact_dir / "gaps.json"
            gaps_path.write_text(
                json.dumps(
                    [
                        {
                            "source": "zenodo_aedes_videos",
                            "reason": "zenodo_material_record_no_video_files",
                            "record_id": 15277051,
                            "query": '"Aedes aegypti" video',
                            "source_url": "https://doi.org/10.5281/zenodo.15277051",
                            "locator": "raw/zenodo_aedes_videos/search.json#hits/1",
                        },
                        {
                            "source": "figshare_aedes_videos",
                            "reason": "figshare_article_not_aedes_scope",
                            "article_id": 32400201,
                            "query": "Aedes aegypti video",
                            "source_url": "https://figshare.com/articles/poster/32400201",
                            "locator": "raw/figshare_aedes_videos/article_32400201.json#article",
                        },
                        {
                            "source": "aedes_video_atoms",
                            "reason": "video_discovery_no_candidates",
                            "repository": "dryad",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            result = build_video_atom_records(artifact_dir, retrieved_at=RETRIEVED_AT)

        gap_records = [record for record in result.records if record.payload and record.payload.get("atom_type") == "video_gap"]
        self.assertEqual(len(gap_records), 2)
        promoted = {(record.payload["original_source"], record.payload["original_reason"]) for record in gap_records}
        self.assertIn(("zenodo_aedes_videos", "zenodo_material_record_no_video_files"), promoted)
        self.assertIn(("figshare_aedes_videos", "figshare_article_not_aedes_scope"), promoted)
        self.assertTrue(all(record.source == VIDEO_ATOMS_SOURCE_ID for record in gap_records))
        self.assertTrue(all(record.payload["reason"] == "video_manifest_gap" for record in gap_records))
        zenodo = next(record for record in gap_records if record.payload["original_source"] == "zenodo_aedes_videos")
        self.assertEqual(zenodo.provenance.locator, "raw/zenodo_aedes_videos/search.json#hits/1")
        self.assertEqual(zenodo.url, "https://doi.org/10.5281/zenodo.15277051")
        self.assertIn("Original source: zenodo_aedes_videos", zenodo.text)
        self.assertIn("Original reason: zenodo_material_record_no_video_files", zenodo.text)

    def test_archive_video_candidates_expand_bounded_zip_members(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="dryad:file:video-archive",
                        lane="media",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti behavior video archive.zip",
                        text="ZIP archive containing Aedes aegypti assay videos.",
                        species="Aedes aegypti",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/example",
                        media_url="https://datadryad.org/stash/downloads/file_stream/example.zip",
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad/file.json#files/1",
                            retrieved_at=RETRIEVED_AT,
                            license="https://spdx.org/licenses/CC0-1.0.html",
                        ),
                        payload={"filename": "video-archive.zip", "size": 123_456},
                    )
                ]
            )
            archive_path = Path(tmpdir) / "video-archive.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("clip.mp4", b"fake mp4 bytes")
                archive.writestr(
                    "tracks.csv",
                    "video_id,track_id,frame,time_seconds,x,y,behavior\n"
                    "clip.mp4,track-7,12,0.4,10,20,host seeking\n",
                )

            result = build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                mirror_videos=True,
                fetch_video_bytes_fn=lambda url, max_bytes: archive_path.read_bytes(),
                probe_video_file_fn=lambda path: {
                    "duration_seconds": 1.2,
                    "fps": 30.0,
                    "width": 640,
                    "height": 480,
                    "codec": "h264",
                },
            )

            reasons = {gap["reason"] for gap in result.gaps}
            self.assertNotIn("video_archive_not_expanded", reasons)
            manifest = next(record for record in result.records if record.payload.get("atom_type") == "video_archive_manifest")
            self.assertEqual(manifest.payload["video_member_count"], 1)
            member = next(record for record in result.records if record.payload.get("atom_type") == "video_archive_member")
            self.assertEqual(member.payload["member_name"], "clip.mp4")
            asset = next(record for record in result.records if record.payload.get("atom_type") == "video_asset")
            self.assertEqual(asset.payload["verification_status"], "verified")
            self.assertEqual(asset.payload["member_name"], "clip.mp4")
            self.assertEqual(asset.payload["archive_source_video_record_id"], "dryad:file:video-archive")
            self.assertTrue((artifact_dir / asset.payload["raw_asset_path"]).exists())
            rows = [record for record in result.records if record.payload.get("atom_type") == "video_motion_row"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].payload["track_id"], "track-7")
            self.assertIn("source_video_asset_id", rows[0].payload)
            self.assertEqual(rows[0].payload["repository"], "dryad")
            self.assertEqual(rows[0].media_url, asset.media_url)
            self.assertIn("raw/video_atoms/archive_tables/dryad:file:video-archive/tracks.csv#row/1", rows[0].provenance.locator)

    def test_archive_extension_uses_nested_dryad_file_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="dryad:file:nested-video-archive",
                        lane="media",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti behavior video archive",
                        text="ZIP archive containing Aedes aegypti assay videos.",
                        species="Aedes aegypti",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/example",
                        media_url="https://datadryad.org/api/v2/files/10/download",
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad/file.json#files/1",
                            retrieved_at=RETRIEVED_AT,
                            license="CC0",
                        ),
                        payload={
                            "raw_file": {"path": "host_seeking_videos.zip"},
                            "download_url": "https://datadryad.org/api/v2/files/10/download",
                        },
                    )
                ]
            )
            archive_path = Path(tmpdir) / "host_seeking_videos.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("clip.mp4", b"fake mp4 bytes")

            result = build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                mirror_videos=True,
                fetch_video_bytes_fn=lambda url, max_bytes: archive_path.read_bytes(),
                probe_video_file_fn=lambda path: {
                    "duration_seconds": 1.2,
                    "fps": 30.0,
                    "width": 640,
                    "height": 480,
                    "codec": "h264",
                },
            )

        reasons = {gap["reason"] for gap in result.gaps}
        self.assertNotIn("video_archive_unsupported_format", reasons)
        manifest = next(record for record in result.records if record.payload.get("atom_type") == "video_archive_manifest")
        self.assertTrue(manifest.payload["raw_archive_path"].endswith(".zip"))
        asset = next(record for record in result.records if record.payload.get("atom_type") == "video_asset")
        self.assertEqual(asset.payload["verification_status"], "verified")
        self.assertEqual(asset.payload["member_name"], "clip.mp4")

    def test_archive_video_candidates_expand_bounded_tar_gz_members(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="dryad:file:video-tarball",
                        lane="media",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti behavior video archive.tar.gz",
                        text="Tar archive containing Aedes aegypti assay videos.",
                        species="Aedes aegypti",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/example",
                        media_url="https://datadryad.org/stash/downloads/file_stream/example.tar.gz",
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad/file.json#files/2",
                            retrieved_at=RETRIEVED_AT,
                            license="https://spdx.org/licenses/CC0-1.0.html",
                        ),
                        payload={"filename": "video-archive.tar.gz", "size": 123_456},
                    )
                ]
            )
            archive_path = Path(tmpdir) / "video-archive.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                for name, payload in (
                    ("clip.mp4", b"fake mp4 bytes"),
                    (
                        "tracks.csv",
                        b"video_id,track_id,frame,time_seconds,x,y,behavior\n"
                        b"clip.mp4,track-8,16,0.5,11,21,flight\n",
                    ),
                ):
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    archive.addfile(info, io.BytesIO(payload))

            result = build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                mirror_videos=True,
                fetch_video_bytes_fn=lambda url, max_bytes: archive_path.read_bytes(),
                probe_video_file_fn=lambda path: {
                    "duration_seconds": 1.5,
                    "fps": 60.0,
                    "width": 800,
                    "height": 600,
                    "codec": "h264",
                },
            )

            reasons = {gap["reason"] for gap in result.gaps}
            self.assertNotIn("video_archive_unsupported_format", reasons)
            manifest = next(record for record in result.records if record.payload.get("atom_type") == "video_archive_manifest")
            self.assertTrue(manifest.payload["raw_archive_path"].endswith(".tar.gz"))
            self.assertEqual(manifest.payload["video_member_count"], 1)
            asset = next(record for record in result.records if record.payload.get("atom_type") == "video_asset")
            self.assertEqual(asset.payload["verification_status"], "verified")
            self.assertEqual(asset.payload["member_name"], "clip.mp4")
            rows = [record for record in result.records if record.payload.get("atom_type") == "video_motion_row"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].payload["track_id"], "track-8")
            self.assertIn("raw/video_atoms/archive_tables/dryad:file:video-tarball/tracks.csv#row/1", rows[0].provenance.locator)

    def test_ignores_audio_files_from_mixed_media_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="mendeley:file:audio",
                        lane="media",
                        source="mendeley_aedes_behavior_media",
                        title="Aedes aegypti Mendeley video/audio/archive file File 1.wav",
                        text="Wingbeat sound file for Aedes aegypti behavior data.",
                        species="Aedes aegypti",
                        url="https://data.mendeley.com/datasets/example",
                        media_url="https://data.mendeley.com/public-files/file_downloaded",
                        provenance=Provenance(
                            source_id="mendeley_aedes_behavior_media",
                            locator="raw/mendeley_behavior_media/files.json#files/root/1",
                            retrieved_at=RETRIEVED_AT,
                            license="CC BY 4.0",
                        ),
                        payload={"filename": "File 1.wav", "download_url": "https://data.mendeley.com/public-files/file_downloaded"},
                    )
                ]
            )

            result = build_video_atom_records(artifact_dir, retrieved_at=RETRIEVED_AT)

        self.assertEqual(result.video_asset_count, 0)
        self.assertEqual(result.records, [])

    def test_ignores_data_files_from_video_titled_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="dryad:file:data-array",
                        lane="media",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti visual cue tracking video dataset file m_air.npy",
                        text="Dataset file from a visual cue tracking assay, but this file is a NumPy array rather than a video.",
                        species="Aedes aegypti",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/example",
                        media_url="https://datadryad.org/api/v2/files/1726869/download",
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad_behavior_videos/dataset.json#files/1",
                            retrieved_at=RETRIEVED_AT,
                            license="CC0",
                        ),
                        payload={
                            "filename": "m_air.npy",
                            "download_url": "https://datadryad.org/api/v2/files/1726869/download",
                            "size": 816128,
                        },
                    )
                ]
            )

            result = build_video_atom_records(artifact_dir, retrieved_at=RETRIEVED_AT)

        self.assertEqual(result.video_asset_count, 0)
        self.assertEqual(result.records, [])

    def test_ignores_nested_data_files_from_video_titled_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="dryad:file:nested-data-array",
                        lane="media",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti visual cue tracking dataset",
                        text="Visual cue tracking assay file from a mosquito experiment.",
                        species="Aedes aegypti",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/example",
                        media_url="https://datadryad.org/api/v2/files/1726869/download",
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad_behavior_videos/dataset.json#files/1",
                            retrieved_at=RETRIEVED_AT,
                            license="CC0",
                        ),
                        payload={
                            "raw_file": {"path": "m_air.npy"},
                            "download_url": "https://datadryad.org/api/v2/files/1726869/download",
                        },
                    )
                ]
            )

            result = build_video_atom_records(artifact_dir, retrieved_at=RETRIEVED_AT)

        self.assertEqual(result.video_asset_count, 0)
        self.assertEqual(result.records, [])

    def test_ignores_behavior_rows_when_finding_video_assets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="mendeley:table-row:flight",
                        lane="behavior",
                        source="mendeley_aedes_behavior_media",
                        title="Aedes aegypti flight tracking table row",
                        text="Behavior row with flight, tracking, wingbeat, and high-speed terms but no downloadable video file.",
                        species="Aedes aegypti",
                        url="https://data.mendeley.com/datasets/example",
                        media_url=None,
                        provenance=Provenance(
                            source_id="mendeley_aedes_behavior_media",
                            locator="raw/mendeley_behavior_media/table.csv#row/1",
                            retrieved_at=RETRIEVED_AT,
                            license="CC BY 4.0",
                        ),
                    )
                ]
            )

            result = build_video_atom_records(artifact_dir, retrieved_at=RETRIEVED_AT)

        self.assertEqual(result.video_asset_count, 0)
        self.assertEqual(result.records, [])

    def test_builds_video_candidates_from_zenodo_source_lane(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="zenodo:aedes-video:101:oviposition_mp4",
                        lane="media",
                        source="zenodo_aedes_videos",
                        title="Aedes aegypti Zenodo video file oviposition.mp4",
                        text="Zenodo Aedes aegypti video file oviposition.mp4.",
                        species="Aedes aegypti",
                        url="https://zenodo.org/records/101",
                        media_url="https://zenodo.org/api/records/101/files/oviposition.mp4/content",
                        provenance=Provenance(
                            source_id="zenodo_aedes_videos",
                            locator="raw/zenodo_aedes_videos/search.json#hits/1/files/1",
                            retrieved_at=RETRIEVED_AT,
                            license="cc-by-4.0",
                            source_url="https://zenodo.org/api/records/101/files/oviposition.mp4/content",
                        ),
                        payload={
                            "filename": "oviposition.mp4",
                            "download_url": "https://zenodo.org/api/records/101/files/oviposition.mp4/content",
                            "source_byte_size": 123456,
                            "source_hashes": {"md5": "0123456789abcdef0123456789abcdef"},
                        },
                    )
                ]
            )

            result = build_video_atom_records(artifact_dir, retrieved_at=RETRIEVED_AT)

        assets = [record for record in result.records if record.payload.get("atom_type") == "video_asset"]
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0].payload["repository"], "zenodo")
        self.assertEqual(assets[0].payload["source_byte_size"], 123456)
        self.assertEqual(assets[0].payload["source_hashes"]["md5"], "0123456789abcdef0123456789abcdef")

    def test_generates_inspectable_video_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)

            def fake_fetch(url: str, max_bytes: int) -> bytes:
                return b"fake-video-bytes"

            def fake_probe(path: Path) -> dict[str, object]:
                return {"duration_seconds": 4.0, "fps": 24.0, "width": 640, "height": 480, "codec": "h264"}

            def fake_artifacts(asset_path: Path, output_dir: Path, probe: dict[str, object]) -> dict[str, object]:
                output_dir.mkdir(parents=True, exist_ok=True)
                files = {
                    "thumbnail_path": output_dir / "thumbnail.jpg",
                    "keyframe_paths": [output_dir / "keyframe_000001.jpg", output_dir / "keyframe_000096.jpg"],
                    "preview_clip_path": output_dir / "preview.mp4",
                    "frame_manifest_path": output_dir / "frames.json",
                }
                for key, value in files.items():
                    if isinstance(value, list):
                        for path in value:
                            path.write_bytes(b"jpg")
                    elif str(value).endswith(".json"):
                        value.write_text(json.dumps([{"frame": 1, "time_seconds": 0.04}]), encoding="utf-8")
                    else:
                        value.write_bytes(b"artifact")
                return {key: ([p.as_posix() for p in value] if isinstance(value, list) else value.as_posix()) for key, value in files.items()}

            result = build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                mirror_videos=True,
                generate_artifacts=True,
                fetch_video_bytes_fn=fake_fetch,
                probe_video_file_fn=fake_probe,
                artifact_generator_fn=fake_artifacts,
                allowed_licenses=("Creative Commons Attribution License",),
            )

        artifact_records = [
            record
            for record in result.records
            if str(record.payload.get("atom_type", "")).startswith("video_")
            and record.payload["atom_type"] not in {"video_asset", "video_gap"}
        ]
        atom_types = {record.payload["atom_type"] for record in artifact_records}
        self.assertIn("video_thumbnail", atom_types)
        self.assertIn("video_keyframe", atom_types)
        self.assertIn("video_preview_clip", atom_types)
        self.assertIn("video_frame_manifest", atom_types)
        self.assertEqual(result.artifact_count, 5)
        self.assertTrue(all(record.payload["source_video_record_id"] == "pmc:video:PMC123:video1.mp4" for record in artifact_records))

    def test_rehydrates_existing_inspectable_video_artifacts(self):
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
            first = build_video_atom_records(
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

            result = build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                mirror_videos=False,
                generate_artifacts=False,
                probe_video_file_fn=lambda path: probe,
            )

        artifact_records = [
            record
            for record in result.records
            if str(record.payload.get("atom_type", "")).startswith("video_")
            and record.payload["atom_type"] not in {"video_asset", "video_gap"}
        ]
        self.assertEqual(
            {record.payload["atom_type"] for record in artifact_records},
            {"video_thumbnail", "video_keyframe", "video_preview_clip", "video_frame_manifest"},
        )
        self.assertEqual(result.artifact_count, 4)
        self.assertTrue(all(record.media_url and record.media_url.startswith("raw/video_atoms/artifacts/") for record in artifact_records))

    def test_default_artifact_generator_samples_multiple_keyframes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            asset_path = artifact_dir / "raw" / "video_atoms" / "assets" / "clip.mp4"
            output_dir = artifact_dir / "raw" / "video_atoms" / "artifacts" / "clip"
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            asset_path.write_bytes(b"video")

            def fake_check_call(command: list[str]) -> None:
                output = Path(command[-1])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"artifact")

            with mock.patch.object(video_atoms.shutil, "which", return_value="/usr/bin/ffmpeg"), mock.patch.object(
                video_atoms.subprocess, "check_call", side_effect=fake_check_call
            ):
                payload = video_atoms.generate_video_artifacts(
                    asset_path,
                    output_dir,
                    {"duration_seconds": 12.0, "fps": 30.0, "width": 640, "height": 480, "codec": "h264"},
                )

            self.assertEqual(len(payload["keyframe_paths"]), 6)
            self.assertTrue(all(Path(path).name.startswith("keyframe_") for path in payload["keyframe_paths"]))
            manifest = json.loads(Path(payload["frame_manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["keyframes"]), 6)
            self.assertEqual(manifest["keyframes"][0]["frame_index"], 1)
            self.assertIn("time_seconds", manifest["keyframes"][0])

    def test_generate_artifacts_upgrades_thumbnail_only_existing_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)
            safe_id = video_atoms._safe_id("pmc:video:PMC123:video1.mp4")
            asset_path = artifact_dir / "raw" / "video_atoms" / "assets" / f"{safe_id}_existing.mp4"
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            asset_path.write_bytes(b"existing-video-bytes")
            probe = {"duration_seconds": 4.0, "fps": 24.0, "width": 640, "height": 480, "codec": "h264"}
            first = build_video_atom_records(
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

            def regenerate(asset_path: Path, output_dir: Path, probe: dict[str, object]) -> dict[str, object]:
                (output_dir / "keyframe_000001.jpg").write_bytes(b"jpg")
                (output_dir / "keyframe_000002.jpg").write_bytes(b"jpg")
                return {
                    "thumbnail_path": (output_dir / "thumbnail.jpg").as_posix(),
                    "keyframe_paths": [
                        (output_dir / "keyframe_000001.jpg").as_posix(),
                        (output_dir / "keyframe_000002.jpg").as_posix(),
                    ],
                    "preview_clip_path": (output_dir / "preview.mp4").as_posix(),
                    "frame_manifest_path": (output_dir / "frames.json").as_posix(),
                }

            result = build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                mirror_videos=False,
                generate_artifacts=True,
                probe_video_file_fn=lambda path: probe,
                artifact_generator_fn=regenerate,
            )

        keyframes = [record for record in result.records if record.payload.get("atom_type") == "video_keyframe"]
        self.assertEqual(len(keyframes), 2)
        self.assertEqual(result.artifact_count, 5)

    def test_parses_motion_rows_from_existing_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)
            table_path = artifact_dir / "raw" / "mendeley_behavior_media" / "motion.csv"
            table_path.parent.mkdir(parents=True)
            table_path.write_text(
                "video_id,track_id,frame,time_seconds,x,y,behavior,sex,life_stage,assay,stimulus,arena,confidence\n"
                "pmc:video:PMC123:video1.mp4,track-1,150,5.0,122.4,93.1,host seeking,female,adult,flight assay,CO2,wind tunnel,source_table\n",
                encoding="utf-8",
            )

            result = build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                motion_table_paths=[table_path],
            )

        rows = [record for record in result.records if record.payload.get("atom_type") == "video_motion_row"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.lane, "behavior")
        self.assertEqual(row.payload["source_video_record_id"], "pmc:video:PMC123:video1.mp4")
        self.assertEqual(row.payload["track_id"], "track-1")
        self.assertEqual(row.payload["frame"], 150)
        self.assertEqual(row.payload["time_seconds"], 5.0)
        self.assertEqual(row.payload["x"], 122.4)
        self.assertEqual(row.payload["y"], 93.1)
        self.assertEqual(row.payload["behavior_type"], "host seeking")
        self.assertEqual(row.payload["confidence"], "source_table")
        self.assertIn("source_video_asset_id", row.payload)
        self.assertEqual(row.payload["repository"], "pmc_oa")
        self.assertEqual(row.payload["source_dataset"], "BiteOscope")
        self.assertEqual(row.payload["download_url"], "https://example.org/video1.mp4")
        self.assertEqual(row.media_url, "https://example.org/video1.mp4")
        self.assertIn("raw/mendeley_behavior_media/motion.csv#row/1", row.provenance.locator)

    def test_motion_rows_emit_queryable_gap_when_source_video_is_unmatched(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)
            table_path = artifact_dir / "raw" / "mendeley_behavior_media" / "unknown-motion.csv"
            table_path.parent.mkdir(parents=True)
            table_path.write_text(
                "video_id,track_id,frame,time_seconds,x,y,behavior\n"
                "unknown-video.mp4,track-1,1,0.1,2,3,flight\n"
                "unknown-video.mp4,track-1,2,0.2,3,4,flight\n",
                encoding="utf-8",
            )

            result = build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                motion_table_paths=[table_path],
            )

        rows = [record for record in result.records if record.payload.get("atom_type") == "video_motion_row"]
        self.assertEqual(len(rows), 2)
        self.assertNotIn("source_video_asset_id", rows[0].payload)
        gap_records = [
            record
            for record in result.records
            if record.payload.get("atom_type") == "video_gap"
            and record.payload.get("reason") == "video_motion_unmatched_source_video"
        ]
        self.assertEqual(len(gap_records), 1)
        self.assertEqual(gap_records[0].payload["source_video_record_id"], "unknown-video.mp4")
        self.assertIn("raw/mendeley_behavior_media/unknown-motion.csv#row/1", gap_records[0].provenance.locator)

    def test_parses_trackmate_spot_statistics_motion_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)
            table_path = artifact_dir / "raw" / "mendeley_behavior_media" / "Video S1 - Spot Statistics.csv"
            table_path.parent.mkdir(parents=True)
            table_path.write_text(
                "Label,ID,TRACK_ID,QUALITY,POSITION_X,POSITION_Y,POSITION_Z,POSITION_T,FRAME\n"
                "ID947,947,2,0.204027742,213.639373433,212.619909425,0,0.125,15\n",
                encoding="utf-8",
            )

            result = build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                motion_table_paths=[table_path],
            )

        rows = [record for record in result.records if record.payload.get("atom_type") == "video_motion_row"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.payload["source_video_record_id"], "Video S1 - Spot Statistics")
        self.assertEqual(row.payload["track_id"], "2")
        self.assertEqual(row.payload["frame"], 15)
        self.assertEqual(row.payload["time_seconds"], 0.125)
        self.assertEqual(row.payload["x"], 213.639373433)
        self.assertEqual(row.payload["y"], 212.619909425)
        self.assertEqual(row.payload["behavior_type"], "video motion")
        self.assertIn("raw/mendeley_behavior_media/Video S1 - Spot Statistics.csv#row/1", row.provenance.locator)

    def test_discovers_default_mendeley_motion_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)
            table_path = artifact_dir / "raw" / "mendeley_behavior_media" / "table_files" / "Video S1 - Spot Statistics.csv"
            table_path.parent.mkdir(parents=True)
            table_path.write_text(
                "Label,ID,TRACK_ID,QUALITY,POSITION_X,POSITION_Y,POSITION_Z,POSITION_T,FRAME\n"
                "ID947,947,2,0.204027742,213.639373433,212.619909425,0,0.125,15\n",
                encoding="utf-8",
            )

            result = build_video_atom_records(artifact_dir, retrieved_at=RETRIEVED_AT)

        rows = [record for record in result.records if record.payload.get("atom_type") == "video_motion_row"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(result.motion_row_count, 1)
        self.assertIn("raw/mendeley_behavior_media/table_files/Video S1 - Spot Statistics.csv#row/1", rows[0].provenance.locator)

    def test_discovers_recursive_motion_tables_across_video_source_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)
            table_path = artifact_dir / "raw" / "dryad_behavior_videos" / "dataset-1" / "tracks" / "trajectory.tsv"
            table_path.parent.mkdir(parents=True)
            table_path.write_text(
                "video_id\ttrack_id\tframe\ttime_seconds\tx\ty\tbehavior\n"
                "dryad-video-1\tadult-7\t42\t1.4\t3.2\t9.8\todor tracking\n",
                encoding="utf-8",
            )

            result = build_video_atom_records(artifact_dir, retrieved_at=RETRIEVED_AT)

        rows = [record for record in result.records if record.payload.get("atom_type") == "video_motion_row"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].payload["source_video_record_id"], "dryad-video-1")
        self.assertEqual(rows[0].payload["track_id"], "adult-7")
        self.assertEqual(rows[0].payload["behavior_type"], "odor tracking")
        self.assertIn("raw/dryad_behavior_videos/dataset-1/tracks/trajectory.tsv#row/1", rows[0].provenance.locator)

    def test_parses_mendeley_xlsx_locomotory_video_analysis_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)
            table_path = (
                artifact_dir
                / "raw"
                / "mendeley_behavior_media"
                / "table_files"
                / "Data_VideoAnalysis_temperature gradients_AeAegypti.xlsx"
            )
            table_path.parent.mkdir(parents=True)
            table_path.write_bytes(
                tiny_xlsx(
                    [
                        [
                            "Behavioural_Activity",
                            "Trial",
                            "Subject",
                            "Zone",
                            "Day",
                            "Temperature",
                            "Species",
                            "Feeding_Status",
                            "Age",
                            "Velocity.center.point.Mean.cm.s",
                            "Distance.moved.center.point.Total.cm",
                        ],
                        ["Flying", "Trial 1", "Subject 2", "In S 5", "1", "10 - 20", "Aedes aegypti", "non-blood-fed", "5", "15.8844", "10.5939"],
                    ]
                )
            )

            result = build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                motion_table_paths=[table_path],
            )

        rows = [record for record in result.records if record.payload.get("atom_type") == "video_motion_row"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.payload["source_video_record_id"], "Data_VideoAnalysis_temperature gradients_AeAegypti")
        self.assertEqual(row.payload["track_id"], "Subject 2")
        self.assertEqual(row.payload["behavior_type"], "Flying")
        self.assertEqual(row.payload["assay"], "locomotory video analysis")
        self.assertEqual(row.payload["arena"], "In S 5")
        self.assertEqual(row.payload["temperature"], "10 - 20")
        self.assertEqual(row.payload["feeding_status"], "non-blood-fed")
        self.assertEqual(row.payload["age"], 5)
        self.assertEqual(row.payload["velocity_mean_cm_s"], 15.8844)
        self.assertEqual(row.payload["distance_moved_total_cm"], 10.5939)
        self.assertIn("raw/mendeley_behavior_media/table_files/Data_VideoAnalysis_temperature gradients_AeAegypti.xlsx#sheet/1/row/2", row.provenance.locator)

    def test_discovers_or_gaps_external_video_candidates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)

            discovery_clients = {
                "zenodo": lambda: [
                    {
                        "title": "Aedes aegypti oviposition movie",
                        "download_url": "https://zenodo.org/record/1/files/movie.mp4",
                        "source_url": "https://zenodo.org/record/1",
                        "license": "CC-BY-4.0",
                        "repository": "zenodo",
                        "species_scope": "Aedes aegypti",
                        "locator": "zenodo-api#record/1/file/movie.mp4",
                    }
                ],
                "figshare": lambda: [
                    {
                        "title": "Culex video",
                        "download_url": "https://figshare.com/video.mp4",
                        "source_url": "https://figshare.com/articles/1",
                        "license": "CC-BY",
                        "repository": "figshare",
                        "species_scope": "Culex quinquefasciatus",
                    }
                ],
                "mendeley": lambda: [
                    {
                        "title": "Aedes aegypti video analysis paper",
                        "download_url": "https://data.mendeley.com/files/analysis.pdf",
                        "source_url": "https://data.mendeley.com/datasets/example",
                        "license": "CC-BY",
                        "repository": "mendeley",
                        "species_scope": "Aedes aegypti",
                    }
                ],
                "institutional": lambda: [
                    {
                        "title": "Aedes aegypti video with missing download",
                        "source_url": "https://example.edu/aedes-video",
                        "license": "CC-BY",
                        "repository": "institutional",
                        "species_scope": "Aedes aegypti",
                    }
                ],
                "osf": lambda: [
                    {
                        "title": "Thermal video of rodent motion",
                        "description": "Rodent thermal video with a polluted search-scope string.",
                        "download_url": "https://osf.io/download/rodent.mp4",
                        "source_url": "https://osf.io/rodent/",
                        "license": "institutional repository license not supplied",
                        "repository": "osf",
                        "species_scope": "Aedes aegypti Thermal video of rodent motion",
                    },
                    {
                        "title": "Aedes aegypti larval motion video",
                        "description": "Aedes aegypti larval motion assay video.",
                        "download_url": "https://osf.io/download/aedes-larvae.mp4",
                        "source_url": "https://osf.io/aedes-larvae/",
                        "license": "institutional repository license not supplied",
                        "repository": "osf",
                        "locator": "https://api.osf.io/v2/nodes/aedes-larvae/files/osfstorage/#file/1",
                        "size": 123456,
                        "sha256": "b" * 64,
                    }
                ],
                "paper_supplements": lambda: [],
            }

            result = build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                discover_sources=True,
                discovery_clients=discovery_clients,
            )

        discovered = [record for record in result.records if record.payload.get("discovery_repository") == "zenodo"]
        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0].payload["atom_type"], "video_asset")
        self.assertEqual(discovered[0].payload["download_url"], "https://zenodo.org/record/1/files/movie.mp4")
        self.assertEqual(discovered[0].provenance.locator, "zenodo-api#record/1/file/movie.mp4")
        reasons = {gap["reason"] for gap in result.gaps}
        self.assertIn("video_discovery_not_aedes_scope", reasons)
        self.assertIn("video_discovery_not_video_media", reasons)
        self.assertIn("video_discovery_no_download_url", reasons)
        self.assertIn("video_discovery_license_unclear", reasons)
        self.assertIn("video_discovery_client_missing", reasons)
        self.assertIn("video_discovery_no_candidates", reasons)
        polluted_osf = [
            gap
            for gap in result.gaps
            if gap.get("repository") == "osf" and gap.get("title") == "Thermal video of rodent motion"
        ]
        self.assertEqual({gap["reason"] for gap in polluted_osf}, {"video_discovery_not_aedes_scope"})
        license_gap = next(
            gap
            for gap in result.gaps
            if gap.get("repository") == "osf" and gap.get("reason") == "video_discovery_license_unclear"
        )
        self.assertEqual(license_gap["download_url"], "https://osf.io/download/aedes-larvae.mp4")
        self.assertEqual(license_gap["source_url"], "https://osf.io/aedes-larvae/")
        self.assertEqual(license_gap["locator"], "https://api.osf.io/v2/nodes/aedes-larvae/files/osfstorage/#file/1")
        self.assertEqual(license_gap["source_byte_size"], 123456)
        self.assertEqual(license_gap["source_hashes"]["sha256"], "b" * 64)
        self.assertEqual(license_gap["license"], "institutional repository license not supplied")
        receipts = {receipt["repository"]: receipt for receipt in result.discovery_sweep_receipts}
        self.assertEqual(set(receipts), set(DISCOVERY_REPOSITORIES))
        self.assertEqual(receipts["zenodo"]["status"], "accepted_candidates")
        self.assertEqual(receipts["paper_supplements"]["status"], "no_candidates")
        sweep_records = [record for record in result.records if record.payload.get("atom_type") == "video_sweep"]
        self.assertEqual({record.payload["repository"] for record in sweep_records}, set(DISCOVERY_REPOSITORIES))

    def test_repository_scope_limits_video_discovery_and_source_candidates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)
            discovery_clients = {
                "zenodo": lambda: [
                    {
                        "title": "Aedes aegypti oviposition movie",
                        "download_url": "https://zenodo.org/record/1/files/movie.mp4",
                        "source_url": "https://zenodo.org/record/1",
                        "license": "CC-BY-4.0",
                        "repository": "zenodo",
                        "species_scope": "Aedes aegypti",
                    }
                ],
                "figshare": lambda: [
                    {
                        "title": "Aedes aegypti ignored Figshare movie",
                        "download_url": "https://figshare.com/video.mp4",
                        "source_url": "https://figshare.com/articles/1",
                        "license": "CC-BY",
                        "repository": "figshare",
                        "species_scope": "Aedes aegypti",
                    }
                ],
            }

            result = build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                discover_sources=True,
                discovery_clients=discovery_clients,
                discovery_repositories=("zenodo",),
                parse_motion_rows=False,
            )

        repositories = {
            record.payload.get("repository") or record.payload.get("discovery_repository")
            for record in result.records
            if record.payload
        }
        self.assertIn("zenodo", repositories)
        self.assertNotIn("figshare", repositories)
        self.assertNotIn("pmc_oa", repositories)
        self.assertNotIn("osf", repositories)
        self.assertEqual([receipt["repository"] for receipt in result.discovery_sweep_receipts], ["zenodo"])
        self.assertEqual(result.video_asset_count, 1)

    def test_discovery_sweep_receipts_preserve_page_coverage_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)

            discovery_clients = {repository: (lambda: []) for repository in DISCOVERY_REPOSITORIES}
            request_url = "https://zenodo.org/api/records?q=%22Aedes+aegypti%22+video&size=25"
            discovery_clients["zenodo"] = lambda: DiscoverySweepResult(
                items=[],
                receipt={
                    "coverage_method": "api_search",
                    "queries": ['"Aedes aegypti" video'],
                    "request_urls": [request_url],
                    "page_size": 25,
                    "page_count": 1,
                    "cursor_or_page_complete": True,
                    "candidate_limit": 25,
                },
            )

            result = build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                discover_sources=True,
                discovery_clients=discovery_clients,
            )

        receipt = {item["repository"]: item for item in result.discovery_sweep_receipts}["zenodo"]
        self.assertEqual(receipt["coverage_method"], "api_search")
        self.assertEqual(receipt["queries"], ['"Aedes aegypti" video'])
        self.assertEqual(receipt["request_urls"], [request_url])
        self.assertEqual(receipt["page_size"], 25)
        self.assertEqual(receipt["page_count"], 1)
        self.assertTrue(receipt["cursor_or_page_complete"])
        sweep_record = next(record for record in result.records if record.record_id == "video_atom:sweep:zenodo")
        self.assertEqual(sweep_record.payload["request_urls"], [request_url])

    def test_discovery_not_aedes_scope_gap_is_suppressed_for_source_backed_video(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="pmc:video:PMC7535929:video1.mp4",
                        lane="media",
                        source="pmc_open_access_videos",
                        title="Aedes aegypti PMC supplementary video video1.mp4",
                        text="BiteOscope Aedes aegypti supplementary video.",
                        species="Aedes aegypti",
                        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC7535929/",
                        media_url="https://cdn.ncbi.nlm.nih.gov/pmc/blobs/example/video1.mp4",
                        provenance=Provenance(
                            source_id="pmc_open_access_videos",
                            locator="raw/pmc_videos/PMC7535929.html#video/1",
                            retrieved_at=RETRIEVED_AT,
                            license="Creative Commons Attribution License",
                            source_url="https://pmc.ncbi.nlm.nih.gov/articles/PMC7535929/",
                        ),
                        payload={
                            "filename": "video1.mp4",
                            "download_url": "https://cdn.ncbi.nlm.nih.gov/pmc/blobs/example/video1.mp4",
                            "article_title": "BiteOscope, an open platform to study mosquito biting behavior",
                        },
                    )
                ]
            )

            discovery_clients = {repository: (lambda: []) for repository in DISCOVERY_REPOSITORIES}
            discovery_clients["pmc_oa"] = lambda: [
                {
                    "repository": "pmc_oa",
                    "title": "BiteOscope, an open platform to study mosquito biting behavior",
                    "description": "Mosquito biting behavior video.",
                    "filename": "video1.mp4",
                    "download_url": "https://cdn.ncbi.nlm.nih.gov/pmc/blobs/example/video1.mp4",
                    "source_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7535929/",
                    "license": "Creative Commons Attribution License",
                }
            ]

            result = build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                discover_sources=True,
                discovery_clients=discovery_clients,
            )

        self.assertFalse(any(gap["reason"] == "video_discovery_not_aedes_scope" for gap in result.gaps))
        self.assertEqual(result.video_asset_count, 1)

    def test_dataverse_search_terms_do_not_count_as_aedes_scope(self):
        payload = {
            "data": {
                "items": [
                    {
                        "name": "unrelated_movie.mp4",
                        "file_content_type": "video/mp4",
                        "url": "https://dataverse.harvard.edu/file.xhtml?fileId=1",
                        "dataset_name": "AI Videos Spreading Bioweapons Disinformation Cite Kremlin",
                        "description": "Dataset about synthetic media narratives in Africa.",
                        "dataset_citation": "Unrelated social science dataset.",
                        "license": "CC0",
                        "file_id": 1,
                    }
                ]
            }
        }

        original_fetch_json = video_atoms._fetch_json
        try:
            video_atoms._fetch_json = lambda url: payload
            discovery_result = video_atoms._dataverse_institutional_discovery_candidates()
        finally:
            video_atoms._fetch_json = original_fetch_json

        discovered = discovery_result.items
        self.assertEqual(len(discovered), 1)
        self.assertNotIn("Aedes aegypti", discovered[0]["species_scope"])
        self.assertEqual(discovery_result.receipt["coverage_method"], "api_search")
        self.assertEqual(discovery_result.receipt["page_count"], 3)

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)
            result = build_video_atom_records(
                artifact_dir,
                retrieved_at=RETRIEVED_AT,
                discover_sources=True,
                discovery_clients={
                    "institutional": lambda: discovered,
                    "paper_supplements": lambda: [],
                },
            )

        dataverse_gaps = [gap for gap in result.gaps if gap.get("repository") == "institutional"]
        self.assertIn("video_discovery_not_aedes_scope", {gap["reason"] for gap in dataverse_gaps})
        self.assertNotIn("video_discovery_license_unclear", {gap["reason"] for gap in dataverse_gaps})

    def test_default_discovery_clients_cover_declared_repositories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            clients = default_discovery_clients(Path(tmpdir) / "mosquito-v1")

        self.assertEqual(set(DISCOVERY_REPOSITORIES), set(clients))

    def test_institutional_sqlite_scan_skips_irrelevant_large_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            provenance = Provenance(
                source_id="vectorbase_aedes_genomics",
                locator="raw/vectorbase#row/1",
                retrieved_at=RETRIEVED_AT,
            )
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="vectorbase:noise:1",
                        lane="genome_features",
                        source="vectorbase_aedes_genomics",
                        title="Aedes aegypti irrelevant mp4 text",
                        text="Aedes aegypti genome note mentioning https://example.org/not-video.mp4",
                        species="Aedes aegypti",
                        url="https://example.org/not-video.mp4",
                        media_url=None,
                        provenance=provenance,
                        payload={"note": "Aedes aegypti https://example.org/not-video.mp4"},
                    )
                ]
            )

            original_fetch_json = video_atoms._fetch_json
            try:
                video_atoms._fetch_json = lambda url: {"data": {"items": []}}
                discovery_result = video_atoms._default_institutional_discovery_client(artifact_dir)
            finally:
                video_atoms._fetch_json = original_fetch_json

        self.assertEqual(discovery_result.items, [])
        self.assertIn("source_index.sqlite", discovery_result.receipt["raw_artifacts"])

    def test_figshare_discovery_uses_broader_page_size(self):
        requested_urls: list[str] = []

        def fake_fetch_json(url: str) -> object:
            requested_urls.append(url)
            return []

        original_fetch_json = video_atoms._fetch_json
        try:
            video_atoms._fetch_json = fake_fetch_json
            discovery_result = video_atoms._default_figshare_discovery_client()
        finally:
            video_atoms._fetch_json = original_fetch_json

        self.assertEqual(discovery_result.items, [])
        self.assertEqual(discovery_result.receipt["coverage_method"], "api_search")
        self.assertEqual(discovery_result.receipt["page_size"], 100)
        query = parse_qs(urlparse(requested_urls[0]).query)
        self.assertEqual(query["page_size"], ["100"])

    def test_figshare_discovery_preserves_detail_fetch_failures_as_gap_candidates(self):
        requested_urls: list[str] = []

        def fake_fetch_json(url: str) -> object:
            requested_urls.append(url)
            if url.endswith("/32407513"):
                raise RuntimeError("HTTP Error 404: Not Found")
            return [{"id": 32407513, "title": "Aedes aegypti video article"}]

        original_fetch_json = video_atoms._fetch_json
        try:
            video_atoms._fetch_json = fake_fetch_json
            discovery_result = video_atoms._default_figshare_discovery_client()
        finally:
            video_atoms._fetch_json = original_fetch_json

        self.assertEqual(len(discovery_result.items), 1)
        self.assertEqual(discovery_result.items[0]["repository"], "figshare")
        self.assertIn("HTTP Error 404", discovery_result.items[0]["fetch_error"])
        self.assertEqual(discovery_result.receipt["coverage_method"], "api_search")
        self.assertEqual(discovery_result.receipt["request_urls"], requested_urls)


if __name__ == "__main__":
    unittest.main()
