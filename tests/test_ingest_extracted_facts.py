from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.literature import FullTextUnit
from scripts.ingest_extracted_facts import ingest_extracted_facts
from tests.test_extracted_facts_source import write_extracted_facts_fixture


class IngestExtractedFactsTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_extracted_facts_fixture(artifact_dir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="fixture:aedes",
                        lane="taxonomy",
                        source="mosquito_v1_fixtures",
                        title="Aedes aegypti",
                        text="Fixture taxonomy row.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="mosquito_v1_fixtures",
                            locator="fixture#1",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                    )
                ]
            )

            result = ingest_extracted_facts(
                artifact_dir=artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertGreaterEqual(result["record_count"], 6)
            self.assertEqual(result["max_fulltext_units"], 5000)
            self.assertEqual(result["max_candidate_text_chars"], 50000)
            self.assertEqual(result["selected_fulltext_unit_count"], 1)
            self.assertEqual(result["selected_record_text_count"], 0)
            counts = {
                (row["source"], row["lane"]): int(row["n"])
                for row in index.sql("select source,lane,count(*) as n from records group by source,lane", limit=100)
            }
            self.assertGreaterEqual(counts[("aedes_extracted_facts", "vector_competence")], 1)
            self.assertGreaterEqual(counts[("aedes_extracted_facts", "resistance")], 1)
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 1)
            payload_rows = index.sql(
                "select count(*) as n from record_payloads where source='aedes_extracted_facts'"
            )
            self.assertGreaterEqual(payload_rows[0]["n"], 6)
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn("aedes_extracted_facts", status["sources"])
            self.assertEqual(status["aedes_extracted_facts"]["record_count"], result["record_count"])
            self.assertEqual(status["aedes_extracted_facts"]["max_fulltext_units"], 5000)
            self.assertEqual(status["aedes_extracted_facts"]["selected_record_text_count"], 0)

    def test_ingest_can_download_and_parse_supplement_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_extracted_facts_fixture(artifact_dir)

            def fake_file_fetch(url: str, max_bytes: int) -> bytes:
                self.assertEqual(url, "https://example.org/aedes-facts/supp-table-1.csv")
                self.assertEqual(max_bytes, 100000)
                return (
                    "domain,pathogen,infection rate,temperature,tissue,strain\n"
                    "vector competence,dengue virus,80%,28 C,saliva,Rockefeller\n"
                ).encode("utf-8")

            result = ingest_extracted_facts(
                artifact_dir=artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                download_supplements=True,
                fetch_supplement_file_fn=fake_file_fetch,
                max_supplement_files=3,
                max_supplement_bytes=100000,
                max_pdf_supplement_files=10,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["downloaded_supplement_file_count"], 1)
            self.assertEqual(result["parsed_supplement_file_count"], 1)
            self.assertEqual(result["parsed_supplement_row_count"], 1)
            self.assertEqual(result["max_pdf_supplement_files"], 10)
            self.assertEqual(result["parsed_pdf_supplement_file_count"], 0)
            self.assertEqual(result["skipped_pdf_supplement_file_count"], 0)
            self.assertEqual(result["supplement_discovery_record_count"], 0)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select payload_json, provenance_json from record_payloads where source='aedes_extracted_facts' and json_extract(payload_json, '$.confidence')='parsed'",
                limit=5,
            )
            self.assertEqual(len(rows), 1)
            self.assertIn('"infection rate": "80%"', rows[0]["payload_json"])
            self.assertIn("raw/extracted_facts/supplements/", rows[0]["provenance_json"])
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["aedes_extracted_facts"]["parsed_supplement_row_count"], 1)

    def test_incremental_merge_replaces_one_paper_without_removing_other_extracted_facts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_extracted_facts_fixture(artifact_dir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.upsert_records_and_fulltext_units(
                [
                    EvidenceRecord(
                        record_id="openalex:WFACT2",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Aedes aegypti resistance and dengue vector competence second paper",
                        text="Second Aedes aegypti evidence paper.",
                        species="Aedes aegypti",
                        url="https://example.org/aedes-facts-2",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_literature_openalex",
                            locator="raw/literature/page.json#WFACT2",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                    )
                ],
                [
                    FullTextUnit(
                        unit_id="openalex:WFACT2:fulltext:0",
                        record_id="openalex:WFACT2",
                        source="aedes_literature_openalex",
                        unit_index=0,
                        text=(
                            "Vector competence dengue virus infection rate 77%, transmission rate 12% in saliva. "
                            "Resistance permethrin bioassay mortality 44%, VGSC F1534C in Brazil."
                        ),
                        url="https://example.org/aedes-facts-2/fulltext",
                        license="CC-BY",
                        provenance=Provenance(
                            source_id="aedes_literature_openalex",
                            locator="raw/fulltext/WFACT2.txt#chunk/0",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                    )
                ],
            )

            first = ingest_extracted_facts(
                artifact_dir=artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
            )
            original_record_count = first["record_count"]
            before = {
                row["source_record_id"]: int(row["n"])
                for row in index.sql(
                    """
                    select json_extract(payload_json, '$.source_record_id') as source_record_id, count(*) as n
                    from record_payloads
                    where source='aedes_extracted_facts'
                    group by source_record_id
                    """,
                    limit=10,
                )
            }
            self.assertGreater(before["openalex:WFACT1"], 0)
            self.assertGreater(before["openalex:WFACT2"], 0)

            second = ingest_extracted_facts(
                artifact_dir=artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                source_record_ids=["openalex:WFACT1"],
                merge_existing=True,
            )

            self.assertTrue(second["ok"])
            self.assertTrue(second["merge_existing"])
            self.assertEqual(second["source_record_ids"], ["openalex:WFACT1"])
            self.assertEqual(second["record_count"], original_record_count)
            self.assertEqual(second["deleted_existing_record_count"], before["openalex:WFACT1"])
            after = {
                row["source_record_id"]: int(row["n"])
                for row in index.sql(
                    """
                    select json_extract(payload_json, '$.source_record_id') as source_record_id, count(*) as n
                    from record_payloads
                    where source='aedes_extracted_facts'
                    group by source_record_id
                    """,
                    limit=10,
                )
            }
            self.assertEqual(after["openalex:WFACT1"], before["openalex:WFACT1"])
            self.assertEqual(after["openalex:WFACT2"], before["openalex:WFACT2"])


if __name__ == "__main__":
    unittest.main()
