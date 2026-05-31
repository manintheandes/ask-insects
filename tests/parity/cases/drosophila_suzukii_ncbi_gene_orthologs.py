import gzip
from pathlib import Path

from tests.parity.fixtures import ParityCase
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.drosophila_suzukii_ncbi_gene_orthologs import (
    fetch_drosophila_suzukii_ncbi_gene_ortholog_records,
)

_RETRIEVED_AT = "2026-05-29T00:00:00Z"
_ARTIFACT_DIR = "/tmp/ask-insects-parity/drosophila_suzukii_ncbi_gene_orthologs"

_ORTHOLOGS_DATA = "\n".join(
    [
        "#tax_id\tGeneID\trelationship\tOther_tax_id\tOther_GeneID",
        "7227\t40650\tOrtholog\t28584\t108011252",
        "28584\t108011252\tOrtholog\t7217\t999",
        "9606\t1\tOrtholog\t10090\t2",
    ]
).encode()


def _fake_fetch_bytes(url, max_bytes):
    return gzip.compress(_ORTHOLOGS_DATA)


def _run():
    # gene_orthologs adapter reads from SourceIndex, so we need a real artifact_dir
    artifact_dir = Path(_ARTIFACT_DIR)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.upsert_records(
        [
            EvidenceRecord(
                record_id="swd:genome_files:gene:gene-Orco",
                lane="genes",
                source="drosophila_suzukii_genome_files",
                title="Drosophila suzukii gene Orco",
                text="NCBI genome gene Orco for Drosophila suzukii.",
                species="Drosophila suzukii",
                url="https://www.ncbi.nlm.nih.gov/datasets/genome/GCF_043229965.1/",
                media_url=None,
                provenance=Provenance(
                    source_id="drosophila_suzukii_genome_files",
                    locator="raw/genomic.gff#line/1",
                    retrieved_at=_RETRIEVED_AT,
                ),
                payload={
                    "gff_attributes": {
                        "Dbxref": "GeneID:108011252",
                        "gene": "Orco",
                        "description": "odorant receptor co-receptor",
                    }
                },
            )
        ]
    )
    r = fetch_drosophila_suzukii_ncbi_gene_ortholog_records(
        artifact_dir=artifact_dir,
        fetch_bytes=_fake_fetch_bytes,
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="drosophila_suzukii_ncbi_gene_orthologs",
    run=_run,
    raw_dir=_ARTIFACT_DIR,
)
