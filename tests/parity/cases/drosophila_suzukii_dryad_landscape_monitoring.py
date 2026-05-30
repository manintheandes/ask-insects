from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_drosophila_suzukii_dryad_landscape_monitoring_source import (
    landscape_fetch_json,
    landscape_fetch_text,
    RETRIEVED_AT,
)
from askinsects.sources.drosophila_suzukii_dryad_landscape_monitoring import (
    fetch_drosophila_suzukii_dryad_landscape_monitoring_records,
)

# Fixed raw_dir so raw_path/locator are stable; _serialize redacts it to
# "<raw_dir>" (via CASE.raw_dir below) so the golden is machine-independent.
_RAW_DIR = "/tmp/ask-insects-parity/drosophila_suzukii_dryad_landscape_monitoring"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)
    r = fetch_drosophila_suzukii_dryad_landscape_monitoring_records(
        raw_dir=raw_dir,
        fetch_json=landscape_fetch_json,
        fetch_text=landscape_fetch_text,
        retrieved_at=RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="drosophila_suzukii_dryad_landscape_monitoring",
    run=_run,
    raw_dir=_RAW_DIR,
)
