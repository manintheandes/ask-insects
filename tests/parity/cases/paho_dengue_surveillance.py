from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_paho_surveillance_source import CORE_INDICATORS_HTML, DASHBOARD_HTML, REPORT_HTML, _core_indicators_zip
from askinsects.sources.paho_surveillance import fetch_paho_dengue_surveillance_records

_RAW_DIR = "/tmp/ask-insects-parity/paho_dengue_surveillance"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    def fake_fetch_text(url):
        if "dashboard" in url:
            return DASHBOARD_HTML
        if "core-indicators" in url:
            return CORE_INDICATORS_HTML
        return REPORT_HTML

    def fake_fetch_bytes(url):
        if url.endswith(".zip"):
            return _core_indicators_zip()
        raise AssertionError(f"unexpected byte fetch {url}")

    r = fetch_paho_dengue_surveillance_records(
        [{"url": "https://example.org/report", "landing_url": "https://example.org/report", "organization": "PAHO/WHO", "topic": "custom PAHO dengue surveillance report"}],
        raw_dir=raw_dir,
        fetch_text=fake_fetch_text,
        fetch_bytes=fake_fetch_bytes,
        retrieved_at=_RETRIEVED_AT,
        dashboard_pages=["https://example.org/dashboard"],
        core_indicator_pages=["https://opendata.paho.org/core-indicators"],
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="aedes_paho_dengue_surveillance",
    run=_run,
    raw_dir=_RAW_DIR,
)
