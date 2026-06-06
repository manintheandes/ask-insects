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

    def test_present_antennal_transcriptome_does_not_suppress_unrelated_domain_gaps(self):
        # An antennal transcriptome is none of the four EXPECTED_DOMAINS, so all four
        # domain-absence gaps must still fire. (Regression: a first-token substring
        # check wrongly suppressed the connectome and antennal-lobe-map gaps here.)
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
        reasons = {g["reason"] for g in result.gaps}
        for key in (
            "swd_neurobiology_domain_absent:whole_brain_atlas",
            "swd_neurobiology_domain_absent:connectome",
            "swd_neurobiology_domain_absent:single_nucleus_brain_rnaseq",
            "swd_neurobiology_domain_absent:antennal_lobe_map",
        ):
            self.assertIn(key, reasons)

    def test_connectome_dataset_suppresses_only_connectome_gap(self):
        connectome_summary = {
            "result": {
                "uids": ["200099999"],
                "200099999": {
                    "uid": "200099999",
                    "accession": "GSE99999",
                    "title": "Brain connectome of Drosophila suzukii",
                    "summary": "Connectome reconstruction of the Drosophila suzukii central brain.",
                    "taxon": "Drosophila suzukii",
                    "gdstype": "Other",
                    "n_samples": "1",
                },
            }
        }

        def fetch(url):
            if "esearch.fcgi" in url:
                return {"esearchresult": {"count": "1", "idlist": ["200099999"]}}
            if "esummary.fcgi" in url:
                return connectome_summary
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmp:
            result = fetch_drosophila_suzukii_neurobiology_records(
                raw_dir=Path(tmp) / "raw", fetch_json=fetch,
                retrieved_at="2026-06-05T00:00:00Z", max_results=10, page_size=10, delay_seconds=0,
            )
        reasons = {g["reason"] for g in result.gaps}
        self.assertNotIn("swd_neurobiology_domain_absent:connectome", reasons)
        self.assertIn("swd_neurobiology_domain_absent:whole_brain_atlas", reasons)

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
