import tempfile
import unittest
from pathlib import Path
from unittest import mock

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.server import activate_source_staging, copy_artifact_to_staging, dispatch_request, prepare_mutable_staging
from askinsects.sources.dryad_behavior_videos import DryadBehaviorVideoResult
from askinsects.sources.gbif import GBIFBuildResult
from askinsects.sources.inaturalist import INaturalistBuildResult
from askinsects.sources.irmapper import IRMapperBuildResult
from askinsects.sources.literature import FullTextUnit
from askinsects.sources.mosquito_alert import MosquitoAlertBuildResult
from askinsects.sources.ncbi_biosample import NCBIBioSampleResult
from askinsects.sources.pathogen_taxonomy import PathogenTaxonomyResult
from askinsects.sources.public_health import PublicHealthGuidanceResult
from tests.test_inaturalist_source import observation


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

    def test_staging_copy_hardlinks_raw_files_but_copies_mutable_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "mosquito-v1"
            raw_dir = artifact_dir / "raw" / "large_source"
            raw_dir.mkdir(parents=True)
            (artifact_dir / "source_index.sqlite").write_text("mutable-db", encoding="utf-8")
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
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["irmapper_aedes"], 1)
            provenance_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select provenance_json from records where source='irmapper_aedes'",
            )
            self.assertIn(str(artifact_dir), provenance_rows[0]["provenance_json"])
            self.assertNotIn(".staging", provenance_rows[0]["provenance_json"])

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


if __name__ == "__main__":
    unittest.main()
