from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_vectornet_surveillance_source import vectornet_archive_bytes
from askinsects.sources.vectornet_surveillance import fetch_vectornet_surveillance_records

_RAW_DIR = "/tmp/ask-insects-parity/vectornet_surveillance"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    r = fetch_vectornet_surveillance_records(
        raw_dir=raw_dir,
        fetch_bytes=lambda url: vectornet_archive_bytes(),
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="vectornet_aedes_surveillance",
    run=_run,
    raw_dir=_RAW_DIR,
)
