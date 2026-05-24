import tempfile
import unittest
from pathlib import Path

from askinsects.sources.ncbi_biosample import NCBI_BIOSAMPLE_SOURCE_ID, fetch_ncbi_biosample_records


def biosample_summary_payload() -> dict[str, object]:
    sampledata = """
    <BioSample>
      <Ids>
        <Id db="BioSample">SAMN59867395</Id>
        <Id db_label="Sample name">GNMa-Ae-3</Id>
        <Id db="SRA">SRS29208944</Id>
      </Ids>
      <Package display_name="Invertebrate"/>
      <Owner><Name>Chongqing Medical University</Name></Owner>
      <Status status="live" when="2026-05-01"/>
      <Attributes>
        <Attribute attribute_name="isolate">not collected</Attribute>
        <Attribute attribute_name="strain">Rockefeller</Attribute>
        <Attribute harmonized_name="isolation_source">laboratory reared</Attribute>
        <Attribute harmonized_name="collection_date">2026-05</Attribute>
        <Attribute harmonized_name="geo_loc_name">China: Chongqing</Attribute>
        <Attribute harmonized_name="tissue">whole body</Attribute>
      </Attributes>
    </BioSample>
    """
    return {
        "result": {
            "uids": ["59867395"],
            "59867395": {
                "uid": "59867395",
                "accession": "SAMN59867395",
                "title": "GNMa-Ae-3",
                "organization": "Chongqing Medical University",
                "taxonomy": "7159",
                "organism": "Aedes aegypti",
                "sampledata": sampledata,
                "identifiers": "BioSample: SAMN59867395; Sample name: GNMa-Ae-3; SRA: SRS29208944",
            },
        }
    }


class NCBIBioSampleSourceTests(unittest.TestCase):
    def test_fetch_ncbi_biosample_records_normalizes_samples_and_limit_gap(self):
        calls = []

        def fake_fetch_json(url: str):
            calls.append(url)
            if "esearch.fcgi" in url:
                return {"esearchresult": {"count": "3", "idlist": ["59867395"]}}
            return biosample_summary_payload()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_ncbi_biosample_records(
                species="Aedes aegypti",
                raw_dir=Path(tmpdir) / "raw",
                limit=1,
                page_size=1,
                delay_seconds=0,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-24T00:00:00Z",
            )

        self.assertEqual(result.source_id, NCBI_BIOSAMPLE_SOURCE_ID)
        self.assertEqual(result.total_count, 3)
        self.assertEqual(result.fetched_count, 1)
        self.assertEqual(len(result.records), 1)
        record = result.records[0]
        self.assertEqual(record.record_id, "ncbi:biosample:SAMN59867395")
        self.assertEqual(record.lane, "biosamples")
        self.assertEqual(record.source, "ncbi_biosamples")
        self.assertEqual(record.species, "Aedes aegypti")
        self.assertIn("China: Chongqing", record.text)
        self.assertIn("Rockefeller", record.text)
        self.assertIn("SRS29208944", record.text)
        self.assertEqual(record.payload["parsed_sampledata"]["attributes"]["geo_loc_name"], "China: Chongqing")
        self.assertEqual(result.gaps[0]["reason"], "biosample_limit_applied")
        self.assertTrue(any("esearch.fcgi" in call for call in calls))
        self.assertTrue(any("esummary.fcgi" in call for call in calls))

    def test_fetch_ncbi_biosample_records_records_xml_parse_gap_in_payload(self):
        def fake_fetch_json(url: str):
            if "esearch.fcgi" in url:
                return {"esearchresult": {"count": "1", "idlist": ["1"]}}
            payload = biosample_summary_payload()
            payload["result"]["1"] = dict(payload["result"]["59867395"], uid="1", accession="SAMN1", sampledata="<BioSample>")
            payload["result"]["uids"] = ["1"]
            payload["result"].pop("59867395")
            return payload

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_ncbi_biosample_records(
                raw_dir=Path(tmpdir) / "raw",
                limit=1,
                page_size=1,
                delay_seconds=0,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-24T00:00:00Z",
            )

        self.assertEqual(len(result.records), 1)
        parsed = result.records[0].payload["parsed_sampledata"]
        self.assertEqual(parsed["parse_error"], "sampledata_xml_parse_failed")


if __name__ == "__main__":
    unittest.main()
