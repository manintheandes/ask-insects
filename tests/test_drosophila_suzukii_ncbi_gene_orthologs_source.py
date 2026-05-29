import gzip
import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.drosophila_suzukii_ncbi_gene_orthologs import (
    DROSOPHILA_SUZUKII_NCBI_GENE_ORTHOLOGS_SOURCE_ID,
    fetch_drosophila_suzukii_ncbi_gene_ortholog_records,
)


class DrosophilaSuzukiiNcbiGeneOrthologsSourceTests(unittest.TestCase):
    def test_fetch_builds_ortholog_records_and_joins_current_gene_id(self):
        data = "\n".join(
            [
                "#tax_id\tGeneID\trelationship\tOther_tax_id\tOther_GeneID",
                "7227\t40650\tOrtholog\t28584\t108011252",
                "28584\t108011252\tOrtholog\t7217\t999",
                "9606\t1\tOrtholog\t10090\t2",
            ]
        ).encode()

        def fake_fetch_bytes(url, max_bytes):
            return gzip.compress(data)

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
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
                            retrieved_at="2026-05-29T00:00:00Z",
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

            result = fetch_drosophila_suzukii_ncbi_gene_ortholog_records(
                artifact_dir=artifact_dir,
                fetch_bytes=fake_fetch_bytes,
                retrieved_at="2026-05-29T00:00:00Z",
            )

        self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_NCBI_GENE_ORTHOLOGS_SOURCE_ID)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.swd_gene_count, 1)
        self.assertEqual(result.partner_taxon_count, 2)
        self.assertEqual(result.matched_gene_record_count, 1)
        self.assertEqual(result.records[0].lane, "genome_features")
        self.assertIn("Orco", result.records[0].text)
        self.assertTrue(result.records[0].payload["current_id_mapping"])

    def test_download_failure_becomes_gap(self):
        def fake_fetch_bytes(url, max_bytes):
            raise RuntimeError("offline")

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_ncbi_gene_ortholog_records(
                artifact_dir=Path(tmpdir) / "mosquito-v1",
                fetch_bytes=fake_fetch_bytes,
                retrieved_at="2026-05-29T00:00:00Z",
            )

        self.assertEqual(result.records, [])
        self.assertEqual(result.gaps[0]["reason"], "swd_ncbi_gene_orthologs_download_failed")


if __name__ == "__main__":
    unittest.main()
