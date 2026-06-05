import unittest
from pathlib import Path
import tempfile

from askinsects.sources.drosophila_suzukii_neurobiology import (
    DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID,
    fetch_drosophila_suzukii_neurobiology_records,
)

# Minimal NCBI E-utilities db=gds shaped fixtures.
ESEARCH_GDS = {"esearchresult": {"count": "1", "idlist": ["200012345"]}}
ESUMMARY_GDS = {
    "result": {
        "uids": ["200012345"],
        "200012345": {
            "uid": "200012345",
            "accession": "GSE12345",
            "title": "Antennal transcriptome of Drosophila suzukii",
            "summary": "RNA-seq of Drosophila suzukii antennae profiling odorant receptor expression.",
            "taxon": "Drosophila suzukii",
            "gdstype": "Expression profiling by high throughput sequencing",
            "gpl": "GPL00000",
            "n_samples": "6",
        },
    }
}


def _fake_fetch(url):
    if "esearch.fcgi" in url:
        return ESEARCH_GDS
    if "esummary.fcgi" in url:
        return ESUMMARY_GDS
    raise AssertionError(url)


class NeurobiologySourceTests(unittest.TestCase):
    def test_geo_dataset_becomes_neurobiology_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = fetch_drosophila_suzukii_neurobiology_records(
                raw_dir=Path(tmp) / "raw",
                fetch_json=_fake_fetch,
                retrieved_at="2026-06-05T00:00:00Z",
                max_results=10,
                page_size=10,
                delay_seconds=0,
            )
        datasets = [r for r in result.records if ":gap:" not in r.record_id]
        self.assertEqual(len(datasets), 1)
        rec = datasets[0]
        self.assertEqual(rec.lane, "neurobiology")
        self.assertEqual(rec.source, DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID)
        self.assertEqual(rec.species, "Drosophila suzukii")
        self.assertIn("GSE12345", rec.payload["accession"])
        self.assertIn("antenna", rec.text.lower())

    def test_empty_geo_emits_domain_gap_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = fetch_drosophila_suzukii_neurobiology_records(
                raw_dir=Path(tmp) / "raw",
                fetch_json=lambda url: {"esearchresult": {"count": "0", "idlist": []}},
                retrieved_at="2026-06-05T00:00:00Z",
                max_results=10,
                page_size=10,
                delay_seconds=0,
            )
        datasets = [r for r in result.records if ":gap:" not in r.record_id]
        self.assertEqual(datasets, [])
        reasons = {g["reason"] for g in result.gaps}
        self.assertIn("swd_neurobiology_domain_absent:connectome", reasons)
        self.assertIn("swd_neurobiology_domain_absent:whole_brain_atlas", reasons)


if __name__ == "__main__":
    unittest.main()
