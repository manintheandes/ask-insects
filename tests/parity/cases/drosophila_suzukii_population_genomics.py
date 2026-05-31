from pathlib import Path

from tests.parity.fixtures import ParityCase
from askinsects.sources.drosophila_suzukii_population_genomics import (
    fetch_drosophila_suzukii_population_genomics_records,
)

_RAW_DIR = "/tmp/ask-insects-parity/drosophila_suzukii_population_genomics"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"

_SEARCH_PAYLOAD = {"esearchresult": {"count": "2", "idlist": ["1289399", "1081763"]}}
_SUMMARY_PAYLOAD = {
    "result": {
        "uids": ["1289399", "1081763"],
        "1289399": {
            "project_acc": "PRJNA1289399",
            "project_title": "Pool-seq data from 3 Drosophila suzukii populations collected in Northern Portugal",
            "project_description": "Population genomic pool-seq data for invasive Drosophila suzukii.",
            "project_data_type": "Genome sequencing",
            "project_target_scope": "Multiisolate",
            "submitter_organization": "Test submitter",
            "registration_date": "2025-01-01",
        },
        "1081763": {
            "project_acc": "PRJNA1081763",
            "project_title": "Pool-seq data from 3 Drosophila suzukii populations from North Portugal",
            "project_description": "Genomic signatures of invasion.",
        },
    }
}


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    def fake_fetch(url):
        if "esearch.fcgi" in url:
            return _SEARCH_PAYLOAD
        if "esummary.fcgi" in url:
            return _SUMMARY_PAYLOAD
        raise AssertionError(url)

    r = fetch_drosophila_suzukii_population_genomics_records(
        raw_dir=raw_dir,
        retrieved_at=_RETRIEVED_AT,
        fetch_json=fake_fetch,
        limit=10,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="drosophila_suzukii_population_genomics",
    run=_run,
    raw_dir=_RAW_DIR,
)
