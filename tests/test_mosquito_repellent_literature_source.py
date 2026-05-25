import tempfile
import unittest
from pathlib import Path

from askinsects.sources.mosquito_repellent_literature import fetch_mosquito_repellent_literature_records


ESEARCH = {"esearchresult": {"idlist": ["42000001", "42000002"], "count": "2"}}
ESUMMARY = {
    "result": {
        "uids": ["42000001", "42000002"],
        "42000001": {
            "uid": "42000001",
            "title": "Spatial repellent protection against Aedes mosquito host seeking",
            "fulljournalname": "Vector Control Journal",
            "pubdate": "2026 Jan",
            "authors": [{"name": "Example A"}, {"name": "Example B"}],
            "articleids": [{"idtype": "doi", "value": "10.1000/repellent.1"}],
        },
        "42000002": {
            "uid": "42000002",
            "title": "Picaridin repellency in mosquito landing assays",
            "source": "Mosquito Research",
            "pubdate": "2025 Apr",
            "authors": [{"name": "Example C"}],
            "articleids": [{"idtype": "doi", "value": "10.1000/repellent.2"}],
        },
    }
}
CROSSREF = {
    "message": {
        "total-results": 2,
        "items": [
            {
                "DOI": "10.1000/repellent.1",
                "title": ["Spatial repellent protection against Aedes mosquito host seeking"],
                "publisher": "Example Publisher",
                "container-title": ["Vector Control Journal"],
                "issued": {"date-parts": [[2026, 1, 1]]},
                "type": "journal-article",
                "subject": ["mosquito repellents"],
                "URL": "https://doi.org/10.1000/repellent.1",
            },
            {
                "DOI": "10.1000/deet.3",
                "title": ["DEET and essential oil repellency against Culex mosquitoes"],
                "publisher": "Example Publisher",
                "container-title": ["Medical Entomology"],
                "issued": {"date-parts": [[2024, 5]]},
                "type": "journal-article",
                "subject": ["Culex", "DEET", "repellency"],
                "URL": "https://doi.org/10.1000/deet.3",
            },
        ],
    }
}


class MosquitoRepellentLiteratureSourceTests(unittest.TestCase):
    def test_fetch_builds_deduped_pubmed_and_crossref_records(self):
        calls = []

        def fake_fetch_json(url):
            calls.append(url)
            if "esearch.fcgi" in url:
                return ESEARCH
            if "esummary.fcgi" in url:
                return ESUMMARY
            if "api.crossref.org" in url:
                return CROSSREF
            raise AssertionError(url)

        existing_rows = [
            {
                "record_id": "literature:openalex:W123",
                "source": "aedes_literature_openalex",
                "title": "Picaridin repellency in mosquito landing assays",
                "url": "https://doi.org/10.1000/repellent.2",
                "payload": {"doi": "10.1000/repellent.2"},
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_mosquito_repellent_literature_records(
                raw_dir=Path(tmpdir) / "raw",
                existing_literature_rows=existing_rows,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-25T00:00:00Z",
                pubmed_max_results=20,
                crossref_max_results=20,
                page_size=10,
            )
            self.assertTrue(Path(result.raw_artifacts[0]).exists())

        self.assertEqual(result.source_id, "mosquito_repellent_literature")
        self.assertEqual(result.pubmed_reported_total_count, 2)
        self.assertEqual(result.candidate_count, 3)
        self.assertEqual(result.canonical_literature_row_count, 1)
        self.assertEqual(result.already_indexed_count, 1)
        self.assertEqual(result.pubmed_metadata_ingested_count, 1)
        self.assertEqual(result.crossref_metadata_ingested_count, 2)
        statuses = {record.payload["title"]: record.payload["coverage_status"] for record in result.records}
        self.assertEqual(statuses["Picaridin repellency in mosquito landing assays"], "already_indexed")
        merged = next(record for record in result.records if record.payload["doi"] == "10.1000/repellent.1")
        self.assertEqual(merged.record_id, "mosquito_repellent_literature:pubmed:42000001")
        self.assertEqual(merged.lane, "literature")
        self.assertEqual(merged.species, "Culicidae")
        self.assertIn("pubmed_esearch_esummary", merged.payload["candidate_sources"])
        self.assertIn("crossref_works", merged.payload["candidate_sources"])
        self.assertIn("spatial repellent", merged.payload["repellent_terms"])
        self.assertIn("pubmed_esummary_0001.json#result/42000001", merged.provenance.locator)
        self.assertGreaterEqual(len(calls), 3)

    def test_fetch_reports_result_limit_and_missing_canonical_gaps(self):
        def fake_fetch_json(url):
            if "esearch.fcgi" in url:
                return {"esearchresult": {"idlist": ["1"], "count": "3"}}
            if "esummary.fcgi" in url:
                return {
                    "result": {
                        "uids": ["1"],
                        "1": {
                            "title": "DEET mosquito repellent test",
                            "pubdate": "2025",
                            "articleids": [{"idtype": "doi", "value": "10.1000/test"}],
                        },
                    }
                }
            return {"message": {"total-results": 0, "items": []}}

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_mosquito_repellent_literature_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-25T00:00:00Z",
                pubmed_max_results=1,
                crossref_max_results=1,
                page_size=1,
            )

        reasons = {gap["reason"] for gap in result.gaps}
        self.assertIn("mosquito_repellent_pubmed_result_limit_applied", reasons)
        self.assertIn("mosquito_repellent_no_canonical_literature_rows", reasons)


if __name__ == "__main__":
    unittest.main()
