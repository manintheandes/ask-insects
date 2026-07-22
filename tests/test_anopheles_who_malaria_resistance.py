from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from askinsects.answer import answer_question
from askinsects.index import SourceIndex
from askinsects.sources.anopheles_who_malaria_resistance import fetch_anopheles_who_malaria_resistance


class AnophelesWHOMalariaResistanceTests(unittest.TestCase):
    def test_pages_and_preserves_atomic_assay_fields(self):
        rows = [
            {"Code": "IR1", "SPECIES": "An. gambiae s.l.", "COUNTRY_NAME": "Benin", "VILLAGE_NAME": "Cove", "YEAR_START": 2020, "ASSAY_TYPE": "WHO_TEST", "INSECTICIDE_TYPE": "Deltamethrin", "INSECTICIDE_CLASS": "Pyrethroid", "MORTALITY_ADJUSTED": "80", "RESISTANCE_STATUS": "Resistant", "CITATION_URL": "https://example.test/1"},
            {"Code": "IR2", "SPECIES": "An. funestus s.s.", "COUNTRY_NAME": "Mozambique", "YEAR_START": 2021, "INSECTICIDE_TYPE": "Permethrin"},
            {"Code": "IR3", "SPECIES": "An. stephensi", "COUNTRY_NAME": "India", "YEAR_START": 2022, "INSECTICIDE_TYPE": "DDT"},
        ]

        def fetch_json(url: str):
            if "%24skip=0" in url:
                return {"value": rows[:2]}
            return {"value": rows[2:]}

        with tempfile.TemporaryDirectory() as tmp:
            result = fetch_anopheles_who_malaria_resistance(
                raw_dir=Path(tmp), page_size=2, max_rows=10, delay_seconds=0,
                fetch_json=fetch_json, retrieved_at="2026-07-22T00:00:00Z",
            )
        self.assertEqual(result.fetched_row_count, 3)
        self.assertEqual(len(result.records), 3)
        self.assertTrue(result.records[0].record_id.startswith("anopheles_who:resistance:IR1:"))
        self.assertIn("mortality adjusted: 80", result.records[0].text)
        self.assertIn("#value/0", result.records[0].provenance.locator)
        self.assertEqual(result.species_labels["An. gambiae s.l."], 1)

    def test_records_cap_and_fetch_failures_as_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            capped = fetch_anopheles_who_malaria_resistance(
                raw_dir=Path(tmp), page_size=1, max_rows=1, delay_seconds=0,
                fetch_json=lambda _url: {"value": [{"Code": "IR1", "SPECIES": "An. gambiae s.l."}]},
            )
            failed = fetch_anopheles_who_malaria_resistance(
                raw_dir=Path(tmp), page_size=1, max_rows=1, delay_seconds=0,
                fetch_json=lambda _url: (_ for _ in ()).throw(RuntimeError("offline")),
            )
        self.assertTrue(any(gap["reason"] == "who_anopheles_max_rows_reached" for gap in capped.gaps))
        self.assertTrue(any(gap["reason"] == "who_anopheles_page_fetch_failed" for gap in failed.gaps))

    def test_answer_filters_structured_assay_fields_not_citation_text(self):
        rows = [
            {"Code": "IR1", "SPECIES": "An. gambiae s.l.", "COUNTRY_NAME": "Benin", "INSECTICIDE_TYPE": "NA", "CITATION_LONG": "A deltamethrin study"},
            {"Code": "IR2", "SPECIES": "An. gambiae s.l.", "COUNTRY_NAME": "Benin", "INSECTICIDE_TYPE": "PERMETHRIN", "RESISTANCE_STATUS": "CONFIRMED_RESISTANCE"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = fetch_anopheles_who_malaria_resistance(
                raw_dir=root / "raw", page_size=10, max_rows=10, delay_seconds=0,
                fetch_json=lambda _url: {"value": rows}, retrieved_at="2026-07-22T00:00:00Z",
            )
            index = SourceIndex(root / "source_index.sqlite")
            index.initialize()
            index.upsert_records(result.records)
            false_match = answer_question("show WHO Anopheles gambiae deltamethrin resistance records in Benin", artifact_dir=root)
            exact_match = answer_question("show WHO Anopheles gambiae permethrin resistance records in Benin", artifact_dir=root)
        self.assertFalse(false_match["ok"])
        self.assertTrue(exact_match["ok"])
        self.assertIn("PERMETHRIN", exact_match["answer"])


if __name__ == "__main__":
    unittest.main()
