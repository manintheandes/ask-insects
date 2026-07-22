from __future__ import annotations

import gzip
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from askinsects.answer import answer_question
from askinsects.index import SourceIndex
from askinsects.sources.anopheles_ncbi_genome_features import AnophelesNCBIGenomeFeaturesResult, fetch_anopheles_ncbi_genome_features
from scripts.ingest_anopheles_ncbi_genome_features import ingest_anopheles_ncbi_genome_features


class AnophelesNCBIGenomeFeaturesTests(unittest.TestCase):
    def test_failed_assembly_refresh_installs_scoped_queryable_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            failed = AnophelesNCBIGenomeFeaturesResult(
                source_id="anopheles_ncbi_genome_features",
                records=[],
                gaps=[{
                    "source": "anopheles_ncbi_genome_features",
                    "lane": "genes",
                    "reason": "gff_download_or_parse_failed",
                    "assembly_accession": "GCA_MISSING.1",
                }],
                raw_artifacts=[],
                assembly_accession="GCA_MISSING.1",
                species="Anopheles dirus",
                source_urls=[],
                sha256={},
                lane_counts={},
            )
            with patch(
                "scripts.ingest_anopheles_ncbi_genome_features.fetch_anopheles_ncbi_genome_features",
                return_value=failed,
            ):
                result = ingest_anopheles_ncbi_genome_features(
                    artifact_dir=root,
                    species="Anopheles dirus",
                    assembly_accession="GCA_MISSING.1",
                    assembly_ftp="https://example.test/GCA_MISSING.1",
                    retrieved_at="2026-07-22T00:00:00Z",
                )
            index = SourceIndex(root / "source_index.sqlite")
            rows = index.sql(
                "select record_id from records where source='anopheles_ncbi_genome_features'",
                limit=10,
            )
        self.assertFalse(result["ok"])
        self.assertEqual(
            [row["record_id"] for row in rows],
            ["anopheles_ncbi_genome_features:gap:gff_download_or_parse_failed:GCA_MISSING.1"],
        )

    def test_parses_gene_transcript_functional_cds_and_protein(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_gff = root / "source.gff.gz"
            source_protein = root / "source.faa.gz"
            with gzip.open(source_gff, "wt", encoding="utf-8") as handle:
                handle.write("##gff-version 3\n")
                handle.write("chr2\tNCBI\tgene\t10\t200\t.\t+\t.\tID=gene-LOC1;Name=Orco;description=odorant receptor coreceptor\n")
                handle.write("chr2\tNCBI\tmRNA\t10\t200\t.\t+\t.\tID=rna-XM_1;Parent=gene-LOC1;product=odorant receptor coreceptor\n")
                handle.write("chr2\tNCBI\tCDS\t20\t190\t.\t+\t0\tID=cds-XP_1;Parent=rna-XM_1;product=odorant receptor coreceptor;protein_id=XP_1\n")
                handle.write("chr2\tNCBI\texon\t10\t50\t.\t+\t.\tID=exon-1\n")
            with gzip.open(source_protein, "wt", encoding="utf-8") as handle:
                handle.write(">XP_1 odorant receptor coreceptor [Anopheles gambiae]\nMPEPTIDE\n")

            def fake_download(url: str, path: Path) -> str:
                shutil.copyfile(source_gff if url.endswith("gff.gz") else source_protein, path)
                return "a" * 64

            with patch("askinsects.sources.anopheles_ncbi_genome_features._download", fake_download):
                result = fetch_anopheles_ncbi_genome_features(
                    raw_dir=root / "raw", assembly_accession="GCF_TEST.1", species="Anopheles gambiae",
                    assembly_ftp="https://example.test/GCF_TEST.1_name", annotation_release=None,
                    retrieved_at="2026-07-22T00:00:00Z",
                )
        self.assertEqual(result.lane_counts, {"genes": 1, "transcripts": 1, "genome_features": 1, "proteins": 1})
        self.assertEqual(len(result.records), 4)
        self.assertTrue(all(record.record_id.startswith("anopheles_ncbi_genome:GCF_TEST.1:") for record in result.records))
        self.assertTrue(any("#line/2" in record.provenance.locator for record in result.records))
        self.assertTrue(any("#record/1" in record.provenance.locator for record in result.records))
        self.assertTrue(any(gap["reason"] == "ncbi_expression_annotation_release_not_configured" for gap in result.gaps))

    def test_answer_route_requires_exact_coreceptor_and_resistance_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = SourceIndex(root / "source_index.sqlite")
            index.initialize()
            from askinsects.records import EvidenceRecord, Provenance
            provenance = Provenance(
                source_id="anopheles_ncbi_genome_features", locator="fixture.gff.gz#line/1",
                retrieved_at="2026-07-22T00:00:00Z",
            )
            index.upsert_records([
                EvidenceRecord(
                    record_id="anopheles_ncbi_genome:GCF_TEST:transcripts:rna-coreceptor", lane="transcripts",
                    source="anopheles_ncbi_genome_features", title="Anopheles gambiae mRNA LOC1",
                    text="NCBI mRNA LOC1 for Anopheles gambiae. Annotation: odorant receptor coreceptor.",
                    species="Anopheles gambiae", url=None, media_url=None, provenance=provenance,
                ),
                EvidenceRecord(
                    record_id="anopheles_ncbi_genome:GCF_TEST:genes:gene-p450", lane="genes",
                    source="anopheles_ncbi_genome_features", title="Anopheles gambiae gene LOC2",
                    text="NCBI gene LOC2 for Anopheles gambiae. Annotation: cytochrome P450 4d1.",
                    species="Anopheles gambiae", url=None, media_url=None, provenance=provenance,
                ),
                EvidenceRecord(
                    record_id="anopheles_ncbi_genome:GCF_TEST:go:1:GO:0004984:10", lane="genome_features",
                    source="anopheles_ncbi_genome_features", title="Anopheles gambiae GO annotation LOC1 GO:0004984",
                    text="NCBI Gene Ontology annotation for Anopheles gambiae LOC1: GO:0004984; aspect F; qualifier enables; evidence code IEA.",
                    species="Anopheles gambiae", url=None, media_url=None, provenance=provenance,
                ),
                EvidenceRecord(
                    record_id="anopheles_ncbi_genome:GCF_TEST:expression:gene-LOC1", lane="expression",
                    source="anopheles_ncbi_genome_features", title="Anopheles gambiae NCBI expression profile LOC1",
                    text="NCBI normalized gene-expression profile for Anopheles gambiae LOC1 across 2 public SRA runs; nonzero runs 1; maximum normalized value 2.5.",
                    species="Anopheles gambiae", url=None, media_url=None, provenance=provenance,
                ),
                EvidenceRecord(
                    record_id="anopheles_ncbi_genome:GCF_TEST:transcripts:rna-odorant", lane="transcripts",
                    source="anopheles_ncbi_genome_features", title="Anopheles gambiae mRNA LOC1",
                    text="NCBI mRNA LOC1 for Anopheles gambiae. Annotation: odorant receptor 22c-like.",
                    species="Anopheles gambiae", url=None, media_url=None, provenance=provenance,
                ),
            ])
            coreceptor = answer_question("show NCBI transcripts for the Anopheles gambiae odorant receptor coreceptor", artifact_dir=root)
            exact_resistance = answer_question("show NCBI insecticide resistance gene annotations for Anopheles gambiae", artifact_dir=root)
            candidate_resistance = answer_question("show candidate NCBI insecticide resistance genes for Anopheles gambiae", artifact_dir=root)
            expression = answer_question("what NCBI expression profile is available for Anopheles gambiae LOC1?", artifact_dir=root)
            natural_expression = answer_question("what gene expression data do we have for Anopheles gambiae?", artifact_dir=root)
            go_term = answer_question("show Anopheles gambiae NCBI GO:0004984 annotations", artifact_dir=root)
            go_function = answer_question("show NCBI Gene Ontology annotations for odorant receptors in Anopheles gambiae", artifact_dir=root)
        self.assertTrue(coreceptor["ok"])
        self.assertIn("coreceptor", coreceptor["answer"])
        self.assertFalse(exact_resistance["ok"])
        self.assertTrue(candidate_resistance["ok"])
        self.assertIn("cytochrome P450", candidate_resistance["answer"])
        self.assertTrue(expression["ok"])
        self.assertEqual(expression["evidence"][0]["lane"], "expression")
        self.assertIn("maximum normalized value 2.5", expression["answer"])
        self.assertTrue(natural_expression["ok"])
        self.assertEqual(natural_expression["evidence"][0]["source"], "anopheles_ncbi_genome_features")
        self.assertEqual(natural_expression["evidence"][0]["lane"], "expression")
        self.assertTrue(go_term["ok"])
        self.assertEqual(go_term["evidence"][0]["record_id"], "anopheles_ncbi_genome:GCF_TEST:go:1:GO:0004984:10")
        self.assertTrue(go_function["ok"])
        self.assertIn("odorant receptor", go_function["answer"])
        self.assertEqual(go_function["evidence"][0]["record_id"], "anopheles_ncbi_genome:GCF_TEST:go:1:GO:0004984:10")
        self.assertTrue(any(item["lane"] == "transcripts" for item in go_function["evidence"]))

    def test_failed_download_is_an_explicit_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("askinsects.sources.anopheles_ncbi_genome_features._download", side_effect=RuntimeError("offline")):
                result = fetch_anopheles_ncbi_genome_features(
                    raw_dir=Path(tmp), assembly_accession="GCF_TEST.1", species="Anopheles gambiae",
                    assembly_ftp="https://example.test/GCF_TEST.1_name", annotation_release=None,
                )
        self.assertEqual(result.records, [])
        reasons = {gap["reason"] for gap in result.gaps}
        self.assertIn("gff_download_or_parse_failed", reasons)
        self.assertIn("protein_download_or_parse_failed", reasons)
        self.assertTrue(all(gap["species"] == "Anopheles gambiae" for gap in result.gaps))

    def test_parses_go_and_expression_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures = {}
            for name, content in {
                "gff.gz": "##gff-version 3\n",
                "protein.faa.gz": ">XP_1 test protein\nMPEP\n",
                "gene_ontology.gaf.gz": "!gaf-version: 2.2\nNCBIGene\t1\tLOC1\t\tGO:0001\tPMID:1\tIEA\t\tF\tprotein one\t\tprotein\ttaxon:7165\t20260101\tRefSeq\t\t\n",
                "gene_expression_counts.txt.gz": "#GTFID\tGeneSym\tGeneID\tChr\tGeneStart\tGeneEnd\tStrand\tGFF3ID\tSRR1\tSRR2\nLOC1\tLOC1\tGeneID:1\tchr1\t1\t10\t+\tgene-LOC1\t10\t0\n",
                "normalized_gene_expression_counts.txt.gz": "#GTFID\tGeneSym\tGeneID\tChr\tGeneStart\tGeneEnd\tStrand\tGFF3ID\tSRR1\tSRR2\nLOC1\tLOC1\tGeneID:1\tchr1\t1\t10\t+\tgene-LOC1\t2.5\t0\n",
            }.items():
                path = root / name
                with gzip.open(path, "wt", encoding="utf-8") as handle:
                    handle.write(content)
                fixtures[name] = path

            def fake_download(url: str, path: Path) -> str:
                suffix = max((suffix for suffix in fixtures if url.endswith(suffix)), key=len)
                match = fixtures[suffix]
                shutil.copyfile(match, path)
                return "b" * 64

            with patch("askinsects.sources.anopheles_ncbi_genome_features._download", fake_download):
                result = fetch_anopheles_ncbi_genome_features(
                    raw_dir=root / "raw", assembly_accession="GCF_TEST.1", species="Anopheles gambiae",
                    assembly_ftp="https://example.test/GCF_TEST.1_name", annotation_release="GCF_TEST.1-RS_TEST",
                    retrieved_at="2026-07-22T00:00:00Z",
                )
        self.assertEqual(result.lane_counts["expression"], 1)
        self.assertEqual(sum(1 for record in result.records if (record.payload or {}).get("record_type") == "ncbi_go_annotation"), 1)
        expression = next(record for record in result.records if record.lane == "expression")
        self.assertIn("maximum normalized value 2.5", expression.text)
        self.assertEqual(expression.payload["normalized_counts"]["SRR1"], "2.5")


if __name__ == "__main__":
    unittest.main()
