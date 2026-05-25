import csv
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from askinsects.sources.vectornet_surveillance import (
    VECTORNET_SOURCE_ID,
    fetch_vectornet_surveillance_records,
)


FIELDNAMES = [
    "id",
    "bibliographicCitation",
    "basisOfRecord",
    "dynamicProperties",
    "occurrenceID",
    "individualCount",
    "sex",
    "lifeStage",
    "degreeOfEstablishment",
    "associatedTaxa",
    "eventID",
    "eventDate",
    "samplingProtocol",
    "sampleSizeValue",
    "sampleSizeUnit",
    "eventRemarks",
    "locationID",
    "higherGeographyID",
    "higherGeography",
    "countryCode",
    "locationRemarks",
    "decimalLatitude",
    "decimalLongitude",
    "verbatimIdentification",
    "identificationRemarks",
    "scientificName",
]


def vectornet_archive_bytes(rows=None):
    output = io.BytesIO()
    occurrence = io.StringIO()
    writer = csv.DictWriter(occurrence, fieldnames=FIELDNAMES, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    for row in rows or vectornet_rows():
        writer.writerow(row)
    eml = """<?xml version="1.0" encoding="UTF-8"?>
<eml:eml xmlns:eml="https://eml.ecoinformatics.org/eml-2.2.0">
  <dataset>
    <alternateIdentifier>7a5757c3-58f8-4ff6-9662-32296965a2f3</alternateIdentifier>
    <alternateIdentifier>https://ipt.gbif.org/resource?r=vndatabase</alternateIdentifier>
    <title>VectorNet</title>
    <pubDate>2025-02-05</pubDate>
    <intellectualRights><para>This work is licensed under CC-BY 4.0.</para></intellectualRights>
    <licensed><identifier>CC-BY-4.0</identifier></licensed>
  </dataset>
</eml:eml>
"""
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("occurrence.txt", occurrence.getvalue())
        archive.writestr("eml.xml", eml)
        archive.writestr("meta.xml", "<archive />")
    return output.getvalue()


def vectornet_rows():
    base = {key: "NA" for key in FIELDNAMES}
    aedes = {
        **base,
        "id": "032E6FBB-9ABF-4CF8-8AA4-0076FC80F726",
        "occurrenceID": "032E6FBB-9ABF-4CF8-8AA4-0076FC80F726",
        "individualCount": "4",
        "sex": "female",
        "lifeStage": "adult",
        "degreeOfEstablishment": "Invasive - Established",
        "eventDate": "2017-06-01/2017-09-30",
        "samplingProtocol": "Ovitrap",
        "higherGeography": "Georgia | Zygdidi",
        "countryCode": "GE",
        "decimalLatitude": "42.514",
        "decimalLongitude": "41.8736",
        "verbatimIdentification": "Aedes aegypti",
        "identificationRemarks": "morphological",
        "scientificName": "Aedes aegypti",
    }
    absent = {
        **base,
        "id": "D17F3699-4877-4304-92BC-01375A1BD7A2",
        "occurrenceID": "D17F3699-4877-4304-92BC-01375A1BD7A2",
        "individualCount": "0",
        "lifeStage": "egg",
        "degreeOfEstablishment": "Invasive - Absent",
        "eventDate": "2018-02-08/2018-09-08",
        "samplingProtocol": "Ovitrap",
        "higherGeography": "Austria | Wiener Umland/Nordteil",
        "countryCode": "AT",
        "verbatimIdentification": "Aedes aegypti",
        "identificationRemarks": "PCR_DNA_Barcoding",
        "scientificName": "Aedes aegypti",
    }
    other = {
        **base,
        "id": "4B85477C-5310-4E4E-8AA7-00004B42A332",
        "occurrenceID": "4B85477C-5310-4E4E-8AA7-00004B42A332",
        "individualCount": "25",
        "lifeStage": "egg",
        "degreeOfEstablishment": "Invasive - Established",
        "eventDate": "2020-10-20/2020-10-27",
        "samplingProtocol": "Ovitrap",
        "higherGeography": "Italy | Roma",
        "countryCode": "IT",
        "verbatimIdentification": "Aedes albopictus",
        "identificationRemarks": "morphological",
        "scientificName": "Aedes albopictus",
    }
    return [aedes, absent, other]


class VectorNetSurveillanceSourceTests(unittest.TestCase):
    def test_fetch_vectornet_surveillance_records_normalizes_aedes_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_vectornet_surveillance_records(
                raw_dir=Path(tmpdir) / "raw" / "vectornet_surveillance",
                fetch_bytes=lambda url: vectornet_archive_bytes(),
                retrieved_at="2026-05-25T00:00:00Z",
            )

            self.assertEqual(result.source_id, VECTORNET_SOURCE_ID)
            self.assertEqual(result.dataset_key, "7a5757c3-58f8-4ff6-9662-32296965a2f3")
            self.assertEqual(result.matched_row_count, 2)
            self.assertEqual(result.observation_record_count, 2)
            self.assertGreaterEqual(result.ecology_record_count, 2)
            self.assertFalse(result.gaps)
            self.assertTrue(Path(result.filtered_rows_path).exists())

            observation = next(record for record in result.records if record.record_id.startswith("vectornet:observation:032E6FBB"))
            self.assertEqual(observation.source, VECTORNET_SOURCE_ID)
            self.assertEqual(observation.lane, "observations")
            self.assertIn("VectorNet ECDC/EFSA surveillance", observation.text)
            self.assertIn("reported individual count 4", observation.text)
            self.assertIn("presence bucket detection_or_presence_evidence", observation.text)
            self.assertEqual(observation.provenance.license, "CC-BY-4.0")
            self.assertIn("occurrence.txt/row/2", observation.provenance.locator)
            self.assertEqual(observation.payload["presence_bucket"], "detection_or_presence_evidence")

            absent = next(record for record in result.records if record.record_id.startswith("vectornet:observation:D17F3699"))
            self.assertEqual(absent.payload["presence_bucket"], "absence_surveillance")
            ecology = [record for record in result.records if record.lane == "ecology"]
            self.assertTrue(any("country:Georgia" in record.payload["summary_key"] for record in ecology))

    def test_fetch_vectornet_records_gap_when_no_species_rows(self):
        rows = [row for row in vectornet_rows() if row["scientificName"] == "Aedes albopictus"]
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_vectornet_surveillance_records(
                raw_dir=Path(tmpdir) / "raw" / "vectornet_surveillance",
                fetch_bytes=lambda url: vectornet_archive_bytes(rows=rows),
                retrieved_at="2026-05-25T00:00:00Z",
            )

            self.assertEqual(result.records, [])
            self.assertEqual(result.gaps[0]["source"], VECTORNET_SOURCE_ID)
            self.assertEqual(result.gaps[0]["reason"], "vectornet_no_matching_species_rows")


if __name__ == "__main__":
    unittest.main()
