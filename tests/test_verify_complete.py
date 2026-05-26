import subprocess
import sys
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import verify_complete


class VerifyCompleteTests(unittest.TestCase):
    def test_literature_source_map_gate_passes_without_network(self):
        verify_complete.check_literature_source_map()
        self.assertIn("tests.test_literature_source", verify_complete.UNIT_TEST_MODULES)

    def test_verify_complete_enforces_atomic_source_replacement(self):
        verify_complete.check_atomic_source_replacement()

    def _write_video_atom_artifact(
        self,
        artifact_dir: Path,
        *,
        include_queryable_gap: bool = True,
        include_motion_row: bool = True,
        include_all_repositories: bool = True,
        include_sweep_receipts: bool = True,
        include_sweep_records: bool = True,
        include_sweep_coverage: bool = True,
        include_motion_asset_join: bool = True,
        include_broken_motion_asset_join: bool = False,
        include_stale_archive_gap: bool = False,
    ) -> None:
        artifact_dir.mkdir(parents=True)
        db_path = artifact_dir / "source_index.sqlite"
        with sqlite3.connect(db_path) as conn:
            conn.executescript(
                """
                create table records (
                  record_id text primary key,
                  lane text not null,
                  source text not null,
                  title text not null,
                  text text not null,
                  species text,
                  url text,
                  media_url text,
                  provenance_json text not null
                );
                create table record_payloads (
                  record_id text primary key,
                  source text not null,
                  lane text not null,
                  payload_json text not null,
                  provenance_json text not null
                );
                """
            )

            def add(record_id: str, lane: str, payload: dict[str, object]) -> None:
                provenance = {"source_id": "aedes_video_atoms", "locator": f"records#{record_id}"}
                conn.execute(
                    "insert into records values (?, ?, 'aedes_video_atoms', ?, ?, 'Aedes aegypti', null, null, ?)",
                    (record_id, lane, record_id, record_id, json.dumps(provenance)),
                )
                conn.execute(
                    "insert into record_payloads values (?, 'aedes_video_atoms', ?, ?, ?)",
                    (record_id, lane, json.dumps(payload), json.dumps(provenance)),
                )

            repositories = verify_complete.VIDEO_DISCOVERY_TARGETS if include_all_repositories else ("mendeley",)
            for repository in repositories:
                add(
                    f"video_atom:asset:{repository}",
                    "media",
                    {
                        "atom_type": "video_asset",
                        "repository": repository,
                        "verification_status": "verified",
                        "raw_asset_path": f"raw/video_atoms/assets/{repository}.mp4",
                    },
                )
                if include_sweep_records:
                    sweep_payload = {
                        "atom_type": "video_sweep",
                        "repository": repository,
                        "status": "accepted_candidates",
                        "raw_candidate_count": 1,
                        "accepted_candidate_count": 1,
                        "gap_count": 0,
                    }
                    if include_sweep_coverage:
                        sweep_payload.update(
                            {
                                "coverage_method": "api_search",
                                "queries": [f"{repository} Aedes aegypti video"],
                                "request_urls": [f"https://example.org/{repository}/search"],
                                "page_size": 1,
                                "page_count": 1,
                                "cursor_or_page_complete": True,
                                "candidate_limit": 1,
                            }
                        )
                    add(f"video_atom:sweep:{repository}", "media", sweep_payload)
            add("video_atom:thumbnail:1", "media", {"atom_type": "video_thumbnail"})
            add("video_atom:keyframe:1", "media", {"atom_type": "video_keyframe"})
            add("video_atom:preview:1", "media", {"atom_type": "video_preview_clip"})
            add("video_atom:frame_manifest:1", "media", {"atom_type": "video_frame_manifest"})
            if include_motion_row:
                motion_payload = {"atom_type": "video_motion_row"}
                if include_broken_motion_asset_join:
                    motion_payload["source_video_asset_id"] = "video_atom:asset:missing"
                elif include_motion_asset_join:
                    motion_payload["source_video_asset_id"] = f"video_atom:asset:{repositories[0]}"
                add("video_atom:motion:1", "behavior", motion_payload)
            if include_queryable_gap:
                add("video_atom:gap:1", "media", {"atom_type": "video_gap", "repository": "paper_supplements"})
            if include_stale_archive_gap:
                add(
                    "video_atom:gap:archive",
                    "media",
                    {"atom_type": "video_gap", "reason": "video_archive_not_expanded", "repository": "dryad"},
                )

        table_dir = artifact_dir / "raw" / "mendeley_behavior_media" / "table_files"
        table_dir.mkdir(parents=True)
        (table_dir / "motion.csv").write_text("TRACK_ID,POSITION_X,POSITION_Y,FRAME\n1,2,3,4\n", encoding="utf-8")
        total_records = len(list(sqlite3.connect(db_path).execute("select 1 from records")))
        status = {
            "aedes_video_atoms": {
                "record_count": total_records,
                "video_asset_count": len(repositories),
                "mirrored_video_count": len(repositories),
                "verified_video_count": len(repositories),
                "artifact_count": 4,
                "motion_row_count": 1 if include_motion_row else 0,
                "gap_count": (1 if include_queryable_gap else 0) + (1 if include_stale_archive_gap else 0),
            }
        }
        if include_sweep_receipts:
            receipts = []
            for repository in repositories:
                receipt = {
                    "repository": repository,
                    "status": "accepted_candidates",
                    "raw_candidate_count": 1,
                    "accepted_candidate_count": 1,
                    "gap_count": 0,
                }
                if include_sweep_coverage:
                    receipt.update(
                        {
                            "coverage_method": "api_search",
                            "queries": [f"{repository} Aedes aegypti video"],
                            "request_urls": [f"https://example.org/{repository}/search"],
                            "page_size": 1,
                            "page_count": 1,
                            "cursor_or_page_complete": True,
                            "candidate_limit": 1,
                        }
                    )
                receipts.append(receipt)
            status["aedes_video_atoms"]["discovery_sweep_receipts"] = receipts
        (artifact_dir / "source_status.json").write_text(json.dumps(status), encoding="utf-8")
        gaps = []
        gaps.append({"source": "aedes_video_atoms", "reason": "video_discovery_client_missing", "repository": "paper_supplements"})
        if include_stale_archive_gap:
            gaps.append({"source": "aedes_video_atoms", "reason": "video_archive_not_expanded", "repository": "dryad"})
        (artifact_dir / "gaps.json").write_text(json.dumps(gaps), encoding="utf-8")

    def test_verify_complete_checks_aedes_video_atoms_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            self._write_video_atom_artifact(artifact_dir)

            verify_complete.check_aedes_video_atoms_artifact(artifact_dir)

    def test_verify_complete_rejects_stale_receipt_record_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            artifact_dir.mkdir()
            with sqlite3.connect(artifact_dir / "source_index.sqlite") as conn:
                conn.executescript(
                    """
                    create table records (
                      record_id text primary key,
                      lane text not null,
                      source text not null,
                      title text not null,
                      text text not null,
                      species text,
                      url text,
                      media_url text,
                      provenance_json text not null
                    );
                    insert into records values ('r1', 'genes', 'vectorbase_aedes_genomics', 'one', 'one', 'Aedes aegypti', null, null, '{}');
                    insert into records values ('r2', 'genes', 'vectorbase_aedes_genomics', 'two', 'two', 'Aedes aegypti', null, null, '{}');
                    """
                )
            stale = {
                "record_count": 1,
                "source_counts": {"vectorbase_aedes_genomics": 1},
                "vectorbase_aedes_genomics": {"record_count": 1},
            }
            (artifact_dir / "source_status.json").write_text(json.dumps(stale), encoding="utf-8")
            (artifact_dir / "source_receipt.json").write_text(json.dumps(stale), encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "record_count mismatch"):
                verify_complete.check_receipts_match_sqlite(artifact_dir)

    def test_verify_complete_accepts_receipts_matching_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            artifact_dir.mkdir()
            with sqlite3.connect(artifact_dir / "source_index.sqlite") as conn:
                conn.executescript(
                    """
                    create table records (
                      record_id text primary key,
                      lane text not null,
                      source text not null,
                      title text not null,
                      text text not null,
                      species text,
                      url text,
                      media_url text,
                      provenance_json text not null
                    );
                    insert into records values ('r1', 'genes', 'vectorbase_aedes_genomics', 'one', 'one', 'Aedes aegypti', null, null, '{}');
                    insert into records values ('r2', 'genes', 'vectorbase_aedes_genomics', 'two', 'two', 'Aedes aegypti', null, null, '{}');
                    """
                )
            current = {
                "record_count": 2,
                "source_counts": {"vectorbase_aedes_genomics": 2},
                "vectorbase_aedes_genomics": {"record_count": 2},
            }
            (artifact_dir / "source_status.json").write_text(json.dumps(current), encoding="utf-8")
            (artifact_dir / "source_receipt.json").write_text(json.dumps(current), encoding="utf-8")

            verify_complete.check_receipts_match_sqlite(artifact_dir)

    def test_verify_complete_rejects_non_queryable_video_gaps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            self._write_video_atom_artifact(artifact_dir, include_queryable_gap=False)

            with self.assertRaisesRegex(RuntimeError, "video gaps must be queryable"):
                verify_complete.check_aedes_video_atoms_artifact(artifact_dir)

    def test_verify_complete_rejects_missing_motion_rows_when_tables_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            self._write_video_atom_artifact(artifact_dir, include_motion_row=False)

            with self.assertRaisesRegex(RuntimeError, "motion tables exist"):
                verify_complete.check_aedes_video_atoms_artifact(artifact_dir)

    def test_verify_complete_rejects_broken_motion_asset_references(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            self._write_video_atom_artifact(artifact_dir, include_broken_motion_asset_join=True)

            with self.assertRaisesRegex(RuntimeError, "broken source video asset references"):
                verify_complete.check_aedes_video_atoms_artifact(artifact_dir)

    def test_verify_complete_rejects_stale_archive_not_expanded_gaps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            self._write_video_atom_artifact(artifact_dir, include_stale_archive_gap=True)

            with self.assertRaisesRegex(RuntimeError, "stale unexpanded archive gaps"):
                verify_complete.check_aedes_video_atoms_artifact(artifact_dir)

    def test_verify_complete_detects_recursive_video_motion_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            table_path = artifact_dir / "raw" / "dryad_behavior_videos" / "dataset-1" / "tracks" / "trajectory.tsv"
            table_path.parent.mkdir(parents=True)
            table_path.write_text("TRACK_ID\tPOSITION_X\tPOSITION_Y\tFRAME\n1\t2\t3\t4\n", encoding="utf-8")

            self.assertTrue(verify_complete._has_motion_table_inputs(artifact_dir))

    def test_verify_complete_rejects_missing_video_discovery_targets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            self._write_video_atom_artifact(artifact_dir, include_all_repositories=False)

            with self.assertRaisesRegex(RuntimeError, "discovery targets"):
                verify_complete.check_aedes_video_atoms_artifact(artifact_dir)

    def test_verify_complete_rejects_missing_video_sweep_receipts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            self._write_video_atom_artifact(artifact_dir, include_sweep_receipts=False)

            with self.assertRaisesRegex(RuntimeError, "discovery_sweep_receipts"):
                verify_complete.check_aedes_video_atoms_artifact(artifact_dir)

    def test_verify_complete_rejects_video_sweep_receipts_without_coverage_proof(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            self._write_video_atom_artifact(artifact_dir, include_sweep_coverage=False)

            with self.assertRaisesRegex(RuntimeError, "sweep receipts"):
                verify_complete.check_aedes_video_atoms_artifact(artifact_dir)

    def test_verify_complete_rejects_missing_video_sweep_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            self._write_video_atom_artifact(artifact_dir, include_sweep_records=False)

            with self.assertRaisesRegex(RuntimeError, "sweep records"):
                verify_complete.check_aedes_video_atoms_artifact(artifact_dir)

    def test_verify_complete_requires_open_source_boundary(self):
        required_files = set(verify_complete.REQUIRED_FILES)

        self.assertIn("LICENSE", required_files)
        self.assertIn("NOTICE", required_files)
        self.assertIn("THIRD_PARTY_DATA.md", required_files)
        verify_complete.check_open_source_boundary()

    def test_verify_complete_requires_open_insects_public_identity(self):
        required_files = set(verify_complete.REQUIRED_FILES)

        self.assertIn(
            "docs/superpowers/specs/2026-05-24-open-insects-public-identity-design.md",
            required_files,
        )
        self.assertIn(
            "docs/superpowers/plans/2026-05-24-open-insects-public-identity.md",
            required_files,
        )
        verify_complete.check_public_identity()

    def test_verify_complete_requires_ncbi_genome_lane(self):
        required_files = set(verify_complete.REQUIRED_FILES)
        unit_modules = set(verify_complete.UNIT_TEST_MODULES)

        self.assertIn("askinsects/sources/ncbi_genome.py", required_files)
        self.assertIn("tests/test_ncbi_genome_source.py", required_files)
        self.assertIn(
            "docs/superpowers/specs/2026-05-23-aedes-aegypti-genomics-lane-design.md",
            required_files,
        )
        self.assertIn(
            "docs/superpowers/plans/2026-05-23-aedes-aegypti-genomics-lane.md",
            required_files,
        )
        self.assertIn("tests.test_ncbi_genome_source", unit_modules)

    def test_verify_complete_requires_vectorbase_genomics_lane(self):
        required_files = set(verify_complete.REQUIRED_FILES)
        unit_modules = set(verify_complete.UNIT_TEST_MODULES)

        self.assertIn("askinsects/sources/vectorbase_genomics.py", required_files)
        self.assertIn("scripts/ingest_vectorbase_genomics.py", required_files)
        self.assertIn("tests/test_vectorbase_genomics_source.py", required_files)
        self.assertIn("tests/test_ingest_vectorbase_genomics.py", required_files)
        self.assertIn(
            "docs/superpowers/specs/2026-05-24-aedes-vectorbase-genomics-lane-design.md",
            required_files,
        )
        self.assertIn(
            "docs/superpowers/plans/2026-05-24-aedes-vectorbase-genomics-lane.md",
            required_files,
        )
        self.assertIn("tests.test_vectorbase_genomics_source", unit_modules)
        self.assertIn("tests.test_ingest_vectorbase_genomics", unit_modules)

    def test_verify_complete_requires_neurobiology_lane(self):
        required_files = set(verify_complete.REQUIRED_FILES)
        unit_modules = set(verify_complete.UNIT_TEST_MODULES)

        self.assertIn("askinsects/sources/neurobiology.py", required_files)
        self.assertIn("scripts/ingest_neurobiology_sources.py", required_files)
        self.assertIn("tests/test_neurobiology_source.py", required_files)
        self.assertIn(
            "docs/superpowers/specs/2026-05-23-aedes-aegypti-neurobiology-lane-design.md",
            required_files,
        )
        self.assertIn(
            "docs/superpowers/specs/2026-05-24-aedes-neurobiology-deep-source-completion-design.md",
            required_files,
        )
        self.assertIn(
            "docs/superpowers/specs/2026-05-23-neurobiology-gap-closure-design.md",
            required_files,
        )
        self.assertIn(
            "docs/superpowers/plans/2026-05-23-aedes-aegypti-neurobiology-lane.md",
            required_files,
        )
        self.assertIn(
            "docs/superpowers/plans/2026-05-24-aedes-neurobiology-deep-source-completion.md",
            required_files,
        )
        self.assertIn(
            "docs/superpowers/plans/2026-05-23-neurobiology-gap-closure.md",
            required_files,
        )
        self.assertIn("askinsects/voxels.py", required_files)
        self.assertIn("tests.test_neurobiology_source", unit_modules)

    def test_verify_complete_gate_passes(self):
        result = subprocess.run(
            [sys.executable, "scripts/verify_complete.py"],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("verify_complete ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
