import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.sources.drosophila_suzukii_traits import fetch_drosophila_suzukii_traits_records
from scripts.ingest_drosophila_suzukii_traits import ingest_drosophila_suzukii_traits

ESEARCH = {"esearchresult": {"count": "1", "idlist": ["40000001"]}}
ESUMMARY = {
    "result": {
        "uids": ["40000001"],
        "40000001": {
            "uid": "40000001",
            "title": "Temperature-dependent development and fecundity of Drosophila suzukii",
            "fulljournalname": "Journal of Economic Entomology",
            "pubdate": "2021 Mar",
            "source": "J Econ Entomol",
        },
    }
}


def _fake_fetch(url):
    if "esearch.fcgi" in url:
        return ESEARCH
    if "esummary.fcgi" in url:
        return ESUMMARY
    raise AssertionError(url)


class TraitsSourceTests(unittest.TestCase):
    def test_trait_paper_becomes_traits_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = fetch_drosophila_suzukii_traits_records(
                raw_dir=Path(tmp) / "raw", fetch_json=_fake_fetch,
                retrieved_at="2026-06-05T00:00:00Z", max_results=10, page_size=10, delay_seconds=0,
            )
        recs = [r for r in result.records if ":gap:" not in r.record_id]
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].lane, "traits")
        self.assertEqual(recs[0].species, "Drosophila suzukii")
        reasons = {g["reason"] for g in result.gaps}
        # "development" and "fecundity" present in the title -> those classes NOT gapped;
        # unrelated classes (diapause, cold_hardiness) still gapped.
        self.assertNotIn("swd_traits_class_absent:development_time", reasons)
        self.assertNotIn("swd_traits_class_absent:fecundity", reasons)
        self.assertIn("swd_traits_class_absent:diapause_overwintering", reasons)

    def test_empty_run_is_success_with_class_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "mosquito-v1"
            result = ingest_drosophila_suzukii_traits(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: {"esearchresult": {"count": "0", "idlist": []}},
                retrieved_at="2026-06-05T00:00:00Z", max_results=10, page_size=10, delay_seconds=0,
            )
            self.assertTrue(result["ok"])
            self.assertGreaterEqual(result["gap_count"], 6)

    def test_ingest_installs_traits_lane(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "mosquito-v1"
            result = ingest_drosophila_suzukii_traits(
                artifact_dir=artifact_dir, fetch_json=_fake_fetch,
                retrieved_at="2026-06-05T00:00:00Z", max_results=10, page_size=10, delay_seconds=0,
            )
            self.assertTrue(result["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select count(*) n from records where source='drosophila_suzukii_traits' and lane='traits'",
                limit=5,
            )
            self.assertGreaterEqual(rows[0]["n"], 1)


if __name__ == "__main__":
    unittest.main()
