import tempfile
import unittest
from pathlib import Path

from askinsects.sources.drosophila_suzukii_pubmed_literature import (
    fetch_drosophila_suzukii_pubmed_literature_records,
)


ESEARCH = {"esearchresult": {"idlist": ["40200001", "40200002"], "count": "2"}}
ESUMMARY = {
    "result": {
        "uids": ["40200001", "40200002"],
        "40200001": {
            "uid": "40200001",
            "title": "Temperature changes Drosophila suzukii oviposition behavior",
            "fulljournalname": "Journal of Pest Biology",
            "pubdate": "2025 Mar",
            "authors": [{"name": "Example A"}, {"name": "Example B"}],
            "articleids": [{"idtype": "doi", "value": "10.1000/swd-oviposition"}],
        },
        "40200002": {
            "uid": "40200002",
            "title": "Management of spotted wing drosophila in berry systems",
            "source": "Pest Manag Sci",
            "pubdate": "2024 Nov",
            "authors": [{"name": "Example C"}],
            "articleids": [{"idtype": "doi", "value": "10.1000/swd-management"}],
        },
    }
}


class DrosophilaSuzukiiPubMedLiteratureSourceTests(unittest.TestCase):
    def test_fetch_builds_pubmed_audit_records_with_coverage_status(self):
        calls = []

        def fake_fetch_json(url):
            calls.append(url)
            if "esearch.fcgi" in url:
                return ESEARCH
            if "esummary.fcgi" in url:
                return ESUMMARY
            raise AssertionError(url)

        existing_rows = [
            {
                "record_id": "swd:openalex_literature:openalex:W1",
                "source": "drosophila_suzukii_core",
                "title": "Management of spotted wing drosophila in berry systems",
                "url": "https://doi.org/10.1000/swd-management",
                "payload": {"doi": "10.1000/swd-management"},
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_pubmed_literature_records(
                raw_dir=Path(tmpdir) / "raw",
                existing_literature_rows=existing_rows,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-29T00:00:00Z",
                max_results=20,
                page_size=10,
                delay_seconds=0,
            )
            self.assertTrue(Path(result.raw_artifacts[0]).exists())

        self.assertEqual(result.source_id, "drosophila_suzukii_pubmed_literature")
        self.assertEqual(result.reported_total_count, 2)
        self.assertEqual(result.candidate_count, 2)
        self.assertEqual(result.canonical_literature_row_count, 1)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.gaps, [])
        statuses = {record.payload["pmid"]: record.payload["coverage_status"] for record in result.records}
        self.assertEqual(statuses["40200002"], "already_indexed")
        self.assertEqual(statuses["40200001"], "pubmed_metadata_ingested")
        missing = next(record for record in result.records if record.payload["pmid"] == "40200001")
        self.assertEqual(missing.record_id, "swd_pubmed_literature:pubmed:40200001")
        self.assertEqual(missing.lane, "literature")
        self.assertEqual(missing.source, "drosophila_suzukii_pubmed_literature")
        self.assertEqual(missing.species, "Drosophila suzukii")
        self.assertIn("coverage_status=pubmed_metadata_ingested", missing.text)
        self.assertIn("pubmed_esummary_0001.json#result/40200001", missing.provenance.locator)
        self.assertEqual(len(calls), 2)

    def test_fetch_reports_limit_and_missing_canonical_gaps(self):
        def fake_fetch_json(url):
            if "esearch.fcgi" in url:
                return {"esearchresult": {"idlist": ["1"], "count": "3"}}
            return {"result": {"uids": ["1"], "1": {"title": "Drosophila suzukii test", "pubdate": "2025"}}}

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_pubmed_literature_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-29T00:00:00Z",
                max_results=1,
                page_size=1,
                delay_seconds=0,
            )

        reasons = {gap["reason"] for gap in result.gaps}
        self.assertIn("swd_pubmed_result_limit_applied", reasons)
        self.assertIn("swd_pubmed_no_canonical_literature_rows", reasons)


if __name__ == "__main__":
    unittest.main()
