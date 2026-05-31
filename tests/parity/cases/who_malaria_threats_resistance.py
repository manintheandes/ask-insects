import json
from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_who_malaria_threats_resistance_source import SAMPLE_CSV
from askinsects.sources.who_malaria_threats_resistance import fetch_who_malaria_threats_resistance_records

_RAW_DIR = "/tmp/ask-insects-parity/who_malaria_threats_resistance"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    def fake_fetch(url: str) -> bytes:
        if "format=csv" in url:
            return SAMPLE_CSV.encode("utf-8")
        return json.dumps({"value": []}).encode("utf-8")

    r = fetch_who_malaria_threats_resistance_records(
        raw_dir=raw_dir,
        fetch_bytes=fake_fetch,
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="who_malaria_threats_resistance_audit",
    run=_run,
    raw_dir=_RAW_DIR,
)
