from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_inaturalist_source import observation_payload
from askinsects.sources.inaturalist import fetch_inaturalist_records

_RAW_DIR = "/tmp/ask-insects-parity/inaturalist_observations"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    r = fetch_inaturalist_records(
        ["Aedes aegypti"],
        raw_dir=raw_dir,
        place=None,
        observation_limit=1,
        page_size=10,
        delay_seconds=0,
        fetch_json=lambda url: observation_payload(),
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="inaturalist_api",
    run=_run,
    raw_dir=_RAW_DIR,
)
