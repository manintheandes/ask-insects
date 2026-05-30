from pathlib import Path

from tests.parity.fixtures import ParityCase
from askinsects.sources.drosophila_suzukii_ncbi_marker_review import (
    fetch_drosophila_suzukii_ncbi_marker_review_records,
)

_RAW_DIR = "/tmp/ask-insects-parity/drosophila_suzukii_ncbi_marker_review"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _fake_fetch(url):
    if "esearch.fcgi" in url:
        return {"esearchresult": {"count": "2", "idlist": ["1", "2"]}}
    return {
        "result": {
            "uids": ["1", "2"],
            "1": {
                "uid": "1",
                "title": "Drosophila suzukii cytochrome oxidase subunit I gene",
                "accessionversion": "PV000001.1",
                "slen": "658",
            },
            "2": {
                "uid": "2",
                "title": "Drosophila suzukii internal transcribed spacer 2",
                "accessionversion": "PV000002.1",
                "slen": "420",
            },
        }
    }


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    r = fetch_drosophila_suzukii_ncbi_marker_review_records(
        raw_dir=raw_dir,
        fetch_json=_fake_fetch,
        retrieved_at=_RETRIEVED_AT,
        max_results=10,
        page_size=10,
        delay_seconds=0,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="drosophila_suzukii_ncbi_marker_review",
    run=_run,
    raw_dir=_RAW_DIR,
)
