from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.drosophila_suzukii_susceptibility_assay_rows import (
    DROSOPHILA_SUZUKII_SUSCEPTIBILITY_ASSAY_ROWS_SOURCE_ID,
    build_drosophila_suzukii_susceptibility_assay_records,
)


def write_swd_susceptibility_fixture(artifact_dir: Path) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    parsed_fact = EvidenceRecord(
        record_id="swd_extracted_fact:resistance:openalex:WSWD1:row4",
        lane="resistance",
        source="drosophila_suzukii_extracted_facts",
        title="Drosophila suzukii parsed resistance table row",
        text="Supplement table row. Insecticide: spinosad. Assay: vial bioassay. Mortality: 92%.",
        species="Drosophila suzukii",
        url="https://example.org/swd-resistance.csv",
        media_url=None,
        provenance=Provenance(
            source_id="drosophila_suzukii_extracted_facts",
            locator="records#swd:openalex_literature:openalex:WSWD1;supplement#0;raw/drosophila_suzukii_extracted_facts/supplements/resistance.csv;row#4",
            retrieved_at="2026-05-29T00:00:00Z",
            license="CC-BY",
            source_url="https://example.org/swd-resistance.csv",
        ),
        payload={
            "fact_type": "resistance",
            "confidence": "parsed",
            "extraction_method": "deterministic_supplement_table_row_extract",
            "source_record_id": "swd:openalex_literature:openalex:WSWD1",
            "source_title": "Spinosad susceptibility in Drosophila suzukii field populations",
            "evidence_text": "Spinosad vial bioassay mortality was 92%.",
            "fields": {
                "insecticide": ["spinosad"],
                "assay": ["vial bioassay"],
                "response_metric": ["mortality"],
                "mortality": ["92%"],
                "population": ["field population"],
                "table_headers": ["Population", "Insecticide", "Assay", "Mortality %"],
                "table_row": {
                    "Population": "field population",
                    "Insecticide": "spinosad",
                    "Assay": "vial bioassay",
                    "Mortality %": "92",
                },
                "table_row_index": 4,
            },
            "source_provenance": {
                "source_id": "drosophila_suzukii_core",
                "locator": "raw/drosophila_suzukii/literature/page.json#WSWD1",
                "retrieved_at": "2026-05-29T00:00:00Z",
                "license": "OpenAlex metadata",
            },
        },
    )
    candidate_fact = EvidenceRecord(
        record_id="swd_extracted_fact:resistance:openalex:WSWD2:candidate",
        lane="resistance",
        source="drosophila_suzukii_extracted_facts",
        title="Drosophila suzukii extracted resistance fact",
        text="Pre-treating cherries bioassay found lambda-cyhalothrin and spinosad caused greater than 90% adult mortality.",
        species="Drosophila suzukii",
        url="https://example.org/swd-paper",
        media_url=None,
        provenance=Provenance(
            source_id="drosophila_suzukii_extracted_facts",
            locator="records#swd:openalex_literature:openalex:WSWD2",
            retrieved_at="2026-05-29T00:00:00Z",
            license="OpenAlex metadata",
            source_url="https://example.org/swd-paper",
        ),
        payload={
            "fact_type": "resistance",
            "confidence": "candidate",
            "extraction_method": "deterministic_fulltext_term_extract",
            "source_record_id": "swd:openalex_literature:openalex:WSWD2",
            "source_title": "Impact of traditional pesticides on Drosophila suzukii",
            "evidence_text": "Bioassay results revealed lambda-cyhalothrin and spinosad were highly efficacious, resulting in greater than 90% adult mortality.",
            "fields": {
                "insecticide": ["spinosad", "lambda-cyhalothrin"],
                "assay": ["bioassay"],
                "response_metric": ["mortality"],
                "percent_values": ["90%"],
            },
            "source_provenance": {
                "source_id": "drosophila_suzukii_core",
                "locator": "raw/drosophila_suzukii/literature/page.json#WSWD2",
                "retrieved_at": "2026-05-29T00:00:00Z",
                "license": "OpenAlex metadata",
            },
        },
    )
    index.upsert_records([parsed_fact, candidate_fact])


class DrosophilaSuzukiiSusceptibilityAssayRowTests(unittest.TestCase):
    def test_build_promotes_parsed_table_and_candidate_susceptibility_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_swd_susceptibility_fixture(artifact_dir)

            result = build_drosophila_suzukii_susceptibility_assay_records(
                artifact_dir,
                retrieved_at="2026-05-29T00:00:00Z",
            )

            self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_SUSCEPTIBILITY_ASSAY_ROWS_SOURCE_ID)
            self.assertEqual(result.parsed_table_row_count, 1)
            self.assertEqual(result.candidate_fact_count, 1)
            self.assertEqual(len(result.records), 2)
            parsed = [record for record in result.records if record.payload["confidence"] == "parsed_table_schema_validated"][0]
            self.assertEqual(parsed.source, DROSOPHILA_SUZUKII_SUSCEPTIBILITY_ASSAY_ROWS_SOURCE_ID)
            self.assertEqual(parsed.species, "Drosophila suzukii")
            self.assertEqual(parsed.payload["insecticide_terms"], ["spinosad"])
            self.assertEqual(parsed.payload["metric_fields"], ["mortality"])
            self.assertEqual(parsed.payload["table_row"]["Mortality %"], "92")
            self.assertIn("drosophila_suzukii_extracted_facts#swd_extracted_fact:resistance:openalex:WSWD1:row4", parsed.provenance.locator)
            candidate = [record for record in result.records if record.payload["confidence"] == "candidate_literature_evidence"][0]
            self.assertIn("lambda-cyhalothrin", candidate.text)
            self.assertEqual(candidate.payload["validation_status"], "candidate_not_table_validated")
            self.assertFalse(candidate.payload["human_validated"])

    def test_build_records_gap_when_no_promotable_rows_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            SourceIndex(artifact_dir / "source_index.sqlite").initialize()

            result = build_drosophila_suzukii_susceptibility_assay_records(
                artifact_dir,
                retrieved_at="2026-05-29T00:00:00Z",
            )

            self.assertEqual(len(result.records), 1)
            self.assertEqual(result.records[0].source, DROSOPHILA_SUZUKII_SUSCEPTIBILITY_ASSAY_ROWS_SOURCE_ID)
            self.assertEqual(result.records[0].payload["atom_type"], "source_gap")
            self.assertEqual(result.records[0].payload["reason"], "no_swd_susceptibility_evidence_rows_detected")
            self.assertEqual(result.gaps[0]["source"], DROSOPHILA_SUZUKII_SUSCEPTIBILITY_ASSAY_ROWS_SOURCE_ID)


if __name__ == "__main__":
    unittest.main()
