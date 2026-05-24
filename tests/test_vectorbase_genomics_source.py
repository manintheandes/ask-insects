import gzip
import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.sources.vectorbase_genomics import (
    VECTORBASE_GENOMICS_SOURCE_ID,
    fetch_vectorbase_genomics_records,
)


def write_fake_vectorbase_files(root: Path) -> dict[str, str]:
    root.mkdir(parents=True, exist_ok=True)
    gff = root / "VectorBase-68_AaegyptiLVP_AGWG.gff"
    gff.write_text(
        "\n".join(
            [
                "##gff-version 3",
                "AaegL5_1\tVectorBase\tgene\t100\t900\t.\t+\t.\tID=AAEL000001;Name=AAEL000001;description=odorant receptor coreceptor",
                "AaegL5_1\tVectorBase\tmRNA\t100\t900\t.\t+\t.\tID=AAEL000001-RA;Parent=AAEL000001;Name=AAEL000001-RA;product=odorant receptor coreceptor transcript",
                "bad\trow",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    proteins = root / "VectorBase-68_AaegyptiLVP_AGWG_AnnotatedProteins.fasta"
    proteins.write_text(
        ">AAEL000001-PA | transcript=AAEL000001-RA | gene=AAEL000001 | organism=Aedes_aegypti_LVP_AGWG | gene_product=odorant receptor coreceptor | length=478\n"
        "MADEUPSEQ\n",
        encoding="utf-8",
    )
    gaf = root / "VectorBase-CURRENT_AaegyptiLVP_AGWG_GO.gaf.gz"
    with gzip.open(gaf, "wt", encoding="utf-8") as handle:
        handle.write("!gaf-version: 2.2\n")
        handle.write(
            "VectorBase\tAAEL000001\torco\t\tGO:0004984\tPMID:1\tIEA\t\tF\todorant receptor activity\tOrco\tprotein\ttaxon:7159\t20260524\tVectorBase\t\tAAEL000001-PA\n"
        )
    return {
        "gff": gff.as_uri(),
        "proteins": proteins.as_uri(),
        "go": gaf.as_uri(),
    }


class VectorBaseGenomicsSourceTests(unittest.TestCase):
    def test_fetch_vectorbase_genomics_records_parses_download_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            file_urls = write_fake_vectorbase_files(root)
            result = fetch_vectorbase_genomics_records(
                raw_dir=root / "raw",
                file_urls=file_urls,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertEqual(result.source_id, VECTORBASE_GENOMICS_SOURCE_ID)
            self.assertEqual(result.release, "Current_Release")
            lanes = {record.lane for record in result.records}
            self.assertIn("genes", lanes)
            self.assertIn("transcripts", lanes)
            self.assertIn("proteins", lanes)
            self.assertIn("genome_features", lanes)
            self.assertGreaterEqual(len(result.raw_artifacts), 3)
            gene = next(record for record in result.records if record.lane == "genes")
            self.assertEqual(gene.source, "vectorbase_aedes_genomics")
            self.assertEqual(gene.species, "Aedes aegypti")
            self.assertIn("#line/2", gene.provenance.locator)
            self.assertEqual(gene.payload["gff_attributes"]["ID"], "AAEL000001")
            protein = next(record for record in result.records if record.lane == "proteins")
            self.assertIn("odorant receptor coreceptor", protein.text)
            go = next(record for record in result.records if record.record_id.startswith("vectorbase:go:"))
            self.assertIn("GO:0004984", go.text)
            self.assertEqual(go.payload["go_id"], "GO:0004984")
            self.assertTrue(any(gap["reason"] == "malformed_gff_row" for gap in result.gaps))

    def test_vectorbase_payloads_are_queryable_from_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            file_urls = write_fake_vectorbase_files(root)
            result = fetch_vectorbase_genomics_records(
                raw_dir=root / "raw",
                file_urls=file_urls,
                retrieved_at="2026-05-24T00:00:00Z",
            )
            index = SourceIndex(root / "source_index.sqlite")
            index.initialize()
            index.upsert_records(result.records)

            rows = index.sql(
                "select payload_json from record_payloads where source='vectorbase_aedes_genomics' and record_id='vectorbase:gene:AAEL000001'",
                limit=1,
            )
            self.assertEqual(len(rows), 1)
            self.assertIn("odorant receptor coreceptor", rows[0]["payload_json"])


if __name__ == "__main__":
    unittest.main()
