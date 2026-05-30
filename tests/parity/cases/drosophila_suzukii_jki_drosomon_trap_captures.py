from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_drosophila_suzukii_jki_drosomon_trap_captures_source import (
    DATASET_FIXTURE,
    FetchBody,
    zipped_jki_fixture,
)
from askinsects.sources.drosophila_suzukii_jki_drosomon_trap_captures import (
    fetch_drosophila_suzukii_jki_drosomon_trap_capture_records,
)

_RAW_DIR = "/tmp/ask-insects-parity/drosophila_suzukii_jki_drosomon_trap_captures"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    def fetch_body(url):
        return FetchBody(
            body=zipped_jki_fixture(),
            content_type="application/zip",
            status=200,
            pow_challenge={"attempted": True, "solved": True, "difficulty": 16},
        )

    r = fetch_drosophila_suzukii_jki_drosomon_trap_capture_records(
        raw_dir=raw_dir,
        fetch_json=lambda url: DATASET_FIXTURE,
        fetch_body=fetch_body,
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="drosophila_suzukii_jki_drosomon_trap_captures",
    run=_run,
    raw_dir=_RAW_DIR,
)
