import tempfile
import unittest
from pathlib import Path

from askinsects.sources.aedes_crossref_literature_audit import fetch_aedes_crossref_literature_audit_records


CROSSREF_PAGE = {
    "message": {
        "total-results": 3,
        "next-cursor": "next-page",
        "items": [
            {
                "DOI": "10.1016/j.example.2025.01.001",
                "title": ["Aedes aegypti larval habitat surveillance in Brazil"],
                "abstract": "Aedes aegypti larvae were sampled in urban containers.",
                "publisher": "Example Publisher",
                "container-title": ["Journal of Mosquito Intelligence"],
                "issued": {"date-parts": [[2025, 1, 12]]},
                "type": "journal-article",
                "subject": ["Entomology"],
                "URL": "https://doi.org/10.1016/j.example.2025.01.001",
                "member": "1234",
                "reference-count": 42,
                "license": [{"URL": "https://creativecommons.org/licenses/by/4.0/"}],
            },
            {
                "DOI": "10.1111/example.2024.7",
                "title": ["Climate and oviposition in Ae. aegypti"],
                "abstract": "A study of oviposition behavior.",
                "publisher": "Example Society",
                "container-title": ["Vector Ecology"],
                "issued": {"date-parts": [[2024, 6]]},
                "type": "journal-article",
                "subject": ["Ecology"],
                "URL": "https://doi.org/10.1111/example.2024.7",
                "member": "5678",
            },
            {
                "DOI": "10.1000/out.of.scope",
                "title": ["General mosquito surveillance"],
                "abstract": "No material Aedes species here.",
                "publisher": "Example Publisher",
                "issued": {"date-parts": [[2025]]},
                "type": "journal-article",
            },
        ],
    }
}


class AedesCrossrefLiteratureAuditSourceTests(unittest.TestCase):
    def test_fetch_builds_crossref_audit_records_with_coverage_status(self):
        calls = []

        def fake_fetch_json(url):
            calls.append(url)
            return CROSSREF_PAGE

        existing_rows = [
            {
                "record_id": "literature:openalex:W123",
                "source": "aedes_literature_openalex",
                "title": "Climate and oviposition in Ae. aegypti",
                "url": "https://doi.org/10.1111/example.2024.7",
                "payload": {"doi": "10.1111/example.2024.7"},
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_aedes_crossref_literature_audit_records(
                raw_dir=Path(tmpdir) / "raw",
                existing_literature_rows=existing_rows,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-25T00:00:00Z",
                max_results=20,
                page_size=10,
            )
            self.assertTrue(Path(result.raw_artifacts[0]).exists())

        self.assertEqual(result.source_id, "aedes_crossref_literature_audit")
        self.assertEqual(result.reported_total_count, 3)
        self.assertEqual(result.candidate_count, 2)
        self.assertEqual(result.canonical_literature_row_count, 1)
        self.assertEqual(result.already_indexed_count, 1)
        self.assertEqual(result.crossref_metadata_ingested_count, 1)
        self.assertEqual(len(result.records), 2)
        statuses = {record.payload["doi"]: record.payload["coverage_status"] for record in result.records}
        self.assertEqual(statuses["10.1111/example.2024.7"], "already_indexed")
        self.assertEqual(statuses["10.1016/j.example.2025.01.001"], "crossref_metadata_ingested")
        missing = next(record for record in result.records if record.payload["doi"] == "10.1016/j.example.2025.01.001")
        self.assertEqual(missing.record_id, "aedes_crossref_literature_audit:doi:10.1016_j.example.2025.01.001")
        self.assertEqual(missing.lane, "literature")
        self.assertEqual(missing.source, "aedes_crossref_literature_audit")
        self.assertEqual(missing.species, "Aedes aegypti")
        self.assertIn("coverage_status=crossref_metadata_ingested", missing.text)
        self.assertIn("crossref_works_0001.json#items/0", missing.provenance.locator)
        self.assertIn("query.bibliographic=Aedes+aegypti", calls[0])

    def test_fetch_reports_limit_and_empty_canonical_gaps(self):
        def fake_fetch_json(url):
            return CROSSREF_PAGE

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_aedes_crossref_literature_audit_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-25T00:00:00Z",
                max_results=1,
                page_size=1,
            )

        self.assertEqual(len(result.records), 1)
        reasons = {gap["reason"] for gap in result.gaps}
        self.assertIn("aedes_crossref_result_limit_applied", reasons)
        self.assertIn("aedes_crossref_no_canonical_literature_rows", reasons)


if __name__ == "__main__":
    unittest.main()
