from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_mosquito_alert_source import FakeMosquitoAlertFetcher
from askinsects.sources.mosquito_alert import fetch_mosquito_alert_records

_RAW_DIR = "/tmp/ask-insects-parity/mosquito_alert_observations"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    r = fetch_mosquito_alert_records(
        raw_dir=raw_dir,
        occurrence_limit=1,
        occurrence_page_size=1,
        fetch_json=FakeMosquitoAlertFetcher(),
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="mosquito_alert_gbif",
    run=_run,
    raw_dir=_RAW_DIR,
)
