from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from askinsects.answer import answer_question
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.anopheles_vector_competence_evidence import (
    ANOPHELES_VECTOR_COMPETENCE_SOURCE_ID,
    extract_anopheles_vector_competence_records,
)
from scripts.ingest_anopheles_vector_competence_evidence import ingest_anopheles_vector_competence_evidence


def literature_record(record_id: str, abstract: str) -> EvidenceRecord:
    return EvidenceRecord(
        record_id=record_id,
        lane="literature",
        source="anopheles_literature_openalex",
        title="Anopheles malaria study",
        text=f"Title: Anopheles malaria study\nAbstract: {abstract}\nDOI: 10.1000/test",
        species="Anopheles",
        url="https://openalex.org/W1",
        media_url=None,
        provenance=Provenance(
            source_id="anopheles_literature_openalex",
            locator="artifacts/raw/anopheles/page.json#work/W1",
            retrieved_at="2026-07-22T00:00:00Z",
            source_url="https://api.openalex.org/works/W1",
        ),
    )


class AnophelesVectorCompetenceEvidenceTests(unittest.TestCase):
    def test_extracts_numeric_field_result_with_exact_sentence_provenance(self) -> None:
        source = literature_record(
            "anopheles_openalex:W1",
            "Plasmodium falciparum was measured in a field survey. "
            "Sporozoite infection rates reached 45% in An. coluzzii and 27.4% in An. arabiensis.",
        )
        result = extract_anopheles_vector_competence_records(
            [source], retrieved_at="2026-07-22T01:00:00Z",
        )
        self.assertEqual(len(result.records), 1)
        record = result.records[0]
        self.assertEqual(record.source, ANOPHELES_VECTOR_COMPETENCE_SOURCE_ID)
        self.assertEqual(record.payload["evidence_class"], "field_surveillance_result")
        self.assertEqual(record.payload["species_mentions"], ["Anopheles coluzzii", "Anopheles arabiensis"])
        self.assertEqual(record.payload["pathogen_mentions"], ["Plasmodium falciparum"])
        self.assertEqual(record.payload["numeric_results"], ["45%", "27.4%"])
        self.assertEqual(record.provenance.locator, "artifacts/raw/anopheles/page.json#work/W1/abstract/sentence/2")
        self.assertEqual(record.payload["source_provenance"]["source_id"], "anopheles_literature_openalex")

    def test_classifies_membrane_feed_as_experimental(self) -> None:
        source = literature_record(
            "anopheles_openalex:W2",
            "Laboratory-reared Anopheles stephensi underwent a membrane feeding assay with Plasmodium vivax. "
            "The oocyst infection rate in Anopheles stephensi was 62%.",
        )
        result = extract_anopheles_vector_competence_records([source])
        self.assertEqual(result.records[0].payload["evidence_class"], "experimental_vector_competence_result")
        self.assertEqual(result.records[0].payload["pathogen_mentions"], ["Plasmodium vivax"])

    def test_excludes_modeled_projection_and_non_numeric_mention(self) -> None:
        modeled = literature_record(
            "anopheles_openalex:W3",
            "A simulation predicted that Anopheles funestus would reduce EIR by 57.7% under treatment.",
        )
        qualitative = literature_record(
            "anopheles_openalex:W4",
            "Anopheles gambiae can carry sporozoites, but no result was reported.",
        )
        result = extract_anopheles_vector_competence_records([modeled, qualitative])
        self.assertEqual(result.records, [])
        self.assertEqual(result.candidate_sentence_count, 1)
        self.assertEqual(result.excluded_model_sentence_count, 1)

    def test_does_not_treat_infected_blood_methods_numbers_as_a_result(self) -> None:
        source = literature_record(
            "anopheles_openalex:W-METHODS",
            "Anopheles darlingi were used in an experiment. "
            "Ivermectin at 0, 5, 10, 20 or 40 ng/mL was mixed into Plasmodium vivax infected blood.",
        )
        result = extract_anopheles_vector_competence_records([source])
        self.assertEqual(result.records, [])

    def test_ingest_and_answer_preserve_evidence_class_and_original_locator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records([literature_record(
                "anopheles_openalex:W5",
                "Laboratory-reared Anopheles stephensi were fed Plasmodium vivax gametocytes by membrane feeding. "
                "The oocyst rate in Anopheles stephensi was 58% (n = 120).",
            )])
            outcome = ingest_anopheles_vector_competence_evidence(
                artifact_dir=artifact_dir, retrieved_at="2026-07-22T01:00:00Z",
            )
            answer = answer_question(
                "What oocyst data do we have for Anopheles stephensi and Plasmodium vivax?",
                artifact_dir=artifact_dir,
            )
        self.assertTrue(outcome["ok"])
        self.assertTrue(answer["ok"])
        self.assertEqual(answer["evidence"][0]["source"], ANOPHELES_VECTOR_COMPETENCE_SOURCE_ID)
        self.assertIn("Controlled experiment", answer["answer"])
        self.assertIn("abstract-level", answer["answer"])
        self.assertIn("#work/W1/abstract/sentence/2", answer["evidence"][0]["provenance"]["locator"])

    def test_sporozoite_question_routes_without_explicit_pathogen_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records([literature_record(
                "anopheles_openalex:W6",
                "Anopheles coluzzii were collected in a field survey. "
                "The sporozoite infection rate in Anopheles coluzzii was 45%.",
            )])
            ingest_anopheles_vector_competence_evidence(artifact_dir=artifact_dir)
            answer = answer_question(
                "What sporozoite infection-rate data do we have for Anopheles coluzzii?",
                artifact_dir=artifact_dir,
            )
        self.assertTrue(answer["ok"])
        self.assertEqual(answer["evidence"][0]["source"], ANOPHELES_VECTOR_COMPETENCE_SOURCE_ID)
        self.assertIn("45%", answer["answer"])

    def test_broad_endpoint_list_can_match_infection_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records([literature_record(
                "anopheles_openalex:W7",
                "Anopheles stephensi underwent membrane feeding with Plasmodium vivax gametocytes. "
                "A total of 58 of 100 Anopheles stephensi mosquitoes were infected.",
            )])
            ingest_anopheles_vector_competence_evidence(artifact_dir=artifact_dir)
            answer = answer_question(
                "What infection, oocyst, sporozoite, or transmission-rate data do we have for Anopheles stephensi and Plasmodium vivax?",
                artifact_dir=artifact_dir,
            )
        self.assertTrue(answer["ok"])
        self.assertIn("58 of 100", answer["answer"])


if __name__ == "__main__":
    unittest.main()
