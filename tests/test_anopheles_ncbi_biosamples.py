import json
import tempfile
import unittest
from pathlib import Path

from askinsects.answer import answer_question
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.anopheles_ncbi_biosamples import (
    ANOPHELES_NCBI_BIOSAMPLES_SOURCE_ID,
    fetch_anopheles_ncbi_biosample_records,
)
from scripts.ingest_anopheles_ncbi_biosamples import ingest_anopheles_ncbi_biosamples


def _summary_payload() -> dict[str, object]:
    sampledata = """
    <BioSample>
      <Ids>
        <Id db="BioSample">SAMN80000001</Id>
        <Id db_label="Sample name">STE2</Id>
        <Id db="SRA">SRS80000001</Id>
      </Ids>
      <Attributes>
        <Attribute harmonized_name="geo_loc_name">India: Bengaluru</Attribute>
        <Attribute harmonized_name="collection_date">2025-06-01</Attribute>
        <Attribute harmonized_name="tissue">antenna</Attribute>
        <Attribute harmonized_name="isolate">STE2</Attribute>
        <Attribute harmonized_name="strain">Indian</Attribute>
      </Attributes>
    </BioSample>
    """
    return {
        "result": {
            "uids": ["80000001"],
            "80000001": {
                "uid": "80000001",
                "accession": "SAMN80000001",
                "title": "Anopheles stephensi antenna sample STE2",
                "organism": "Anopheles stephensi",
                "taxonomy": "30069",
                "sampledata": sampledata,
                "identifiers": "BioSample: SAMN80000001; SRA: SRS80000001",
            },
        }
    }


def _fake_fetch(url: str) -> dict[str, object]:
    if "esearch.fcgi" in url:
        return {"esearchresult": {"count": "1", "idlist": ["80000001"]}}
    return _summary_payload()


def _aedes_record() -> EvidenceRecord:
    return EvidenceRecord(
        record_id="ncbi:biosample:SAMN00000001",
        lane="biosamples",
        source="ncbi_biosamples",
        title="Aedes aegypti BioSample SAMN00000001",
        text="Aedes aegypti sample from India with linked SRA SRS1.",
        species="Aedes aegypti",
        url="https://www.ncbi.nlm.nih.gov/biosample/SAMN00000001",
        media_url=None,
        provenance=Provenance(
            source_id="ncbi_biosamples",
            locator="raw/ncbi_biosamples/aedes.json#uid/1",
            retrieved_at="2026-01-01T00:00:00Z",
            license="NCBI",
        ),
    )


class AnophelesNCBIBioSampleTests(unittest.TestCase):
    def test_fetch_retags_atomic_records_and_preserves_query_taxon(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_anopheles_ncbi_biosample_records(
                raw_dir=Path(tmpdir) / "raw",
                target_taxa=("Anopheles stephensi",),
                limit_per_taxon=1,
                page_size=1,
                delay_seconds=0,
                fetch_json=_fake_fetch,
                retrieved_at="2026-07-22T00:00:00Z",
            )

        self.assertEqual(result.source_id, ANOPHELES_NCBI_BIOSAMPLES_SOURCE_ID)
        self.assertEqual(result.total_counts, {"Anopheles stephensi": 1})
        self.assertEqual(len(result.records), 1)
        record = result.records[0]
        self.assertEqual(record.record_id, "anopheles_ncbi:biosample:SAMN80000001")
        self.assertEqual(record.source, ANOPHELES_NCBI_BIOSAMPLES_SOURCE_ID)
        self.assertEqual(record.provenance.source_id, ANOPHELES_NCBI_BIOSAMPLES_SOURCE_ID)
        self.assertIn("#uid/80000001", record.provenance.locator)
        self.assertEqual(record.payload["anopheles_target_taxon"], "Anopheles stephensi")
        self.assertEqual(record.payload["parsed_sampledata"]["ids"]["SRA"], "SRS80000001")

    def test_ingest_is_additive_and_writes_source_receipt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records([_aedes_record()])

            result = ingest_anopheles_ncbi_biosamples(
                artifact_dir=artifact_dir,
                target_taxa=("Anopheles stephensi",),
                limit_per_taxon=1,
                page_size=1,
                delay_seconds=0,
                fetch_json=_fake_fetch,
                retrieved_at="2026-07-22T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select source, count(*) as n from records where lane='biosamples' group by source order by source",
                limit=10,
            )
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["ncbi_biosamples"], 1)
            self.assertEqual(counts[ANOPHELES_NCBI_BIOSAMPLES_SOURCE_ID], 1)
            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            source_receipt = receipt[ANOPHELES_NCBI_BIOSAMPLES_SOURCE_ID]
            self.assertEqual(source_receipt["reported_total_counts"], {"Anopheles stephensi": 1})
            self.assertEqual(source_receipt["target_taxa"], ["Anopheles stephensi"])

    def test_anopheles_question_uses_anopheles_biosamples_not_aedes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            fetched = fetch_anopheles_ncbi_biosample_records(
                raw_dir=artifact_dir / "raw" / "anopheles_ncbi_biosamples",
                target_taxa=("Anopheles stephensi",),
                limit_per_taxon=1,
                page_size=1,
                delay_seconds=0,
                fetch_json=_fake_fetch,
                retrieved_at="2026-07-22T00:00:00Z",
            )
            index.upsert_records([_aedes_record(), *fetched.records])

            answer = answer_question(
                "show Anopheles stephensi BioSamples from India with linked SRA",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["source"], ANOPHELES_NCBI_BIOSAMPLES_SOURCE_ID)
            self.assertEqual(answer["evidence"][0]["record_id"], "anopheles_ncbi:biosample:SAMN80000001")
            self.assertIn("#uid/80000001", answer["evidence"][0]["provenance"]["locator"])

    def test_unmatched_location_fails_closed_instead_of_returning_other_samples(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            fetched = fetch_anopheles_ncbi_biosample_records(
                raw_dir=artifact_dir / "raw" / "anopheles_ncbi_biosamples",
                target_taxa=("Anopheles stephensi",),
                limit_per_taxon=1,
                page_size=1,
                delay_seconds=0,
                fetch_json=_fake_fetch,
                retrieved_at="2026-07-22T00:00:00Z",
            )
            index.upsert_records(fetched.records)

            answer = answer_question(
                "show Anopheles stephensi BioSamples from Kenya",
                artifact_dir=artifact_dir,
            )

            self.assertFalse(answer["ok"])
            self.assertIn("requested location: kenya", answer["source_gap"]["reason"].lower())


if __name__ == "__main__":
    unittest.main()
