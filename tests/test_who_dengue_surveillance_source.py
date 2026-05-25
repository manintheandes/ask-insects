import tempfile
import unittest
from pathlib import Path

from askinsects.sources.who_dengue_surveillance import fetch_who_dengue_surveillance_records


WPRO_HTML = """
<html>
<body>
<h1>Dengue</h1>
<p>WHO's Western Pacific Regional Office conducts both indicator-based and event-based surveillance for dengue.</p>
<p>A summary of the situation in the region is published bi-weekly.</p>
<a href="https://www.who.int/westernpacific/publications/m/item/dengue-situation-update---745--14-may-2026">17 May 2026 Dengue Situation Update # 745: 14 May 2026</a>
<a href="https://cdn.who.int/media/docs/default-source/wpro---documents/emergency/surveillance/dengue/dengue_biweekly_744_20260430.pdf?sfvrsn=29f63a6a_1">Dengue Situation Update 744</a>
<a href="https://iris.who.int/handle/10665/2026">Dengue Situation Updates 2026</a>
</body>
</html>
"""

WER_HTML = """
<html>
<head><meta name="description" content="Dengue: global situation, surveillance and progress - 2024 update"></head>
<body>
<h1>Dengue: global situation, surveillance and progress - 2024 update</h1>
<p>Weekly epidemiological record</p>
<p>26 December 2025 | Publication</p>
<a href="https://iris.who.int/bitstream/handle/10665/382381/WER10052-eng-fre.pdf">Download (230.5 kB)</a>
<p>WHO received reports of 14 434 584 cases, including 7 718 585 laboratory-confirmed, 52 738 severe and 11 201 deaths in all 6 regions.</p>
<p>Brazil alone reported over 10 000 000 cases and 6321 deaths.</p>
</body>
</html>
"""

DASHBOARD_HTML = """
<html>
<body>
<h1>Dengue surveillance 2021</h1>
<p>WHO's Health Emergencies Programme therefore monitors and assesses the spread of dengue on an ongoing basis.</p>
<a href="https://data.wpro.who.int/shiny/dengue">Enter dashboard</a>
</body>
</html>
"""

EXPORT_HTML = """
<html>
<body>
<h1>Dengue surveillance dataset</h1>
<a href="/files/dengue-surveillance.csv">Download CSV</a>
</body>
</html>
"""


class WhoDengueSurveillanceSourceTests(unittest.TestCase):
    def test_fetch_who_dengue_surveillance_records_parses_pages_links_and_gaps(self):
        def fake_fetch(url):
            if "wer" in url:
                return WER_HTML
            if "dashboard" in url:
                return DASHBOARD_HTML
            return WPRO_HTML

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_who_dengue_surveillance_records(
                [
                    {
                        "url": "https://www.who.int/westernpacific/wpro-emergencies/surveillance/dengue",
                        "page_kind": "wpro_situation_updates",
                        "organization": "WHO Western Pacific",
                        "topic": "Western Pacific dengue situation updates",
                    },
                    {
                        "url": "https://www.who.int/publications/i/item/who-wer10052-665-678",
                        "page_kind": "wer_global_update",
                        "organization": "WHO",
                        "topic": "global dengue update",
                    },
                    {
                        "url": "https://data.wpro.who.int/dashboard",
                        "page_kind": "wpro_dashboard_locator",
                        "organization": "WHO Western Pacific Health Data Platform",
                        "topic": "dashboard locator",
                    },
                ],
                raw_dir=Path(tmpdir) / "raw",
                fetch_text=fake_fetch,
                retrieved_at="2026-05-25T00:00:00Z",
            )

            self.assertEqual(result.source_id, "aedes_who_dengue_surveillance")
            self.assertGreaterEqual(len(result.records), 8)
            self.assertEqual(result.page_count, 3)
            self.assertEqual(result.situation_report_count, 2)
            self.assertEqual(result.archive_count, 1)
            self.assertEqual(result.publication_count, 1)
            self.assertEqual(result.dashboard_locator_count, 1)
            self.assertEqual(result.export_locator_count, 0)
            page = next(record for record in result.records if record.payload.get("page_kind") == "wer_global_update")
            self.assertEqual(page.lane, "public_health")
            self.assertEqual(page.species, "Aedes aegypti")
            self.assertEqual(page.payload["metrics"]["reported_cases"], 14434584.0)
            self.assertEqual(page.payload["metrics"]["deaths"], 11201.0)
            pdf = next(record for record in result.records if record.payload.get("aggregation_type") == "who_dengue_publication_download_locator")
            self.assertEqual(pdf.media_url, "https://iris.who.int/bitstream/handle/10665/382381/WER10052-eng-fre.pdf")
            dashboard = next(record for record in result.records if record.payload.get("aggregation_type") == "who_dengue_dashboard_locator")
            self.assertEqual(dashboard.payload["machine_readable_cell_status"], "not_proven")
            self.assertEqual(result.gaps[0]["reason"], "who_dengue_dashboard_export_not_machine_readable")
            self.assertTrue(Path(result.raw_artifacts[0]).exists())

    def test_fetch_who_dengue_surveillance_records_indexes_export_links_when_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_who_dengue_surveillance_records(
                [
                    {
                        "url": "https://data.wpro.who.int/dashboard",
                        "page_kind": "wpro_dashboard_locator",
                        "organization": "WHO Western Pacific Health Data Platform",
                        "topic": "dashboard locator",
                    }
                ],
                raw_dir=Path(tmpdir) / "raw",
                fetch_text=lambda url: EXPORT_HTML,
                retrieved_at="2026-05-25T00:00:00Z",
            )

            self.assertEqual(result.export_locator_count, 1)
            self.assertEqual(result.gaps, [])
            export = next(record for record in result.records if record.payload.get("aggregation_type") == "who_dengue_export_locator")
            self.assertEqual(export.media_url, "https://data.wpro.who.int/files/dengue-surveillance.csv")

    def test_fetch_who_dengue_surveillance_records_records_fetch_gap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_who_dengue_surveillance_records(
                [{"url": "https://www.who.int/example", "page_kind": "custom"}],
                raw_dir=Path(tmpdir) / "raw",
                fetch_text=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-25T00:00:00Z",
            )

            self.assertFalse(result.records)
            self.assertEqual(result.gaps[0]["reason"], "who_dengue_page_fetch_failed")


if __name__ == "__main__":
    unittest.main()
