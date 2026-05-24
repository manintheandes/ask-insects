import tempfile
import unittest
from pathlib import Path

from askinsects.sources.public_health import DEFAULT_PUBLIC_HEALTH_SOURCES, fetch_public_health_guidance_records


HTML = """
<html>
  <head>
    <title>Integrated mosquito management</title>
    <meta name="description" content="Guidance for vector control programs working on Aedes aegypti, dengue, and Zika.">
  </head>
  <body>
    <h1>Integrated mosquito management</h1>
    <p>Aedes aegypti mosquitoes can transmit dengue, Zika, chikungunya, and yellow fever.</p>
    <p>Vector control programs use surveillance, source reduction, larvicides, adulticides, and community action.</p>
  </body>
</html>
"""


class PublicHealthSourceTests(unittest.TestCase):
    def test_fetch_public_health_guidance_records_normalizes_pages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_public_health_guidance_records(
                [
                    {
                        "organization": "CDC",
                        "url": "https://www.cdc.gov/example",
                        "topic": "integrated mosquito management",
                    }
                ],
                raw_dir=Path(tmpdir) / "raw",
                fetch_text=lambda url: HTML,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertEqual(result.source_id, "aedes_public_health_guidance")
            self.assertEqual(len(result.records), 1)
            record = result.records[0]
            self.assertEqual(record.lane, "public_health")
            self.assertEqual(record.source, "aedes_public_health_guidance")
            self.assertEqual(record.species, "Aedes aegypti")
            self.assertIn("vector control", record.text)
            self.assertIn("dengue", record.text)
            self.assertTrue(record.payload)
            self.assertEqual(record.payload["organization"], "CDC")
            self.assertTrue(Path(result.raw_artifacts[0]).exists())

    def test_fetch_public_health_guidance_records_records_fetch_gaps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_public_health_guidance_records(
                [{"organization": "WHO", "url": "https://www.who.int/missing", "topic": "dengue"}],
                raw_dir=Path(tmpdir) / "raw",
                fetch_text=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertFalse(result.records)
            self.assertEqual(result.gaps[0]["reason"], "public_health_guidance_fetch_failed")

    def test_default_public_health_sources_include_official_aedes_and_dengue_references(self):
        urls = {str(source["url"]) for source in DEFAULT_PUBLIC_HEALTH_SOURCES}

        self.assertIn("https://www.who.int/en/news-room/fact-sheets/detail/dengue-and-severe-dengue", urls)
        self.assertIn("https://www.cdc.gov/dengue/prevention/index.html", urls)
        self.assertIn("https://www.cdc.gov/mosquitoes/about/life-cycle-of-aedes-mosquitoes.html", urls)
        self.assertIn("https://www.ecdc.europa.eu/en/disease-vectors/facts/mosquito-factsheets/aedes-aegypti", urls)


if __name__ == "__main__":
    unittest.main()
