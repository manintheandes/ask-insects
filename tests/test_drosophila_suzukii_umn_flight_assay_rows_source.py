import unittest
import tempfile
from pathlib import Path

from askinsects.sources.drosophila_suzukii_umn_flight_assay_rows import (
    BITSTREAM_API_URL,
    CSV_CONTENT_URL,
    DROSOPHILA_SUZUKII_UMN_FLIGHT_ASSAY_ROWS_SOURCE_ID,
    ITEM_API_URL,
    fetch_drosophila_suzukii_umn_flight_assay_row_records,
)


ITEM_FIXTURE = {
    "uuid": "3c514fff-5e6e-4847-a083-3700326e8ad1",
    "name": "Data supporting: Comparing Drosophila suzukii flight behavior using free-flight and tethered flight assays",
    "handle": "11299/227164",
    "metadata": {
        "dc.title": [{"value": "Data supporting: Comparing Drosophila suzukii flight behavior using free-flight and tethered flight assays"}],
        "dc.contributor.author": [{"value": "Kees, Aubree M"}, {"value": "Tran, Anh K"}],
        "dc.date.issued": [{"value": "2022-05-02"}],
        "dc.description.abstract": [
            {
                "value": "Winter and summer morph Drosophila suzukii flight behavior on a tethered flight mill and free flight chamber was documented."
            }
        ],
        "dc.identifier.doi": [{"value": "https://doi.org/10.13020/4nsz-x660"}],
        "dc.rights": [{"value": "Attribution-NonCommercial 3.0 United States"}],
        "dc.rights.uri": [{"value": "http://creativecommons.org/licenses/by-nc/3.0/us/"}],
    },
}

BITSTREAM_FIXTURE = {
    "uuid": "81028480-4f7d-4b2a-b648-403c683b7f26",
    "name": "data_archival.csv",
    "metadata": {
        "dc.title": [{"value": "data_archival.csv"}],
        "dc.description": [{"value": "flight data (archival copy)"}],
    },
    "sizeBytes": 15543,
    "checkSum": {"checkSumAlgorithm": "MD5", "value": "57f90c4209fe9c677f40d90a60935360"},
}

CSV_FIXTURE = (
    "\ufeffdate,treatment,morph,sex,age,propensity,phototactic,duration,bouts,distancecm,avgvelcm/s\n"
    "2021-01-22,chamber,S,M,2,0,0,.,.,.,.\n"
    "2021-01-28,chamber,W,F,2,1,1,21.84,1,.,.\n"
    "2021-02-01,mill,W,F,3,1,.,4.5,2,12.4,2.75\n"
)


class DrosophilaSuzukiiUmnFlightAssayRowsSourceTests(unittest.TestCase):
    def test_fetch_builds_dataset_file_and_row_records(self):
        def fetch_json(url):
            if url == ITEM_API_URL:
                return ITEM_FIXTURE
            if url == BITSTREAM_API_URL:
                return BITSTREAM_FIXTURE
            raise AssertionError(url)

        def fetch_bytes(url):
            self.assertEqual(url, CSV_CONTENT_URL)
            return CSV_FIXTURE.encode("utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            raw_dir = Path(tmpdir) / "raw" / DROSOPHILA_SUZUKII_UMN_FLIGHT_ASSAY_ROWS_SOURCE_ID
            result = fetch_drosophila_suzukii_umn_flight_assay_row_records(
                raw_dir=raw_dir,
                fetch_json=fetch_json,
                fetch_bytes=fetch_bytes,
                retrieved_at="2026-05-29T00:00:00Z",
                max_rows=3,
            )

        self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_UMN_FLIGHT_ASSAY_ROWS_SOURCE_ID)
        self.assertEqual(result.dataset_count, 1)
        self.assertEqual(result.file_count, 1)
        self.assertEqual(result.parsed_row_count, 3)
        self.assertEqual(len(result.records), 5)
        row_records = [record for record in result.records if record.payload and record.payload.get("atom_type") == "umn_flight_assay_row"]
        self.assertEqual(len(row_records), 3)
        self.assertEqual(row_records[1].payload["assay"], "free-flight chamber")
        self.assertEqual(row_records[1].payload["duration"], 21.84)
        self.assertEqual(row_records[2].payload["avg_velocity_cm_s"], 2.75)
        self.assertTrue(any(record.payload and record.payload.get("atom_type") == "umn_flight_assay_file_manifest" for record in result.records))

    def test_fetch_records_gap_when_csv_unavailable(self):
        def fetch_json(url):
            return ITEM_FIXTURE if url == ITEM_API_URL else BITSTREAM_FIXTURE

        def fetch_bytes(url):
            raise RuntimeError("blocked")

        with tempfile.TemporaryDirectory() as tmpdir:
            raw_dir = Path(tmpdir) / "raw" / DROSOPHILA_SUZUKII_UMN_FLIGHT_ASSAY_ROWS_SOURCE_ID
            result = fetch_drosophila_suzukii_umn_flight_assay_row_records(
                raw_dir=raw_dir,
                fetch_json=fetch_json,
                fetch_bytes=fetch_bytes,
                retrieved_at="2026-05-29T00:00:00Z",
            )

        self.assertEqual(result.parsed_row_count, 0)
        self.assertTrue(any(gap["reason"] == "umn_flight_assay_csv_fetch_or_parse_failed" for gap in result.gaps))
        self.assertTrue(any(record.payload and record.payload.get("reason") == "umn_flight_assay_rows_not_queryable" for record in result.records))


if __name__ == "__main__":
    unittest.main()
