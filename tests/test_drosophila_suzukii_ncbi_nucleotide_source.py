import tempfile
import unittest
from pathlib import Path

from askinsects.sources.drosophila_suzukii_ncbi_nucleotide import (
    DROSOPHILA_SUZUKII_NCBI_NUCLEOTIDE_SOURCE_ID,
    fetch_drosophila_suzukii_ncbi_nucleotide_records,
)


ESEARCH = {
    "esearchresult": {
        "count": "2",
        "idlist": ["3040293388", "3040293126"],
    }
}

ESUMMARY = {
    "result": {
        "uids": ["3040293388", "3040293126"],
        "3040293388": {
            "uid": "3040293388",
            "caption": "PV080836",
            "title": "Drosophila suzukii voucher UHIM.BRU_04107 cytochrome oxidase subunit 1 (COI) gene, partial cds; mitochondrial",
            "accessionversion": "PV080836.1",
            "slen": 659,
            "biomol": "genomic",
            "moltype": "dna",
            "topology": "linear",
            "sourcedb": "insd",
            "genome": "mitochondrion",
            "subtype": "specimen_voucher|country|collection_date",
            "subname": "UHIM.BRU_04107|USA: Hawaii|12-Aug-2021",
            "tech": "barcode",
            "taxid": 28584,
            "organism": "Drosophila suzukii",
        },
        "3040293126": {
            "uid": "3040293126",
            "caption": "PV080705",
            "title": "Drosophila suzukii voucher UHIM.BRU_00989 cytochrome oxidase subunit 1 (COI) gene, partial cds; mitochondrial",
            "accessionversion": "PV080705.1",
            "slen": 658,
            "biomol": "genomic",
            "moltype": "dna",
            "topology": "linear",
            "sourcedb": "insd",
            "genome": "mitochondrion",
            "subtype": "specimen_voucher|country|collection_date",
            "subname": "UHIM.BRU_00989|USA: Hawaii|21-Jun-2018",
            "tech": "barcode",
            "taxid": 28584,
            "organism": "Drosophila suzukii",
        },
    }
}


class DrosophilaSuzukiiNcbiNucleotideSourceTests(unittest.TestCase):
    def test_fetch_builds_genbank_crosscheck_records(self):
        def fake_fetch(url):
            if "esearch.fcgi" in url:
                return ESEARCH
            if "esummary.fcgi" in url:
                return ESUMMARY
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_ncbi_nucleotide_records(
                raw_dir=Path(tmpdir),
                existing_barcode_rows=[
                    {
                        "record_id": "swd:bold:barcode:SWD1",
                        "payload": {"genbank_accession": "PV080836"},
                    }
                ],
                fetch_json=fake_fetch,
                retrieved_at="2026-05-29T00:00:00Z",
                max_results=10,
                page_size=10,
                delay_seconds=0,
            )

        self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_NCBI_NUCLEOTIDE_SOURCE_ID)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.bold_accession_matched_count, 1)
        self.assertEqual(result.genbank_only_count, 1)
        first = result.records[0]
        self.assertEqual(first.lane, "dna_barcodes")
        self.assertEqual(first.source, DROSOPHILA_SUZUKII_NCBI_NUCLEOTIDE_SOURCE_ID)
        self.assertEqual(first.payload["accession"], "PV080836")
        self.assertEqual(first.payload["bold_match_status"], "bold_accession_matched")
        self.assertIn("sequence_length=659 bp", first.text)

    def test_fetch_reports_limit_and_search_failure_gaps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            limited = fetch_drosophila_suzukii_ncbi_nucleotide_records(
                raw_dir=Path(tmpdir),
                existing_barcode_rows=[],
                fetch_json=lambda url: {"esearchresult": {"count": "3", "idlist": ["1"]}}
                if "esearch.fcgi" in url
                else {"result": {"uids": []}},
                retrieved_at="2026-05-29T00:00:00Z",
                max_results=1,
                page_size=1,
                delay_seconds=0,
            )
            failed = fetch_drosophila_suzukii_ncbi_nucleotide_records(
                raw_dir=Path(tmpdir) / "failed",
                fetch_json=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-29T00:00:00Z",
            )

        self.assertEqual(limited.gaps[0]["reason"], "swd_ncbi_nucleotide_limit_applied")
        self.assertEqual(failed.gaps[0]["reason"], "swd_ncbi_nucleotide_search_failed")


if __name__ == "__main__":
    unittest.main()
