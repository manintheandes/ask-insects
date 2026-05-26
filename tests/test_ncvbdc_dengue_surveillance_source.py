import tempfile
import unittest
from pathlib import Path

from askinsects.sources.ncvbdc_dengue_surveillance import fetch_ncvbdc_dengue_surveillance_records


NCVBDC_HTML = """
<html>
<body>
<h1>DENGUE SITUATION IN INDIA</h1>
<p><strong>Dengue Cases and Deaths in the Country</strong></p>
<table>
<tr>
  <td rowspan="2">Sl. No.</td><td rowspan="2">Affected States/UTs</td>
  <td colspan="2">2021</td><td colspan="2">2022</td><td colspan="2">2023</td>
  <td colspan="2">2024</td><td colspan="2">2025</td><td colspan="2">2026*</td>
</tr>
<tr><td>C</td><td>D</td><td>C</td><td>D</td><td>C</td><td>D</td><td>C</td><td>D</td><td>C</td><td>D</td><td>C</td><td>D</td></tr>
<tr>
  <td>1</td><td><strong>Andhra Pradesh</strong></td>
  <td>4760</td><td>0</td><td>6391</td><td>0</td><td>6453</td><td>0</td>
  <td>5555</td><td>2</td><td>2686</td><td>5</td><td>448</td><td>0</td>
</tr>
<tr>
  <td>&nbsp;</td><td><strong>Total</strong></td>
  <td><strong>193245</strong></td><td><strong>346</strong></td>
  <td><strong>233251</strong></td><td><strong>303</strong></td>
  <td><strong>289235</strong></td><td><strong>485</strong></td>
  <td><strong>233519</strong></td><td><strong>297</strong></td>
  <td><strong>121824</strong></td><td><strong>131</strong></td>
  <td><strong>6927</strong></td><td><strong>10</strong></td>
</tr>
</table>
<p>*Provisional till 28th Feb. 2026</p>
<p>C=Cases | D=Deaths | NR=Not Reported</p>
</body>
</html>
"""


class NcvbdcDengueSurveillanceSourceTests(unittest.TestCase):
    def test_fetch_ncvbdc_records_parses_state_country_and_recent_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_ncvbdc_dengue_surveillance_records(
                [{"organization": "NCVBDC", "url": "https://ncvbdc.example/dengue", "topic": "India dengue"}],
                raw_dir=Path(tmpdir) / "raw",
                fetch_text=lambda url: NCVBDC_HTML,
                retrieved_at="2026-05-26T00:00:00Z",
            )

            self.assertEqual(result.source_id, "aedes_ncvbdc_dengue_surveillance")
            self.assertEqual(result.gaps, [])
            self.assertEqual(result.page_count, 1)
            self.assertEqual(result.table_row_count, 2)
            self.assertEqual(result.state_year_record_count, 6)
            self.assertEqual(result.national_year_record_count, 6)
            self.assertEqual(result.recent_summary_count, 1)
            self.assertEqual(len(result.records), 14)

            summary = next(record for record in result.records if "last_two_complete_years" in record.record_id)
            self.assertEqual(summary.lane, "public_health")
            self.assertEqual(summary.species, "Aedes aegypti")
            self.assertEqual(summary.payload["years"], [2024, 2025])
            self.assertEqual(summary.payload["deaths_by_year"], {2024: 297, 2025: 131})
            self.assertEqual(summary.payload["total_deaths"], 428)
            self.assertIn("Total dengue deaths: 428", summary.text)

            row_2026 = next(record for record in result.records if record.record_id.endswith(":country:india:2026"))
            self.assertTrue(row_2026.payload["is_provisional"])
            self.assertIn("Provisional till 28th Feb. 2026", row_2026.text)
            self.assertTrue(Path(result.raw_artifacts[0]).exists())

    def test_fetch_ncvbdc_records_records_fetch_gap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_ncvbdc_dengue_surveillance_records(
                [{"organization": "NCVBDC", "url": "https://ncvbdc.example/missing"}],
                raw_dir=Path(tmpdir) / "raw",
                fetch_text=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-26T00:00:00Z",
            )

            self.assertFalse(result.records)
            self.assertEqual(result.gaps[0]["reason"], "ncvbdc_dengue_page_fetch_failed")


if __name__ == "__main__":
    unittest.main()
