from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_uniprot_proteins_source import PROTEOME_PAYLOAD, UNIPROTKB_PAYLOAD
from askinsects.sources.uniprot_proteins import fetch_uniprot_protein_records

_RAW_DIR = "/tmp/ask-insects-parity/uniprot_proteins"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    def fake_fetch_json(url: str) -> dict:
        if "/uniprotkb/search" in url:
            return UNIPROTKB_PAYLOAD
        if "/proteomes/search" in url:
            return PROTEOME_PAYLOAD
        raise AssertionError(url)

    r = fetch_uniprot_protein_records(
        raw_dir=raw_dir,
        fetch_json=fake_fetch_json,
        retrieved_at=_RETRIEVED_AT,
        protein_limit=25,
        proteome_limit=5,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="aedes_uniprot_proteins",
    run=_run,
    raw_dir=_RAW_DIR,
)
