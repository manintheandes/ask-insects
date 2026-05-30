from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_vectorbyte_traits_source import DATASET_126, DATASET_474, SEARCH_PAYLOAD
from askinsects.sources.vectorbyte_traits import fetch_vectorbyte_trait_records

_RAW_DIR = "/tmp/ask-insects-parity/vectorbyte_traits"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _fake_fetch_json(url):
    if "api.vbdhub.org/search" in url:
        return SEARCH_PAYLOAD
    if "/vectraits-dataset/126/" in url:
        return DATASET_126
    if "/vectraits-dataset/474/" in url:
        return DATASET_474
    raise AssertionError(url)


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    r = fetch_vectorbyte_trait_records(
        raw_dir=raw_dir,
        fetch_json=_fake_fetch_json,
        retrieved_at=_RETRIEVED_AT,
        dataset_limit=2,
        row_limit=100,
        search_limit=10,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="aedes_vectorbyte_traits",
    run=_run,
    raw_dir=_RAW_DIR,
)
