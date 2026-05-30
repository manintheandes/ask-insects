from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_bold_barcode_source import FAKE_BOLD_TSV
from askinsects.sources.bold_barcodes import fetch_bold_barcode_records

_RAW_DIR = "/tmp/ask-insects-parity/bold_barcodes"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)
    r = fetch_bold_barcode_records(
        species="Aedes aegypti",
        raw_dir=raw_dir,
        limit=500,
        fetch_text=lambda url: FAKE_BOLD_TSV,
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="bold_barcodes",
    run=_run,
    raw_dir=_RAW_DIR,
)
