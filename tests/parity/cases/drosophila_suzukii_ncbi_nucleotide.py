from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_drosophila_suzukii_ncbi_nucleotide_source import ESEARCH, ESUMMARY
from askinsects.sources.drosophila_suzukii_ncbi_nucleotide import (
    fetch_drosophila_suzukii_ncbi_nucleotide_records,
)

_RAW_DIR = "/tmp/ask-insects-parity/drosophila_suzukii_ncbi_nucleotide"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    def fake_fetch(url):
        if "esearch.fcgi" in url:
            return ESEARCH
        if "esummary.fcgi" in url:
            return ESUMMARY
        raise AssertionError(url)

    r = fetch_drosophila_suzukii_ncbi_nucleotide_records(
        raw_dir=raw_dir,
        existing_barcode_rows=[
            {
                "record_id": "swd:bold:barcode:SWD1",
                "payload": {"genbank_accession": "PV080836"},
            }
        ],
        fetch_json=fake_fetch,
        retrieved_at=_RETRIEVED_AT,
        max_results=10,
        page_size=10,
        delay_seconds=0,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="drosophila_suzukii_ncbi_nucleotide",
    run=_run,
    raw_dir=_RAW_DIR,
)
