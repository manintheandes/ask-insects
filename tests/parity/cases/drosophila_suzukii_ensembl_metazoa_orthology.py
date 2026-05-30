import gzip
from pathlib import Path

from tests.parity.fixtures import ParityCase
from askinsects.sources.drosophila_suzukii_ensembl_metazoa_orthology import (
    DMEL_HOMOLOG_FILE,
    GENE_ARCHIVE_FILE,
    GENEID_XREF_FILE,
    GENE_MAIN_FILE,
    MAPPING_SESSION_FILE,
    STABLE_ID_EVENT_FILE,
    fetch_drosophila_suzukii_ensembl_metazoa_orthology_records,
)

_RETRIEVED_AT = "2026-05-29T00:00:00Z"
_ARTIFACT_DIR = "/tmp/ask-insects-parity/drosophila_suzukii_ensembl_metazoa_orthology"


def _gz(text: str) -> bytes:
    return gzip.compress(text.encode("utf-8"))


def _fake_fetch(url: str, max_bytes: int) -> bytes:
    filename = url.rsplit("/", 1)[-1]
    if filename == GENE_MAIN_FILE:
        return _gz(
            "2\tprotein_coding\t\\N\t56.44\tEnsembl Metazoa\tGeneID_108018010\tDpit47\tRefSeq\t16534757\tDNA polymerase interacting tpr containing protein of 47kD\tNC_089020.1\t-1\t16533445\t1\t\\N\t1\t1\t1\n"
        )
    if filename == GENEID_XREF_FILE:
        return _gz("2\t\\N\t108018010\t108018010\n")
    if filename == DMEL_HOMOLOG_FILE:
        return _gz(
            "2R\t2\t6662118\t6660645\tortholog_one2one\tmelanogaster group\t91.1616\t100\tFBgn0266518\tFBpp0085479\tXP_016940857.2\tDpit47\t91.1616\t1\n"
        )
    if filename in {GENE_ARCHIVE_FILE, STABLE_ID_EVENT_FILE, MAPPING_SESSION_FILE}:
        return _gz("")
    raise AssertionError(url)


def _run():
    artifact_dir = Path(_ARTIFACT_DIR)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    r = fetch_drosophila_suzukii_ensembl_metazoa_orthology_records(
        artifact_dir=artifact_dir,
        fetch_bytes=_fake_fetch,
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="drosophila_suzukii_ensembl_metazoa_orthology",
    run=_run,
    raw_dir=_ARTIFACT_DIR,
)
