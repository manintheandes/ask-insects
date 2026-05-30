import io
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from askinsects.sources.drosophila_suzukii_plos_climate_suitability import (
    FetchBody,
    fetch_drosophila_suzukii_plos_climate_suitability_records,
)


RETRIEVED_AT = "2026-05-30T00:00:00Z"


def xlsx_fixture(headers, rows, title="fixture table"):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Plan1"
    sheet.append([title])
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def plos_fetcher(url):
    if url.endswith(".s001"):
        return FetchBody(body=b"docx bytes", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", status=200, final_url=url)
    if url.endswith(".s002"):
        return FetchBody(
            body=xlsx_fixture(["PC", "Eigenvalue", "% variance"], [[1, 7.39347, 36.967]]),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            status=200,
            final_url=url,
        )
    if url.endswith(".s003"):
        return FetchBody(
            body=xlsx_fixture([None, "Axis 1", "Axis 2"], [["bio2", 0.1, -0.2]], title="correlation table"),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            status=200,
            final_url=url,
        )
    if url.endswith(".s004"):
        return FetchBody(
            body=xlsx_fixture(["Environmental variables", "Moran's I", "Standard Deviation", "p value"], [["Bio-1", -0.113, -52.013, 1]]),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            status=200,
            final_url=url,
        )
    raise AssertionError(f"unexpected URL: {url}")


class DrosophilaSuzukiiPlosClimateSuitabilitySourceTests(unittest.TestCase):
    def test_fetch_parses_plos_model_supplement_files_and_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_plos_climate_suitability_records(
                raw_dir=Path(tmpdir),
                fetch_body=plos_fetcher,
                retrieved_at=RETRIEVED_AT,
            )

        self.assertEqual(result.file_count, 4)
        self.assertEqual(result.parsed_table_row_count, 3)
        self.assertEqual(result.gaps, [])
        atom_types = {record.payload.get("atom_type") for record in result.records if record.payload}
        self.assertIn("plos_climate_model_summary", atom_types)
        self.assertIn("plos_climate_supplement_file", atom_types)
        self.assertIn("plos_climate_pca_row", atom_types)
        self.assertIn("plos_climate_variable_correlation_row", atom_types)
        self.assertIn("plos_climate_moran_i_row", atom_types)
        self.assertTrue(any(record.payload.get("reason") == "plos_suitability_raster_files_not_downloadable" for record in result.records if record.payload))


if __name__ == "__main__":
    unittest.main()
