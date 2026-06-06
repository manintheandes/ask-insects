import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.sources.drosophila_suzukii_chemoreceptors import fetch_drosophila_suzukii_chemoreceptor_records
from scripts.ingest_drosophila_suzukii_chemoreceptors import ingest_drosophila_suzukii_chemoreceptors

ESEARCH = {"esearchresult": {"count": "3", "idlist": ["139354135", "200000002", "200000003"]}}
ESUMMARY = {"result": {
    "uids": ["139354135", "200000002", "200000003"],
    "139354135": {"uid": "139354135", "name": "Or42b", "description": "Odorant receptor 42b", "chromosome": "2"},
    "200000002": {"uid": "200000002", "name": "Ir84a", "description": "Ionotropic receptor 84a", "chromosome": "3"},
    "200000003": {"uid": "200000003", "name": "Gr5a", "description": "Gustatory receptor 5a", "chromosome": "X"},
}}


def _fake_fetch(url):
    if "esearch.fcgi" in url:
        return ESEARCH
    if "esummary.fcgi" in url:
        return ESUMMARY
    raise AssertionError(url)


class ChemoreceptorTests(unittest.TestCase):
    def test_genes_become_classified_neurobiology_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = fetch_drosophila_suzukii_chemoreceptor_records(
                raw_dir=Path(tmp) / "raw", fetch_json=_fake_fetch,
                retrieved_at="2026-06-06T00:00:00Z", max_results=10, page_size=10, delay_seconds=0,
            )
        recs = [r for r in result.records if ":gap:" not in r.record_id]
        self.assertEqual(len(recs), 3)
        self.assertTrue(all(r.lane == "neurobiology" for r in recs))
        self.assertTrue(all(r.species == "Drosophila suzukii" for r in recs))
        classes = {r.payload["receptor_class"] for r in recs}
        self.assertEqual(classes, {"odorant_receptor", "ionotropic_receptor", "gustatory_receptor"})
        # all three expected classes present -> no class-absence gaps
        reasons = {g["reason"] for g in result.gaps}
        self.assertNotIn("swd_receptor_class_absent:odorant_receptor", reasons)

    def test_empty_run_is_success_with_class_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "mosquito-v1"
            result = ingest_drosophila_suzukii_chemoreceptors(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: {"esearchresult": {"count": "0", "idlist": []}},
                retrieved_at="2026-06-06T00:00:00Z", max_results=10, page_size=10, delay_seconds=0,
            )
            self.assertTrue(result["ok"])
            self.assertGreaterEqual(result["gap_count"], 3)

    def test_ingest_installs_chemoreceptor_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "mosquito-v1"
            result = ingest_drosophila_suzukii_chemoreceptors(
                artifact_dir=artifact_dir, fetch_json=_fake_fetch,
                retrieved_at="2026-06-06T00:00:00Z", max_results=10, page_size=10, delay_seconds=0,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["receptor_count"], 3)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select count(*) n from records where source='drosophila_suzukii_chemoreceptors' and lane='neurobiology'",
                limit=5,
            )
            self.assertEqual(rows[0]["n"], 3)


if __name__ == "__main__":
    unittest.main()
