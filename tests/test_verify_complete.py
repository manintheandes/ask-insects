import subprocess
import sys
from copy import deepcopy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import verify_complete


def public_package_fixture() -> dict[str, object]:
    context_id = "human_landing_response"
    selector_id = "landing_aedes_fixture"
    record_id = "evidence:aedes-landing"
    return {
        "ok": True,
        "schema_version": "ask-insects-evidence-package.v2",
        "package_version": "2026-07-14.test",
        "generated_at": "2026-07-14T12:00:00Z",
        "objective": "Provide bounded public insect evidence.",
        "validation_contract": {
            "producer_linkage": (
                "status_record_count_selected_rows_and_links_verified_in_read_only_source_index"
            ),
            "downstream_validation": "exported_snapshot_internal_consistency_only",
            "snapshot_authentication": "publisher_pinned_content_sha256",
        },
        "knowledge_domains": ["behavior"],
        "upstream_snapshot": {
            "source_id": "ask_insects_fixture",
            "source_status_sha256": "1" * 64,
            "source_status_generated_at": "2026-07-14T11:00:00Z",
            "record_count": 3,
        },
        "contexts": [
            {
                "id": context_id,
                "endpoint_family": "human_host_landing",
                "exposure_routes": ["non_contact"],
                "species_ids": ["aedes_aegypti"],
                "required_domains": ["behavior"],
                "measures": ["landing response"],
                "does_not_establish": ["field efficacy"],
                "plausible_explanations": ["sensory avoidance"],
                "discriminating_evidence": ["matched controls"],
                "provenance": {
                    "source_id": "ask_insects_context_config",
                    "locator": "https://openinsects.org/evidence-package/config#contexts/4",
                    "retrieved_at": "2026-07-14T00:00:00Z",
                    "license": "Apache-2.0",
                },
            }
        ],
        "program_records": [
            {
                "record_id": "program:species:aedes",
                "provenance": {
                    "source_id": "insect_intelligence_programs",
                    "locator": "https://openinsects.org/evidence-package/programs#aedes_aegypti",
                },
            }
        ],
        "evidence_records": [
            {
                "record_id": record_id,
                "context_ids": [context_id],
                "selector_ids": [selector_id],
                "eligibility": {
                    "ruleset_version": "direct-semantic-evidence.v2",
                    "taxon": {
                        "status": "direct_focal_taxon",
                        "basis": [
                            {
                                "field_path": "payload.title",
                                "matched_term": "Aedes aegypti",
                                "excerpt": "Aedes aegypti landing response",
                            }
                        ],
                    },
                    "context": {
                        "status": "direct_context",
                        "basis": [
                            {
                                "field_path": "payload.title",
                                "matched_term": "landing",
                                "excerpt": "Aedes aegypti landing response",
                            }
                        ],
                    },
                },
                "provenance": {
                    "source_id": "aedes_olfaction_literature",
                    "locator": "https://doi.org/10.0000/public-fixture#result/1",
                },
            }
        ],
        "selector_results": [
            {
                "selector_id": selector_id,
                "context_id": context_id,
                "species_id": "aedes_aegypti",
                "candidate_count": 2,
                "eligible_count": 1,
                "selected_count": 1,
                "selected_record_ids": [record_id],
                "rejection_counts": {"taxon_not_directly_confirmed": 1},
            }
        ],
        "gaps": [],
        "content_sha256": "2" * 64,
    }


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
        include_thumbnail_keyframe: bool = False,
        include_frame_manifest_keyframes: bool = True,
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

            def add(record_id: str, lane: str, payload: dict[str, object], media_url: str | None = None) -> None:
                provenance = {"source_id": "aedes_video_atoms", "locator": f"records#{record_id}"}
                conn.execute(
                    "insert into records values (?, ?, 'aedes_video_atoms', ?, ?, 'Aedes aegypti', null, null, ?)",
                    (record_id, lane, record_id, record_id, json.dumps(provenance)),
                )
                conn.execute("update records set media_url=? where record_id=?", (media_url, record_id))
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
            artifact_dir_path = "raw/video_atoms/artifacts/asset-1"
            thumbnail_path = f"{artifact_dir_path}/thumbnail.jpg"
            keyframe_path = thumbnail_path if include_thumbnail_keyframe else f"{artifact_dir_path}/keyframe_000001.jpg"
            frame_manifest_path = f"{artifact_dir_path}/frames.json"
            add("video_atom:thumbnail:1", "media", {"atom_type": "video_thumbnail", "artifact_path": thumbnail_path}, thumbnail_path)
            add("video_atom:keyframe:1", "media", {"atom_type": "video_keyframe", "artifact_path": keyframe_path}, keyframe_path)
            add("video_atom:preview:1", "media", {"atom_type": "video_preview_clip", "artifact_path": f"{artifact_dir_path}/preview.mp4"}, f"{artifact_dir_path}/preview.mp4")
            add("video_atom:frame_manifest:1", "media", {"atom_type": "video_frame_manifest", "artifact_path": frame_manifest_path}, frame_manifest_path)
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
        video_artifact_dir = artifact_dir / "raw" / "video_atoms" / "artifacts" / "asset-1"
        video_artifact_dir.mkdir(parents=True)
        (video_artifact_dir / "thumbnail.jpg").write_bytes(b"jpg")
        (video_artifact_dir / "keyframe_000001.jpg").write_bytes(b"jpg")
        (video_artifact_dir / "preview.mp4").write_bytes(b"mp4")
        frame_payload = (
            {"source": "raw/video_atoms/assets/asset-1.mp4", "keyframes": [{"frame_index": 1, "time_seconds": 0.5, "artifact_path": "raw/video_atoms/artifacts/asset-1/keyframe_000001.jpg"}]}
            if include_frame_manifest_keyframes
            else {"source": "raw/video_atoms/assets/asset-1.mp4", "probe": {}}
        )
        (video_artifact_dir / "frames.json").write_text(json.dumps(frame_payload), encoding="utf-8")
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

    def test_verification_package_seeding_rebinds_fixture_receipts(self):
        from askinsects.index import SourceIndex

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            SourceIndex(artifact_dir / "source_index.sqlite").initialize()
            initial = {
                "generated_at": "2026-07-14T00:00:00Z",
                "record_count": 0,
                "source_counts": {},
                "lanes": {},
                "sources": [],
            }
            (artifact_dir / "source_status.json").write_text(
                json.dumps(initial),
                encoding="utf-8",
            )
            receipt = {**initial, "sources": {}}
            (artifact_dir / "source_receipt.json").write_text(
                json.dumps(receipt),
                encoding="utf-8",
            )

            verify_complete._seed_verification_package_records(artifact_dir)

            status = json.loads((artifact_dir / "source_status.json").read_text())
            updated_receipt = json.loads((artifact_dir / "source_receipt.json").read_text())
            expected_sources = {"aedes_olfaction_literature": 2}
            self.assertEqual(status["record_count"], 2)
            self.assertEqual(status["source_counts"], expected_sources)
            self.assertEqual(status["lanes"], {"literature": 2})
            self.assertEqual(status["sources"], ["aedes_olfaction_literature"])
            self.assertEqual(updated_receipt["record_count"], 2)
            self.assertEqual(updated_receipt["source_counts"], expected_sources)
            self.assertEqual(
                updated_receipt["sources"]["aedes_olfaction_literature"]["record_count"],
                2,
            )
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

    def test_verify_complete_rejects_thumbnail_derived_video_keyframes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            self._write_video_atom_artifact(artifact_dir, include_thumbnail_keyframe=True)

            with self.assertRaisesRegex(RuntimeError, "thumbnail-derived keyframe"):
                verify_complete.check_aedes_video_atoms_artifact(artifact_dir)

    def test_verify_complete_rejects_frame_manifests_without_keyframes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            self._write_video_atom_artifact(artifact_dir, include_frame_manifest_keyframes=False)

            with self.assertRaisesRegex(RuntimeError, "frame manifests without keyframes"):
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

    def test_verify_complete_requires_generic_v2_evidence_package(self):
        required_files = set(verify_complete.REQUIRED_FILES)
        unit_modules = set(verify_complete.UNIT_TEST_MODULES)

        self.assertIn("config/insect-evidence-package.json", required_files)
        self.assertNotIn("config/ask-monarch-context-package.json", required_files)
        self.assertIn(
            "config/ask-monarch-context-package.json",
            verify_complete.FORBIDDEN_FILES,
        )
        self.assertIn("askinsects/context_package.py", required_files)
        self.assertIn("tests/test_context_package.py", required_files)
        self.assertIn(
            "docs/superpowers/specs/2026-07-14-generic-insect-evidence-package-design.md",
            required_files,
        )
        self.assertIn(
            "docs/superpowers/plans/2026-07-14-generic-insect-evidence-package.md",
            required_files,
        )
        self.assertIn("tests.test_context_package", unit_modules)
        verify_complete.check_forbidden_files()

    def test_generic_config_gate_requires_exact_v2_context_shape(self):
        verify_complete.check_generic_evidence_config()

        invalid = json.loads(
            (verify_complete.REPO_ROOT / "config/insect-evidence-package.json").read_text(
                encoding="utf-8"
            )
        )
        invalid["contexts"][0]["private_assay_modes"] = ["contact"]
        with self.assertRaisesRegex(RuntimeError, "generic context fields"):
            verify_complete.validate_generic_evidence_config(invalid)

    def test_public_package_contract_requires_v2_assertions_receipts_and_https(self):
        verify_complete.validate_public_evidence_package(public_package_fixture())

        mutations = {
            "schema v2": lambda package: package.__setitem__("schema_version", "v1"),
            "validation_contract": lambda package: package["validation_contract"].__setitem__(
                "producer_linkage", "claimed_without_source_index"
            ),
            "generic context fields": lambda package: package["contexts"][0].__setitem__(
                "unsupported_assay_modes", ["contact"]
            ),
            "direct focal taxon": lambda package: package["evidence_records"][0][
                "eligibility"
            ]["taxon"].__setitem__("status", "inferred_taxon"),
            "direct context": lambda package: package["evidence_records"][0][
                "eligibility"
            ]["context"].__setitem__("status", "inferred_context"),
            "rejection receipt": lambda package: package["selector_results"][0].__setitem__(
                "rejection_counts", {}
            ),
            "public HTTPS": lambda package: package["evidence_records"][0][
                "provenance"
            ].__setitem__("locator", "https://localhost:8080/result/1"),
            "exact top-level fields": lambda package: package.__setitem__(
                "unexpected", True
            ),
            "credential-shaped key": lambda package: package["upstream_snapshot"].__setitem__(
                "api_token", "secret"
            ),
            "consumer-specific key": lambda package: package["upstream_snapshot"].__setitem__(
                "tenant_identifier", "external-system"
            ),
            "credential or bearer token": lambda package: package.__setitem__(
                "objective", "Authorization is Bearer abcdefghijklmnop"
            ),
            "credentialed URL": lambda package: package.__setitem__(
                "objective", "See https://example.org/data?access_token=secret"
            ),
            "local or private path": lambda package: package.__setitem__(
                "objective", "/opt/private/source_index.sqlite"
            ),
        }
        for expected, mutate in mutations.items():
            with self.subTest(expected=expected):
                invalid = deepcopy(public_package_fixture())
                mutate(invalid)
                with self.assertRaisesRegex(RuntimeError, expected):
                    verify_complete.validate_public_evidence_package(invalid)

    def test_public_package_allows_generic_prose_about_external_systems(self):
        package = public_package_fixture()
        package["objective"] = (
            "Public evidence may inform external private systems, including Monarch."
        )

        verify_complete.validate_public_evidence_package(package)

    def test_public_package_string_limit_counts_characters_at_exact_edges(self):
        limit = verify_complete.MAX_PUBLIC_PACKAGE_STRING_LENGTH

        self.assertEqual(limit, 100_000)
        verify_complete._validate_public_value("é" * limit)
        verify_complete._validate_public_value({"é" * limit: None})

        with self.assertRaisesRegex(RuntimeError, "string length"):
            verify_complete._validate_public_value("é" * (limit + 1))
        with self.assertRaisesRegex(RuntimeError, "key length"):
            verify_complete._validate_public_value({"é" * (limit + 1): None})

    def test_public_package_depth_limit_accepts_20_and_rejects_21(self):
        self.assertEqual(verify_complete.MAX_PUBLIC_PACKAGE_DEPTH, 20)
        nested: object = "leaf"
        for _ in range(verify_complete.MAX_PUBLIC_PACKAGE_DEPTH):
            nested = {"level": nested}

        verify_complete._validate_public_value(nested)
        with self.assertRaisesRegex(RuntimeError, "nesting depth"):
            verify_complete._validate_public_value({"level": nested})

    def test_public_package_byte_limit_accepts_exact_16_mib_and_rejects_next_byte(self):
        byte_limit = verify_complete.MAX_PUBLIC_PACKAGE_BYTES
        string_limit = verify_complete.MAX_PUBLIC_PACKAGE_STRING_LENGTH
        full_chunks = byte_limit // (string_limit + 3)
        at_limit = ["x" * string_limit] * full_chunks + [""]
        remaining = byte_limit - len(verify_complete._canonical_public_package_bytes(at_limit))
        at_limit[-1] = "x" * remaining

        self.assertEqual(byte_limit, 16 * 1024 * 1024)
        self.assertLessEqual(remaining, string_limit)
        self.assertEqual(
            len(verify_complete._canonical_public_package_bytes(at_limit)),
            byte_limit,
        )
        verify_complete._validate_public_value(at_limit)
        verify_complete._validate_public_package_size(at_limit)

        over_limit = [*at_limit[:-1], f"{at_limit[-1]}x"]
        verify_complete._validate_public_value(over_limit)
        with self.assertRaisesRegex(RuntimeError, "package byte limit"):
            verify_complete._validate_public_package_size(over_limit)

    def test_completion_limits_must_match_integrated_producer_constants(self):
        from askinsects import context_package

        producer_limits = {
            "MAX_PACKAGE_BYTES": verify_complete.MAX_PUBLIC_PACKAGE_BYTES,
            "MAX_STRING_LENGTH": verify_complete.MAX_PUBLIC_PACKAGE_STRING_LENGTH,
            "MAX_LIST_ITEMS": verify_complete.MAX_PUBLIC_PACKAGE_LIST_ITEMS,
            "MAX_NESTING_DEPTH": verify_complete.MAX_PUBLIC_PACKAGE_DEPTH,
        }
        with patch.multiple(context_package, create=True, **producer_limits):
            verify_complete._check_producer_limit_alignment()

        producer_limits["MAX_PACKAGE_BYTES"] += 1
        with patch.multiple(context_package, create=True, **producer_limits):
            with self.assertRaisesRegex(RuntimeError, "do not match the producer"):
                verify_complete._check_producer_limit_alignment()

    def test_public_package_rejects_private_and_plain_http_schemes_consistently(self):
        for locator in (
            "private://example.org/result/1",
            "http://example.org/result/1",
        ):
            with self.subTest(locator=locator):
                with self.assertRaisesRegex(RuntimeError, "non-public scheme"):
                    verify_complete._validate_public_value(locator)

                invalid = public_package_fixture()
                invalid["evidence_records"][0]["provenance"]["locator"] = locator
                with self.assertRaisesRegex(RuntimeError, "non-public scheme"):
                    verify_complete.validate_public_evidence_package(invalid)

        for path in (r"C:\Users\private\source.json", r"\\server\private\source.json"):
            with self.subTest(path=path):
                with self.assertRaisesRegex(RuntimeError, "local or private path"):
                    verify_complete._validate_public_value(path)

    def test_active_scan_ignores_historical_docs_and_rejects_consumer_coupling(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runtime = root / "askinsects" / "runtime.py"
            runtime.parent.mkdir(parents=True)
            runtime.write_text("PUBLIC_CONFIG = 'insect-evidence-package.json'\n", encoding="utf-8")
            config = root / "config" / "insect-evidence-package.json"
            config.parent.mkdir(parents=True)
            config.write_text("{}\n", encoding="utf-8")
            skill = root / "skills" / "askinsects" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("Use public insect evidence.\n", encoding="utf-8")
            historical = root / "docs" / "superpowers" / "plans" / "historical.md"
            historical.parent.mkdir(parents=True)
            historical.write_text("Historical Ask Monarch bridge.\n", encoding="utf-8")

            verify_complete.check_active_public_surfaces(root)
            runtime.write_text(
                "XML_NAMESPACE = 'http://schemas.openxmlformats.org/example'\n"
                "NCBI_FTP = 'ftp://ftp.ncbi.nlm.nih.gov/public'\n"
                "FORBIDDEN_SCHEME_PATTERN = r'file:/'\n",
                encoding="utf-8",
            )
            verify_complete.check_active_public_surfaces(root)

            offenders = (
                "from ask_monarch import Client\n",
                "CONFIG = 'config/ask-monarch-context-package.json'\n",
                "PRIVATE = '/Users/josh/projects/ask-monarch/results.json'\n",
                "DROSOPHILA_SUZUKII_MONARCH_TOPIC_SEARCH_TERMS = []\n",
                "LOCATOR = 'gs://monarch-private/results.json'\n",
            )
            for text in offenders:
                with self.subTest(text=text):
                    runtime.write_text(text, encoding="utf-8")
                    with self.assertRaisesRegex(RuntimeError, "active public surface"):
                        verify_complete.check_active_public_surfaces(root)

    def test_clean_public_clone_runs_fixture_package_checks_without_external_state(self):
        verify_complete.check_clean_clone_independence()

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

    def test_verify_complete_gate_passes_after_public_surface_tasks_land(self):
        verify_complete.check_active_public_surfaces()
        result = subprocess.run(
            [sys.executable, "scripts/verify_complete.py"],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("verify_complete ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
