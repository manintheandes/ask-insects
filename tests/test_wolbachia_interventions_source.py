import tempfile
import unittest
from pathlib import Path

from askinsects.sources.wolbachia_interventions import fetch_wolbachia_intervention_records


HTML = """
<html>
  <head>
    <title>Wolbachia reduces dengue in Yogyakarta</title>
    <meta name="description" content="World Mosquito Program Wolbachia method with Aedes aegypti.">
  </head>
  <body>
    <h1>Wolbachia dramatically reduces dengue cases</h1>
    <p>The randomized controlled trial in Yogyakarta, Indonesia showed a 77% reduction in dengue incidence.</p>
    <p>Wolbachia was introduced into local Aedes aegypti mosquitoes to reduce transmission of dengue, Zika, chikungunya, and yellow fever.</p>
  </body>
</html>
"""


class WolbachiaInterventionSourceTests(unittest.TestCase):
    def test_fetch_wolbachia_intervention_records_indexes_page_grain_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_wolbachia_intervention_records(
                [
                    {
                        "organization": "World Mosquito Program",
                        "url": "https://www.worldmosquitoprogram.org/example-yogyakarta",
                        "topic": "Yogyakarta Wolbachia randomized controlled trial",
                        "intervention_type": "wMel Wolbachia replacement",
                    }
                ],
                raw_dir=Path(tmpdir) / "raw",
                fetch_text=lambda url: HTML,
                retrieved_at="2026-05-24T00:00:00Z",
            )
            self.assertTrue(Path(result.raw_artifacts[0]).exists())

        self.assertEqual(result.source_id, "aedes_wolbachia_interventions")
        self.assertEqual(len(result.records), 1)
        record = result.records[0]
        self.assertEqual(record.lane, "public_health")
        self.assertEqual(record.source, "aedes_wolbachia_interventions")
        self.assertEqual(record.species, "Aedes aegypti")
        self.assertIn("77% reduction", record.text)
        self.assertIn("Yogyakarta", record.text)
        self.assertEqual(record.payload["intervention_type"], "wMel Wolbachia replacement")
        self.assertIn("77%", record.payload["metrics"])

    def test_fetch_wolbachia_intervention_records_normalizes_comma_grouped_metrics(self):
        html = """
        <html><body>
          <p>Wolbachia deployments protect 12,000 people across 14 countries.</p>
        </body></html>
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_wolbachia_intervention_records(
                [{"organization": "WMP", "url": "https://example.org/progress", "topic": "Progress"}],
                raw_dir=Path(tmpdir) / "raw",
                fetch_text=lambda url: html,
                retrieved_at="2026-05-24T00:00:00Z",
            )

        self.assertIn("12000 people", result.records[0].payload["metrics"])
        self.assertIn("14 countries", result.records[0].payload["metrics"])
        self.assertNotIn("000 people", result.records[0].payload["metrics"])

    def test_fetch_wolbachia_intervention_records_records_fetch_gaps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_wolbachia_intervention_records(
                [{"organization": "WMP", "url": "https://example.org/missing", "topic": "Wolbachia"}],
                raw_dir=Path(tmpdir) / "raw",
                fetch_text=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-24T00:00:00Z",
            )

        self.assertFalse(result.records)
        self.assertEqual(result.gaps[0]["reason"], "wolbachia_intervention_fetch_failed")


if __name__ == "__main__":
    unittest.main()
