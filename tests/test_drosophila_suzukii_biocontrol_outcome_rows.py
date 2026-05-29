from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.drosophila_suzukii_biocontrol_outcome_rows import (
    DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID,
    build_drosophila_suzukii_biocontrol_outcome_records,
)


def write_swd_biocontrol_fixture(artifact_dir: Path) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.upsert_records(
        [
            EvidenceRecord(
                record_id="swd_extracted_fact:biocontrol:openalex:WSWD1:candidate",
                lane="biocontrol",
                source="drosophila_suzukii_extracted_facts",
                title="Drosophila suzukii extracted biocontrol fact",
                text=(
                    "Trichopria drosophilae parasitoid performance against Drosophila suzukii. "
                    "Laboratory assay measured parasitism, mortality, emergence, and 70% parasitism."
                ),
                species="Drosophila suzukii",
                url="https://example.org/swd-biocontrol",
                media_url=None,
                provenance=Provenance(
                    source_id="drosophila_suzukii_extracted_facts",
                    locator="records#swd:openalex_literature:openalex:WSWD1",
                    retrieved_at="2026-05-29T00:00:00Z",
                    license="OpenAlex metadata",
                    source_url="https://example.org/swd-biocontrol",
                ),
                payload={
                    "fact_type": "biocontrol",
                    "confidence": "candidate",
                    "extraction_method": "deterministic_fulltext_term_extract",
                    "source_record_id": "swd:openalex_literature:openalex:WSWD1",
                    "source_title": "Performance of Trichopria drosophilae against Drosophila suzukii",
                    "evidence_text": "Trichopria drosophilae parasitized Drosophila suzukii pupae in laboratory assays with 70% parasitism.",
                    "fields": {
                        "agent": ["parasitoid", "trichopria"],
                        "assay": ["laboratory"],
                        "effect_metric": ["parasitism", "mortality", "emergence"],
                        "target_stage": ["adult"],
                        "percent_values": ["70%"],
                        "temperature_values": ["25 C"],
                    },
                    "source_provenance": {
                        "source_id": "drosophila_suzukii_core",
                        "locator": "raw/drosophila_suzukii/literature/page.json#WSWD1",
                        "retrieved_at": "2026-05-29T00:00:00Z",
                        "license": "OpenAlex metadata",
                    },
                },
            )
        ]
    )


class DrosophilaSuzukiiBiocontrolOutcomeRowTests(unittest.TestCase):
    def test_build_promotes_candidate_biocontrol_outcome_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_swd_biocontrol_fixture(artifact_dir)

            result = build_drosophila_suzukii_biocontrol_outcome_records(
                artifact_dir,
                retrieved_at="2026-05-29T00:00:00Z",
            )

            self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID)
            self.assertEqual(result.candidate_fact_count, 1)
            self.assertEqual(result.parsed_table_row_count, 0)
            self.assertEqual(len(result.records), 2)
            candidate = [record for record in result.records if record.payload["confidence"] == "candidate_literature_evidence"][0]
            self.assertEqual(candidate.source, DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID)
            self.assertEqual(candidate.lane, "biocontrol")
            self.assertEqual(candidate.species, "Drosophila suzukii")
            self.assertIn("parasitoid", candidate.payload["agent_terms"])
            self.assertIn("trichopria", candidate.payload["agent_terms"])
            self.assertEqual(candidate.payload["effect_metric_terms"], ["parasitism", "mortality", "emergence"])
            self.assertEqual(candidate.payload["percent_values"], ["70%"])
            self.assertFalse(candidate.payload["human_validated"])
            self.assertIn(
                "drosophila_suzukii_extracted_facts#swd_extracted_fact:biocontrol:openalex:WSWD1:candidate",
                candidate.provenance.locator,
            )
            gap = [record for record in result.records if record.payload.get("atom_type") == "source_gap"][0]
            self.assertEqual(gap.payload["reason"], "no_parsed_swd_biocontrol_table_rows_detected")

    def test_build_records_gap_when_no_promotable_rows_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            SourceIndex(artifact_dir / "source_index.sqlite").initialize()

            result = build_drosophila_suzukii_biocontrol_outcome_records(
                artifact_dir,
                retrieved_at="2026-05-29T00:00:00Z",
            )

            self.assertEqual(len(result.records), 1)
            self.assertEqual(result.records[0].source, DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID)
            self.assertEqual(result.records[0].payload["atom_type"], "source_gap")
            self.assertEqual(result.records[0].payload["reason"], "no_swd_biocontrol_evidence_rows_detected")
            self.assertEqual(result.gaps[0]["source"], DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID)


if __name__ == "__main__":
    unittest.main()
