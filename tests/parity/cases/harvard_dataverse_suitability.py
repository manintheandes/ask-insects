from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_harvard_dataverse_suitability_source import dataset_detail, search_payload
from askinsects.sources.harvard_dataverse_suitability import fetch_harvard_dataverse_suitability_records

_RAW_DIR = "/tmp/ask-insects-parity/harvard_dataverse_suitability"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    def fake_json(url: str) -> dict:
        if "/api/search?" in url:
            return search_payload()
        if "/api/datasets/:persistentId/" in url:
            return dataset_detail()
        raise AssertionError(url)

    r = fetch_harvard_dataverse_suitability_records(
        raw_dir=raw_dir,
        queries=('"Aedes aegypti" suitability',),
        per_page=10,
        dataset_limit=2,
        fetch_json=fake_json,
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="harvard_dataverse_aedes_suitability",
    run=_run,
    raw_dir=_RAW_DIR,
)
