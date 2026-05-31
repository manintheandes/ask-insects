from pathlib import Path
from tests.parity.fixtures import ParityCase
from tests.test_expression_omics_source import GEO_ESEARCH, GEO_ESUMMARY, SRA_ESEARCH, SRA_ESUMMARY
from askinsects.sources.expression_omics import fetch_expression_omics_records

_RAW_DIR = "/tmp/ask-insects-parity/expression_omics"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _fake_fetch_json(url):
    if "db=gds" in url and "esearch.fcgi" in url:
        return GEO_ESEARCH
    if "db=gds" in url and "esummary.fcgi" in url:
        return GEO_ESUMMARY
    if "db=sra" in url and "esearch.fcgi" in url:
        return SRA_ESEARCH
    if "db=sra" in url and "esummary.fcgi" in url:
        return SRA_ESUMMARY
    raise AssertionError(f"unexpected URL: {url}")


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)
    r = fetch_expression_omics_records(
        raw_dir=raw_dir,
        fetch_json=_fake_fetch_json,
        retrieved_at=_RETRIEVED_AT,
        geo_limit=1,
        sra_limit=1,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="aedes_expression_omics",
    run=_run,
    raw_dir=_RAW_DIR,
)
