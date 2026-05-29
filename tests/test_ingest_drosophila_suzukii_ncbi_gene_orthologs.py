import tempfile
import unittest
from pathlib import Path
from unittest import mock

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.drosophila_suzukii_ncbi_gene_orthologs import DrosophilaSuzukiiNcbiGeneOrthologsResult
from scripts.ingest_drosophila_suzukii_ncbi_gene_orthologs import ingest_drosophila_suzukii_ncbi_gene_orthologs


class IngestDrosophilaSuzukiiNcbiGeneOrthologsTests(unittest.TestCase):
    def test_ingest_replaces_gene_ortholog_source_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch_records(**kwargs):
                return DrosophilaSuzukiiNcbiGeneOrthologsResult(
                    source_id="drosophila_suzukii_ncbi_gene_orthologs",
                    records=[
                        EvidenceRecord(
                            record_id="swd_ncbi_gene_ortholog:108011252:7227:40650:2",
                            lane="genome_features",
                            source="drosophila_suzukii_ncbi_gene_orthologs",
                            title="Drosophila suzukii NCBI Gene ortholog: Orco",
                            text="NCBI Gene ortholog row for Drosophila suzukii GeneID 108011252 links to Drosophila melanogaster GeneID 40650.",
                            species="Drosophila suzukii",
                            url="https://www.ncbi.nlm.nih.gov/gene/108011252",
                            media_url=None,
                            provenance=Provenance(
                                source_id="drosophila_suzukii_ncbi_gene_orthologs",
                                locator="raw/gene_orthologs.gz#line/2",
                                retrieved_at="2026-05-29T00:00:00Z",
                            ),
                            payload={"atom_type": "ncbi_gene_ortholog_pair", "relationship": "Ortholog"},
                        )
                    ],
                    gaps=[],
                    raw_artifacts=["raw/gene_orthologs.gz"],
                    requested_urls=["https://ftp.ncbi.nlm.nih.gov/gene/DATA/gene_orthologs.gz"],
                    fetched_pair_count=1,
                    swd_gene_count=1,
                    partner_taxon_count=1,
                    relationship_counts={"Ortholog": 1},
                    matched_gene_record_count=1,
                )

            with mock.patch(
                "scripts.ingest_drosophila_suzukii_ncbi_gene_orthologs.fetch_drosophila_suzukii_ncbi_gene_ortholog_records",
                fake_fetch_records,
            ):
                result = ingest_drosophila_suzukii_ncbi_gene_orthologs(
                    artifact_dir=artifact_dir,
                    retrieved_at="2026-05-29T00:00:00Z",
                )

            self.assertTrue(result["ok"])
            self.assertEqual(result["record_count"], 1)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            counts = {
                (row["source"], row["lane"]): row["n"]
                for row in index.sql(
                    "select source, lane, count(*) as n from records group by source, lane order by source, lane",
                    limit=100,
                )
            }
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 4)
            self.assertEqual(counts[("drosophila_suzukii_ncbi_gene_orthologs", "genome_features")], 1)


if __name__ == "__main__":
    unittest.main()
