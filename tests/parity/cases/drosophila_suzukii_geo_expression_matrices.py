import gzip
from pathlib import Path

from tests.parity.fixtures import ParityCase
from askinsects.sources.drosophila_suzukii_geo_expression_matrices import (
    fetch_drosophila_suzukii_geo_expression_matrices_records,
)

_RETRIEVED_AT = "2026-05-29T00:00:00Z"
_ARTIFACT_DIR = "/tmp/ask-insects-parity/drosophila_suzukii_geo_expression_matrices"

_TABLE = (
    "test_id\tgene_id\tgene\tlocus\tsample_1\tsample_2\tstatus\tvalue_1\tvalue_2\tlog2(fold_change)\ttest_stat\tp_value\tq_value\tsignificant\n"
    "XLOC_1\tXLOC_1\tDS10_00000001\tscaffold1:1-2\tControl\tAcclimated\tOK\t56.4\t40.5\t-0.47\t-1.7\t0.004\t0.02\tyes\n"
    "XLOC_2\tXLOC_2\tDS10_00000002\tscaffold1:3-4\tControl\tAcclimated\tOK\t10\t11\t-inf\t0.2\t0.5\t0.9\tno\n"
)


def _run():
    artifact_dir = Path(_ARTIFACT_DIR)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    def fake_fetch_bytes(url):
        return gzip.compress(_TABLE.encode("utf-8"))

    r = fetch_drosophila_suzukii_geo_expression_matrices_records(
        artifact_dir=artifact_dir,
        fetch_bytes=fake_fetch_bytes,
        retrieved_at=_RETRIEVED_AT,
        max_rows_per_file=2,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="drosophila_suzukii_geo_expression_matrices",
    run=_run,
    raw_dir=_ARTIFACT_DIR,
)
