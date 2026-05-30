from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_vectorbyte_abundance_source import DATASET_27006_PAGE_1, SEARCH_PAYLOAD
from askinsects.sources.vectorbyte_abundance import fetch_vectorbyte_abundance_records

_RAW_DIR = "/tmp/ask-insects-parity/vectorbyte_abundance"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _fake_fetch_json(url):
    if "vecdynbyprovider" in url:
        return SEARCH_PAYLOAD
    if "vecdyncsv" in url and "piids=27006" in url:
        return DATASET_27006_PAGE_1
    raise AssertionError(url)


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    r = fetch_vectorbyte_abundance_records(
        raw_dir=raw_dir,
        fetch_json=_fake_fetch_json,
        retrieved_at=_RETRIEVED_AT,
        dataset_limit=1,
        row_limit=100,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="aedes_vectorbyte_abundance",
    run=_run,
    raw_dir=_RAW_DIR,
)
