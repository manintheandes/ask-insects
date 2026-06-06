from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_who_dengue_surveillance_source import DASHBOARD_HTML, WER_HTML, WPRO_HTML
from askinsects.sources.who_dengue_surveillance import fetch_who_dengue_surveillance_records, who_dengue_source_spec

_RAW_DIR = "/tmp/ask-insects-parity/who_dengue_surveillance"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    def fake_fetch(url):
        if "wer" in url:
            return WER_HTML
        if "dashboard" in url:
            return DASHBOARD_HTML
        return WPRO_HTML

    sources = [
        who_dengue_source_spec("https://www.who.int/westernpacific/wpro-emergencies/surveillance/dengue", index=1),
        who_dengue_source_spec("https://www.who.int/publications/i/item/who-wer10052-665-678", index=2),
        who_dengue_source_spec("https://data.wpro.who.int/dashboard", index=3),
    ]

    r = fetch_who_dengue_surveillance_records(
        sources,
        raw_dir=raw_dir,
        fetch_text=fake_fetch,
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="aedes_who_dengue_surveillance",
    run=_run,
    raw_dir=_RAW_DIR,
)
