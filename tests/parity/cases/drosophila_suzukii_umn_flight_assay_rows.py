from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_drosophila_suzukii_umn_flight_assay_rows_source import (
    BITSTREAM_API_URL,
    BITSTREAM_FIXTURE,
    CSV_CONTENT_URL,
    CSV_FIXTURE,
    ITEM_API_URL,
    ITEM_FIXTURE,
)
from askinsects.sources.drosophila_suzukii_umn_flight_assay_rows import (
    fetch_drosophila_suzukii_umn_flight_assay_row_records,
)

_RAW_DIR = "/tmp/ask-insects-parity/drosophila_suzukii_umn_flight_assay_rows"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    def fetch_json(url):
        if url == ITEM_API_URL:
            return ITEM_FIXTURE
        if url == BITSTREAM_API_URL:
            return BITSTREAM_FIXTURE
        raise AssertionError(url)

    def fetch_bytes(url):
        assert url == CSV_CONTENT_URL
        return CSV_FIXTURE.encode("utf-8")

    r = fetch_drosophila_suzukii_umn_flight_assay_row_records(
        raw_dir=raw_dir,
        fetch_json=fetch_json,
        fetch_bytes=fetch_bytes,
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="drosophila_suzukii_umn_flight_assay_rows",
    run=_run,
    raw_dir=_RAW_DIR,
)
