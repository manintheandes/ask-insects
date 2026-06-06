from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_pathogen_taxonomy_source import taxonomy_payload
from askinsects.sources.pathogen_taxonomy import fetch_pathogen_taxonomy_records

_RAW_DIR = "/tmp/ask-insects-parity/pathogen_taxonomy"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    r = fetch_pathogen_taxonomy_records(
        raw_dir=raw_dir,
        fetch_json=lambda url: taxonomy_payload(),
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="aedes_pathogen_taxonomy",
    run=_run,
    raw_dir=_RAW_DIR,
)
