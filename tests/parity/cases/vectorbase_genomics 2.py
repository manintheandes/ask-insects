from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_vectorbase_genomics_source import write_fake_vectorbase_files
from askinsects.sources.vectorbase_genomics import fetch_vectorbase_genomics_records

_RAW_DIR = "/tmp/ask-insects-parity/vectorbase_genomics"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)
    files_dir = raw_dir / "files"
    file_urls = write_fake_vectorbase_files(files_dir)

    r = fetch_vectorbase_genomics_records(
        raw_dir=raw_dir / "raw",
        file_urls=file_urls,
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="vectorbase_aedes_genomics",
    run=_run,
    raw_dir=_RAW_DIR,
)
