import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from scripts.ingest_drosophila_suzukii_ncbi_biosamples import (
    DROSOPHILA_SUZUKII_NCBI_BIOSAMPLES_SOURCE_ID,
    ingest_drosophila_suzukii_ncbi_biosamples,
)


def _swd_summary_payload():
    sampledata = """
    <BioSample>
      <Ids>
        <Id db="BioSample">SAMN70000001</Id>
        <Id db_label="Sample name">SWD-1</Id>
      </Ids>
      <Attributes>
        <Attribute harmonized_name="geo_loc_name">USA: Oregon</Attribute>
        <Attribute harmonized_name="tissue">antenna</Attribute>
      </Attributes>
    </BioSample>
    """
    return {"result": {"uids": ["70000001"], "70000001": {
        "uid": "70000001", "accession": "SAMN70000001", "title": "SWD-1",
        "organism": "Drosophila suzukii", "taxonomy": "28584", "sampledata": sampledata,
        "identifiers": "BioSample: SAMN70000001"}}}


def _fake_fetch(url):
    if "esearch.fcgi" in url:
        return {"esearchresult": {"count": "1", "idlist": ["70000001"]}}
    return _swd_summary_payload()


class IngestSWDBioSamplesTests(unittest.TestCase):
    def test_swd_biosamples_added_without_touching_aedes(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            # Seed an existing Aedes biosample under the shared source.
            index.upsert_records([EvidenceRecord(
                record_id="ncbi:biosample:SAMN00000001", lane="biosamples", source="ncbi_biosamples",
                title="Aedes BioSample", text="Aedes aegypti biosample", species="Aedes aegypti",
                url="https://www.ncbi.nlm.nih.gov/biosample/SAMN00000001", media_url=None,
                provenance=Provenance(source_id="ncbi_biosamples", locator="x", retrieved_at="2026-01-01T00:00:00Z"),
            )])

            result = ingest_drosophila_suzukii_ncbi_biosamples(
                artifact_dir=artifact_dir, fetch_json=_fake_fetch,
                retrieved_at="2026-06-06T00:00:00Z", limit=1, page_size=1, delay_seconds=0,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["source"], DROSOPHILA_SUZUKII_NCBI_BIOSAMPLES_SOURCE_ID)

            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select source, species, count(*) n from records where lane='biosamples' group by source, species order by source",
                limit=50,
            )
            by = {(r["source"], r["species"]): r["n"] for r in rows}
            # Aedes preserved, SWD added under dedicated source.
            self.assertEqual(by[("ncbi_biosamples", "Aedes aegypti")], 1)
            self.assertEqual(by[(DROSOPHILA_SUZUKII_NCBI_BIOSAMPLES_SOURCE_ID, "Drosophila suzukii")], 1)


if __name__ == "__main__":
    unittest.main()
