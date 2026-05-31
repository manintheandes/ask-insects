from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_ncbi_biosample_source import biosample_summary_payload
from askinsects.sources.ncbi_biosample import fetch_ncbi_biosample_records

_RAW_DIR = "/tmp/ask-insects-parity/ncbi_biosamples"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    def fake_fetch_json(url: str):
        if "esearch.fcgi" in url:
            return {"esearchresult": {"count": "1", "idlist": ["59867395"]}}
        return biosample_summary_payload()

    r = fetch_ncbi_biosample_records(
        species="Aedes aegypti",
        raw_dir=raw_dir,
        limit=1,
        page_size=1,
        delay_seconds=0,
        fetch_json=fake_fetch_json,
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="ncbi_biosamples",
    run=_run,
    raw_dir=_RAW_DIR,
)
