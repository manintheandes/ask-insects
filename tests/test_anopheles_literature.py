from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from askinsects.answer import answer_question
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.anopheles_literature import (
    ANOPHELES_LITERATURE_SOURCE_ID,
    ANOPHELES_TARGET_TAXA,
    fetch_anopheles_literature_records,
)


def openalex_work(
    work_id: str,
    *,
    title: str,
    abstract_terms: dict[str, list[int]],
    doi: str | None = None,
) -> dict[str, object]:
    return {
        "id": f"https://openalex.org/{work_id}",
        "doi": doi,
        "display_name": title,
        "publication_date": "2025-01-01",
        "type": "article",
        "abstract_inverted_index": abstract_terms,
        "authorships": [{"author": {"display_name": "Researcher"}}],
        "primary_location": {"source": {"display_name": "Malaria Vector Journal"}},
        "ids": {"openalex": f"https://openalex.org/{work_id}", "doi": doi},
    }


class AnophelesLiteratureTests(unittest.TestCase):
    def test_fetches_and_retargets_openalex_records(self) -> None:
        calls: list[str] = []

        def fake_fetch_json(url: str) -> dict[str, object]:
            calls.append(url)
            return {
                "meta": {"count": 1, "next_cursor": None},
                "results": [
                    openalex_work(
                        "W-ANOPHELES-1",
                        title="Anopheles stephensi host seeking and repellents",
                        abstract_terms={
                            "Anopheles": [0],
                            "stephensi": [1],
                            "host": [2],
                            "seeking": [3],
                            "repellents": [4],
                        },
                        doi="https://doi.org/10.1000/anopheles1",
                    )
                ],
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_anopheles_literature_records(
                raw_dir=Path(tmpdir) / "raw",
                from_date="2020-01-01",
                to_date="2026-12-31",
                max_works=1,
                page_size=1,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-07-22T00:00:00Z",
            )

        self.assertEqual(result.source_id, ANOPHELES_LITERATURE_SOURCE_ID)
        self.assertEqual(len(result.records), 1)
        record = result.records[0]
        self.assertEqual(record.source, ANOPHELES_LITERATURE_SOURCE_ID)
        self.assertEqual(record.record_id, "anopheles_openalex:W-ANOPHELES-1")
        self.assertEqual(record.provenance.source_id, ANOPHELES_LITERATURE_SOURCE_ID)
        self.assertEqual(record.species, "Anopheles")
        self.assertIn("Anopheles stephensi", record.text)
        self.assertEqual(record.payload["original_record_id"], "openalex:W-ANOPHELES-1")
        self.assertEqual(len(record.payload["target_taxa"]), 21)
        self.assertIn("Anopheles darlingi", ANOPHELES_TARGET_TAXA)
        self.assertTrue(calls)

    def test_anopheles_domain_question_cannot_fall_through_to_aedes_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            provenance = Provenance(
                source_id=ANOPHELES_LITERATURE_SOURCE_ID,
                locator="raw/anopheles.json#works/W1",
                retrieved_at="2026-07-22T00:00:00Z",
            )
            index.upsert_records([
                EvidenceRecord(
                    record_id="anopheles_openalex:W1", lane="literature",
                    source=ANOPHELES_LITERATURE_SOURCE_ID,
                    title="Host seeking by Anopheles funestus",
                    text="Anopheles funestus host-seeking behavior under field conditions.",
                    species="Anopheles", url="https://openalex.org/W1", media_url=None,
                    provenance=provenance,
                    payload={"openalex_candidate_status": "exact_title_abstract"},
                ),
                EvidenceRecord(
                    record_id="facet:behavior:aedes", lane="behavior", source="aedes_literature_facets",
                    title="Aedes host seeking", text="Aedes aegypti host-seeking behavior.",
                    species="Aedes aegypti", url=None, media_url=None,
                    provenance=Provenance(
                        source_id="aedes_literature_facets", locator="aedes#1",
                        retrieved_at="2026-07-22T00:00:00Z",
                    ),
                ),
            ])
            answer = answer_question(
                "What is known about host-seeking behavior in Anopheles funestus?",
                artifact_dir=artifact_dir,
            )
        self.assertTrue(answer["ok"])
        self.assertTrue(all(item["source"] == ANOPHELES_LITERATURE_SOURCE_ID for item in answer["evidence"]))
        self.assertIn("Anopheles funestus", answer["answer"])


if __name__ == "__main__":
    unittest.main()
