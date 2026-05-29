import tempfile
import unittest
from pathlib import Path

from askinsects.sources.drosophila_suzukii_ncbi_marker_review import (
    DROSOPHILA_SUZUKII_NCBI_MARKER_REVIEW_SOURCE_ID,
    fetch_drosophila_suzukii_ncbi_marker_review_records,
)


class DrosophilaSuzukiiNcbiMarkerReviewSourceTests(unittest.TestCase):
    def test_fetch_builds_marker_review_records_and_counts_groups(self):
        def fake_fetch(url):
            if "esearch.fcgi" in url:
                return {"esearchresult": {"count": "2", "idlist": ["1", "2"]}}
            return {
                "result": {
                    "uids": ["1", "2"],
                    "1": {
                        "uid": "1",
                        "title": "Drosophila suzukii cytochrome oxidase subunit I gene",
                        "accessionversion": "PV000001.1",
                        "slen": "658",
                    },
                    "2": {
                        "uid": "2",
                        "title": "Drosophila suzukii internal transcribed spacer 2",
                        "accessionversion": "PV000002.1",
                        "slen": "420",
                    },
                }
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_ncbi_marker_review_records(
                raw_dir=Path(tmpdir),
                fetch_json=fake_fetch,
                retrieved_at="2026-05-29T00:00:00Z",
                max_results=10,
                page_size=10,
                delay_seconds=0,
            )

        self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_NCBI_MARKER_REVIEW_SOURCE_ID)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.marker_group_counts["mitochondrial_coi_barcode"], 1)
        self.assertEqual(result.marker_group_counts["nuclear_ribosomal_or_its"], 1)
        self.assertEqual(result.records[0].lane, "dna_barcodes")
        self.assertIn("marker-review", result.records[0].text)

    def test_search_failure_becomes_gap(self):
        def fake_fetch(url):
            raise RuntimeError("offline")

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_ncbi_marker_review_records(
                raw_dir=Path(tmpdir),
                fetch_json=fake_fetch,
                retrieved_at="2026-05-29T00:00:00Z",
                max_results=10,
                page_size=10,
                delay_seconds=0,
            )

        self.assertEqual(result.records, [])
        self.assertEqual(result.gaps[0]["reason"], "swd_ncbi_marker_review_search_failed")


if __name__ == "__main__":
    unittest.main()
