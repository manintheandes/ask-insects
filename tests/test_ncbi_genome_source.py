import json
import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.sources.ncbi_genome import NCBI_GENOME_SOURCE_ID, fetch_ncbi_genome_records


def write_fake_ncbi_package(root: Path) -> Path:
    package_dir = root / "ncbi-package"
    data_dir = package_dir / "ncbi_dataset" / "data"
    assembly_dir = data_dir / "GCF_002204515.2"
    assembly_dir.mkdir(parents=True)
    assembly_report = {
        "accession": "GCF_002204515.2",
        "assemblyInfo": {
            "assemblyName": "AaegL5.0",
            "assemblyLevel": "Chromosome",
            "assemblyStatus": "current",
            "bioprojectAccession": "PRJNA392114",
        },
        "organism": {
            "organismName": "Aedes aegypti",
            "taxId": 7159,
            "commonName": "yellow fever mosquito",
        },
        "annotationInfo": {
            "name": "NCBI RefSeq Annotation",
            "releaseDate": "2024-01-01",
        },
    }
    (data_dir / "assembly_data_report.jsonl").write_text(json.dumps(assembly_report) + "\n", encoding="utf-8")
    (assembly_dir / "genomic.gff").write_text(
        "\n".join(
            [
                "##gff-version 3",
                "NC_035107.1\tRefSeq\tgene\t100\t900\t.\t+\t.\tID=gene-LOC5566000;Name=orco;gene=orco;gene_biotype=protein_coding;description=odorant receptor coreceptor",
                "NC_035107.1\tRefSeq\tmRNA\t100\t900\t.\t+\t.\tID=rna-XM_001;Parent=gene-LOC5566000;Name=orco transcript;product=odorant receptor coreceptor transcript",
                "NC_035107.1\tRefSeq\tCDS\t150\t850\t.\t+\t0\tID=cds-XP_001;Parent=rna-XM_001;Name=XP_001;product=odorant receptor coreceptor;protein_id=XP_001",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (assembly_dir / "protein.faa").write_text(
        ">XP_001 odorant receptor coreceptor [Aedes aegypti]\nMNNNNNNNNN\n"
        ">XP_002 gustatory receptor protein [Aedes aegypti]\nMQQQQQ\n",
        encoding="utf-8",
    )
    return package_dir


class NCBIGenomeSourceTests(unittest.TestCase):
    def test_fetch_ncbi_genome_records_normalizes_package_atoms(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            package_dir = write_fake_ncbi_package(Path(tmpdir))
            result = fetch_ncbi_genome_records(
                package_dir=package_dir,
                assembly_accession="GCF_002204515.2",
                retrieved_at="2026-05-23T00:00:00Z",
            )

            self.assertEqual(result.source_id, NCBI_GENOME_SOURCE_ID)
            self.assertFalse(result.gaps)
            self.assertEqual(result.assembly_accession, "GCF_002204515.2")
            self.assertTrue(result.raw_artifacts)

            lanes = {record.lane for record in result.records}
            self.assertIn("genome_assemblies", lanes)
            self.assertIn("genes", lanes)
            self.assertIn("transcripts", lanes)
            self.assertIn("genome_features", lanes)
            self.assertIn("proteins", lanes)

            assembly = next(record for record in result.records if record.lane == "genome_assemblies")
            self.assertEqual(assembly.source, NCBI_GENOME_SOURCE_ID)
            self.assertEqual(assembly.species, "Aedes aegypti")
            self.assertIn("AaegL5.0", assembly.text)
            self.assertIn("assembly_data_report.jsonl", assembly.provenance.locator)
            self.assertEqual(assembly.payload["assembly_report"]["accession"], "GCF_002204515.2")

            gene = next(record for record in result.records if record.lane == "genes")
            self.assertEqual(gene.record_id, "ncbi:gene:gene-LOC5566000")
            self.assertIn("odorant receptor coreceptor", gene.text)
            self.assertIn("genomic.gff#line/2", gene.provenance.locator)
            self.assertEqual(gene.payload["gff_attributes"]["gene"], "orco")

            protein = next(record for record in result.records if record.record_id == "ncbi:protein:XP_002")
            self.assertEqual(protein.lane, "proteins")
            self.assertIn("gustatory receptor", protein.text)
            self.assertEqual(protein.payload["sequence_length"], 6)

    def test_fetch_ncbi_genome_records_records_gap_when_optional_proteins_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            package_dir = write_fake_ncbi_package(Path(tmpdir))
            (package_dir / "ncbi_dataset" / "data" / "GCF_002204515.2" / "protein.faa").unlink()

            result = fetch_ncbi_genome_records(
                package_dir=package_dir,
                assembly_accession="GCF_002204515.2",
                retrieved_at="2026-05-23T00:00:00Z",
            )

            self.assertTrue(any(gap["lane"] == "proteins" for gap in result.gaps))
            self.assertTrue(any(record.lane == "genes" for record in result.records))

    def test_ncbi_genome_payloads_are_queryable_from_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            package_dir = write_fake_ncbi_package(Path(tmpdir))
            result = fetch_ncbi_genome_records(
                package_dir=package_dir,
                assembly_accession="GCF_002204515.2",
                retrieved_at="2026-05-23T00:00:00Z",
            )
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(result.records)

            rows = index.sql(
                """
                select record_id, json_extract(payload_json, '$.gff_attributes.gene') as gene_symbol
                from record_payloads
                where record_id='ncbi:gene:gene-LOC5566000'
                """
            )

            self.assertEqual(rows[0]["gene_symbol"], "orco")


if __name__ == "__main__":
    unittest.main()
