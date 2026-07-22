import json
import tempfile
import unittest
from pathlib import Path

from askinsects.answer import answer_question
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.anopheles_ncbi_sra import (
    ANOPHELES_NCBI_SRA_SOURCE_ID,
    fetch_anopheles_ncbi_sra_records,
)
from scripts.ingest_anopheles_ncbi_sra import ingest_anopheles_ncbi_sra


def _sra_summary() -> dict[str, object]:
    exp_xml = """
    <Summary>
      <Experiment acc="SRX80000001" />
      <Title>Anopheles gambiae antenna RNA-seq after odor exposure</Title>
      <Bioproject>PRJNA80000001</Bioproject>
      <Biosample>SAMN80000001</Biosample>
      <Platform instrument_model="Illumina NovaSeq 6000">ILLUMINA</Platform>
      <LIBRARY_STRATEGY>RNA-Seq</LIBRARY_STRATEGY>
      <LIBRARY_SOURCE>TRANSCRIPTOMIC</LIBRARY_SOURCE>
      <LIBRARY_SELECTION>cDNA</LIBRARY_SELECTION>
    </Summary>
    """
    runs = '<Runs><Run acc="SRR80000001" total_spots="1000" total_bases="150000" size="50000"/><Run acc="SRR80000002" total_spots="2000" total_bases="300000" size="100000"/></Runs>'
    return {
        "result": {
            "uids": ["80000001"],
            "80000001": {
                "uid": "80000001",
                "Accession": "SRX80000001",
                "Title": "Anopheles gambiae antenna RNA-seq after odor exposure",
                "ExpXml": exp_xml,
                "Runs": runs,
            },
        }
    }


def _fake_fetch(url: str) -> dict[str, object]:
    if "esearch.fcgi" in url:
        return {"esearchresult": {"count": "2", "idlist": ["80000001"]}}
    return _sra_summary()


def _aedes_dataset() -> EvidenceRecord:
    return EvidenceRecord(
        record_id="expression:sra_run:SRR1",
        lane="expression",
        source="aedes_expression_omics",
        title="Aedes SRA run",
        text="Aedes aegypti SRA RNA-seq run.",
        species="Aedes aegypti",
        url="https://www.ncbi.nlm.nih.gov/sra/SRR1",
        media_url=None,
        provenance=Provenance(
            source_id="aedes_expression_omics",
            locator="raw/aedes_sra.json#result/1/run/1",
            retrieved_at="2026-01-01T00:00:00Z",
            license="NCBI",
        ),
    )


class AnophelesNCBISRATests(unittest.TestCase):
    def test_fetch_creates_one_atomic_record_per_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_anopheles_ncbi_sra_records(
                raw_dir=Path(tmpdir) / "raw",
                target_taxa=("Anopheles gambiae",),
                experiment_limit_per_taxon=1,
                page_size=1,
                delay_seconds=0,
                fetch_json=_fake_fetch,
                retrieved_at="2026-07-22T00:00:00Z",
            )

        self.assertEqual(result.source_id, ANOPHELES_NCBI_SRA_SOURCE_ID)
        self.assertEqual(result.reported_total_counts, {"Anopheles gambiae": 2})
        self.assertEqual(result.fetched_experiment_counts, {"Anopheles gambiae": 1})
        self.assertEqual(result.run_counts, {"Anopheles gambiae": 2})
        self.assertEqual({record.record_id for record in result.records}, {"anopheles_sra:run:SRR80000001", "anopheles_sra:run:SRR80000002"})
        first = result.records[0]
        self.assertEqual(first.source, ANOPHELES_NCBI_SRA_SOURCE_ID)
        self.assertEqual(first.lane, "datasets")
        self.assertEqual(first.payload["biosample"], "SAMN80000001")
        self.assertEqual(first.payload["library_strategy"], "RNA-Seq")
        self.assertIn("#result/80000001/run/1", first.provenance.locator)
        self.assertIn("sra_experiment_limit_applied", {gap["reason"] for gap in result.gaps})
        self.assertIn("raw_sra_reads_not_downloaded", {gap["reason"] for gap in result.gaps})

    def test_ingest_preserves_aedes_and_writes_run_receipt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records([_aedes_dataset()])

            result = ingest_anopheles_ncbi_sra(
                artifact_dir=artifact_dir,
                target_taxa=("Anopheles gambiae",),
                experiment_limit_per_taxon=1,
                page_size=1,
                delay_seconds=0,
                fetch_json=_fake_fetch,
                retrieved_at="2026-07-22T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["run_record_count"], 2)
            self.assertEqual(SourceIndex(artifact_dir / "source_index.sqlite").sql("select count(*) as n from records where source='aedes_expression_omics'")[0]["n"], 1)
            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            source_receipt = receipt[ANOPHELES_NCBI_SRA_SOURCE_ID]
            self.assertEqual(source_receipt["run_counts"], {"Anopheles gambiae": 2})
            self.assertEqual(source_receipt["reported_total_counts"], {"Anopheles gambiae": 2})

    def test_anopheles_sra_question_excludes_aedes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            fetched = fetch_anopheles_ncbi_sra_records(
                raw_dir=artifact_dir / "raw" / "anopheles_ncbi_sra",
                target_taxa=("Anopheles gambiae",),
                experiment_limit_per_taxon=1,
                page_size=1,
                delay_seconds=0,
                fetch_json=_fake_fetch,
                retrieved_at="2026-07-22T00:00:00Z",
            )
            index.upsert_records([_aedes_dataset(), *fetched.records])

            answer = answer_question("show Anopheles gambiae antenna RNA-seq SRA runs", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["source"], ANOPHELES_NCBI_SRA_SOURCE_ID)
            self.assertTrue(all(item["species"] == "Anopheles gambiae" for item in answer["evidence"]))

    def test_combined_biosample_and_sra_question_returns_both_lanes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            provenance = Provenance(
                source_id="anopheles_ncbi_biosamples",
                locator="raw/biosample.json#uid/1",
                retrieved_at="2026-07-22T00:00:00Z",
                license="NCBI",
            )
            biosample = EvidenceRecord(
                record_id="anopheles_ncbi:biosample:SAMN80000001",
                lane="biosamples",
                source="anopheles_ncbi_biosamples",
                title="Anopheles gambiae BioSample SAMN80000001",
                text="NCBI BioSample SAMN80000001 for Anopheles gambiae.",
                species="Anopheles gambiae",
                url="https://www.ncbi.nlm.nih.gov/biosample/SAMN80000001",
                media_url=None,
                provenance=provenance,
            )
            fetched = fetch_anopheles_ncbi_sra_records(
                raw_dir=artifact_dir / "raw" / "anopheles_ncbi_sra",
                target_taxa=("Anopheles gambiae",),
                experiment_limit_per_taxon=1,
                page_size=1,
                delay_seconds=0,
                fetch_json=_fake_fetch,
                retrieved_at="2026-07-22T00:00:00Z",
            )
            index.upsert_records([biosample, *fetched.records])

            answer = answer_question(
                "What BioSamples and SRA runs are available for Anopheles gambiae?",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(
                {item["source"] for item in answer["evidence"]},
                {"anopheles_ncbi_biosamples", ANOPHELES_NCBI_SRA_SOURCE_ID},
            )
            self.assertIn("BioSample evidence:", answer["answer"])
            self.assertIn("SRA run evidence:", answer["answer"])


if __name__ == "__main__":
    unittest.main()
