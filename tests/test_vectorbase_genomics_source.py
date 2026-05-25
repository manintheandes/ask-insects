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
    cds = root / "VectorBase-68_AaegyptiLVP_AGWG_AnnotatedCDSs.fasta"
    cds.write_text(
        ">AAEL000001-RA | organism=Aedes_aegypti_LVP_AGWG | product=odorant receptor coreceptor | location=AaegL5_1:100-900(+) | length=9 | sequence_SO=chromosome | SO=protein_coding_gene\n"
        "ATGGCTTAA\n",
        encoding="utf-8",
    )
    transcript_sequences = root / "VectorBase-68_AaegyptiLVP_AGWG_AnnotatedTranscripts.fasta"
    transcript_sequences.write_text(
        ">AAEL000001-RA | gene=AAEL000001 | organism=Aedes_aegypti_LVP_AGWG | gene_product=odorant receptor coreceptor | transcript_product=odorant receptor coreceptor transcript | location=AaegL5_1:100-900(+) | length=12 | sequence_SO=chromosome | SO=protein_coding_gene | is_pseudo=false\n"
        "AAATGGCTTAAA\n",
        encoding="utf-8",
    )
    gaf = root / "VectorBase-CURRENT_AaegyptiLVP_AGWG_GO.gaf.gz"
    with gzip.open(gaf, "wt", encoding="utf-8") as handle:
        handle.write("!gaf-version: 2.2\n")
        handle.write(
            "VectorBase\tAAEL000001\torco\t\tGO:0004984\tPMID:1\tIEA\t\tF\todorant receptor activity\tOrco\tprotein\ttaxon:7159\t20260524\tVectorBase\t\tAAEL000001-PA\n"
        )
    codon_usage = root / "VectorBase-68_AaegyptiLVP_AGWG_CodonUsage.txt"
    codon_usage.write_text(
        "CODON\tAA\tFREQ\tABUNDANCE\nAUG\tM\t22.88 \t1.00\n",
        encoding="utf-8",
    )
    id_events = root / "VectorBase-68_AaegyptiLVP_AGWG_ids_events.tab"
    id_events.write_text(
        "AAEL000355\t\tdeletion\tpre-BRC4 52\t2009-06\n",
        encoding="utf-8",
    )
    ncbi_linkout = root / "VectorBase-68_AaegyptiLVP_AGWG_NCBILinkout_Nucleotide.xml"
    ncbi_linkout.write_text(
        """<?xml version="1.0"?>
<LinkSet>
  <Link>
    <LinkId>1</LinkId>
    <ProviderId>5941</ProviderId>
    <ObjectSelector>
      <Database>Nucleotide</Database>
      <ObjectList>
        <Query>AaegL5_1</Query>
      </ObjectList>
    </ObjectSelector>
    <ObjectUrl>
      <Base>https://vectorbase.org/a/app/record/genomic-sequence/</Base>
      <Rule></Rule>
    </ObjectUrl>
  </Link>
</LinkSet>
""",
        encoding="utf-8",
    )
    orthologs = root / "orthologs.txt.gz"
    with gzip.open(orthologs, "wt", encoding="utf-8") as handle:
        handle.write("aaeg-old|AAEL000076\taaeo|O67680\t0.352\n")
        handle.write("aaeo|O67868\taaeg-old|AAEL000108\t1.353\n")
        handle.write("aaeo|O1\taaeo|O2\t0.100\n")
        handle.write("aaeg-old|AAELBAD\taaeo|OBAD\tnot-a-score\n")
        handle.write("malformed row\n")
    return {
        "gff": gff.as_uri(),
        "proteins": proteins.as_uri(),
        "cds": cds.as_uri(),
        "transcript_sequences": transcript_sequences.as_uri(),
        "go": gaf.as_uri(),
        "codon_usage": codon_usage.as_uri(),
        "id_events": id_events.as_uri(),
        "ncbi_linkout": ncbi_linkout.as_uri(),
        "orthologs": orthologs.as_uri(),
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
            cds = next(record for record in result.records if record.record_id == "vectorbase:cds:AAEL000001-RA")
            self.assertEqual(cds.lane, "genome_features")
            self.assertIn("Observed FASTA sequence length: 9 nucleotides", cds.text)
            self.assertEqual(cds.payload["observed_sequence_length"], 9)
            transcript_sequence = next(
                record for record in result.records if record.record_id == "vectorbase:transcript_sequence:AAEL000001-RA"
            )
            self.assertEqual(transcript_sequence.lane, "transcripts")
            self.assertIn("transcript sequence AAEL000001-RA", transcript_sequence.text)
            self.assertEqual(transcript_sequence.payload["declared_length"], 12)
            go = next(record for record in result.records if record.record_id.startswith("vectorbase:go:"))
            self.assertIn("GO:0004984", go.text)
            self.assertEqual(go.payload["go_id"], "GO:0004984")
            codon = next(record for record in result.records if record.record_id == "vectorbase:codon_usage:AUG")
            self.assertIn("frequency 22.88", codon.text)
            self.assertEqual(codon.payload["amino_acid"], "M")
            id_event = next(record for record in result.records if record.record_id.startswith("vectorbase:id_event:AAEL000355"))
            self.assertIn("deletion to no successor", id_event.text)
            self.assertEqual(id_event.payload["event"], "deletion")
            linkout = next(record for record in result.records if record.record_id.startswith("vectorbase:ncbi_linkout:Nucleotide:AaegL5_1"))
            self.assertIn("NCBI LinkOut", linkout.text)
            self.assertEqual(linkout.payload["query"], "AaegL5_1")
            ortholog = next(record for record in result.records if record.record_id.startswith("vectorbase:ortholog:aaeg-old_AAEL000076"))
            self.assertEqual(ortholog.lane, "genome_features")
            self.assertIn("OrthoMCL CURRENT ortholog pair", ortholog.text)
            self.assertEqual(ortholog.payload["relationship_type"], "ortholog")
            self.assertEqual(ortholog.payload["aedes_gene_id"], "AAEL000076")
            self.assertEqual(ortholog.payload["partner_species_code"], "aaeo")
            self.assertEqual(ortholog.payload["partner_id"], "O67680")
            self.assertEqual(ortholog.payload["score"], 0.352)
            self.assertTrue(any(gap["reason"] == "malformed_gff_row" for gap in result.gaps))
            self.assertTrue(any(gap["reason"] == "malformed_orthomcl_score" for gap in result.gaps))
            self.assertTrue(any(gap["reason"] == "malformed_orthomcl_pair_row" for gap in result.gaps))

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
