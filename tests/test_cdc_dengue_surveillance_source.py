import tempfile
import unittest
from pathlib import Path

from askinsects.sources.cdc_dengue_surveillance import fetch_cdc_dengue_surveillance_records


CDC_HTML = """
<html>
<head>
<title>Current Year Data (2026) | Dengue | CDC</title>
<meta name="description" content="Current dengue data reported to CDC.">
</head>
<body>
<h1>Current Year Data (2026)</h1>
<span class="dfe-field">These data are provisional and subject to change. This page displays human cases only.</span>
<div class="wcms-viz-container" data-config-url="/dengue/statistics-maps/final-pages/data-visuals/current-year-tabs-updated.json"></div>
<h2>Limitations of ArboNET</h2>
<p>Surveillance data have several limitations that should be considered when using and interpreting the data.</p>
<p>1. Under-reporting is a limitation common to all surveillance systems.</p>
<p>2. Surveillance data are reported by county of residence, not the location of exposure.</p>
</body>
</html>
"""


CONFIG_JSON = """
{
  "type": "dashboard",
  "multiDashboards": [
    {
      "visualizations": {
        "map1": {
          "type": "map",
          "dataKey": "https://www.cdc.gov/wcms/vizdata/live/ncezid_dvbd/DEN/Cases_by_Jurisdiction_Current.csv",
          "table": {"label": "Data Table - Dengue cases by jurisdiction based on travel status selected above, 2026"}
        },
        "chart1": {
          "type": "chart",
          "dataKey": "https://www.cdc.gov/wcms/vizdata/live/ncezid_dvbd/DEN/Epi_Curve_Current.csv",
          "table": {"label": "Data Table - Dengue cases by week based on travel status selected above, 2026"}
        }
      }
    }
  ],
  "datasets": {
    "https://www.cdc.gov/wcms/vizdata/live/ncezid_dvbd/DEN/Cases_by_Jurisdiction_Current.csv": {
      "dataUrl": "https://www.cdc.gov/wcms/vizdata/live/ncezid_dvbd/DEN/Cases_by_Jurisdiction_Current.csv",
      "dataFileFormat": "CSV"
    }
  }
}
"""


JURISDICTION_CSV = """Year,Travel status,Jurisdiction,Count,Legend,Notes
2026,All,FL,14,5 to 49,
2026,Travel associated,NY,3,1 to 4,
"""


EPI_CSV = """Year,Travel status,Week,Reported cases
2026,All,01,50
2026,All,02,124
"""


class CdcDengueSurveillanceSourceTests(unittest.TestCase):
    def test_fetch_cdc_dengue_surveillance_records_parses_pages_configs_and_csv_rows(self):
        def fake_fetch(url):
            if url.endswith("current-data.html"):
                return CDC_HTML
            if url.endswith("current-year-tabs-updated.json"):
                return CONFIG_JSON
            if url.endswith("Cases_by_Jurisdiction_Current.csv"):
                return JURISDICTION_CSV
            if url.endswith("Epi_Curve_Current.csv"):
                return EPI_CSV
            raise AssertionError(f"unexpected URL {url}")

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_cdc_dengue_surveillance_records(
                [
                    {
                        "organization": "CDC",
                        "url": "https://www.cdc.gov/dengue/data-research/facts-stats/current-data.html",
                        "page_kind": "current_year",
                        "topic": "current dengue surveillance",
                    }
                ],
                raw_dir=Path(tmpdir) / "raw",
                fetch_text=fake_fetch,
                retrieved_at="2026-05-25T00:00:00Z",
            )

            self.assertEqual(result.source_id, "aedes_cdc_dengue_surveillance")
            self.assertEqual(result.page_count, 1)
            self.assertEqual(result.config_count, 1)
            self.assertEqual(result.dataset_count, 2)
            self.assertEqual(result.dataset_row_count, 4)
            self.assertEqual(result.limitation_count, 3)
            self.assertFalse(result.gaps)
            page = next(record for record in result.records if record.payload["aggregation_type"] == "cdc_surveillance_page")
            self.assertEqual(page.lane, "public_health")
            self.assertEqual(page.species, "Aedes aegypti")
            self.assertEqual(page.payload["config_urls"], ["https://www.cdc.gov/dengue/statistics-maps/final-pages/data-visuals/current-year-tabs-updated.json"])
            row = next(record for record in result.records if record.payload["aggregation_type"] == "cdc_dengue_csv_row" and record.payload["row"]["Jurisdiction"] == "FL")
            self.assertEqual(row.payload["measures"]["Count"], 14.0)
            self.assertEqual(row.payload["dimensions"]["Jurisdiction"], "FL")
            self.assertIn("#row/1", row.provenance.locator)
            limitation = next(record for record in result.records if record.payload["aggregation_type"] == "arbonet_limitation" and record.payload["limitation_index"] == 2)
            self.assertIn("Under-reporting", limitation.text)
            self.assertTrue(Path(result.raw_artifacts[0]).exists())

    def test_fetch_cdc_dengue_surveillance_records_records_fetch_gap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_cdc_dengue_surveillance_records(
                [{"url": "https://www.cdc.gov/dengue/data-research/facts-stats/current-data.html", "page_kind": "current_year"}],
                raw_dir=Path(tmpdir) / "raw",
                fetch_text=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-25T00:00:00Z",
            )

            self.assertFalse(result.records)
            self.assertEqual(result.gaps[0]["reason"], "cdc_dengue_page_fetch_failed")


if __name__ == "__main__":
    unittest.main()
