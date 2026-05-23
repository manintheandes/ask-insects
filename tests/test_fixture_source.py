import unittest
from pathlib import Path

from askinsects.sources.fixtures import load_fixture_records


class FixtureSourceTests(unittest.TestCase):
    def test_fixture_loader_returns_records_with_provenance(self):
        records = load_fixture_records(Path("data/fixtures/mosquito_records.json"))

        self.assertGreaterEqual(len(records), 7)
        first = records[0]
        self.assertEqual(first.source, "mosquito_v1_fixtures")
        self.assertTrue(first.provenance.locator.startswith("data/fixtures/mosquito_records.json#"))
        self.assertEqual(first.provenance.retrieved_at, "2026-05-23T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
