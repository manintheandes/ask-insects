from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_cdc_dengue_surveillance_source import CDC_HTML, CONFIG_JSON, EPI_CSV, JURISDICTION_CSV
from askinsects.sources.cdc_dengue_surveillance import fetch_cdc_dengue_surveillance_records

_RAW_DIR = "/tmp/ask-insects-parity/cdc_dengue_surveillance"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    def fake_fetch(url):
        if url.endswith("current-data.html"):
            return CDC_HTML
        if url.endswith("current-year-tabs-updated.json"):
            return CONFIG_JSON
        if url.endswith("Cases_by_Jurisdiction_Current.csv"):
            return JURISDICTION_CSV
        if url.endswith("Epi_Curve_Current.csv"):
            return EPI_CSV
        raise AssertionError(f"unexpected URL {url}")

    r = fetch_cdc_dengue_surveillance_records(
        [
            {
                "organization": "CDC",
                "url": "https://www.cdc.gov/dengue/data-research/facts-stats/current-data.html",
                "page_kind": "current_year",
                "topic": "current dengue surveillance",
            }
        ],
        raw_dir=raw_dir,
        fetch_text=fake_fetch,
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="aedes_cdc_dengue_surveillance",
    run=_run,
    raw_dir=_RAW_DIR,
)
