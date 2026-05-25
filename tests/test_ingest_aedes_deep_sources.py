import json
import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.aedes_deep_sources import AEDES_TAXONOMY_AUTHORITIES_SOURCE_ID
from scripts.ingest_aedes_deep_sources import ingest_aedes_deep_sources


class IngestAedesDeepSourcesTests(unittest.TestCase):
    def test_ingest_updates_all_five_sources_without_removing_existing_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="fixture:taxon:aedes",
                        lane="taxonomy",
                        source="mosquito_v1_fixtures",
                        title="Aedes aegypti",
                        text="Seed record",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="mosquito_v1_fixtures",
                            locator="fixture#line/1",
                            retrieved_at="2026-05-23T00:00:00Z",
                        ),
                    )
                ]
            )

            def fake_result(raw_dir, fetch_text, fetch_json, fetch_bytes, retrieved_at, compendium_row_limit, bioproject_limit, worldclim_sample_limit):
                return type(
                    "Result",
                    (),
                    {
                        "source_ids": (
                            AEDES_TAXONOMY_AUTHORITIES_SOURCE_ID,
                            "aedes_worldclim_climate",
                            "aedes_global_compendium_occurrence",
                            "aedes_population_genomics",
                            "aedes_who_resistance_guidance",
                        ),
                        "records": [
                            EvidenceRecord(
                                record_id="taxonomy:authority:aedes_aegypti",
                                lane="taxonomy",
                                source=AEDES_TAXONOMY_AUTHORITIES_SOURCE_ID,
                                title="Aedes taxonomy",
                                text="Aedes (Stegomyia) aegypti authoritative taxonomy.",
                                species="Aedes aegypti",
                                url="https://example.org/taxonomy",
                                media_url=None,
                                provenance=Provenance(
                                    source_id=AEDES_TAXONOMY_AUTHORITIES_SOURCE_ID,
                                    locator="raw/taxonomy.html#page",
                                    retrieved_at=retrieved_at,
                                ),
                                payload={"kind": "taxonomy_page"},
                            )
                        ],
                        "gaps": [],
                        "raw_artifacts": ["raw/taxonomy.html"],
                        "requested_urls": ["https://example.org/taxonomy"],
                        "source_record_counts": {
                            AEDES_TAXONOMY_AUTHORITIES_SOURCE_ID: 1,
                            "aedes_worldclim_climate": 0,
                            "aedes_global_compendium_occurrence": 0,
                            "aedes_population_genomics": 0,
                            "aedes_who_resistance_guidance": 0,
                        },
                    },
                )()

            payload = ingest_aedes_deep_sources(
                artifact_dir=artifact_dir,
                retrieved_at="2026-05-25T00:00:00Z",
                worldclim_sample_limit=3,
                fetch_records=fake_result,
            )

            self.assertTrue(payload["ok"])
            self.assertIn(AEDES_TAXONOMY_AUTHORITIES_SOURCE_ID, payload["source_counts"])
            self.assertIn("mosquito_v1_fixtures", payload["source_counts"])
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn("aedes_deep_sources", status)
            self.assertEqual(status["aedes_deep_sources"]["source_record_counts"][AEDES_TAXONOMY_AUTHORITIES_SOURCE_ID], 1)


if __name__ == "__main__":
    unittest.main()
