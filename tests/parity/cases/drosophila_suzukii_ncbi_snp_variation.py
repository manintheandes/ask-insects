from pathlib import Path

from tests.parity.fixtures import ParityCase
from askinsects.sources.drosophila_suzukii_ncbi_snp_variation import (
    fetch_drosophila_suzukii_ncbi_snp_variation_records,
)

_RAW_DIR = "/tmp/ask-insects-parity/drosophila_suzukii_ncbi_snp_variation"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    def fake_fetch(url):
        return {"esearchresult": {"count": "0", "idlist": []}}

    r = fetch_drosophila_suzukii_ncbi_snp_variation_records(
        raw_dir=raw_dir,
        fetch_json=fake_fetch,
        retrieved_at=_RETRIEVED_AT,
        limit=10,
        page_size=10,
        delay_seconds=0,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="drosophila_suzukii_ncbi_snp_variation",
    run=_run,
    raw_dir=_RAW_DIR,
)
