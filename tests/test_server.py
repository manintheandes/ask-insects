import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.server import (
    activate_source_staging,
    copy_artifact_to_staging,
    copy_default_video_motion_inputs_to_staging,
    dispatch_request,
    ingest_image_atoms_staged,
    ingest_video_atoms_staged,
    prepare_mutable_staging,
    rewrite_artifact_references,
)
import askinsects.server as server_module
from askinsects.sources.cdc_dengue_surveillance import CdcDengueSurveillanceResult
from askinsects.sources.dryad_behavior_videos import DryadBehaviorVideoResult
from askinsects.sources.figshare_aedes_videos import FigshareAedesVideoResult
from askinsects.sources.gbif import GBIFBuildResult
from askinsects.sources.harvard_dataverse_suitability import HarvardDataverseSuitabilityResult
from askinsects.sources.inaturalist import INaturalistBuildResult
from askinsects.sources.irmapper import IRMapperBuildResult
from askinsects.sources.literature import FullTextUnit
from askinsects.sources.mendeley_behavior_media import MendeleyBehaviorMediaResult
from askinsects.sources.mosquito_alert import MosquitoAlertBuildResult
from askinsects.sources.ncbi_biosample import NCBIBioSampleResult
from askinsects.sources.ncvbdc_dengue_surveillance import NcvbdcDengueSurveillanceResult
from askinsects.sources.opendatasus_dengue_surveillance import OpenDataSusDengueSurveillanceResult
from askinsects.sources.ncbi_snp_variation import NCBISnpVariationResult
from askinsects.sources.osf_flighttrackai_videos import OSFFlightTrackAIResult
from askinsects.sources.paho_surveillance import PahoDengueSurveillanceResult
from askinsects.sources.pathogen_taxonomy import PathogenTaxonomyResult
from askinsects.sources.pmc_videos import PMCVideosResult
from askinsects.sources.public_health import PublicHealthGuidanceResult
from askinsects.sources.vectorbase_genomics import VectorBaseGenomicsResult
from askinsects.sources.vectornet_surveillance import VectorNetBuildResult
from askinsects.sources.who_dengue_surveillance import WhoDengueSurveillanceResult
from askinsects.sources.who_malaria_threats_resistance import WhoMalariaThreatsResistanceResult
from askinsects.sources.zenodo_aedes_videos import ZenodoAedesVideoResult
from tests.test_inaturalist_source import observation
from tests.test_image_atoms_source import write_image_fixture
from tests.test_video_atoms_source import RETRIEVED_AT, write_video_fixture


class ServerTests(unittest.TestCase):
    def test_auth_required(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            response = dispatch_request(
                "GET",
                "/health",
                None,
                headers={},
                artifact_dir=Path(tmpdir),
                token="secret",
            )

            self.assertEqual(response.status, 401)
            self.assertFalse(response.payload["ok"])

    def test_read_endpoints_reject_missing_source_index_without_creating_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            response = dispatch_request(
                "POST",
                "/sql",
                {"sql": "select count(*) as n from records"},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
            )

            self.assertEqual(response.status, 503)
            self.assertFalse(response.payload["ok"])
            self.assertEqual(response.payload["error"], "source_index_unavailable")
            self.assertEqual(response.payload["reason"], "source_index_missing")
            self.assertFalse((artifact_dir / "source_index.sqlite").exists())

    def test_read_endpoints_reject_empty_source_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            (artifact_dir / "source_index.sqlite").write_bytes(b"")
            response = dispatch_request(
                "POST",
                "/ask",
                {"question": "What Aedes papers are indexed?"},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
            )

            self.assertEqual(response.status, 503)
            self.assertFalse(response.payload["ok"])
            self.assertEqual(response.payload["reason"], "source_index_empty")

    def test_staging_copy_hardlinks_raw_files_but_copies_mutable_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "mosquito-v1"
            raw_dir = artifact_dir / "raw" / "large_source"
            raw_dir.mkdir(parents=True)
            (artifact_dir / "source_index.sqlite").write_text("mutable-db", encoding="utf-8")
            (artifact_dir / "source_index.sqlite-journal").write_text("stale rollback journal", encoding="utf-8")
            (artifact_dir / "source_status.json").write_text("{}", encoding="utf-8")
            (raw_dir / "page.json").write_text('{"ok": true}', encoding="utf-8")

            staging = root / ".mosquito-v1.staging"
            copy_artifact_to_staging(artifact_dir, staging)

            self.assertNotEqual(
                (artifact_dir / "source_index.sqlite").stat().st_ino,
                (staging / "source_index.sqlite").stat().st_ino,
            )
            self.assertEqual(
                (raw_dir / "page.json").stat().st_ino,
                (staging / "raw" / "large_source" / "page.json").stat().st_ino,
            )
            self.assertFalse((staging / "source_index.sqlite-journal").exists())

    def test_source_staging_replaces_mutables_and_one_raw_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "mosquito-v1"
            old_raw = artifact_dir / "raw" / "old_source"
            new_raw = artifact_dir / "raw" / "mosquito_alert"
            old_raw.mkdir(parents=True)
            new_raw.mkdir(parents=True)
            (artifact_dir / "source_index.sqlite").write_text("old-db", encoding="utf-8")
            (old_raw / "keep.json").write_text("keep", encoding="utf-8")
            (new_raw / "old.json").write_text("old", encoding="utf-8")

            staging = root / ".mosquito-v1.staging"
            prepare_mutable_staging(artifact_dir, staging)
            (staging / "source_index.sqlite").write_text("new-db", encoding="utf-8")
            staged_raw = staging / "raw" / "mosquito_alert"
            staged_raw.mkdir(parents=True)
            (staged_raw / "new.json").write_text("new", encoding="utf-8")

            activate_source_staging(staging, artifact_dir, Path("raw") / "mosquito_alert")

            self.assertEqual((artifact_dir / "source_index.sqlite").read_text(encoding="utf-8"), "new-db")
            self.assertEqual((old_raw / "keep.json").read_text(encoding="utf-8"), "keep")
            self.assertFalse((new_raw / "old.json").exists())
            self.assertEqual((new_raw / "new.json").read_text(encoding="utf-8"), "new")
            self.assertFalse(staging.exists())

    def test_video_atom_staging_copies_relative_motion_tables_for_parsing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)
            table_path = artifact_dir / "raw" / "mendeley_behavior_media" / "table_files" / "motion.csv"
            table_path.parent.mkdir(parents=True, exist_ok=True)
            table_path.write_text(
                "video_id,track_id,frame,time_seconds,x,y,behavior\n"
                "pmc:video:PMC123:video1.mp4,track-1,7,0.28,10.5,20.5,flight\n",
                encoding="utf-8",
            )

            response = ingest_video_atoms_staged(
                {
                    "retrieved_at": RETRIEVED_AT,
                    "motion_table_paths": ["raw/mendeley_behavior_media/table_files/motion.csv"],
                },
                artifact_dir=artifact_dir,
            )

            self.assertTrue(response["ok"])
            self.assertTrue(response["staged"])
            self.assertEqual(response["motion_row_count"], 1)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='aedes_video_atoms' and lane='behavior'",
                limit=5,
            )
            self.assertIn("raw/mendeley_behavior_media/table_files/motion.csv#row/1", rows[0]["provenance_json"])
            self.assertNotIn(".video-atoms-staging", rows[0]["provenance_json"])

    def test_video_atom_staging_copies_default_motion_tables_for_parsing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_video_fixture(artifact_dir)
            table_path = artifact_dir / "raw" / "mendeley_behavior_media" / "table_files" / "default-motion.csv"
            table_path.parent.mkdir(parents=True, exist_ok=True)
            table_path.write_text(
                "video_id,track_id,frame,time_seconds,x,y,behavior\n"
                "pmc:video:PMC123:video1.mp4,track-1,7,0.28,10.5,20.5,flight\n",
                encoding="utf-8",
            )

            response = ingest_video_atoms_staged(
                {"retrieved_at": RETRIEVED_AT},
                artifact_dir=artifact_dir,
            )

            self.assertTrue(response["ok"])
            self.assertEqual(response["motion_row_count"], 1)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='aedes_video_atoms' and lane='behavior'",
                limit=5,
            )
            self.assertIn("raw/mendeley_behavior_media/table_files/default-motion.csv#row/1", rows[0]["provenance_json"])
            self.assertNotIn(".video-atoms-staging", rows[0]["provenance_json"])

    def test_video_atom_staging_copies_existing_mirrors_and_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            asset = artifact_dir / "raw" / "video_atoms" / "assets" / "existing.mp4"
            artifact = artifact_dir / "raw" / "video_atoms" / "artifacts" / "existing" / "thumbnail.jpg"
            csv_path = artifact_dir / "raw" / "video_atoms" / "motion.csv"
            asset.parent.mkdir(parents=True)
            artifact.parent.mkdir(parents=True)
            asset.write_bytes(b"mp4")
            artifact.write_bytes(b"jpg")
            csv_path.write_text("video_id,frame\nexisting,1\n", encoding="utf-8")

            staging = Path(tmpdir) / ".mosquito-v1.video-atoms-staging"
            copy_default_video_motion_inputs_to_staging(artifact_dir, staging)

            self.assertTrue((staging / "raw" / "video_atoms" / "assets" / "existing.mp4").exists())
            self.assertTrue((staging / "raw" / "video_atoms" / "artifacts" / "existing" / "thumbnail.jpg").exists())
            self.assertTrue((staging / "raw" / "video_atoms" / "motion.csv").exists())

    def test_image_atom_ingest_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_image_fixture(artifact_dir)
            response = ingest_image_atoms_staged({"retrieved_at": RETRIEVED_AT}, artifact_dir=artifact_dir)

            self.assertTrue(response["ok"])
            self.assertFalse(response["staged"])
            self.assertTrue(response["updated_in_place"])
            self.assertEqual(response["image_asset_count"], 2)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select source, count(*) as n from records group by source",
                limit=20,
            )
            counts = {row["source"]: int(row["n"]) for row in rows}
            self.assertEqual(counts["inaturalist_api"], 1)
            self.assertEqual(counts["mosquito_alert_gbif"], 1)
            self.assertGreater(counts["aedes_image_atoms"], 2)
            self.assertFalse((artifact_dir.parent / ".mosquito-v1.image-atoms-staging").exists())

    def test_rewrite_artifact_references_can_limit_sqlite_updates_to_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "mosquito-v1"
            staging = root / ".mosquito-v1.extracted-facts-staging"
            staging.mkdir(parents=True)
            index = SourceIndex(staging / "source_index.sqlite")
            index.initialize()
            old = staging.as_posix()
            records = [
                EvidenceRecord(
                    record_id="target:1",
                    lane="behavior",
                    source="aedes_extracted_facts",
                    title="Target",
                    text="target text",
                    species="Aedes aegypti",
                    url=None,
                    media_url=None,
                    provenance=Provenance(
                        source_id="aedes_extracted_facts",
                        locator=f"{old}/source_index.sqlite#target",
                        retrieved_at="2026-05-24T00:00:00Z",
                    ),
                    payload={"path": f"{old}/raw/extracted_facts/target.json"},
                ),
                EvidenceRecord(
                    record_id="other:1",
                    lane="behavior",
                    source="other_source",
                    title="Other",
                    text="other text",
                    species="Aedes aegypti",
                    url=None,
                    media_url=None,
                    provenance=Provenance(
                        source_id="other_source",
                        locator=f"{old}/source_index.sqlite#other",
                        retrieved_at="2026-05-24T00:00:00Z",
                    ),
                    payload={"path": f"{old}/raw/other_source/other.json"},
                ),
            ]
            index.upsert_records(records)

            result = rewrite_artifact_references(
                staging,
                artifact_dir,
                {"artifact_dir": old},
                source="aedes_extracted_facts",
            )

            self.assertEqual(result["artifact_dir"], artifact_dir.as_posix())
            rows = SourceIndex(staging / "source_index.sqlite").sql(
                "select r.source, r.provenance_json, p.payload_json from records r join record_payloads p using(record_id) order by r.source"
            )
            by_source = {row["source"]: row for row in rows}
            self.assertIn(artifact_dir.as_posix(), by_source["aedes_extracted_facts"]["provenance_json"])
            self.assertIn(artifact_dir.as_posix(), by_source["aedes_extracted_facts"]["payload_json"])
            self.assertIn(old, by_source["other_source"]["provenance_json"])
            self.assertIn(old, by_source["other_source"]["payload_json"])

    def test_health_summary_sources_ask_and_sql(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            headers = {"Authorization": "Bearer secret"}

            health = dispatch_request("GET", "/health", None, headers=headers, artifact_dir=artifact_dir, token="secret")
            self.assertTrue(health.payload["ok"])
            self.assertEqual(health.payload["db_path"], str(artifact_dir / "source_index.sqlite"))

            summary = dispatch_request("GET", "/summary", None, headers=headers, artifact_dir=artifact_dir, token="secret")
            self.assertEqual(summary.payload["record_count"], 7)

            sources = dispatch_request("GET", "/sources", None, headers=headers, artifact_dir=artifact_dir, token="secret")
            self.assertIn("mosquito_v1_fixtures", sources.payload["sources"])

            answer = dispatch_request(
                "POST",
                "/ask",
                {"question": "what do we know about Aedes aegypti?", "limit": 2},
                headers=headers,
                artifact_dir=artifact_dir,
                token="secret",
            )
            self.assertTrue(answer.payload["ok"])
            self.assertTrue(answer.payload["evidence"])

            sql = dispatch_request(
                "POST",
                "/sql",
                {"sql": "select source, count(*) as n from records group by source"},
                headers=headers,
                artifact_dir=artifact_dir,
                token="secret",
            )
            self.assertTrue(sql.payload["ok"])
            self.assertEqual(sql.payload["rows"][0]["n"], 7)

    def test_search_literature_fulltext_route(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            provenance = Provenance(
                source_id="aedes_literature_openalex",
                locator="raw/literature/page.json#WSRV",
                retrieved_at="2026-05-23T00:00:00Z",
            )
            index.upsert_records_and_fulltext_units(
                [
                    EvidenceRecord(
                        record_id="openalex:WSRV",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Aedes aegypti full text paper",
                        text="Aedes aegypti metadata.",
                        species="Aedes aegypti",
                        url="https://example.org/paper",
                        media_url=None,
                        provenance=provenance,
                    )
                ],
                [
                    FullTextUnit(
                        unit_id="openalex:WSRV:fulltext:0",
                        record_id="openalex:WSRV",
                        source="aedes_literature_openalex",
                        unit_index=0,
                        text="Aedes aegypti legal full text mentions microbiota.",
                        url="https://example.org/fulltext",
                        license="CC BY",
                        provenance=provenance,
                    )
                ],
            )

            response = dispatch_request(
                "POST",
                "/search",
                {"lane": "literature_fulltext", "query": "microbiota", "limit": 5},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["rows"][0]["lane"], "literature_fulltext")

    def test_ingest_expression_omics_route_passes_limits(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch("scripts.ingest_expression_omics.ingest_expression_omics") as ingest:
                ingest.return_value = {"ok": True, "source": "aedes_expression_omics", "record_count": 3}
                response = dispatch_request(
                    "POST",
                    "/ingest/expression-omics",
                    {"geo_limit": 7, "sra_limit": 9},
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(artifact_dir=artifact_dir, geo_limit=7, sra_limit=9)

    def test_ingest_uniprot_proteins_route_passes_limits(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch("scripts.ingest_uniprot_proteins.ingest_uniprot_proteins") as ingest:
                ingest.return_value = {"ok": True, "source": "aedes_uniprot_proteins", "record_count": 3}
                response = dispatch_request(
                    "POST",
                    "/ingest/uniprot-proteins",
                    {"protein_limit": 12, "proteome_limit": 4},
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(artifact_dir=artifact_dir, protein_limit=12, proteome_limit=4)

    def test_ingest_wolbachia_interventions_route_passes_source_urls(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            source_urls = ["https://www.worldmosquitoprogram.org/example"]
            with mock.patch("scripts.ingest_wolbachia_interventions.ingest_wolbachia_interventions") as ingest:
                ingest.return_value = {"ok": True, "source": "aedes_wolbachia_interventions", "record_count": 1}
                response = dispatch_request(
                    "POST",
                    "/ingest/wolbachia-interventions",
                    {"source_urls": source_urls},
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(artifact_dir=artifact_dir, source_urls=source_urls)

    def test_ingest_vectorbyte_traits_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch("scripts.ingest_vectorbyte_traits.ingest_vectorbyte_traits") as ingest:
                ingest.return_value = {"ok": True, "source": "aedes_vectorbyte_traits", "record_count": 42}
                response = dispatch_request(
                    "POST",
                    "/ingest/vectorbyte-traits",
                    {"query": "Aedes aegypti", "dataset_limit": 3, "row_limit": 250, "search_limit": 25},
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                query="Aedes aegypti",
                dataset_limit=3,
                row_limit=250,
                search_limit=25,
            )

    def test_ingest_vectorbyte_abundance_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch("scripts.ingest_vectorbyte_abundance.ingest_vectorbyte_abundance") as ingest:
                ingest.return_value = {"ok": True, "source": "aedes_vectorbyte_abundance", "record_count": 42}
                response = dispatch_request(
                    "POST",
                    "/ingest/vectorbyte-abundance",
                    {
                        "query": "Aedes aegypti",
                        "dataset_limit": 3,
                        "row_limit": 250,
                        "search_page_limit": 2,
                        "dataset_page_limit": 12,
                        "dataset_ids": ["27006", "220"],
                        "merge_existing": True,
                    },
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                query="Aedes aegypti",
                dataset_limit=3,
                row_limit=250,
                search_page_limit=2,
                dataset_page_limit=12,
                dataset_ids=["27006", "220"],
                merge_existing=True,
            )

    def test_ingest_aedes_deep_sources_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch("scripts.ingest_aedes_deep_sources.ingest_aedes_deep_sources") as ingest:
                ingest.return_value = {"ok": True, "sources": ["aedes_taxonomy_authorities"], "record_count": 5}
                response = dispatch_request(
                    "POST",
                    "/ingest/aedes-deep-sources",
                    {"compendium_row_limit": 25, "bioproject_limit": 7, "worldclim_sample_limit": 3},
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                compendium_row_limit=25,
                bioproject_limit=7,
                worldclim_sample_limit=3,
            )

    def test_ingest_drosophila_suzukii_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch("scripts.ingest_drosophila_suzukii.ingest_drosophila_suzukii") as ingest:
                ingest.return_value = {"ok": True, "sources": ["drosophila_suzukii_core"], "record_count": 5}
                response = dispatch_request(
                    "POST",
                    "/ingest/drosophila-suzukii",
                    {
                        "gbif_occurrence_limit": 11,
                        "inaturalist_observation_limit": 12,
                        "literature_max_works": 13,
                        "bold_limit": 14,
                        "retrieved_at": "2026-05-28T00:00:00Z",
                    },
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                gbif_occurrence_limit=11,
                inaturalist_observation_limit=12,
                literature_max_works=13,
                bold_limit=14,
                retrieved_at="2026-05-28T00:00:00Z",
            )

    def test_ingest_drosophila_suzukii_deep_sources_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch("scripts.ingest_drosophila_suzukii_deep_sources.ingest_drosophila_suzukii_deep_sources") as ingest:
                ingest.return_value = {"ok": True, "sources": ["drosophila_suzukii_deep_sources"], "record_count": 5}
                response = dispatch_request(
                    "POST",
                    "/ingest/drosophila-suzukii-deep-sources",
                    {
                        "ncbi_limit": 15,
                        "protein_limit": 16,
                        "proteome_limit": 17,
                        "repository_limit": 18,
                        "retrieved_at": "2026-05-28T00:00:00Z",
                    },
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                ncbi_limit=15,
                protein_limit=16,
                proteome_limit=17,
                repository_limit=18,
                retrieved_at="2026-05-28T00:00:00Z",
            )

    def test_ingest_drosophila_suzukii_genome_files_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch("scripts.ingest_drosophila_suzukii_genome_files.ingest_drosophila_suzukii_genome_files") as ingest:
                ingest.return_value = {"ok": True, "source": "drosophila_suzukii_genome_files", "record_count": 5}
                response = dispatch_request(
                    "POST",
                    "/ingest/drosophila-suzukii-genome-files",
                    {
                        "assembly_accession": "GCF_043229965.1",
                        "max_download_bytes": 12345,
                        "retrieved_at": "2026-05-28T00:00:00Z",
                    },
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                assembly_accession="GCF_043229965.1",
                retrieved_at="2026-05-28T00:00:00Z",
                max_download_bytes=12345,
            )

    def test_ingest_drosophila_suzukii_literature_fulltext_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch(
                "scripts.ingest_drosophila_suzukii_literature_fulltext.ingest_drosophila_suzukii_literature_fulltext"
            ) as ingest:
                ingest.return_value = {"ok": True, "source": "drosophila_suzukii_literature_fulltext"}
                response = dispatch_request(
                    "POST",
                    "/ingest/drosophila-suzukii-literature-fulltext",
                    {
                        "email": "sources@openinsects.org",
                        "limit": 31,
                        "delay_seconds": 0,
                        "max_fulltext_bytes": 12345,
                        "include_unpaywall": True,
                        "resume": False,
                    },
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                email="sources@openinsects.org",
                limit=31,
                delay_seconds=0.0,
                max_fulltext_bytes=12345,
                include_unpaywall=True,
                resume=False,
            )

    def test_ingest_drosophila_suzukii_extracted_facts_route_installs_audit_rows(self):
        from tests.test_drosophila_suzukii_extracted_facts import write_swd_literature_fixture

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            write_swd_literature_fixture(artifact_dir)

            response = dispatch_request(
                "POST",
                "/ingest/drosophila-suzukii-extracted-facts",
                {},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertTrue(response.payload["staged"])
            self.assertEqual(response.payload["supplement_audit_record_count"], 2)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select source, lane, count(*) as n from records where source='drosophila_suzukii_extracted_facts' group by source, lane",
                limit=20,
            )
            counts = {(row["source"], row["lane"]): int(row["n"]) for row in rows}
            self.assertGreaterEqual(counts[("drosophila_suzukii_extracted_facts", "literature")], 3)
            self.assertFalse((artifact_dir.parent / ".mosquito-v1.drosophila-suzukii-extracted-facts-staging").exists())

    def test_ingest_drosophila_suzukii_video_atoms_route_installs_video_rows(self):
        from tests.test_drosophila_suzukii_video_atoms import write_swd_video_fixture

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            write_swd_video_fixture(artifact_dir)

            response = dispatch_request(
                "POST",
                "/ingest/drosophila-suzukii-video-atoms",
                {"max_video_bytes": 1000},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertTrue(response.payload["staged"])
            self.assertEqual(response.payload["video_asset_count"], 1)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select source, lane, count(*) as n from records where source='drosophila_suzukii_video_atoms' group by source, lane",
                limit=20,
            )
            counts = {(row["source"], row["lane"]): int(row["n"]) for row in rows}
            self.assertGreaterEqual(counts[("drosophila_suzukii_video_atoms", "media")], 2)
            self.assertFalse((artifact_dir.parent / ".mosquito-v1.drosophila-suzukii-video-atoms-staging").exists())

    def test_ingest_drosophila_suzukii_dryad_table_rows_route_installs_rows(self):
        from tests.test_drosophila_suzukii_dryad_table_rows import PREVIEW, write_dryad_manifest_fixture

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            write_dryad_manifest_fixture(artifact_dir)

            with mock.patch(
                "askinsects.sources.drosophila_suzukii_dryad_table_rows._default_fetch_preview_text",
                return_value=PREVIEW,
            ):
                response = dispatch_request(
                    "POST",
                    "/ingest/drosophila-suzukii-dryad-table-rows",
                    {"max_table_files": 1, "max_table_rows_per_file": 10},
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertTrue(response.payload["staged"])
            self.assertEqual(response.payload["table_row_count"], 2)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select source, lane, count(*) as n from records where source='drosophila_suzukii_dryad_table_rows' group by source, lane",
                limit=20,
            )
            counts = {(row["source"], row["lane"]): int(row["n"]) for row in rows}
            self.assertGreaterEqual(counts[("drosophila_suzukii_dryad_table_rows", "behavior")], 3)
            self.assertFalse((artifact_dir.parent / ".mosquito-v1.drosophila-suzukii-dryad-table-rows-staging").exists())

    def test_ingest_drosophila_suzukii_pubmed_literature_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch(
                "scripts.ingest_drosophila_suzukii_pubmed_literature.ingest_drosophila_suzukii_pubmed_literature"
            ) as ingest:
                ingest.return_value = {
                    "ok": True,
                    "source": "drosophila_suzukii_pubmed_literature",
                    "record_count": 2,
                }
                response = dispatch_request(
                    "POST",
                    "/ingest/drosophila-suzukii-pubmed-literature",
                    {
                        "max_results": 250,
                        "page_size": 50,
                        "delay_seconds": 0,
                        "retrieved_at": "2026-05-29T00:00:00Z",
                    },
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["source"], "drosophila_suzukii_pubmed_literature")
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                max_results=250,
                page_size=50,
                delay_seconds=0.0,
                retrieved_at="2026-05-29T00:00:00Z",
            )

    def test_ingest_drosophila_suzukii_ncbi_nucleotide_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch(
                "scripts.ingest_drosophila_suzukii_ncbi_nucleotide.ingest_drosophila_suzukii_ncbi_nucleotide"
            ) as ingest:
                ingest.return_value = {
                    "ok": True,
                    "source": "drosophila_suzukii_ncbi_nucleotide",
                    "record_count": 2,
                }
                response = dispatch_request(
                    "POST",
                    "/ingest/drosophila-suzukii-ncbi-nucleotide",
                    {
                        "max_results": 250,
                        "page_size": 50,
                        "delay_seconds": 0,
                        "retrieved_at": "2026-05-29T00:00:00Z",
                    },
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["source"], "drosophila_suzukii_ncbi_nucleotide")
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                max_results=250,
                page_size=50,
                delay_seconds=0.0,
                retrieved_at="2026-05-29T00:00:00Z",
            )

    def test_ingest_drosophila_suzukii_ncbi_snp_variation_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch(
                "scripts.ingest_drosophila_suzukii_ncbi_snp_variation.ingest_drosophila_suzukii_ncbi_snp_variation"
            ) as ingest:
                ingest.return_value = {
                    "ok": True,
                    "source": "drosophila_suzukii_ncbi_snp_variation",
                    "record_count": 1,
                }
                response = dispatch_request(
                    "POST",
                    "/ingest/drosophila-suzukii-ncbi-snp-variation",
                    {
                        "limit": 250,
                        "page_size": 50,
                        "delay_seconds": 0,
                        "retrieved_at": "2026-05-29T00:00:00Z",
                    },
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["source"], "drosophila_suzukii_ncbi_snp_variation")
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                limit=250,
                page_size=50,
                delay_seconds=0.0,
                retrieved_at="2026-05-29T00:00:00Z",
            )

    def test_ingest_drosophila_suzukii_ncbi_marker_review_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch(
                "scripts.ingest_drosophila_suzukii_ncbi_marker_review.ingest_drosophila_suzukii_ncbi_marker_review"
            ) as ingest:
                ingest.return_value = {
                    "ok": True,
                    "source": "drosophila_suzukii_ncbi_marker_review",
                    "record_count": 3,
                }
                response = dispatch_request(
                    "POST",
                    "/ingest/drosophila-suzukii-ncbi-marker-review",
                    {
                        "max_results": 250,
                        "page_size": 50,
                        "delay_seconds": 0,
                        "retrieved_at": "2026-05-29T00:00:00Z",
                    },
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["source"], "drosophila_suzukii_ncbi_marker_review")
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                max_results=250,
                page_size=50,
                delay_seconds=0.0,
                retrieved_at="2026-05-29T00:00:00Z",
            )

    def test_ingest_drosophila_suzukii_extension_guidance_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch(
                "scripts.ingest_drosophila_suzukii_extension_guidance.ingest_drosophila_suzukii_extension_guidance"
            ) as ingest:
                ingest.return_value = {
                    "ok": True,
                    "source": "drosophila_suzukii_extension_guidance",
                    "record_count": 1,
                }
                response = dispatch_request(
                    "POST",
                    "/ingest/drosophila-suzukii-extension-guidance",
                    {
                        "source_urls": ["https://extension.example/swd"],
                        "retrieved_at": "2026-05-29T00:00:00Z",
                    },
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["source"], "drosophila_suzukii_extension_guidance")
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                source_urls=["https://extension.example/swd"],
                retrieved_at="2026-05-29T00:00:00Z",
            )

    def test_ingest_drosophila_suzukii_jki_drosomon_trap_captures_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch(
                "scripts.ingest_drosophila_suzukii_jki_drosomon_trap_captures.ingest_drosophila_suzukii_jki_drosomon_trap_captures"
            ) as ingest:
                ingest.return_value = {
                    "ok": True,
                    "source": "drosophila_suzukii_jki_drosomon_trap_captures",
                    "record_count": 5,
                }
                response = dispatch_request(
                    "POST",
                    "/ingest/drosophila-suzukii-jki-drosomon-trap-captures",
                    {
                        "retrieved_at": "2026-05-29T00:00:00Z",
                    },
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["source"], "drosophila_suzukii_jki_drosomon_trap_captures")
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                retrieved_at="2026-05-29T00:00:00Z",
            )

    def test_ingest_drosophila_suzukii_ncbi_gene_orthologs_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch(
                "scripts.ingest_drosophila_suzukii_ncbi_gene_orthologs.ingest_drosophila_suzukii_ncbi_gene_orthologs"
            ) as ingest:
                ingest.return_value = {
                    "ok": True,
                    "source": "drosophila_suzukii_ncbi_gene_orthologs",
                    "record_count": 3,
                }
                response = dispatch_request(
                    "POST",
                    "/ingest/drosophila-suzukii-ncbi-gene-orthologs",
                    {
                        "max_download_bytes": 123456,
                        "max_rows": 42,
                        "retrieved_at": "2026-05-29T00:00:00Z",
                    },
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["source"], "drosophila_suzukii_ncbi_gene_orthologs")
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                max_download_bytes=123456,
                max_rows=42,
                retrieved_at="2026-05-29T00:00:00Z",
            )

    def test_ingest_drosophila_suzukii_ensembl_metazoa_orthology_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch(
                "scripts.ingest_drosophila_suzukii_ensembl_metazoa_orthology.ingest_drosophila_suzukii_ensembl_metazoa_orthology"
            ) as ingest:
                ingest.return_value = {
                    "ok": True,
                    "source": "drosophila_suzukii_ensembl_metazoa_orthology",
                    "record_count": 3,
                }
                response = dispatch_request(
                    "POST",
                    "/ingest/drosophila-suzukii-ensembl-metazoa-orthology",
                    {
                        "max_download_bytes": 123456,
                        "max_rows_per_file": 42,
                        "retrieved_at": "2026-05-29T00:00:00Z",
                    },
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["source"], "drosophila_suzukii_ensembl_metazoa_orthology")
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                max_download_bytes=123456,
                max_rows_per_file=42,
                retrieved_at="2026-05-29T00:00:00Z",
            )

    def test_ingest_drosophila_suzukii_geo_expression_matrices_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch(
                "scripts.ingest_drosophila_suzukii_geo_expression_matrices.ingest_drosophila_suzukii_geo_expression_matrices"
            ) as ingest:
                ingest.return_value = {
                    "ok": True,
                    "source": "drosophila_suzukii_geo_expression_matrices",
                    "record_count": 3,
                }
                response = dispatch_request(
                    "POST",
                    "/ingest/drosophila-suzukii-geo-expression-matrices",
                    {
                        "max_download_bytes": 123456,
                        "max_rows_per_file": 42,
                        "retrieved_at": "2026-05-29T00:00:00Z",
                    },
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["source"], "drosophila_suzukii_geo_expression_matrices")
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                max_download_bytes=123456,
                max_rows_per_file=42,
                retrieved_at="2026-05-29T00:00:00Z",
            )

    def test_ingest_drosophila_suzukii_figshare_mk_selection_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch(
                "scripts.ingest_drosophila_suzukii_figshare_mk_selection.ingest_drosophila_suzukii_figshare_mk_selection"
            ) as ingest:
                ingest.return_value = {
                    "ok": True,
                    "source": "drosophila_suzukii_figshare_mk_selection",
                    "record_count": 3,
                }
                response = dispatch_request(
                    "POST",
                    "/ingest/drosophila-suzukii-figshare-mk-selection",
                    {
                        "max_download_bytes": 123456,
                        "max_rows": 42,
                        "retrieved_at": "2026-05-29T00:00:00Z",
                    },
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["source"], "drosophila_suzukii_figshare_mk_selection")
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                max_download_bytes=123456,
                max_rows=42,
                retrieved_at="2026-05-29T00:00:00Z",
            )

    def test_ingest_drosophila_suzukii_population_genomics_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch(
                "scripts.ingest_drosophila_suzukii_population_genomics.ingest_drosophila_suzukii_population_genomics"
            ) as ingest:
                ingest.return_value = {
                    "ok": True,
                    "source": "drosophila_suzukii_population_genomics",
                    "record_count": 3,
                }
                response = dispatch_request(
                    "POST",
                    "/ingest/drosophila-suzukii-population-genomics",
                    {
                        "limit": 42,
                        "retrieved_at": "2026-05-29T00:00:00Z",
                    },
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["source"], "drosophila_suzukii_population_genomics")
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                limit=42,
                retrieved_at="2026-05-29T00:00:00Z",
            )

    def test_ingest_drosophila_suzukii_dryad_population_variants_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch(
                "scripts.ingest_drosophila_suzukii_dryad_population_variants.ingest_drosophila_suzukii_dryad_population_variants"
            ) as ingest:
                ingest.return_value = {
                    "ok": True,
                    "source": "drosophila_suzukii_dryad_population_variants",
                    "record_count": 3,
                }
                response = dispatch_request(
                    "POST",
                    "/ingest/drosophila-suzukii-dryad-population-variants",
                    {
                        "max_mirror_bytes": 123456,
                        "retrieved_at": "2026-05-29T00:00:00Z",
                    },
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["source"], "drosophila_suzukii_dryad_population_variants")
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                max_mirror_bytes=123456,
                retrieved_at="2026-05-29T00:00:00Z",
            )

    def test_ingest_aedes_olfaction_literature_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch("scripts.ingest_aedes_olfaction_literature.ingest_aedes_olfaction_literature") as ingest:
                ingest.return_value = {"ok": True, "source": "aedes_olfaction_literature", "record_count": 183}
                response = dispatch_request(
                    "POST",
                    "/ingest/aedes-olfaction-literature",
                    {
                        "max_results": 250,
                        "page_size": 50,
                        "include_fulltext": True,
                        "unpaywall_email": "sources@openinsects.org",
                        "fulltext_limit": 25,
                        "delay_seconds": 0,
                        "max_fulltext_bytes": 123456,
                    },
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                max_results=250,
                page_size=50,
                include_fulltext=True,
                unpaywall_email="sources@openinsects.org",
                fulltext_limit=25,
                delay_seconds=0.0,
                max_fulltext_bytes=123456,
            )

    def test_ingest_crossref_literature_audit_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch("scripts.ingest_aedes_crossref_literature_audit.ingest_aedes_crossref_literature_audit") as ingest:
                ingest.return_value = {"ok": True, "source": "aedes_crossref_literature_audit", "record_count": 200}
                response = dispatch_request(
                    "POST",
                    "/ingest/crossref-literature-audit",
                    {"max_results": 250, "page_size": 50},
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                max_results=250,
                page_size=50,
            )

    def test_ingest_mosquito_repellent_literature_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch("scripts.ingest_mosquito_repellent_literature.ingest_mosquito_repellent_literature") as ingest:
                ingest.return_value = {"ok": True, "source": "mosquito_repellent_literature", "record_count": 300}
                response = dispatch_request(
                    "POST",
                    "/ingest/mosquito-repellent-literature",
                    {"pubmed_max_results": 250, "crossref_max_results": 350, "page_size": 50},
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                pubmed_max_results=250,
                crossref_max_results=350,
                page_size=50,
            )

    def test_ingest_mosquito_repellent_external_discovery_route_passes_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch(
                "scripts.ingest_mosquito_repellent_external_discovery.ingest_mosquito_repellent_external_discovery"
            ) as ingest:
                ingest.return_value = {"ok": True, "source": "mosquito_repellent_external_discovery", "record_count": 120}
                response = dispatch_request(
                    "POST",
                    "/ingest/mosquito-repellent-external-discovery",
                    {"max_results_per_source": 25},
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            ingest.assert_called_once_with(
                artifact_dir=artifact_dir,
                max_results_per_source=25,
            )

    def test_ingest_inaturalist_uses_staging_then_activates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            calls = []

            def fake_fetch(*args, **kwargs):
                calls.append((args, kwargs))
                raw_dir = kwargs["raw_dir"]
                raw_dir.mkdir(parents=True, exist_ok=True)
                raw_path = raw_dir / "page.json"
                raw_path.write_text("{}\n", encoding="utf-8")
                return INaturalistBuildResult(
                    source_id="inaturalist_api",
                    records=[],
                    gaps=[],
                    raw_artifacts=[raw_path.as_posix()],
                    requested_species=list(args[0]),
                    place=kwargs["place"],
                    observation_limit=kwargs["observation_limit"],
                    page_size=kwargs["page_size"],
                    delay_seconds=kwargs["delay_seconds"],
                    total_results={"Aedes aegypti": 0},
                )

            headers = {"Authorization": "Bearer secret"}
            response = dispatch_request(
                "POST",
                "/ingest/inaturalist",
                {"species": ["Aedes aegypti"], "observation_limit": 10, "page_size": 10, "delay_seconds": 0},
                headers=headers,
                artifact_dir=artifact_dir,
                token="secret",
                fetch_inaturalist_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertIn("mosquito_v1_fixtures", response.payload["sources"])
            self.assertTrue((artifact_dir / "source_index.sqlite").exists())
            self.assertFalse((artifact_dir.parent / ".mosquito-v1.staging").exists())
            self.assertEqual(len(calls), 1)

    def test_ingest_records_final_artifact_paths_in_provenance(self):
        def fake_fetch(*args, **kwargs):
            raw_dir = kwargs["raw_dir"]
            return INaturalistBuildResult(
                source_id="inaturalist_api",
                records=[
                    EvidenceRecord(
                        record_id="inat:media:1",
                        lane="media",
                        source="inaturalist_api",
                        title="Aedes aegypti image",
                        text="Aedes aegypti image.",
                        species="Aedes aegypti",
                        url="https://www.inaturalist.org/observations/1",
                        media_url="https://static.inaturalist.org/photos/1/medium.jpg",
                        provenance=Provenance(
                            source_id="inaturalist_api",
                            locator=f"{raw_dir}/page.json#observations/1/photos/1",
                            retrieved_at="2026-05-23T00:00:00Z",
                            license="cc-by",
                            source_url="https://www.inaturalist.org/observations/1",
                        ),
                    )
                ],
                gaps=[],
                raw_artifacts=[(raw_dir / "page.json").as_posix()],
                requested_species=list(args[0]),
                place=kwargs["place"],
                observation_limit=kwargs["observation_limit"],
                page_size=kwargs["page_size"],
                delay_seconds=kwargs["delay_seconds"],
                total_results={"Aedes aegypti": 1},
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            response = dispatch_request(
                "POST",
                "/ingest/inaturalist",
                {"species": ["Aedes aegypti"], "observation_limit": 1},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_inaturalist_records_fn=fake_fetch,
            )

            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select provenance_json from records where source='inaturalist_api'")
            self.assertIn(str(artifact_dir), rows[0]["provenance_json"])
            self.assertNotIn(".staging", rows[0]["provenance_json"])

    def test_ingest_inaturalist_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="bold:barcode:test",
                        lane="dna_barcodes",
                        source="bold_api",
                        title="BOLD barcode",
                        text="BOLD barcode for Aedes aegypti.",
                        species="Aedes aegypti",
                        url="https://portal.boldsystems.org/record/test",
                        media_url=None,
                        provenance=Provenance(
                            source_id="bold_api",
                            locator="test.tsv#row/1",
                            retrieved_at="2026-05-23T00:00:00Z",
                            license="BOLD public data",
                        ),
                    )
                ]
            )

            def fake_fetch(*args, **kwargs):
                raw_dir = kwargs["raw_dir"]
                return INaturalistBuildResult(
                    source_id="inaturalist_api",
                    records=[
                        EvidenceRecord(
                            record_id="inat:observation:1",
                            lane="observations",
                            source="inaturalist_api",
                            title="Aedes aegypti observation",
                            text="Aedes aegypti observed with a photo.",
                            species="Aedes aegypti",
                            url="https://www.inaturalist.org/observations/1",
                            media_url="https://static.inaturalist.org/photos/1/medium.jpg",
                            provenance=Provenance(
                                source_id="inaturalist_api",
                                locator=f"{raw_dir}/page.json#observations/1",
                                retrieved_at="2026-05-23T00:00:00Z",
                                license="cc-by",
                                source_url="https://api.inaturalist.org/v1/observations",
                            ),
                        )
                    ],
                    gaps=[],
                    raw_artifacts=[(raw_dir / "page.json").as_posix()],
                    requested_species=["Aedes aegypti"],
                    place=None,
                    observation_limit=1,
                    page_size=200,
                    delay_seconds=0.0,
                    total_results={"Aedes aegypti": 1},
                )

            response = dispatch_request(
                "POST",
                "/ingest/inaturalist",
                {"species": ["Aedes aegypti"], "observation_limit": 1},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_inaturalist_records_fn=fake_fetch,
            )

            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["bold_api"], 1)
            self.assertEqual(counts["inaturalist_api"], 1)

    def test_ingest_inaturalist_streams_default_fetch_into_existing_index(self):
        class FakeClient:
            def observations(self, species, *, place, page, page_size):
                return (
                    "https://api.inaturalist.org/v1/observations",
                    {
                        "total_results": 1,
                        "results": [observation(1, 101)],
                    },
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            with mock.patch("askinsects.server.INaturalistClient", return_value=FakeClient()):
                response = dispatch_request(
                    "POST",
                    "/ingest/inaturalist",
                    {"species": ["Aedes aegypti"], "observation_limit": 1, "page_size": 10, "delay_seconds": 0},
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                )

            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, lane, count(*) as n from records group by source, lane")
            counts = {(row["source"], row["lane"]): row["n"] for row in rows}
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 4)
            self.assertEqual(counts[("inaturalist_api", "observations")], 1)
            self.assertEqual(counts[("inaturalist_api", "media")], 1)
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='inaturalist_api'",
                limit=2,
            )
            self.assertTrue(provenance_rows)
            for row in provenance_rows:
                self.assertIn(str(artifact_dir), row["provenance_json"])
                self.assertNotIn(".staging", row["provenance_json"])

    def test_ingest_keeps_active_index_available_during_build(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            active_db = artifact_dir / "source_index.sqlite"

            def fake_fetch(*args, **kwargs):
                self.assertTrue(active_db.exists())
                self.assertNotEqual(kwargs["raw_dir"].parents[1], artifact_dir)
                return INaturalistBuildResult(
                    source_id="inaturalist_api",
                    records=[],
                    gaps=[],
                    raw_artifacts=[],
                    requested_species=list(args[0]),
                    place=kwargs["place"],
                    observation_limit=kwargs["observation_limit"],
                    page_size=kwargs["page_size"],
                    delay_seconds=kwargs["delay_seconds"],
                    total_results={"Aedes aegypti": 0},
                )

            response = dispatch_request(
                "POST",
                "/ingest/inaturalist",
                {"species": ["Aedes aegypti"], "observation_limit": 1},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_inaturalist_records_fn=fake_fetch,
            )

            self.assertTrue(response.payload["ok"])
            self.assertTrue(active_db.exists())

    def test_ingest_gbif_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="inat:observation:1",
                        lane="observations",
                        source="inaturalist_api",
                        title="Aedes aegypti iNaturalist observation",
                        text="Aedes aegypti observed on iNaturalist.",
                        species="Aedes aegypti",
                        url="https://www.inaturalist.org/observations/1",
                        media_url=None,
                        provenance=Provenance(
                            source_id="inaturalist_api",
                            locator=f"{artifact_dir}/raw/inaturalist/page.json#observations/1",
                            retrieved_at="2026-05-23T00:00:00Z",
                            license="cc-by",
                            source_url="https://api.inaturalist.org/v1/observations",
                        ),
                    )
                ]
            )

            def fake_gbif_fetch(*args, **kwargs):
                raw_dir = kwargs["raw_dir"]
                return GBIFBuildResult(
                    source_id="gbif_api",
                    records=[
                        EvidenceRecord(
                            record_id="gbif:occurrence:444",
                            lane="observations",
                            source="gbif_api",
                            title="Aedes aegypti occurrence 444",
                            text="GBIF occurrence record for Aedes aegypti in Brazil.",
                            species="Aedes aegypti",
                            url="https://www.gbif.org/occurrence/444",
                            media_url=None,
                            provenance=Provenance(
                                source_id="gbif_api",
                                locator=f"{raw_dir}/Aedes_aegypti_occurrences_offset_000000.json#occurrence/444",
                                retrieved_at="2026-05-23T00:00:00Z",
                                license="CC_BY_4_0",
                                source_url="https://www.gbif.org/occurrence/444",
                            ),
                            payload={"raw_occurrence": {"key": 444}},
                        )
                    ],
                    gaps=[],
                    taxon_keys={"Aedes aegypti": 1651891},
                    raw_artifacts=[(raw_dir / "Aedes_aegypti_occurrences_offset_000000.json").as_posix()],
                    requested_species=["Aedes aegypti"],
                    occurrence_limit=1,
                    occurrence_page_size=300,
                    occurrence_workers=1,
                    total_results={"Aedes aegypti": 82237},
                    page_count=1,
                )

            response = dispatch_request(
                "POST",
                "/ingest/gbif",
                {"species": ["Aedes aegypti"], "occurrence_limit": 1},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_gbif_records_fn=fake_gbif_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["inaturalist_api"], 1)
            self.assertEqual(counts["gbif_api"], 1)
            payload_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select record_id from record_payloads where source='gbif_api'")
            self.assertEqual(payload_rows[0]["record_id"], "gbif:occurrence:444")

    def test_ingest_irmapper_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(*, raw_dir, species, retrieved_at):
                raw_path = raw_dir / "Aedes_aegypti.json"
                return IRMapperBuildResult(
                    source_id="irmapper_aedes",
                    records=[
                        EvidenceRecord(
                            record_id="irmapper:aedes:301",
                            lane="resistance",
                            source="irmapper_aedes",
                            title="Aedes aegypti IR Mapper resistance deltamethrin Brazil",
                            text="IR Mapper resistance record for Aedes aegypti in Brazil with deltamethrin.",
                            species="Aedes aegypti",
                            url="https://example.org/paper",
                            media_url=None,
                            provenance=Provenance(
                                source_id="irmapper_aedes",
                                locator=f"{raw_path}#row/1",
                                retrieved_at=retrieved_at,
                                license="IR Mapper public API",
                                source_url="https://api.irmapper.com/api/aedes",
                            ),
                            payload={"raw_row": {"id": 301}},
                        )
                    ],
                    gaps=[],
                    raw_artifacts=[raw_path.as_posix()],
                    requested_species=species,
                    fetched_row_count=1,
                )

            with mock.patch("askinsects.server.copy_artifact_to_staging") as copy_artifact_to_staging:
                copy_artifact_to_staging.side_effect = AssertionError("IR Mapper ingest should use source-scoped staging")
                response = dispatch_request(
                    "POST",
                    "/ingest/irmapper",
                    {"species": "Aedes aegypti"},
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                    fetch_irmapper_records_fn=fake_fetch,
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertFalse(response.payload["staged"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["irmapper_aedes"], 1)
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='irmapper_aedes'",
            )
            self.assertIn(str(artifact_dir), provenance_rows[0]["provenance_json"])
            self.assertNotIn(".staging", provenance_rows[0]["provenance_json"])

    def test_ingest_irmapper_skips_replace_when_records_are_unchanged(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            raw_path = artifact_dir / "raw" / "irmapper" / "Aedes_aegypti.json"
            record = EvidenceRecord(
                record_id="irmapper:aedes:301",
                lane="resistance",
                source="irmapper_aedes",
                title="Aedes aegypti IR Mapper resistance deltamethrin Brazil",
                text="IR Mapper resistance record for Aedes aegypti in Brazil with deltamethrin.",
                species="Aedes aegypti",
                url="https://example.org/paper",
                media_url=None,
                provenance=Provenance(
                    source_id="irmapper_aedes",
                    locator=f"{raw_path}#row/1",
                    retrieved_at="2026-05-25T00:00:00Z",
                    license="IR Mapper public API",
                    source_url="https://api.irmapper.com/api/aedes",
                ),
                payload={"raw_row": {"id": 301}},
            )
            SourceIndex(artifact_dir / "source_index.sqlite").upsert_records([record])

            def fake_fetch(*, raw_dir, species, retrieved_at):
                return IRMapperBuildResult(
                    source_id="irmapper_aedes",
                    records=[record],
                    gaps=[],
                    raw_artifacts=[(raw_dir / "Aedes_aegypti.json").as_posix()],
                    requested_species=species,
                    fetched_row_count=1,
                )

            with mock.patch("askinsects.server.SourceIndex.replace_source_records") as replace_source_records:
                replace_source_records.side_effect = AssertionError("unchanged IR Mapper records should not rewrite SQLite")
                response = dispatch_request(
                    "POST",
                    "/ingest/irmapper",
                    {"species": "Aedes aegypti"},
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                    fetch_irmapper_records_fn=fake_fetch,
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertTrue(response.payload["records_unchanged"])

    def test_ingest_who_malaria_threats_resistance_adds_gap_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(*, raw_dir, species, sample_limit, aedes_limit, fetch_bytes, retrieved_at):
                raw_path = raw_dir / "FACT_PREVENTION_VIEW_Aedes_aegypti.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text('{"value":[]}', encoding="utf-8")
                return WhoMalariaThreatsResistanceResult(
                    source_id="who_malaria_threats_resistance_audit",
                    records=[
                        EvidenceRecord(
                            record_id="who:malaria-threats:resistance:source",
                            lane="resistance",
                            source="who_malaria_threats_resistance_audit",
                            title="WHO Malaria Threats Map insecticide-resistance database availability",
                            text="WHO Malaria Threats Map exposes the WHO global insecticide-resistance database.",
                            species="mosquito vectors",
                            url="https://www.who.int/teams/global-malaria-programme/prevention/vector-control/global-database-on-insecticide-resistance-in-malaria-vectors",
                            media_url=None,
                            provenance=Provenance(
                                source_id="who_malaria_threats_resistance_audit",
                                locator=f"{raw_path}#sample",
                                retrieved_at=retrieved_at,
                                license="WHO public data; WHO terms apply",
                            ),
                        ),
                        EvidenceRecord(
                            record_id="who:malaria-threats:resistance:gap:aedes_aegypti:who_malaria_threats_no_aedes_rows",
                            lane="resistance",
                            source="who_malaria_threats_resistance_audit",
                            title="WHO Malaria Threats Map Aedes resistance source gap",
                            text="WHO Malaria Threats Map resistance audit found no rows matching Aedes aegypti.",
                            species="Aedes aegypti",
                            url="https://apps.who.int/malaria/maps/threats/",
                            media_url=None,
                            provenance=Provenance(
                                source_id="who_malaria_threats_resistance_audit",
                                locator=f"{raw_path}#gap/who_malaria_threats_no_aedes_rows",
                                retrieved_at=retrieved_at,
                                license="WHO public data; WHO terms apply",
                            ),
                            payload={"gap": {"reason": "who_malaria_threats_no_aedes_rows"}},
                        ),
                    ],
                    gaps=[{"source": "who_malaria_threats_resistance_audit", "reason": "who_malaria_threats_no_aedes_rows"}],
                    raw_artifacts=[raw_path.as_posix()],
                    species=species,
                    sample_row_count=1,
                    aedes_row_count=0,
                )

            response = dispatch_request(
                "POST",
                "/ingest/who-malaria-threats-resistance",
                {"species": "Aedes aegypti", "sample_limit": 2, "aedes_limit": 10},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_who_malaria_threats_resistance_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["who_malaria_threats_resistance_audit"], 2)

    def test_ingest_harvard_dataverse_suitability_adds_ecology_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(*, raw_dir, queries, per_page, dataset_limit, fetch_json, retrieved_at):
                raw_path = raw_dir / "search.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text('{"data":{"items":[]}}', encoding="utf-8")
                return HarvardDataverseSuitabilityResult(
                    source_id="harvard_dataverse_aedes_suitability",
                    records=[
                        EvidenceRecord(
                            record_id="ecology:dataverse_suitability:3623893",
                            lane="ecology",
                            source="harvard_dataverse_aedes_suitability",
                            title="Aedes aegypti Dataverse suitability raster TCurMean30Sum_97ae.tif",
                            text="Harvard Dataverse Aedes aegypti suitability raster manifest.",
                            species="Aedes aegypti",
                            url="https://doi.org/10.7910/DVN/NSG5UH",
                            media_url="https://dataverse.harvard.edu/api/access/datafile/3623893",
                            provenance=Provenance(
                                source_id="harvard_dataverse_aedes_suitability",
                                locator=f"{raw_path}#data/items/1",
                                retrieved_at=retrieved_at,
                                license="CC0 1.0",
                            ),
                            payload={"filename": "TCurMean30Sum_97ae.tif"},
                        ),
                        EvidenceRecord(
                            record_id="ecology:dataverse_suitability:gap:download",
                            lane="ecology",
                            source="harvard_dataverse_aedes_suitability",
                            title="Aedes aegypti Dataverse suitability source gap: dataverse_file_download_not_public",
                            text="Harvard Dataverse Aedes suitability source gap: dataverse_file_download_not_public.",
                            species="Aedes aegypti",
                            url="https://doi.org/10.7910/DVN/NSG5UH",
                            media_url=None,
                            provenance=Provenance(
                                source_id="harvard_dataverse_aedes_suitability",
                                locator=f"{raw_path}#data/items/1",
                                retrieved_at=retrieved_at,
                                license="CC0 1.0",
                            ),
                            payload={"gap": {"reason": "dataverse_file_download_not_public"}},
                        ),
                    ],
                    gaps=[{"source": "harvard_dataverse_aedes_suitability", "reason": "dataverse_file_download_not_public"}],
                    raw_artifacts=[raw_path.as_posix()],
                    query_count=len(queries),
                    search_item_count=1,
                    dataset_count=1,
                    file_record_count=1,
                )

            response = dispatch_request(
                "POST",
                "/ingest/harvard-dataverse-suitability",
                {"queries": ['"Aedes aegypti" suitability'], "per_page": 10, "dataset_limit": 2},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_harvard_dataverse_suitability_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["harvard_dataverse_aedes_suitability"], 2)

    def test_ingest_public_health_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(sources, *, raw_dir, retrieved_at):
                raw_path = raw_dir / "cdc.html"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text("<html>Aedes aegypti dengue vector control guidance.</html>", encoding="utf-8")
                return PublicHealthGuidanceResult(
                    source_id="aedes_public_health_guidance",
                    records=[
                        EvidenceRecord(
                            record_id="public_health:guidance:cdc",
                            lane="public_health",
                            source="aedes_public_health_guidance",
                            title="CDC guidance",
                            text="Official public-health guidance for Aedes aegypti dengue vector control.",
                            species="Aedes aegypti",
                            url="https://www.cdc.gov/example",
                            media_url=None,
                            provenance=Provenance(
                                source_id="aedes_public_health_guidance",
                                locator=f"{raw_path}#page",
                                retrieved_at=retrieved_at,
                                license="Public health web guidance; source page terms apply",
                                source_url="https://www.cdc.gov/example",
                            ),
                            payload={"organization": "CDC"},
                        )
                    ],
                    gaps=[],
                    raw_artifacts=[raw_path.as_posix()],
                    requested_urls=["https://www.cdc.gov/example"],
                )

            response = dispatch_request(
                "POST",
                "/ingest/public-health",
                {"source_urls": ["https://www.cdc.gov/example"]},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_public_health_guidance_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["aedes_public_health_guidance"], 1)
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='aedes_public_health_guidance'",
            )
            self.assertIn(str(artifact_dir), provenance_rows[0]["provenance_json"])
            self.assertNotIn(".staging", provenance_rows[0]["provenance_json"])

    def test_ingest_public_health_empty_source_urls_uses_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            seen_source_count = []

            def fake_fetch(sources, *, raw_dir, retrieved_at):
                seen_source_count.append(len(sources))
                return PublicHealthGuidanceResult(
                    source_id="aedes_public_health_guidance",
                    records=[],
                    gaps=[],
                    raw_artifacts=[],
                    requested_urls=[str(source["url"]) for source in sources],
                )

            response = dispatch_request(
                "POST",
                "/ingest/public-health",
                {"source_urls": []},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_public_health_guidance_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertGreater(seen_source_count[0], 1)

    def test_ingest_paho_dengue_surveillance_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(reports, *, raw_dir, retrieved_at, dashboard_pages, core_indicator_pages):
                raw_path = raw_dir / "paho.html"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text("<html>PAHO dengue surveillance.</html>", encoding="utf-8")
                return PahoDengueSurveillanceResult(
                    source_id="aedes_paho_dengue_surveillance",
                    records=[
                        EvidenceRecord(
                            record_id="public_health:surveillance:paho_dengue:regional_week_summary:2024:week50",
                            lane="public_health",
                            source="aedes_paho_dengue_surveillance",
                            title="PAHO dengue surveillance",
                            text="Official PAHO dengue surveillance for Aedes aegypti public-health intelligence.",
                            species="Aedes aegypti",
                            url="https://ais.paho.org/example",
                            media_url=None,
                            provenance=Provenance(
                                source_id="aedes_paho_dengue_surveillance",
                                locator=f"{raw_path}#regional_week_summary",
                                retrieved_at=retrieved_at,
                                license="PAHO/WHO public health surveillance page; source page terms apply",
                                source_url="https://ais.paho.org/example",
                            ),
                            payload={"aggregation_type": "regional_week_summary", "raw_html_path": raw_path.as_posix()},
                        )
                    ],
                    gaps=[
                        {
                            "source": "aedes_paho_dengue_surveillance",
                            "lane": "public_health",
                            "reason": "paho_dashboard_data_not_yet_cell_queryable",
                            "retrieved_at": retrieved_at,
                        }
                    ],
                    raw_artifacts=[raw_path.as_posix()],
                    requested_urls=["https://ais.paho.org/example"],
                    report_count=1,
                    dashboard_page_count=len(dashboard_pages),
                    core_indicator_page_count=len(core_indicator_pages),
                    core_indicator_download_count=0,
                    core_indicator_row_count=0,
                )

            response = dispatch_request(
                "POST",
                "/ingest/paho-dengue-surveillance",
                {
                    "report_urls": ["https://ais.paho.org/example"],
                    "dashboard_pages": ["https://www.paho.org/dashboard"],
                    "core_indicator_pages": [],
                },
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_paho_dengue_surveillance_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["aedes_paho_dengue_surveillance"], 1)
            self.assertFalse(response.payload["fully_parsed"])
            self.assertEqual(response.payload["aedes_paho_dengue_surveillance"]["dashboard_page_count"], 1)
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='aedes_paho_dengue_surveillance'",
            )
            self.assertIn(str(artifact_dir), provenance_rows[0]["provenance_json"])
            self.assertNotIn(".staging", provenance_rows[0]["provenance_json"])
            payload_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select payload_json from record_payloads where source='aedes_paho_dengue_surveillance'",
            )
            self.assertIn(str(artifact_dir), payload_rows[0]["payload_json"])
            self.assertNotIn(".staging", payload_rows[0]["payload_json"])

    def test_ingest_cdc_dengue_surveillance_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(sources, *, raw_dir, retrieved_at):
                raw_path = raw_dir / "cdc.csv"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text("Year,Travel status,Jurisdiction,Count\n2026,All,FL,14\n", encoding="utf-8")
                return CdcDengueSurveillanceResult(
                    source_id="aedes_cdc_dengue_surveillance",
                    records=[
                        EvidenceRecord(
                            record_id="public_health:surveillance:cdc_dengue:csv:Cases_by_Jurisdiction_Current.csv:row:000001:test",
                            lane="public_health",
                            source="aedes_cdc_dengue_surveillance",
                            title="CDC dengue surveillance CSV row",
                            text="CDC ArboNET dengue surveillance CSV row for Aedes aegypti.",
                            species="Aedes aegypti",
                            url="https://www.cdc.gov/wcms/vizdata/live/ncezid_dvbd/DEN/Cases_by_Jurisdiction_Current.csv",
                            media_url=None,
                            provenance=Provenance(
                                source_id="aedes_cdc_dengue_surveillance",
                                locator=f"{raw_path}#row/1",
                                retrieved_at=retrieved_at,
                                license="CDC public CSV data; source page terms apply",
                                source_url="https://www.cdc.gov/wcms/vizdata/live/ncezid_dvbd/DEN/Cases_by_Jurisdiction_Current.csv",
                            ),
                            payload={"aggregation_type": "cdc_dengue_csv_row", "raw_csv_path": raw_path.as_posix()},
                        )
                    ],
                    gaps=[],
                    raw_artifacts=[raw_path.as_posix()],
                    requested_urls=["https://www.cdc.gov/dengue/data-research/facts-stats/current-data.html"],
                    page_count=1,
                    config_count=1,
                    dataset_count=1,
                    dataset_row_count=1,
                    limitation_count=0,
                )

            response = dispatch_request(
                "POST",
                "/ingest/cdc-dengue-surveillance",
                {"source_urls": ["https://www.cdc.gov/dengue/data-research/facts-stats/current-data.html"]},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_cdc_dengue_surveillance_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["aedes_cdc_dengue_surveillance"], 1)
            self.assertEqual(response.payload["aedes_cdc_dengue_surveillance"]["dataset_row_count"], 1)
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='aedes_cdc_dengue_surveillance'",
            )
            self.assertIn(str(artifact_dir), provenance_rows[0]["provenance_json"])
            self.assertNotIn(".staging", provenance_rows[0]["provenance_json"])
            payload_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select payload_json from record_payloads where source='aedes_cdc_dengue_surveillance'",
            )
            self.assertIn(str(artifact_dir), payload_rows[0]["payload_json"])
            self.assertNotIn(".staging", payload_rows[0]["payload_json"])
            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["source_counts"]["aedes_cdc_dengue_surveillance"], 1)

    def test_ingest_who_dengue_surveillance_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(sources, *, raw_dir, retrieved_at):
                raw_path = raw_dir / "who.html"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text("<html>WHO dengue surveillance.</html>", encoding="utf-8")
                return WhoDengueSurveillanceResult(
                    source_id="aedes_who_dengue_surveillance",
                    records=[
                        EvidenceRecord(
                            record_id="public_health:surveillance:who_dengue:wer_global_update:test",
                            lane="public_health",
                            source="aedes_who_dengue_surveillance",
                            title="WHO WER dengue global update",
                            text="Official WHO dengue global situation, surveillance and progress update for Aedes aegypti public-health intelligence.",
                            species="Aedes aegypti",
                            url="https://www.who.int/publications/i/item/who-wer10052-665-678",
                            media_url=None,
                            provenance=Provenance(
                                source_id="aedes_who_dengue_surveillance",
                                locator=f"{raw_path}#page",
                                retrieved_at=retrieved_at,
                                license="WHO public page; source page terms apply",
                                source_url="https://www.who.int/publications/i/item/who-wer10052-665-678",
                            ),
                            payload={"page_kind": "wer_global_update", "raw_html_path": raw_path.as_posix()},
                        )
                    ],
                    gaps=[
                        {
                            "source": "aedes_who_dengue_surveillance",
                            "lane": "public_health",
                            "reason": "who_dengue_dashboard_export_not_machine_readable",
                            "retrieved_at": retrieved_at,
                        }
                    ],
                    raw_artifacts=[raw_path.as_posix()],
                    requested_urls=["https://www.who.int/publications/i/item/who-wer10052-665-678"],
                    page_count=1,
                    situation_report_count=0,
                    archive_count=0,
                    publication_count=0,
                    dashboard_locator_count=0,
                    export_locator_count=0,
                )

            response = dispatch_request(
                "POST",
                "/ingest/who-dengue-surveillance",
                {"source_urls": ["https://www.who.int/publications/i/item/who-wer10052-665-678"]},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_who_dengue_surveillance_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["aedes_who_dengue_surveillance"], 1)
            self.assertFalse(response.payload["fully_parsed"])
            self.assertEqual(response.payload["aedes_who_dengue_surveillance"]["page_count"], 1)
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='aedes_who_dengue_surveillance'",
            )
            self.assertIn(str(artifact_dir), provenance_rows[0]["provenance_json"])
            self.assertNotIn(".staging", provenance_rows[0]["provenance_json"])
            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["source_counts"]["aedes_who_dengue_surveillance"], 1)

    def test_ingest_ncvbdc_dengue_surveillance_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(sources, *, raw_dir, retrieved_at):
                raw_path = raw_dir / "ncvbdc.html"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text("<html>NCVBDC dengue surveillance.</html>", encoding="utf-8")
                return NcvbdcDengueSurveillanceResult(
                    source_id="aedes_ncvbdc_dengue_surveillance",
                    records=[
                        EvidenceRecord(
                            record_id="public_health:surveillance:ncvbdc_dengue:country:last_two_complete_years:2024-2025",
                            lane="public_health",
                            source="aedes_ncvbdc_dengue_surveillance",
                            title="NCVBDC India dengue deaths in the two latest complete years (2024-2025)",
                            text="Official NCVBDC India dengue surveillance summary. 2024: 297 deaths; 2025: 131 deaths. Total dengue deaths: 428.",
                            species="Aedes aegypti",
                            url="https://ncvbdc.mohfw.gov.in/index4.php?lang=1&level=0&lid=3715&linkid=431&theme=Green",
                            media_url=None,
                            provenance=Provenance(
                                source_id="aedes_ncvbdc_dengue_surveillance",
                                locator=f"{raw_path}#table-total-2024-2025",
                                retrieved_at=retrieved_at,
                                license="NCVBDC Government of India public web page; source page terms apply",
                                source_url="https://ncvbdc.mohfw.gov.in/index4.php?lang=1&level=0&lid=3715&linkid=431&theme=Green",
                            ),
                            payload={"aggregation_type": "ncvbdc_dengue_country_recent_complete_years", "total_deaths": 428, "raw_html_path": raw_path.as_posix()},
                        )
                    ],
                    gaps=[],
                    raw_artifacts=[raw_path.as_posix()],
                    requested_urls=["https://ncvbdc.mohfw.gov.in/index4.php?lang=1&level=0&lid=3715&linkid=431&theme=Green"],
                    page_count=1,
                    table_row_count=39,
                    state_year_record_count=213,
                    national_year_record_count=6,
                    recent_summary_count=1,
                )

            response = dispatch_request(
                "POST",
                "/ingest/ncvbdc-dengue-surveillance",
                {"source_urls": ["https://ncvbdc.mohfw.gov.in/index4.php?lang=1&level=0&lid=3715&linkid=431&theme=Green"]},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_ncvbdc_dengue_surveillance_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["aedes_ncvbdc_dengue_surveillance"], 1)
            self.assertEqual(response.payload["aedes_ncvbdc_dengue_surveillance"]["recent_summary_count"], 1)
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='aedes_ncvbdc_dengue_surveillance'",
            )
            self.assertIn(str(artifact_dir), provenance_rows[0]["provenance_json"])
            self.assertNotIn(".staging", provenance_rows[0]["provenance_json"])
            payload_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select payload_json from record_payloads where source='aedes_ncvbdc_dengue_surveillance'",
            )
            self.assertIn(str(artifact_dir), payload_rows[0]["payload_json"])
            self.assertNotIn(".staging", payload_rows[0]["payload_json"])
            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["source_counts"]["aedes_ncvbdc_dengue_surveillance"], 1)

    def test_ingest_opendatasus_dengue_surveillance_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(specs, *, raw_dir, retrieved_at):
                raw_path = raw_dir / "DENGBR25.csv.zip"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_bytes(b"fake zip")
                return OpenDataSusDengueSurveillanceResult(
                    source_id="aedes_opendatasus_dengue_surveillance",
                    records=[
                        EvidenceRecord(
                            record_id="public_health:surveillance:opendatasus_dengue:country:brazil:2025",
                            lane="public_health",
                            source="aedes_opendatasus_dengue_surveillance",
                            title="OpenDataSUS Brazil dengue surveillance summary, 2025",
                            text="Official Brazil OpenDataSUS SINAN dengue aggregate for 2025. Notifications: 3. Deaths coded as death by disease in EVOLUCAO=2: 1.",
                            species="Aedes aegypti",
                            url="https://opendatasus.example/DENGBR25.csv.zip",
                            media_url=None,
                            provenance=Provenance(
                                source_id="aedes_opendatasus_dengue_surveillance",
                                locator=f"{raw_path}#aggregate/country/Brazil/year/2025",
                                retrieved_at=retrieved_at,
                                license="Brazil Ministry of Health OpenDataSUS public open-data files; source portal terms apply",
                                source_url="https://opendatasus.example/DENGBR25.csv.zip",
                            ),
                            payload={
                                "aggregation_type": "opendatasus_dengue_country_year",
                                "country": "Brazil",
                                "year": 2025,
                                "raw_zip_path": raw_path.as_posix(),
                                "notifications": 3,
                                "deaths_by_disease": 1,
                            },
                        )
                    ],
                    gaps=[],
                    raw_artifacts=[raw_path.as_posix()],
                    requested_urls=["https://opendatasus.example/DENGBR25.csv.zip"],
                    file_count=1,
                    source_file_record_count=0,
                    country_year_record_count=1,
                    state_year_record_count=0,
                    country_week_record_count=0,
                    state_week_record_count=0,
                    row_count=3,
                    years=[2025],
                )

            response = dispatch_request(
                "POST",
                "/ingest/opendatasus-dengue-surveillance",
                {"years": [2025], "file_urls": ["https://opendatasus.example/DENGBR25.csv.zip"]},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_opendatasus_dengue_surveillance_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["aedes_opendatasus_dengue_surveillance"], 1)
            self.assertEqual(response.payload["aedes_opendatasus_dengue_surveillance"]["country_year_record_count"], 1)
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='aedes_opendatasus_dengue_surveillance'",
            )
            self.assertIn(str(artifact_dir), provenance_rows[0]["provenance_json"])
            self.assertNotIn(".staging", provenance_rows[0]["provenance_json"])
            payload_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select payload_json from record_payloads where source='aedes_opendatasus_dengue_surveillance'",
            )
            self.assertIn(str(artifact_dir), payload_rows[0]["payload_json"])
            self.assertNotIn(".staging", payload_rows[0]["payload_json"])
            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["source_counts"]["aedes_opendatasus_dengue_surveillance"], 1)

    def test_ingest_vectorbase_genomics_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(*, raw_dir, file_urls, retrieved_at):
                raw_path = raw_dir / "vectorbase.gff"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text("##gff-version 3\n", encoding="utf-8")
                return VectorBaseGenomicsResult(
                    source_id="vectorbase_aedes_genomics",
                    records=[
                        EvidenceRecord(
                            record_id="vectorbase:gene:AAEL000001",
                            lane="genes",
                            source="vectorbase_aedes_genomics",
                            title="Aedes aegypti VectorBase gene AAEL000001",
                            text="VectorBase gene AAEL000001 for Aedes aegypti.",
                            species="Aedes aegypti",
                            url="https://vectorbase.org/gff",
                            media_url=None,
                            provenance=Provenance(
                                source_id="vectorbase_aedes_genomics",
                                locator=f"{raw_path}#line/2",
                                retrieved_at=retrieved_at,
                                license="VectorBase/VEuPathDB public download; source terms apply",
                                source_url="https://vectorbase.org/gff",
                            ),
                            payload={"raw_path": raw_path.as_posix(), "gff_attributes": {"ID": "AAEL000001"}},
                        )
                    ],
                    gaps=[],
                    raw_artifacts=[raw_path.as_posix()],
                    requested_urls=["https://vectorbase.org/gff"],
                    release="Current_Release",
                    organism="AaegyptiLVP_AGWG",
                )

            rewrite_calls = []
            original_rewrite = server_module.rewrite_artifact_references

            def capture_rewrite(*args, **kwargs):
                rewrite_calls.append(kwargs.copy())
                return original_rewrite(*args, **kwargs)

            with mock.patch("askinsects.server.rewrite_artifact_references", side_effect=capture_rewrite):
                response = dispatch_request(
                    "POST",
                    "/ingest/vectorbase-genomics",
                    {"file_urls": {"gff": "https://vectorbase.org/gff"}},
                    headers={"Authorization": "Bearer secret"},
                    artifact_dir=artifact_dir,
                    token="secret",
                    fetch_vectorbase_genomics_records_fn=fake_fetch,
                )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["vectorbase_aedes_genomics"], 1)
            self.assertEqual(response.payload["vectorbase_genomics"]["release"], "Current_Release")
            self.assertTrue(response.payload["staged"])
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='vectorbase_aedes_genomics'",
            )
            self.assertIn(str(artifact_dir), provenance_rows[0]["provenance_json"])
            self.assertNotIn(".vectorbase-staging", provenance_rows[0]["provenance_json"])
            payload_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select payload_json from record_payloads where source='vectorbase_aedes_genomics'",
            )
            self.assertIn(str(artifact_dir), payload_rows[0]["payload_json"])
            self.assertNotIn(".vectorbase-staging", payload_rows[0]["payload_json"])
            self.assertEqual(rewrite_calls[0]["source"], "vectorbase_aedes_genomics")

    def test_ingest_vectorbase_genomics_failure_preserves_existing_source_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="vectorbase:gene:old",
                        lane="genes",
                        source="vectorbase_aedes_genomics",
                        title="Old VectorBase row",
                        text="Existing VectorBase row that must survive a failed refresh.",
                        species="Aedes aegypti",
                        url="https://vectorbase.org/old",
                        media_url=None,
                        provenance=Provenance(
                            source_id="vectorbase_aedes_genomics",
                            locator=f"{artifact_dir}/raw/vectorbase_genomics/old.gff#line/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                    )
                ]
            )

            def failing_fetch(*, raw_dir, file_urls, retrieved_at):
                raw_dir.mkdir(parents=True, exist_ok=True)
                (raw_dir / "partial.gff").write_text("partial\n", encoding="utf-8")
                raise RuntimeError("simulated vectorbase fetch failure")

            response = dispatch_request(
                "POST",
                "/ingest/vectorbase-genomics",
                {"file_urls": {"gff": "https://vectorbase.org/gff"}},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_vectorbase_genomics_records_fn=failing_fetch,
            )

            self.assertEqual(response.status, 500)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select record_id from records where source='vectorbase_aedes_genomics'",
            )
            self.assertEqual([row["record_id"] for row in rows], ["vectorbase:gene:old"])
            self.assertFalse((artifact_dir.parent / ".mosquito-v1.vectorbase-staging").exists())

    def test_ingest_mosquito_alert_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(*, raw_dir, occurrence_limit, occurrence_page_size, retrieved_at):
                raw_path = raw_dir / "aedes_aegypti_occurrences_offset_000000.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text('{"results":[]}', encoding="utf-8")
                return MosquitoAlertBuildResult(
                    source_id="mosquito_alert_gbif",
                    records=[
                        EvidenceRecord(
                            record_id="mosquito_alert:observation:4909387174",
                            lane="observations",
                            source="mosquito_alert_gbif",
                            title="Aedes aegypti Mosquito Alert observation 4909387174",
                            text="Mosquito Alert citizen-science observation of Aedes aegypti in Brazil with one still image.",
                            species="Aedes aegypti",
                            url="https://www.gbif.org/occurrence/4909387174",
                            media_url="http://webserver.mosquitoalert.com/media/tigapics/example.jpg",
                            provenance=Provenance(
                                source_id="mosquito_alert_gbif",
                                locator=f"{raw_path}#occurrence/4909387174",
                                retrieved_at=retrieved_at,
                                license="http://creativecommons.org/publicdomain/zero/1.0/legalcode",
                                source_url="https://www.gbif.org/occurrence/4909387174",
                            ),
                            payload={"raw_occurrence": {"key": 4909387174}},
                        )
                    ],
                    gaps=[],
                    raw_artifacts=[raw_path.as_posix()],
                    dataset_key="1fef1ead-3d02-495e-8ff1-6aeb01123408",
                    dataset_doi="10.15470/t5a1os",
                    taxon_key=1651891,
                    occurrence_limit=occurrence_limit,
                    occurrence_page_size=occurrence_page_size,
                    total_results=1,
                    page_count=1,
                )

            response = dispatch_request(
                "POST",
                "/ingest/mosquito-alert",
                {"occurrence_limit": 1, "occurrence_page_size": 1},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_mosquito_alert_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["mosquito_alert_gbif"], 1)
            payload_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select record_id from record_payloads where source='mosquito_alert_gbif'",
            )
            self.assertEqual(payload_rows[0]["record_id"], "mosquito_alert:observation:4909387174")
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='mosquito_alert_gbif'",
            )
            self.assertIn(str(artifact_dir), provenance_rows[0]["provenance_json"])
            self.assertNotIn(".staging", provenance_rows[0]["provenance_json"])

    def test_ingest_vectornet_surveillance_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(*, raw_dir, species, max_records, retrieved_at):
                raw_path = raw_dir / "dwca-vndatabase-v1.3.zip"
                filtered_path = raw_dir / "vectornet_aedes_aegypti_occurrence_rows.tsv"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_bytes(b"fake zip")
                filtered_path.write_text("source_row_number\tid\n2\tVNET-1\n", encoding="utf-8")
                return VectorNetBuildResult(
                    source_id="vectornet_aedes_surveillance",
                    records=[
                        EvidenceRecord(
                            record_id="vectornet:observation:VNET_1",
                            lane="observations",
                            source="vectornet_aedes_surveillance",
                            title="VectorNet Aedes aegypti surveillance row VNET-1",
                            text="Official VectorNet ECDC/EFSA surveillance occurrence row for Aedes aegypti in Georgia.",
                            species=species,
                            url="https://ipt.gbif.org/resource?r=vndatabase#occurrence/VNET-1",
                            media_url=None,
                            provenance=Provenance(
                                source_id="vectornet_aedes_surveillance",
                                locator=f"{raw_path}#occurrence.txt/row/2;{filtered_path}#row/2",
                                retrieved_at=retrieved_at,
                                license="CC-BY-4.0",
                                source_url="https://ipt.gbif.org/archive.do?r=vndatabase",
                            ),
                            payload={"raw_occurrence": {"id": "VNET-1"}, "presence_bucket": "detection_or_presence_evidence"},
                        ),
                        EvidenceRecord(
                            record_id="vectornet:ecology:country_Georgia",
                            lane="ecology",
                            source="vectornet_aedes_surveillance",
                            title="VectorNet Aedes aegypti regional surveillance summary: country:Georgia",
                            text="VectorNet ECDC/EFSA has 1 Aedes aegypti surveillance row for country:Georgia.",
                            species=species,
                            url="https://ipt.gbif.org/resource?r=vndatabase",
                            media_url=None,
                            provenance=Provenance(
                                source_id="vectornet_aedes_surveillance",
                                locator=f"{filtered_path}#summary/country_Georgia",
                                retrieved_at=retrieved_at,
                                license="CC-BY-4.0",
                                source_url="https://ipt.gbif.org/resource?r=vndatabase",
                            ),
                            payload={"summary_key": "country:Georgia"},
                        ),
                    ],
                    gaps=[],
                    raw_artifacts=[raw_path.as_posix(), filtered_path.as_posix()],
                    dataset_key="7a5757c3-58f8-4ff6-9662-32296965a2f3",
                    dataset_title="VectorNet",
                    species=species,
                    archive_url="https://ipt.gbif.org/archive.do?r=vndatabase",
                    resource_url="https://ipt.gbif.org/resource?r=vndatabase",
                    row_count=3,
                    matched_row_count=1,
                    observation_record_count=1,
                    ecology_record_count=1,
                    filtered_rows_path=filtered_path.as_posix(),
                    pub_date="2025-02-05",
                    license="CC-BY-4.0",
                )

            response = dispatch_request(
                "POST",
                "/ingest/vectornet-surveillance",
                {"species": "Aedes aegypti"},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_vectornet_surveillance_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["vectornet_aedes_surveillance"], 2)
            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["source_counts"]["vectornet_aedes_surveillance"], 2)
            self.assertEqual(response.payload["vectornet_surveillance"]["matched_row_count"], 1)
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='vectornet_aedes_surveillance'",
            )
            self.assertIn(str(artifact_dir), provenance_rows[0]["provenance_json"])
            self.assertNotIn("raw-staging", provenance_rows[0]["provenance_json"])
            self.assertTrue((artifact_dir / "raw" / "vectornet_surveillance" / "dwca-vndatabase-v1.3.zip").exists())

    def test_ingest_dryad_behavior_videos_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(*args, raw_dir, retrieved_at):
                raw_path = raw_dir / "10_5061_dryad_example_files.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text('{"_embedded":{"stash:files":[]}}', encoding="utf-8")
                return DryadBehaviorVideoResult(
                    source_id="dryad_aedes_behavior_videos",
                    records=[
                        EvidenceRecord(
                            record_id="dryad:file:10_5061_dryad_example:host_seeking_videos_zip",
                            lane="media",
                            source="dryad_aedes_behavior_videos",
                            title="Aedes aegypti Dryad video/archive file host_seeking_videos.zip",
                            text="Dryad video archive for Aedes aegypti host seeking behavior.",
                            species="Aedes aegypti",
                            url="https://datadryad.org/dataset/doi%3A10.5061%2Fdryad.example",
                            media_url="https://datadryad.org/api/v2/files/10/download",
                            provenance=Provenance(
                                source_id="dryad_aedes_behavior_videos",
                                locator=f"{raw_path}#file/1",
                                retrieved_at=retrieved_at,
                                license="https://spdx.org/licenses/CC0-1.0.html",
                                source_url="https://datadryad.org/api/v2/files/10/download",
                            ),
                            payload={"raw_file": {"path": "host_seeking_videos.zip"}},
                        )
                    ],
                    gaps=[],
                    raw_artifacts=[raw_path.as_posix()],
                    requested_dois=["10.5061/dryad.example"],
                    dataset_count=1,
                    file_count=1,
                    media_file_count=1,
                    landing_page_count=1,
                    assay_method_count=2,
                )

            response = dispatch_request(
                "POST",
                "/ingest/dryad-behavior-videos",
                {"dois": ["10.5061/dryad.example"]},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_dryad_behavior_video_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["dryad_aedes_behavior_videos"], 1)
            payload_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select record_id from record_payloads where source='dryad_aedes_behavior_videos'",
            )
            self.assertEqual(payload_rows[0]["record_id"], "dryad:file:10_5061_dryad_example:host_seeking_videos_zip")
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='dryad_aedes_behavior_videos'",
            )
            self.assertIn(str(artifact_dir), provenance_rows[0]["provenance_json"])
            self.assertNotIn(".staging", provenance_rows[0]["provenance_json"])
            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["source_counts"]["dryad_aedes_behavior_videos"], 1)
            self.assertEqual(receipt["dryad_behavior_videos"]["landing_page_count"], 1)
            self.assertEqual(receipt["dryad_behavior_videos"]["assay_method_count"], 2)
            self.assertEqual(status["source_counts"]["dryad_aedes_behavior_videos"], 1)
            self.assertEqual(status["dryad_behavior_videos"]["landing_page_count"], 1)
            self.assertEqual(status["dryad_behavior_videos"]["assay_method_count"], 2)

    def test_ingest_mendeley_behavior_media_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(*args, raw_dir, retrieved_at):
                raw_path = raw_dir / "6gvs94p6r2_v1_files.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text("[]", encoding="utf-8")
                return MendeleyBehaviorMediaResult(
                    source_id="mendeley_aedes_behavior_media",
                    records=[
                        EvidenceRecord(
                            record_id="mendeley:file:6gvs94p6r2:v1:file_video",
                            lane="media",
                            source="mendeley_aedes_behavior_media",
                            title="Aedes aegypti Mendeley video/audio/archive file wing-flash-video.mp4",
                            text="Mendeley video archive for Aedes aegypti wing flash behavior.",
                            species="Aedes aegypti",
                            url="https://data.mendeley.com/datasets/6gvs94p6r2/1",
                            media_url="https://data.mendeley.com/public-files/video/file_downloaded",
                            provenance=Provenance(
                                source_id="mendeley_aedes_behavior_media",
                                locator=f"{raw_path}#files/root/1",
                                retrieved_at=retrieved_at,
                                license="CC BY 4.0",
                                source_url="https://data.mendeley.com/public-files/video/file_downloaded",
                            ),
                            payload={"filename": "wing-flash-video.mp4"},
                        )
                    ],
                    gaps=[],
                    raw_artifacts=[raw_path.as_posix()],
                    requested_datasets=["6gvs94p6r2:v1"],
                    dataset_count=1,
                    folder_count=0,
                    file_count=1,
                    media_file_count=1,
                )

            response = dispatch_request(
                "POST",
                "/ingest/mendeley-behavior-media",
                {"datasets": ["6gvs94p6r2:1"]},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_mendeley_behavior_media_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["mendeley_aedes_behavior_media"], 1)
            payload_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select record_id from record_payloads where source='mendeley_aedes_behavior_media'",
            )
            self.assertEqual(payload_rows[0]["record_id"], "mendeley:file:6gvs94p6r2:v1:file_video")
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='mendeley_aedes_behavior_media'",
            )
            self.assertIn(str(artifact_dir), provenance_rows[0]["provenance_json"])
            self.assertNotIn(".staging", provenance_rows[0]["provenance_json"])

    def test_ingest_osf_flighttrackai_videos_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(*, raw_dir, retrieved_at):
                raw_path = raw_dir / "cx762_osfstorage_root.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text('{"data":[]}', encoding="utf-8")
                return OSFFlightTrackAIResult(
                    source_id="osf_flighttrackai_aedes_videos",
                    records=[
                        EvidenceRecord(
                            record_id="osf:flighttrackai:file:video_a",
                            lane="media",
                            source="osf_flighttrackai_aedes_videos",
                            title="Aedes aegypti OSF FlightTrackAI video file Video A.mp4",
                            text="OSF FlightTrackAI video file for Aedes aegypti flight-behavior tracking.",
                            species="Aedes aegypti",
                            url="https://osf.io/cx762/",
                            media_url="https://osf.io/download/pu8zf/",
                            provenance=Provenance(
                                source_id="osf_flighttrackai_aedes_videos",
                                locator=f"{raw_path}#files/1",
                                retrieved_at=retrieved_at,
                                license="OSF project license not supplied",
                                source_url="https://api.osf.io/v2/files/video-a/",
                            ),
                            payload={"name": "Video A.mp4"},
                        )
                    ],
                    gaps=[],
                    raw_artifacts=[raw_path.as_posix()],
                    project_id="cx762",
                    folder_count=1,
                    file_count=1,
                    media_file_count=1,
                    software_file_count=0,
                )

            response = dispatch_request(
                "POST",
                "/ingest/osf-flighttrackai-videos",
                {},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_osf_flighttrackai_video_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["osf_flighttrackai_aedes_videos"], 1)
            payload_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select record_id from record_payloads where source='osf_flighttrackai_aedes_videos'",
            )
            self.assertEqual(payload_rows[0]["record_id"], "osf:flighttrackai:file:video_a")
            self.assertEqual(response.payload["media_file_count"], 1)

    def test_ingest_pmc_videos_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(*, article_urls, raw_dir, retrieved_at):
                raw_path = raw_dir / "PMC123.html"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text("<html>video</html>", encoding="utf-8")
                return PMCVideosResult(
                    source_id="pmc_open_access_videos",
                    records=[
                        EvidenceRecord(
                            record_id="pmc:video:PMC123:video1.mp4",
                            lane="media",
                            source="pmc_open_access_videos",
                            title="Aedes aegypti PMC supplementary video video1.mp4",
                            text="PMC Aedes aegypti supplementary video.",
                            species="Aedes aegypti",
                            url=article_urls[0],
                            media_url="https://cdn.ncbi.nlm.nih.gov/pmc/blobs/example/video1.mp4",
                            provenance=Provenance(
                                source_id="pmc_open_access_videos",
                                locator=f"{raw_path}#video/1",
                                retrieved_at=retrieved_at,
                                license="Creative Commons Attribution License",
                                source_url=article_urls[0],
                            ),
                            payload={"filename": "video1.mp4", "raw_html": raw_path.as_posix()},
                        )
                    ],
                    gaps=[],
                    raw_artifacts=[raw_path.as_posix()],
                    article_count=1,
                    video_count=1,
                )

            response = dispatch_request(
                "POST",
                "/ingest/pmc-videos",
                {"article_urls": ["https://pmc.ncbi.nlm.nih.gov/articles/PMC123/"], "retrieved_at": RETRIEVED_AT},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_pmc_video_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["pmc_open_access_videos"], 1)
            self.assertEqual(response.payload["video_count"], 1)

    def test_ingest_zenodo_aedes_videos_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(*, raw_dir, retrieved_at, query, size):
                raw_path = raw_dir / "search_fixture.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text('{"hits":{"hits":[]}}', encoding="utf-8")
                return ZenodoAedesVideoResult(
                    source_id="zenodo_aedes_videos",
                    records=[
                        EvidenceRecord(
                            record_id="zenodo:aedes-video:101:oviposition_mp4",
                            lane="media",
                            source="zenodo_aedes_videos",
                            title="Aedes aegypti Zenodo video file oviposition.mp4",
                            text="Zenodo video file for Aedes aegypti oviposition behavior.",
                            species="Aedes aegypti",
                            url="https://zenodo.org/records/101",
                            media_url="https://zenodo.org/api/records/101/files/oviposition.mp4/content",
                            provenance=Provenance(
                                source_id="zenodo_aedes_videos",
                                locator=f"{raw_path}#hits/1/files/1",
                                retrieved_at=retrieved_at,
                                license="cc-by-4.0",
                                source_url="https://zenodo.org/api/records/101/files/oviposition.mp4/content",
                            ),
                            payload={"filename": "oviposition.mp4", "source_byte_size": 123456},
                        )
                    ],
                    gaps=[],
                    raw_artifacts=[raw_path.as_posix()],
                    query=query,
                    search_result_count=1,
                    material_record_count=1,
                    file_count=1,
                    media_file_count=1,
                )

            response = dispatch_request(
                "POST",
                "/ingest/zenodo-aedes-videos",
                {"query": '"Aedes aegypti" mp4', "size": 7},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_zenodo_aedes_video_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["zenodo_aedes_videos"], 1)
            self.assertEqual(response.payload["query"], '"Aedes aegypti" mp4')
            self.assertEqual(response.payload["media_file_count"], 1)

    def test_ingest_figshare_aedes_videos_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(*, raw_dir, retrieved_at, query, page_size):
                raw_path = raw_dir / "article_101.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text('{"id":101,"files":[]}', encoding="utf-8")
                return FigshareAedesVideoResult(
                    source_id="figshare_aedes_videos",
                    records=[
                        EvidenceRecord(
                            record_id="figshare:aedes-video:101:oviposition_mp4",
                            lane="media",
                            source="figshare_aedes_videos",
                            title="Aedes aegypti Figshare video file oviposition.mp4",
                            text="Figshare video file for Aedes aegypti oviposition behavior.",
                            species="Aedes aegypti",
                            url="https://figshare.com/articles/dataset/101",
                            media_url="https://ndownloader.figshare.com/files/202",
                            provenance=Provenance(
                                source_id="figshare_aedes_videos",
                                locator=f"{raw_path}#files/1",
                                retrieved_at=retrieved_at,
                                license="CC BY 4.0",
                                source_url="https://ndownloader.figshare.com/files/202",
                            ),
                            payload={"filename": "oviposition.mp4", "source_byte_size": 123456},
                        )
                    ],
                    gaps=[],
                    raw_artifacts=[raw_path.as_posix()],
                    query=query,
                    search_result_count=1,
                    material_record_count=1,
                    file_count=1,
                    media_file_count=1,
                )

            response = dispatch_request(
                "POST",
                "/ingest/figshare-aedes-videos",
                {"query": "Aedes aegypti mp4", "page_size": 7},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_figshare_aedes_video_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["figshare_aedes_videos"], 1)
            self.assertEqual(response.payload["query"], "Aedes aegypti mp4")
            self.assertEqual(response.payload["media_file_count"], 1)

    def test_ingest_pathogen_taxonomy_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(*, raw_dir, retrieved_at):
                raw_path = raw_dir / "aedes_pathogen_taxonomy_esummary.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text('{"result":{}}', encoding="utf-8")
                return PathogenTaxonomyResult(
                    source_id="aedes_pathogen_taxonomy",
                    records=[
                        EvidenceRecord(
                            record_id="pathogen:ncbi_taxonomy:64320",
                            lane="vector_competence",
                            source="aedes_pathogen_taxonomy",
                            title="Aedes aegypti pathogen taxonomy Zika virus",
                            text="NCBI Taxonomy pathogen record for Zika virus.",
                            species="Aedes aegypti",
                            url="https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=64320",
                            media_url=None,
                            provenance=Provenance(
                                source_id="aedes_pathogen_taxonomy",
                                locator=f"{raw_path}#taxonomy/64320",
                                retrieved_at=retrieved_at,
                                license="NCBI Taxonomy public data; NCBI terms apply",
                                source_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                            ),
                            payload={"raw_summary": {"scientificname": "Zika virus"}},
                        )
                    ],
                    gaps=[],
                    raw_artifacts=[raw_path.as_posix()],
                    requested_taxids=[64320],
                    pathogen_count=1,
                )

            response = dispatch_request(
                "POST",
                "/ingest/pathogen-taxonomy",
                {},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_pathogen_taxonomy_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["aedes_pathogen_taxonomy"], 1)
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='aedes_pathogen_taxonomy'",
            )
            self.assertIn(str(artifact_dir), provenance_rows[0]["provenance_json"])
            self.assertNotIn(".staging", provenance_rows[0]["provenance_json"])

    def test_ingest_ncbi_biosamples_adds_records_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(*, raw_dir, species, limit, page_size, delay_seconds, fetch_json, retrieved_at):
                raw_path = raw_dir / "Aedes_aegypti_esummary_000000.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text('{"result":{}}', encoding="utf-8")
                return NCBIBioSampleResult(
                    source_id="ncbi_biosamples",
                    records=[
                        EvidenceRecord(
                            record_id="ncbi:biosample:SAMN1",
                            lane="biosamples",
                            source="ncbi_biosamples",
                            title="Aedes aegypti BioSample SAMN1",
                            text="NCBI BioSample SAMN1 for Aedes aegypti. Sample name: Rockefeller.",
                            species="Aedes aegypti",
                            url="https://www.ncbi.nlm.nih.gov/biosample/SAMN1",
                            media_url=None,
                            provenance=Provenance(
                                source_id="ncbi_biosamples",
                                locator=f"{raw_path}#uid/1",
                                retrieved_at=retrieved_at,
                                license="NCBI BioSample public metadata; NCBI terms apply",
                                source_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                            ),
                            payload={"accession": "SAMN1"},
                        )
                    ],
                    gaps=[],
                    raw_artifacts=[raw_path.as_posix()],
                    species=species,
                    total_count=1,
                    requested_limit=limit,
                    fetched_count=1,
                    page_count=1,
                )

            response = dispatch_request(
                "POST",
                "/ingest/ncbi-biosamples",
                {"species": "Aedes aegypti", "limit": 1, "page_size": 1, "delay_seconds": 0},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_ncbi_biosample_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["ncbi_biosamples"], 1)
            self.assertTrue(response.payload["staged"])
            self.assertEqual(response.payload["activated_artifact_dir"], str(artifact_dir))
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='ncbi_biosamples'",
            )
            self.assertIn(str(artifact_dir), provenance_rows[0]["provenance_json"])
            self.assertNotIn(".ncbi-biosamples-staging", provenance_rows[0]["provenance_json"])

    def test_ingest_ncbi_biosamples_failure_preserves_existing_source_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="ncbi:biosample:old",
                        lane="biosamples",
                        source="ncbi_biosamples",
                        title="Old BioSample row",
                        text="Existing BioSample row that must survive a failed refresh.",
                        species="Aedes aegypti",
                        url="https://www.ncbi.nlm.nih.gov/biosample/old",
                        media_url=None,
                        provenance=Provenance(
                            source_id="ncbi_biosamples",
                            locator=f"{artifact_dir}/raw/ncbi_biosamples/old.json#uid/old",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                    )
                ]
            )

            def failing_fetch(*, raw_dir, species, limit, page_size, delay_seconds, fetch_json, retrieved_at):
                raw_dir.mkdir(parents=True, exist_ok=True)
                (raw_dir / "partial.json").write_text("{}", encoding="utf-8")
                raise RuntimeError("simulated biosample fetch failure")

            response = dispatch_request(
                "POST",
                "/ingest/ncbi-biosamples",
                {"species": "Aedes aegypti", "limit": 1, "page_size": 1, "delay_seconds": 0},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_ncbi_biosample_records_fn=failing_fetch,
            )

            self.assertEqual(response.status, 500)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select record_id from records where source='ncbi_biosamples'",
            )
            self.assertEqual([row["record_id"] for row in rows], ["ncbi:biosample:old"])
            self.assertFalse((artifact_dir.parent / ".mosquito-v1.ncbi-biosamples-staging").exists())

    def test_ingest_ncbi_snp_variation_adds_gap_record_without_removing_existing_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(*, raw_dir, species, limit, page_size, delay_seconds, fetch_json, retrieved_at):
                raw_path = raw_dir / "Aedes_aegypti_snp_esearch_000000.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text('{"esearchresult":{"count":"0","idlist":[]}}', encoding="utf-8")
                return NCBISnpVariationResult(
                    source_id="aedes_ncbi_snp_variation",
                    records=[
                        EvidenceRecord(
                            record_id="ncbi_snp_variation:gap:aedes_aegypti:ncbi_snp_no_aedes_records",
                            lane="genome_features",
                            source="aedes_ncbi_snp_variation",
                            title="Aedes aegypti NCBI dbSNP variation source gap",
                            text="NCBI dbSNP returned zero records for Aedes aegypti.",
                            species="Aedes aegypti",
                            url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                            media_url=None,
                            provenance=Provenance(
                                source_id="aedes_ncbi_snp_variation",
                                locator=f"{raw_path}#gap/ncbi_snp_no_aedes_records",
                                retrieved_at=retrieved_at,
                                license="NCBI dbSNP public metadata; NCBI terms apply",
                                source_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                            ),
                            payload={"gap": {"reason": "ncbi_snp_no_aedes_records"}},
                        )
                    ],
                    gaps=[{"source": "aedes_ncbi_snp_variation", "reason": "ncbi_snp_no_aedes_records"}],
                    raw_artifacts=[raw_path.as_posix()],
                    species=species,
                    total_count=0,
                    requested_limit=limit,
                    fetched_count=0,
                    page_count=1,
                )

            response = dispatch_request(
                "POST",
                "/ingest/ncbi-snp-variation",
                {"species": "Aedes aegypti", "limit": 1, "page_size": 1, "delay_seconds": 0},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
                fetch_ncbi_snp_variation_records_fn=fake_fetch,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["aedes_ncbi_snp_variation"], 1)
            self.assertTrue(response.payload["staged"])
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='aedes_ncbi_snp_variation'",
            )
            self.assertIn(str(artifact_dir), provenance_rows[0]["provenance_json"])
            self.assertNotIn(".ncbi-snp-variation-staging", provenance_rows[0]["provenance_json"])

    def test_ingest_vector_competence_assays_adds_records_without_removing_existing_sources(self):
        from tests.test_vector_competence_assays_source import write_assay_literature_fixture

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            write_assay_literature_fixture(artifact_dir)

            response = dispatch_request(
                "POST",
                "/ingest/vector-competence-assays",
                {},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["aedes_vector_competence_assays"], 1)
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='aedes_vector_competence_assays'",
            )
            self.assertIn("literature_fulltext_units#openalex:WVC1:fulltext:0", provenance_rows[0]["provenance_json"])

    def test_ingest_resistance_markers_adds_records_without_removing_existing_sources(self):
        from tests.test_resistance_markers_source import write_resistance_marker_fixture

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            write_resistance_marker_fixture(artifact_dir)

            response = dispatch_request(
                "POST",
                "/ingest/resistance-markers",
                {},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertGreaterEqual(counts["aedes_resistance_markers"], 3)
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='aedes_resistance_markers'",
            )
            self.assertIn("literature_fulltext_units#openalex:WRM1:fulltext:0", provenance_rows[0]["provenance_json"])

    def test_ingest_resistance_table_rows_adds_records_without_removing_existing_sources(self):
        from tests.test_resistance_table_rows_source import write_resistance_table_fixture

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            write_resistance_table_fixture(artifact_dir)

            response = dispatch_request(
                "POST",
                "/ingest/resistance-table-rows",
                {},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["aedes_resistance_table_rows"], 1)
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='aedes_resistance_table_rows'",
            )
            self.assertIn("aedes_extracted_facts#extracted_fact:resistance:openalex:WRTABLE1:row7", provenance_rows[0]["provenance_json"])

    def test_ingest_extracted_facts_adds_cross_lane_records_without_removing_existing_sources(self):
        from tests.test_extracted_facts_source import write_extracted_facts_fixture

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            write_extracted_facts_fixture(artifact_dir)

            response = dispatch_request(
                "POST",
                "/ingest/extracted-facts",
                {},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertTrue(response.payload["staged"])
            self.assertEqual(response.payload["selected_fulltext_unit_count"], 1)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, lane, count(*) as n from records group by source, lane")
            counts = {(row["source"], row["lane"]): row["n"] for row in rows}
            self.assertGreaterEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 1)
            self.assertGreaterEqual(counts[("aedes_extracted_facts", "vector_competence")], 1)
            self.assertGreaterEqual(counts[("aedes_extracted_facts", "public_health")], 1)
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='aedes_extracted_facts' and lane='vector_competence'",
            )
            self.assertIn("literature_fulltext_units#openalex:WFACT1:fulltext:0", provenance_rows[0]["provenance_json"])
            self.assertNotIn(".extracted-facts-staging", provenance_rows[0]["provenance_json"])
            self.assertFalse((artifact_dir.parent / ".mosquito-v1.extracted-facts-staging").exists())

    def test_ingest_extracted_facts_rejects_invalid_supplement_limits(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            response = dispatch_request(
                "POST",
                "/ingest/extracted-facts",
                {"max_supplement_files": 0},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
            )

            self.assertEqual(response.status, 400)
            self.assertIn("max_supplement_files must be positive", response.payload["error"])

            response = dispatch_request(
                "POST",
                "/ingest/extracted-facts",
                {"max_supplement_discovery_records": 0},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
            )

            self.assertEqual(response.status, 400)
            self.assertIn("max_supplement_discovery_records must be positive", response.payload["error"])

            response = dispatch_request(
                "POST",
                "/ingest/extracted-facts",
                {"source_record_ids": "openalex:WFACT1"},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
            )

            self.assertEqual(response.status, 400)
            self.assertIn("source_record_ids must be a list", response.payload["error"])

            response = dispatch_request(
                "POST",
                "/ingest/extracted-facts",
                {"merge_existing": True},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
            )

            self.assertEqual(response.status, 400)
            self.assertIn("merge_existing requires at least one source_record_id", response.payload["error"])

    def test_ingest_video_atoms_adds_records_without_removing_existing_sources(self):
        from tests.test_video_atoms_source import write_video_fixture

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            write_video_fixture(artifact_dir)

            response = dispatch_request(
                "POST",
                "/ingest/video-atoms",
                {"max_video_bytes": 100, "mirror_videos": False},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertTrue(response.payload["staged"])
            self.assertEqual(response.payload["video_asset_count"], 2)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, lane, count(*) as n from records group by source, lane")
            counts = {(row["source"], row["lane"]): row["n"] for row in rows}
            self.assertGreaterEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 1)
            self.assertEqual(counts[("aedes_video_atoms", "media")], 2)
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='aedes_video_atoms'",
            )
            provenance_json = "\n".join(str(row["provenance_json"]) for row in provenance_rows)
            self.assertIn("records#pmc:video:PMC123:video1.mp4", provenance_json)
            self.assertNotIn(".video-atoms-staging", provenance_json)
            self.assertFalse((artifact_dir.parent / ".mosquito-v1.video-atoms-staging").exists())

    def test_ingest_video_atoms_rejects_scoped_refresh_without_merge(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            response = dispatch_request(
                "POST",
                "/ingest/video-atoms",
                {"discover_sources": True, "discovery_repositories": ["dryad"]},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
            )

            self.assertEqual(response.status, 400)
            self.assertIn("discovery_repositories requires merge_existing", response.payload["error"])

    def test_video_atom_scoped_merge_refresh_updates_in_place_without_staging_copy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            fake_result = {
                "ok": True,
                "source": "aedes_video_atoms",
                "record_count": 1,
                "discovery_repositories": ["institutional"],
            }
            with (
                mock.patch("askinsects.server.prepare_mutable_staging", side_effect=AssertionError("should not stage-copy scoped refresh")),
                mock.patch("scripts.ingest_video_atoms.ingest_video_atoms", return_value=fake_result) as ingest,
            ):
                response = ingest_video_atoms_staged(
                    {
                        "discover_sources": True,
                        "discovery_repositories": ["institutional"],
                        "merge_existing": True,
                        "parse_motion_rows": False,
                    },
                    artifact_dir=artifact_dir,
                )

            self.assertTrue(response["ok"])
            self.assertFalse(response["staged"])
            self.assertTrue(response["updated_in_place"])
            self.assertEqual(response["activated_artifact_dir"], str(artifact_dir))
            self.assertFalse((artifact_dir.parent / ".mosquito-v1.video-atoms-staging").exists())
            self.assertEqual(ingest.call_args.kwargs["artifact_dir"], artifact_dir)
            self.assertEqual(ingest.call_args.kwargs["discovery_repositories"], ["institutional"])
            self.assertTrue(ingest.call_args.kwargs["merge_existing"])
            self.assertFalse(ingest.call_args.kwargs["parse_motion_rows"])

    def test_ingest_occurrence_ecology_adds_records_without_removing_existing_sources(self):
        from tests.test_occurrence_ecology_source import write_occurrence_ecology_fixture

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            write_occurrence_ecology_fixture(artifact_dir)

            response = dispatch_request(
                "POST",
                "/ingest/occurrence-ecology",
                {},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["aedes_occurrence_ecology"], 7)
            payload_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select payload_json from record_payloads where source='aedes_occurrence_ecology' and record_id='occurrence_ecology:country:Brazil'",
            )
            self.assertIn('"observation_count": 3', payload_rows[0]["payload_json"])

    def test_ingest_drosophila_suzukii_occurrence_ecology_adds_records_without_removing_existing_sources(self):
        from tests.test_drosophila_suzukii_occurrence_ecology import write_swd_occurrence_ecology_fixture

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            write_swd_occurrence_ecology_fixture(artifact_dir)

            response = dispatch_request(
                "POST",
                "/ingest/drosophila-suzukii-occurrence-ecology",
                {},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["drosophila_suzukii_occurrence_ecology"], 5)
            payload_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select payload_json from record_payloads where source='drosophila_suzukii_occurrence_ecology' and record_id='swd_occurrence_ecology:country:United_States_of_America'",
            )
            self.assertIn('"observation_count": 3', payload_rows[0]["payload_json"])

    def test_ingest_observation_climate_join_adds_records_without_removing_existing_sources(self):
        from askinsects.sources.observation_climate import OBSERVATION_CLIMATE_SOURCE_ID
        from tests.test_observation_climate_source import write_observation_climate_fixture

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            write_observation_climate_fixture(artifact_dir)

            response = dispatch_request(
                "POST",
                "/ingest/observation-climate-join",
                {"limit": 10},
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts[OBSERVATION_CLIMATE_SOURCE_ID], 2)
            payload_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                f"select payload_json from record_payloads where source='{OBSERVATION_CLIMATE_SOURCE_ID}' order by record_id limit 1",
            )
            self.assertIn('"bio1_annual_mean_temperature_c": 24.0', payload_rows[0]["payload_json"])

if __name__ == "__main__":
    unittest.main()
