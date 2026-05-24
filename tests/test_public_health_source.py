import tempfile
import unittest
from pathlib import Path

from askinsects.sources.public_health import fetch_public_health_guidance_records


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


if __name__ == "__main__":
    unittest.main()
