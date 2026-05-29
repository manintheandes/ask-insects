import tempfile
import unittest
from pathlib import Path

from askinsects.sources.drosophila_suzukii_extension_guidance import (
    DROSOPHILA_SUZUKII_EXTENSION_GUIDANCE_SOURCE_ID,
    fetch_drosophila_suzukii_extension_guidance_records,
)


HTML = """
<html>
  <head>
    <title>Spotted wing drosophila management</title>
    <meta name="description" content="Monitor traps, harvest fruit, use sanitation, and manage spotted wing drosophila.">
  </head>
  <body>
    <h1>Spotted wing drosophila management</h1>
    Drosophila suzukii integrated pest management includes monitoring, trapping, sanitation,
    exclusion netting, insecticide rotation, and fruit damage prevention.
  </body>
</html>
"""


class DrosophilaSuzukiiExtensionGuidanceSourceTests(unittest.TestCase):
    def test_guidance_page_becomes_management_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_extension_guidance_records(
                [
                    {
                        "organization": "Test Extension",
                        "url": "https://extension.example/swd",
                        "topic": "spotted wing drosophila management",
                        "region": "test region",
                    }
                ],
                raw_dir=Path(tmpdir),
                fetch_text=lambda url: HTML,
                retrieved_at="2026-05-29T00:00:00Z",
            )

        self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_EXTENSION_GUIDANCE_SOURCE_ID)
        self.assertEqual(len(result.records), 1)
        record = result.records[0]
        self.assertEqual(record.source, DROSOPHILA_SUZUKII_EXTENSION_GUIDANCE_SOURCE_ID)
        self.assertEqual(record.lane, "management")
        self.assertEqual(record.species, "Drosophila suzukii")
        self.assertEqual(record.payload["atom_type"], "extension_guidance_page")
        self.assertIn("monitoring", record.text.lower())
        self.assertTrue(result.raw_artifacts[0].endswith(".html"))

    def test_fetch_failure_becomes_gap(self):
        def fail(url):
            raise RuntimeError("offline")

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_extension_guidance_records(
                [{"organization": "Test Extension", "url": "https://extension.example/swd"}],
                raw_dir=Path(tmpdir),
                fetch_text=fail,
                retrieved_at="2026-05-29T00:00:00Z",
            )

        self.assertEqual(result.records, [])
        self.assertEqual(result.gaps[0]["source"], DROSOPHILA_SUZUKII_EXTENSION_GUIDANCE_SOURCE_ID)
        self.assertEqual(result.gaps[0]["reason"], "swd_extension_guidance_fetch_failed")


if __name__ == "__main__":
    unittest.main()
