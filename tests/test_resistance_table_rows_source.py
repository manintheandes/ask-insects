from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.resistance_table_rows import (
    RESISTANCE_TABLE_ROW_SOURCE_ID,
    build_resistance_table_row_records,
)


def write_resistance_table_fixture(artifact_dir: Path) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    source_paper = EvidenceRecord(
        record_id="openalex:WRTABLE1",
        lane="literature",
        source="aedes_literature_openalex",
        title="Insecticide resistance and kdr frequencies in Aedes aegypti field populations",
        text="Aedes aegypti resistance supplement source paper.",
        species="Aedes aegypti",
        url="https://example.org/resistance-table",
        media_url=None,
        provenance=Provenance(
            source_id="aedes_literature_openalex",
            locator="raw/literature/page.json#WRTABLE1",
            retrieved_at="2026-05-24T00:00:00Z",
            license="OpenAlex metadata",
        ),
    )
    parsed_fact = EvidenceRecord(
        record_id="extracted_fact:resistance:openalex:WRTABLE1:row7",
        lane="resistance",
        source="aedes_extracted_facts",
        title="Aedes aegypti extracted resistance table row",
        text=(
            "Supplement table row. Population: Brazil field population. "
            "Insecticide: deltamethrin. Mortality: 43%. V1016G allele frequency: 0.72."
        ),
        species="Aedes aegypti",
        url="https://example.org/resistance-supplement.csv",
        media_url=None,
        provenance=Provenance(
            source_id="aedes_extracted_facts",
            locator="records#openalex:WRTABLE1;supplement#0;raw/extracted_facts/supplements/resistance.csv;row#7",
            retrieved_at="2026-05-24T00:00:00Z",
            license="CC-BY",
            source_url="https://example.org/resistance-supplement.csv",
        ),
        payload={
            "fact_type": "resistance",
            "confidence": "parsed",
            "extraction_method": "deterministic_supplement_table_row_extract",
            "schema_version": "2026-05-24.v1",
            "source_record_id": "openalex:WRTABLE1",
            "source_title": "Insecticide resistance and kdr frequencies in Aedes aegypti field populations",
            "evidence_text": "Deltamethrin mortality 43%; V1016G allele frequency 0.72 in Brazil field population.",
            "fields": {
                "insecticide": ["deltamethrin"],
                "assay": ["WHO tube bioassay"],
                "mortality": ["43%"],
                "mutation": ["V1016G"],
                "genotype_frequency": ["0.72"],
                "country": ["Brazil"],
                "table_headers": [
                    "Population",
                    "Insecticide",
                    "Assay",
                    "Mortality %",
                    "V1016G allele frequency",
                ],
                "table_row": {
                    "Population": "Brazil field population",
                    "Insecticide": "deltamethrin",
                    "Assay": "WHO tube bioassay",
                    "Mortality %": "43",
                    "V1016G allele frequency": "0.72",
                },
                "table_row_index": 7,
            },
            "source_provenance": {
                "source_id": "aedes_literature_openalex",
                "locator": "raw/literature/page.json#WRTABLE1",
                "retrieved_at": "2026-05-24T00:00:00Z",
                "license": "OpenAlex metadata",
            },
        },
    )
    index.upsert_records([source_paper, parsed_fact])


class ResistanceTableRowSourceTests(unittest.TestCase):
    def test_build_resistance_table_row_records_promotes_parsed_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_resistance_table_fixture(artifact_dir)

            result = build_resistance_table_row_records(artifact_dir, retrieved_at="2026-05-24T00:00:00Z")

            self.assertEqual(result.source_id, RESISTANCE_TABLE_ROW_SOURCE_ID)
            self.assertEqual(result.parsed_table_row_count, 1)
            self.assertEqual(result.skipped_table_row_count, 0)
            record = result.records[0]
            self.assertEqual(record.source, RESISTANCE_TABLE_ROW_SOURCE_ID)
            self.assertEqual(record.lane, "resistance")
            self.assertIn("deltamethrin", record.text)
            self.assertEqual(record.payload["confidence"], "parsed_table_schema_validated")
            self.assertEqual(record.payload["validation_status"], "schema_validated")
            self.assertFalse(record.payload["human_validated"])
            self.assertEqual(record.payload["insecticide_terms"], ["deltamethrin"])
            self.assertEqual(record.payload["marker_terms"], ["V1016G"])
            self.assertEqual(record.payload["metric_fields"], ["genotype_frequency", "mortality"])
            self.assertEqual(record.payload["table_row"]["V1016G allele frequency"], "0.72")
            self.assertIn("Source record: openalex:WRTABLE1.", record.text)
            self.assertEqual(record.payload["source_extracted_fact_record_id"], "extracted_fact:resistance:openalex:WRTABLE1:row7")
            self.assertIn("aedes_extracted_facts#extracted_fact:resistance:openalex:WRTABLE1:row7", record.provenance.locator)

    def test_build_resistance_table_row_records_promotes_discriminating_concentration_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            parsed_fact = EvidenceRecord(
                record_id="extracted_fact:resistance:openalex:W7128925281:row3",
                lane="resistance",
                source="aedes_extracted_facts",
                title="Aedes aegypti extracted resistance fact",
                text=(
                    "Aedes aegypti extracted resistance fact from Additional file 1 of Toxicity of ivermectin "
                    "on multiple insecticide-resistant populations. Supplement table row. "
                    "Discriminating concentration s: Deltamethrin."
                ),
                species="Aedes aegypti",
                url="https://ndownloader.figshare.com/files/61896451",
                media_url=None,
                provenance=Provenance(
                    source_id="aedes_extracted_facts",
                    locator="records#openalex:W7128925281;supplement#0;raw/extracted_facts/supplements/resistance.docx;row#3",
                    retrieved_at="2026-05-27T00:00:00Z",
                    license="CC BY + CC0",
                    source_url="https://ndownloader.figshare.com/files/61896451",
                ),
                payload={
                    "fact_type": "resistance",
                    "confidence": "parsed",
                    "extraction_method": "deterministic_supplement_table_row_extract",
                    "schema_version": "2026-05-24.v1",
                    "source_record_id": "openalex:W7128925281",
                    "source_title": "Toxicity of ivermectin on multiple insecticide-resistant populations",
                    "evidence_text": "Discriminating concentration s: Deltamethrin.",
                    "fields": {
                        "discriminating_concentration": ["discriminating concentration"],
                        "insecticide": ["deltamethrin"],
                        "table_headers": ["Discriminating concentration s"],
                        "table_row": {"Discriminating concentration s": "Deltamethrin"},
                        "table_row_index": 3,
                    },
                    "source_provenance": {
                        "source_id": "aedes_literature_openalex",
                        "locator": "raw/literature/page.json#W7128925281",
                        "retrieved_at": "2026-05-23T22:26:07Z",
                        "license": "OpenAlex metadata",
                    },
                },
            )
            index.upsert_records([parsed_fact])

            result = build_resistance_table_row_records(artifact_dir, retrieved_at="2026-05-27T00:00:00Z")

            self.assertEqual(result.parsed_table_row_count, 1)
            self.assertEqual(result.skipped_table_row_count, 0)
            record = result.records[0]
            self.assertEqual(record.payload["insecticide_terms"], ["deltamethrin"])
            self.assertEqual(record.payload["metric_fields"], ["discriminating_concentration"])
            self.assertEqual(record.payload["table_row"]["Discriminating concentration s"], "Deltamethrin")
            self.assertIn("Source record: openalex:W7128925281.", record.text)

    def test_build_resistance_table_row_records_promotes_cnv_amplification_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            parsed_fact = EvidenceRecord(
                record_id="extracted_fact:resistance:openalex:W3208836499:row12",
                lane="resistance",
                source="aedes_extracted_facts",
                title="Aedes aegypti extracted resistance fact",
                text=(
                    "Aedes aegypti extracted resistance fact from a genomic amplification affecting "
                    "a carboxylesterase gene cluster. Supplement table row. Gene: CCEAE3A. "
                    "CNV: 30.86636. CNV_normalized_bora: 28.91394581. amplification: YES."
                ),
                species="Aedes aegypti",
                url="https://example.org/data_CNV_individuals.csv",
                media_url=None,
                provenance=Provenance(
                    source_id="aedes_extracted_facts",
                    locator="records#openalex:W3208836499;supplement#0;raw/extracted_facts/supplements/data_CNV_individuals.csv;row#12",
                    retrieved_at="2026-05-27T00:00:00Z",
                    license="CC-BY",
                    source_url="https://example.org/data_CNV_individuals.csv",
                ),
                payload={
                    "fact_type": "resistance",
                    "confidence": "parsed",
                    "extraction_method": "deterministic_supplement_table_row_extract",
                    "schema_version": "2026-05-24.v1",
                    "source_record_id": "openalex:W3208836499",
                    "source_title": (
                        "A genomic amplification affecting a carboxylesterase gene cluster confers "
                        "organophosphate resistance in the mosquito Aedes aegypti"
                    ),
                    "evidence_text": "CCEAE3A CNV 30.86636 CNV_normalized_bora 28.91394581 amplification YES.",
                    "fields": {
                        "copy_number": ["cnv", "cnv_normalized_bora"],
                        "amplification": ["amplification"],
                        "metabolic_marker": ["carboxylesterase", "cceae3a"],
                        "gene": ["cceae3a"],
                        "insecticide": ["organophosphate"],
                        "table_headers": [
                            "gene",
                            "lines",
                            "positive_sample",
                            "population",
                            "CNV",
                            "CNV_normalized_bora",
                            "amplification",
                        ],
                        "table_row": {
                            "gene": "CCEAE3A",
                            "lines": "G5_Mala",
                            "positive_sample": "G6 MAL 1",
                            "population": "G6 MAL",
                            "CNV": "30.86636",
                            "CNV_normalized_bora": "28.91394581",
                            "amplification": "YES",
                        },
                        "table_row_index": 12,
                    },
                    "source_provenance": {
                        "source_id": "aedes_literature_openalex",
                        "locator": "raw/literature/page.json#W3208836499",
                        "retrieved_at": "2026-05-23T22:26:07Z",
                        "license": "OpenAlex metadata",
                    },
                },
            )
            index.upsert_records([parsed_fact])

            result = build_resistance_table_row_records(artifact_dir, retrieved_at="2026-05-27T00:00:00Z")

            self.assertEqual(result.parsed_table_row_count, 1)
            self.assertEqual(result.skipped_table_row_count, 0)
            record = result.records[0]
            self.assertEqual(record.payload["insecticide_terms"], ["organophosphate"])
            self.assertIn("copy_number", record.payload["metric_fields"])
            self.assertIn("amplification", record.payload["metric_fields"])
            self.assertTrue({"cceae3a", "carboxylesterase"} & set(record.payload["marker_terms"]))
            self.assertEqual(record.payload["table_row"]["gene"], "CCEAE3A")
            self.assertEqual(record.payload["table_row_index"], 12)
            self.assertIn("Source record: openalex:W3208836499.", record.text)

    def test_build_resistance_table_row_records_records_gap_when_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            SourceIndex(artifact_dir / "source_index.sqlite").initialize()

            result = build_resistance_table_row_records(artifact_dir, retrieved_at="2026-05-24T00:00:00Z")

            self.assertEqual(len(result.records), 1)
            self.assertEqual(result.records[0].source, RESISTANCE_TABLE_ROW_SOURCE_ID)
            self.assertEqual(result.records[0].payload["atom_type"], "source_gap")
            self.assertEqual(result.records[0].payload["reason"], "no_resistance_table_rows_detected")
            self.assertEqual(result.gaps[0]["source"], RESISTANCE_TABLE_ROW_SOURCE_ID)


if __name__ == "__main__":
    unittest.main()
