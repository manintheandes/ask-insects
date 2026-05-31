import hashlib
from pathlib import Path
from unittest import mock

import askinsects.sources.drosophila_suzukii_figshare_mk_selection as _mk
from tests.parity.fixtures import ParityCase
from tests.test_drosophila_suzukii_figshare_mk_selection_source import TABLE
from askinsects.sources.drosophila_suzukii_figshare_mk_selection import (
    fetch_drosophila_suzukii_figshare_mk_selection_records,
)

_ARTIFACT_DIR = "/tmp/ask-insects-parity/figshare_mk_artifact"
# The adapter writes to artifact_dir / "raw" / source_id / filename
_RAW_DIR = f"{_ARTIFACT_DIR}/raw/drosophila_suzukii_figshare_mk_selection"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"
_DATA = TABLE.encode("utf-8")
_MD5 = hashlib.md5(_DATA).hexdigest()


def _run():
    artifact_dir = Path(_ARTIFACT_DIR)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    with mock.patch.object(_mk, "FIGSHARE_FILE_MD5", _MD5):
        r = fetch_drosophila_suzukii_figshare_mk_selection_records(
            artifact_dir=artifact_dir,
            fetch_bytes=lambda url: _DATA,
            retrieved_at=_RETRIEVED_AT,
        )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="drosophila_suzukii_figshare_mk_selection",
    run=_run,
    raw_dir=_RAW_DIR,
)
