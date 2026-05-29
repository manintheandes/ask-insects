from __future__ import annotations

import gzip
import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.drosophila_suzukii_genome_files import (
    DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID,
    fetch_drosophila_suzukii_genome_file_records,
)


RETRIEVED_AT = "2026-05-28T00:00:00Z"
ASSEMBLY_ACCESSION = "GCF_043229965.1"
FTP_PATH = "ftp://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/043/229/965/GCF_043229965.1_CBGP_Dsuzu_IsoJpt1.0"


def write_swd_assembly_fixture(artifact_dir: Path) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.upsert_records(
        [
            EvidenceRecord(
                record_id=f"swd:assembly:{ASSEMBLY_ACCESSION}",
                lane="genome_assemblies",
                source="drosophila_suzukii_deep_sources",
                title="Drosophila suzukii assembly GCF_043229965.1: CBGP_Dsuzu_IsoJpt1.0",
                text="NCBI Assembly record GCF_043229965.1 for Drosophila suzukii.",
                species="Drosophila suzukii",
                url=f"https://www.ncbi.nlm.nih.gov/assembly/{ASSEMBLY_ACCESSION}",
                media_url=None,
                provenance=Provenance(
                    source_id="drosophila_suzukii_deep_sources",
                    locator="raw/drosophila_suzukii_deep_sources/ncbi/ncbi_assembly_esummary.json#result/1",
                    retrieved_at=RETRIEVED_AT,
                    license="NCBI public metadata",
                    source_url=f"https://www.ncbi.nlm.nih.gov/assembly/{ASSEMBLY_ACCESSION}",
                ),
                payload={
                    "accession": ASSEMBLY_ACCESSION,
                    "assembly_name": "CBGP_Dsuzu_IsoJpt1.0",
                    "biosample": "SAMN41502703",
                    "raw_summary": {
                        "assemblyaccession": ASSEMBLY_ACCESSION,
                        "assemblyname": "CBGP_Dsuzu_IsoJpt1.0",
                        "assemblystatus": "Chromosome",
                        "ftppath_refseq": FTP_PATH,
                    },
                },
            )
        ]
    )


def fake_fetch_bytes(url: str, max_bytes: int) -> bytes:
    if url.endswith("_genomic.gff.gz"):
        text = "\n".join(
            [
                "##gff-version 3",
                "NC_1\tRefSeq\tgene\t100\t900\t.\t+\t.\tID=gene-DS10;Name=orco;gene=orco;description=odorant receptor coreceptor",
                "NC_1\tRefSeq\tmRNA\t100\t900\t.\t+\t.\tID=rna-XM_1;Parent=gene-DS10;Name=orco transcript;product=odorant receptor coreceptor transcript",
                "NC_1\tRefSeq\tCDS\t150\t850\t.\t+\t0\tID=cds-XP_1;Parent=rna-XM_1;Name=XP_1;product=odorant receptor coreceptor;protein_id=XP_1",
            ]
        ) + "\n"
        return gzip.compress(text.encode("utf-8"))
    if url.endswith("_protein.faa.gz"):
        return gzip.compress(b">XP_1 odorant receptor coreceptor [Drosophila suzukii]\nMNNNN\n")
    raise AssertionError(url)


class DrosophilaSuzukiiGenomeFilesTests(unittest.TestCase):
    def test_fetch_downloads_and_parses_swd_gff_and_proteins(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_swd_assembly_fixture(artifact_dir)

            result = fetch_drosophila_suzukii_genome_file_records(
                artifact_dir,
                assembly_accession=ASSEMBLY_ACCESSION,
                retrieved_at=RETRIEVED_AT,
                fetch_bytes_fn=fake_fetch_bytes,
            )

            self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID)
            self.assertFalse(result.gaps)
            self.assertGreaterEqual(result.lane_counts["genes"], 1)
            self.assertGreaterEqual(result.lane_counts["transcripts"], 1)
            self.assertGreaterEqual(result.lane_counts["proteins"], 1)
            gene = next(record for record in result.records if record.lane == "genes")
            self.assertEqual(gene.source, DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID)
            self.assertEqual(gene.species, "Drosophila suzukii")
            self.assertIn("orco", gene.text)
            self.assertTrue(gene.record_id.startswith("swd:genome_files:gene:"))


if __name__ == "__main__":
    unittest.main()
