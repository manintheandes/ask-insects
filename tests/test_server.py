import tempfile
import unittest
from pathlib import Path
from unittest import mock

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.server import dispatch_request
from askinsects.sources.gbif import GBIFBuildResult
from askinsects.sources.inaturalist import INaturalistBuildResult
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

    def test_ingest_inaturalist_uses_staging_then_activates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch(*args, **kwargs):
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


if __name__ == "__main__":
    unittest.main()
