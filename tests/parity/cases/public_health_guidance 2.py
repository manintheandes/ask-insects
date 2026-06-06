from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_public_health_source import HTML
from askinsects.sources.public_health import fetch_public_health_guidance_records

_RAW_DIR = "/tmp/ask-insects-parity/public_health_guidance"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    r = fetch_public_health_guidance_records(
        [
            {
                "organization": "CDC",
                "url": "https://www.cdc.gov/example",
                "topic": "integrated mosquito management",
            }
        ],
        raw_dir=raw_dir,
        fetch_text=lambda url: HTML,
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="aedes_public_health_guidance",
    run=_run,
    raw_dir=_RAW_DIR,
)
