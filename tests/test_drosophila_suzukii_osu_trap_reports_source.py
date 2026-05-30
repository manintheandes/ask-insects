import io
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from askinsects.sources.drosophila_suzukii_osu_trap_reports import (
    FetchBody,
    ReportSpec,
    fetch_drosophila_suzukii_osu_trap_report_records,
)


RETRIEVED_AT = "2026-05-30T00:00:00Z"


def xlsx_fixture() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "SWD 2020"
    sheet.append(["Spotted wing drosophila trapping, 2020"])
    sheet.append(["County", "Cooperator", "Crop", "Trap ID/#", "Lure", "June 13 - 19", "June 20 - 26"])
    sheet.append(["Athens", "Brown", "Blackberry", 1, "Scentry lure over 25% ACV", 0, 4])
    sheet.append(["Athens", "Brown", "Blackberry", 2, "Scentry lure over 25% ACV", "", "did not set"])
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


CSV_FIXTURE = b'''"SPOTTED WIING DROSOPHILA, 2021 Trapping Period: June 15 - July 15 County Farm Cooperator Crop","Athens Brown Blackberry","Adams B and D Berry Purdin Blackberry"\n"Trap ID/#","1","2"\n"Lure","Scentry","ACV"\n"June 13 - 19","8","0"\n"June 20 - 26","40","set 6/20"\n'''


def osu_fetcher(url: str) -> FetchBody:
    if "2015" in url or "1g2sFMxG-EKJdBXdXyF1fFLUfCGp6piwwWvjv-IQEoWw" in url:
        return FetchBody(body=b"gone", content_type="text/plain", status=410, final_url=url)
    if url.endswith(".xlsx") or "2020" in url:
        return FetchBody(body=xlsx_fixture(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", status=200, final_url=url)
    if "2021" in url or "gviz" in url or "output=csv" in url:
        return FetchBody(body=CSV_FIXTURE, content_type="text/csv", status=200, final_url=url)
    return FetchBody(body=b"gone", content_type="text/plain", status=410, final_url=url)


class DrosophilaSuzukiiOsuTrapReportsSourceTests(unittest.TestCase):
    def test_fetch_parses_csv_and_xlsx_trap_report_rows_and_gap(self):
        specs = [
            ReportSpec(2021, "https://example.org/2021.csv", "2021.csv", "csv"),
            ReportSpec(2020, "https://example.org/2020.xlsx", "2020.xlsx", "xlsx", "SWD 2020"),
            ReportSpec(2015, "https://example.org/2015.csv", "2015.csv", "csv", expected_unavailable=True),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_osu_trap_report_records(
                raw_dir=Path(tmpdir),
                fetch_body=osu_fetcher,
                retrieved_at=RETRIEVED_AT,
                report_specs=specs,
            )

        self.assertEqual(result.file_count, 2)
        self.assertEqual(result.parsed_trap_site_count, 4)
        self.assertEqual(result.parsed_trap_observation_count, 7)
        atom_types = {record.payload.get("atom_type") for record in result.records if record.payload}
        self.assertIn("osu_swd_trap_report_file_manifest", atom_types)
        self.assertIn("osu_swd_trap_site", atom_types)
        self.assertIn("osu_swd_trap_observation", atom_types)
        self.assertTrue(any(record.payload.get("reason") == "osu_swd_trap_report_unavailable" for record in result.records if record.payload))


if __name__ == "__main__":
    unittest.main()
