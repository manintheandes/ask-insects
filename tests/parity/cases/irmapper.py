from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_irmapper_source import IRMAPPER_ROWS
from askinsects.sources.irmapper import fetch_irmapper_records

_RAW_DIR = "/tmp/ask-insects-parity/irmapper"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    r = fetch_irmapper_records(
        raw_dir=raw_dir,
        fetch_json=lambda url: IRMAPPER_ROWS,
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="irmapper_aedes",
    run=_run,
    raw_dir=_RAW_DIR,
)
