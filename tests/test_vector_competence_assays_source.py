from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.literature import FullTextUnit
from askinsects.sources.vector_competence_assays import (
    VECTOR_COMPETENCE_ASSAY_SOURCE_ID,
    build_vector_competence_assay_records,
)


def write_assay_literature_fixture(artifact_dir: Path) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    literature = EvidenceRecord(
        record_id="openalex:WVC1",
        lane="literature",
        source="aedes_literature_openalex",
        title="Vector competence of Aedes aegypti for Zika virus",
        text="Aedes aegypti vector competence study with oral infection.",
        species="Aedes aegypti",
        url="https://example.org/vector-competence",
        media_url=None,
        provenance=Provenance(
            source_id="aedes_literature_openalex",
            locator="raw/literature/page.json#WVC1",
            retrieved_at="2026-05-24T00:00:00Z",
            license="open metadata",
            source_url="https://example.org/vector-competence",
        ),
    )
    unit = FullTextUnit(
        unit_id="openalex:WVC1:fulltext:0",
        record_id="openalex:WVC1",
        source="aedes_literature_openalex",
        unit_index=0,
        text=(
            "Aedes aegypti mosquitoes were orally infected with ZIKV at 10^6 PFU in an artificial blood meal. "
            "At 28 C and 14 days post infection, midgut infection rate, dissemination rate in legs and wings, "
            "and transmission rate based on saliva samples were measured in the field population."
        ),
        url="https://example.org/vector-competence/fulltext",
        license="CC-BY",
        provenance=Provenance(
            source_id="aedes_literature_openalex",
            locator="raw/fulltext/WVC1.txt#chunk/0",
            retrieved_at="2026-05-24T00:00:00Z",
            license="CC-BY",
            source_url="https://example.org/vector-competence/fulltext",
        ),
    )
    index.upsert_records_and_fulltext_units([literature], [unit])


def write_parsed_extracted_fact_fixture(artifact_dir: Path) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    source_paper = EvidenceRecord(
        record_id="openalex:WTABLE1",
        lane="literature",
        source="aedes_literature_openalex",
        title="Vertically infected Aedes aegypti excrete infectious arboviruses in saliva",
        text="Aedes aegypti vector competence supplement source paper.",
        species="Aedes aegypti",
        url="https://example.org/table-paper",
        media_url=None,
        provenance=Provenance(
            source_id="aedes_literature_openalex",
            locator="raw/literature/page.json#WTABLE1",
            retrieved_at="2026-05-24T00:00:00Z",
            license="OpenAlex metadata",
        ),
    )
    parsed_fact = EvidenceRecord(
        record_id="extracted_fact:vector_competence:openalex:WTABLE1:row3",
        lane="vector_competence",
        source="aedes_extracted_facts",
        title="Aedes aegypti extracted vector competence fact",
        text=(
            "Supplement table row. Viral strain (dose provided): DENV-1 (10 7 FFU/mL). "
            "Aedes aegypti saliva transmission row."
        ),
        species="Aedes aegypti",
        url="https://example.org/supplement.csv",
        media_url=None,
        provenance=Provenance(
            source_id="aedes_extracted_facts",
            locator="records#openalex:WTABLE1;supplement#0;raw/extracted_facts/supplements/table.csv;row#3",
            retrieved_at="2026-05-24T00:00:00Z",
            license="CC-BY",
            source_url="https://example.org/supplement.csv",
        ),
        payload={
            "fact_type": "vector_competence",
            "confidence": "parsed",
            "extraction_method": "deterministic_supplement_table_row_extract",
            "source_record_id": "openalex:WTABLE1",
            "fulltext_unit_id": None,
            "evidence_text": "Viral strain (dose provided): DENV-1 (10 7 FFU/mL). Saliva transmission row.",
            "fields": {
                "pathogen": ["denv"],
                "dose_values": ["7 FFU"],
                "infection": ["infected"],
                "transmission": ["saliva"],
                "tissue": ["saliva"],
                "strain": ["strain"],
                "table_headers": [
                    "Viral strain (dose provided)",
                    "Genotype",
                    "Year of first isolation/Place/host",
                    "Viral stock passage history",
                    "Cell type used for virus passage",
                    "GenBank accession number",
                ],
                "table_row": {
                    "Viral strain (dose provided)": "DENV-1 (10 7 FFU/mL)",
                    "Genotype": "genotype V",
                    "Year of first isolation/Place/host": "2013/Guadeloupe/human",
                    "Viral stock passage history": "P2",
                    "Cell type used for virus passage": "C6/36",
                    "GenBank accession number": "OR486055",
                },
                "table_row_index": 3,
            },
            "source_provenance": source_paper.provenance.to_dict(),
            "unit_provenance": None,
        },
    )
    index.upsert_records([source_paper, parsed_fact])


class VectorCompetenceAssaySourceTests(unittest.TestCase):
    def test_build_vector_competence_assay_records_extracts_structured_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_assay_literature_fixture(artifact_dir)

            result = build_vector_competence_assay_records(artifact_dir, retrieved_at="2026-05-24T00:00:00Z")

            self.assertEqual(result.source_id, VECTOR_COMPETENCE_ASSAY_SOURCE_ID)
            self.assertEqual(result.candidate_count, 1)
            self.assertEqual(result.source_record_count, 1)
            self.assertEqual(result.fulltext_unit_count, 1)
            record = result.records[0]
            self.assertEqual(record.source, VECTOR_COMPETENCE_ASSAY_SOURCE_ID)
            self.assertEqual(record.lane, "vector_competence")
            self.assertIn("Zika virus", record.title)
            self.assertIn("infection", record.payload["assay_fields"])
            self.assertIn("dissemination", record.payload["assay_fields"])
            self.assertIn("transmission", record.payload["assay_fields"])
            self.assertIn("dose", record.payload["assay_fields"])
            self.assertIn("temperature", record.payload["assay_fields"])
            self.assertIn("literature_fulltext_units#openalex:WVC1:fulltext:0", record.provenance.locator)

    def test_build_vector_competence_assay_records_promotes_parsed_table_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_parsed_extracted_fact_fixture(artifact_dir)

            result = build_vector_competence_assay_records(artifact_dir, retrieved_at="2026-05-24T00:00:00Z")

            self.assertEqual(result.parsed_table_row_count, 1)
            record = result.records[0]
            self.assertEqual(record.source, VECTOR_COMPETENCE_ASSAY_SOURCE_ID)
            self.assertEqual(record.lane, "vector_competence")
            self.assertIn("dengue virus", record.title)
            self.assertEqual(record.payload["pathogen"], "dengue virus")
            self.assertEqual(record.payload["confidence"], "parsed_table_schema_validated")
            self.assertEqual(record.payload["validation_status"], "schema_validated")
            self.assertEqual(record.payload["source_extracted_fact_record_id"], "extracted_fact:vector_competence:openalex:WTABLE1:row3")
            self.assertEqual(record.payload["source_confidence"], "parsed")
            self.assertEqual(record.payload["table_row"]["Viral strain (dose provided)"], "DENV-1 (10 7 FFU/mL)")
            self.assertIn("aedes_extracted_facts#extracted_fact:vector_competence:openalex:WTABLE1:row3", record.provenance.locator)

    def test_build_vector_competence_assay_records_ignores_derived_literature_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_assay_literature_fixture(artifact_dir)
            SourceIndex(artifact_dir / "source_index.sqlite").upsert_records(
                [
                    EvidenceRecord(
                        record_id="extracted_fact:supplement_audit:openalex:WVC1",
                        lane="literature",
                        source="aedes_extracted_facts",
                        title="Aedes aegypti dengue vector competence supplement audit",
                        text=(
                            "Internal supplement audit row mentioning infection rate, transmission rate, "
                            "viral dose, and oral infection."
                        ),
                        species="Aedes aegypti",
                        url="https://example.org/audit",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_extracted_facts",
                            locator="records#openalex:WVC1;supplement-audit",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="test",
                        ),
                    )
                ]
            )

            result = build_vector_competence_assay_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertEqual(result.source_record_count, 1)
            self.assertEqual(result.candidate_count, 1)
            self.assertTrue(all("supplement_audit" not in record.record_id for record in result.records))

    def test_build_vector_competence_assay_records_records_gap_when_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            SourceIndex(artifact_dir / "source_index.sqlite").initialize()

            result = build_vector_competence_assay_records(artifact_dir, retrieved_at="2026-05-24T00:00:00Z")

            self.assertEqual(result.records, [])
            self.assertEqual(result.gaps[0]["source"], VECTOR_COMPETENCE_ASSAY_SOURCE_ID)


if __name__ == "__main__":
    unittest.main()
