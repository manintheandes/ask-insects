import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from scripts.ingest_drosophila_suzukii_neurobiology import ingest_drosophila_suzukii_neurobiology
from tests.test_drosophila_suzukii_neurobiology_source import ESEARCH_GDS, ESUMMARY_GDS


def _fake_fetch(url):
    if "esearch.fcgi" in url:
        return ESEARCH_GDS
    if "esummary.fcgi" in url:
        return ESUMMARY_GDS
    raise AssertionError(url)


class IngestNeurobiologyTests(unittest.TestCase):
    def test_ingest_installs_neurobiology_lane(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "mosquito-v1"
            result = ingest_drosophila_suzukii_neurobiology(
                artifact_dir=artifact_dir,
                fetch_json=_fake_fetch,
                retrieved_at="2026-06-05T00:00:00Z",
                max_results=10,
                page_size=10,
                delay_seconds=0,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["source"], "drosophila_suzukii_neurobiology_sources")
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select lane, count(*) as n from records "
                "where source='drosophila_suzukii_neurobiology_sources' group by lane",
                limit=50,
            )
            lanes = {r["lane"]: r["n"] for r in rows}
            self.assertGreaterEqual(lanes.get("neurobiology", 0), 1)

    def test_gap_only_run_is_success(self):
        # GEO returns zero datasets -> only domain-absence gaps. That is a valid
        # finding (SWD brain data is sparse), so ok must be True and the gap rows live.
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "mosquito-v1"
            result = ingest_drosophila_suzukii_neurobiology(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: {"esearchresult": {"count": "0", "idlist": []}},
                retrieved_at="2026-06-05T00:00:00Z", max_results=10, page_size=10, delay_seconds=0,
            )
            self.assertTrue(result["ok"])
            self.assertGreaterEqual(result["gap_count"], 4)
            self.assertEqual(result["dataset_count"], 0)

    def test_fetch_error_is_failure(self):
        # A real fetch error must report ok=False (not masked as a gap-only finding).
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "mosquito-v1"
            result = ingest_drosophila_suzukii_neurobiology(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-06-05T00:00:00Z", max_results=10, page_size=10, delay_seconds=0,
            )
            self.assertFalse(result["ok"])

    def test_failed_refresh_preserves_existing_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "mosquito-v1"
            ingest_drosophila_suzukii_neurobiology(
                artifact_dir=artifact_dir, fetch_json=_fake_fetch,
                retrieved_at="2026-06-05T00:00:00Z", max_results=10, page_size=10, delay_seconds=0,
            )
            failed = ingest_drosophila_suzukii_neurobiology(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-06-05T01:00:00Z", max_results=10, page_size=10, delay_seconds=0,
            )
            self.assertTrue(failed["preserved_existing"])
            self.assertGreaterEqual(failed["record_count"], 1)


if __name__ == "__main__":
    unittest.main()
