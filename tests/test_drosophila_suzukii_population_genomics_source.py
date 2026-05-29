import tempfile
import unittest
from pathlib import Path

from askinsects.sources.drosophila_suzukii_population_genomics import (
    DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID,
    fetch_drosophila_suzukii_population_genomics_records,
)


class DrosophilaSuzukiiPopulationGenomicsSourceTests(unittest.TestCase):
    def test_fetch_builds_bioproject_records_with_raw_locators(self):
        calls: list[str] = []

        def fake_fetch(url: str):
            calls.append(url)
            if "esearch.fcgi" in url:
                return {"esearchresult": {"count": "2", "idlist": ["1289399", "1081763"]}}
            if "esummary.fcgi" in url:
                return {
                    "result": {
                        "uids": ["1289399", "1081763"],
                        "1289399": {
                            "project_acc": "PRJNA1289399",
                            "project_title": "Pool-seq data from 3 Drosophila suzukii populations collected in Northern Portugal",
                            "project_description": "Population genomic pool-seq data for invasive Drosophila suzukii.",
                            "project_data_type": "Genome sequencing",
                            "project_target_scope": "Multiisolate",
                            "submitter_organization": "Test submitter",
                            "registration_date": "2025-01-01",
                        },
                        "1081763": {
                            "project_acc": "PRJNA1081763",
                            "project_title": "Pool-seq data from 3 Drosophila suzukii populations from North Portugal",
                            "project_description": "Genomic signatures of invasion.",
                        },
                    }
                }
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_population_genomics_records(
                raw_dir=Path(tmpdir),
                retrieved_at="2026-05-29T00:00:00Z",
                fetch_json=fake_fetch,
                limit=10,
            )

        self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID)
        self.assertEqual(result.reported_count, 2)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.records[0].record_id, "swd_population_genomics:bioproject:PRJNA1289399")
        self.assertEqual(result.records[0].source, DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID)
        self.assertIn("Pool-seq", result.records[0].text)
        self.assertIn("#result/1289399", result.records[0].provenance.locator)
        self.assertEqual(result.gaps, [])
        self.assertEqual(len(calls), 2)

    def test_fetch_reports_empty_search_gap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_population_genomics_records(
                raw_dir=Path(tmpdir),
                retrieved_at="2026-05-29T00:00:00Z",
                fetch_json=lambda _url: {"esearchresult": {"count": "0", "idlist": []}},
                limit=10,
            )

        self.assertEqual(result.records, [])
        self.assertEqual({gap["reason"] for gap in result.gaps}, {"swd_population_genomics_bioproject_search_empty"})


if __name__ == "__main__":
    unittest.main()
