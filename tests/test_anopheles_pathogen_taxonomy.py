from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from askinsects.answer import answer_question
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.anopheles_pathogen_taxonomy import (
    ANOPHELES_PATHOGEN_TAXONOMY_SOURCE_ID,
    ANOPHELES_PATHOGENS,
    fetch_anopheles_pathogen_taxonomy,
)
from scripts.ingest_anopheles_pathogen_taxonomy import ingest_anopheles_pathogen_taxonomy


def _payload():
    result = {"uids": [str(spec.taxid) for spec in ANOPHELES_PATHOGENS]}
    for spec in ANOPHELES_PATHOGENS:
        result[str(spec.taxid)] = {
            "taxid": spec.taxid,
            "scientificname": spec.display_name,
            "rank": "species",
            "division": "invertebrates",
        }
    return {"result": result}


class AnophelesPathogenTaxonomyTests(unittest.TestCase):
    def test_fetch_builds_atomic_ncbi_taxonomy_anchors(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = fetch_anopheles_pathogen_taxonomy(
                raw_dir=Path(tmp), fetch_json=lambda url: _payload(), retrieved_at="2026-07-22T00:00:00Z",
            )
        self.assertEqual(result.pathogen_count, len(ANOPHELES_PATHOGENS))
        falciparum = next(record for record in result.records if record.payload["taxid"] == 5833)
        self.assertEqual(falciparum.source, ANOPHELES_PATHOGEN_TAXONOMY_SOURCE_ID)
        self.assertIn("does not by itself prove vector competence", falciparum.text)
        self.assertIn("#taxonomy/5833", falciparum.provenance.locator)

    def test_ingest_and_answer_use_anopheles_pathogen_lane(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            outcome = ingest_anopheles_pathogen_taxonomy(
                artifact_dir=artifact_dir, fetch_json=lambda url: _payload(), retrieved_at="2026-07-22T00:00:00Z",
            )
            answer = answer_question(
                "Which Plasmodium pathogen taxonomy records are available for Anopheles research?",
                artifact_dir=artifact_dir,
            )
            named_answer = answer_question(
                "What is Plasmodium falciparum in the context of Anopheles research?",
                artifact_dir=artifact_dir,
            )
            count = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select count(*) n from records where source='anopheles_pathogen_taxonomy'"
            )[0]["n"]
        self.assertTrue(outcome["ok"])
        self.assertEqual(count, len(ANOPHELES_PATHOGENS))
        self.assertTrue(answer["ok"])
        self.assertTrue(all(item["source"] == ANOPHELES_PATHOGEN_TAXONOMY_SOURCE_ID for item in answer["evidence"]))
        self.assertIn("Plasmodium falciparum", answer["answer"])
        self.assertIn("Plasmodium cynomolgi", answer["answer"])
        self.assertTrue(named_answer["ok"])
        self.assertEqual(named_answer["evidence"][0]["species"], "Plasmodium falciparum")
        self.assertIn("does not by itself prove vector competence", named_answer["answer"])

    def test_vector_competence_question_fails_closed_with_coverage_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records([EvidenceRecord(
                record_id="anopheles_source_coverage:domain:vector_competence",
                lane="source_coverage",
                source="anopheles_source_coverage",
                title="Anopheles coverage status: vector_competence",
                text="Assay-level Anopheles vector-competence records are not started.",
                species="Anopheles",
                url="https://example.test/coverage",
                media_url=None,
                provenance=Provenance(
                    source_id="anopheles_source_coverage",
                    locator="config/anopheles-intelligence-coverage.json#domain/vector_competence",
                    retrieved_at="2026-07-22T00:00:00Z",
                ),
                payload={"domain": "vector_competence", "atom_type": "source_coverage_domain"},
            )])
            answer = answer_question(
                "Can Anopheles gambiae transmit Plasmodium falciparum, and what assay evidence supports that?",
                artifact_dir=artifact_dir,
            )
        self.assertFalse(answer["ok"])
        self.assertTrue(answer["answer"].startswith("Source gap:"))
        self.assertEqual(answer["evidence"][0]["source"], "anopheles_source_coverage")
        self.assertIn("cannot prove competence", answer["answer"])

    def test_named_pathogen_interaction_uses_materially_matching_anopheles_literature(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records([EvidenceRecord(
                record_id="anopheles_openalex:W1",
                lane="literature",
                source="anopheles_literature_openalex",
                title="Microsporidia MB in Anopheles coluzzii",
                text="A field study of Microsporidia MB in Anopheles coluzzii in Cameroon.",
                species="Anopheles",
                url="https://openalex.org/W1",
                media_url=None,
                provenance=Provenance(
                    source_id="anopheles_literature_openalex",
                    locator="raw/anopheles_literature/page.json#work/W1",
                    retrieved_at="2026-07-22T00:00:00Z",
                ),
            )])
            answer = answer_question(
                "What do we know about Microsporidia MB in Anopheles coluzzii?",
                artifact_dir=artifact_dir,
            )
        self.assertTrue(answer["ok"])
        self.assertEqual(answer["evidence"][0]["source"], "anopheles_literature_openalex")
        self.assertIn("Microsporidia MB", answer["answer"])


if __name__ == "__main__":
    unittest.main()
