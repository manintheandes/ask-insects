import json
import tempfile
import unittest
from pathlib import Path

from askinsects.sources.gbif import GBIF_SOURCE_ID, fetch_gbif_records


class FakeGBIFFetcher:
    def __init__(self):
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        if "/v2/species/match" in url:
            return {
                "usageKey": 1651891,
                "scientificName": "Aedes aegypti (Linnaeus, 1762)",
                "canonicalName": "Aedes aegypti",
                "rank": "SPECIES",
                "status": "ACCEPTED",
                "kingdom": "Animalia",
                "phylum": "Arthropoda",
                "class": "Insecta",
                "order": "Diptera",
                "family": "Culicidae",
                "genus": "Aedes",
                "species": "Aedes aegypti",
            }
        if "/v1/occurrence/search" in url:
            return {
                "count": 1,
                "results": [
                    {
                        "key": 444,
                        "species": "Aedes aegypti",
                        "scientificName": "Aedes aegypti",
                        "country": "Brazil",
                        "eventDate": "2020-01-02",
                        "datasetKey": "dataset-1",
                        "datasetName": "Example mosquito dataset",
                        "license": "CC_BY_4_0",
                        "references": "https://example.org/occurrence/444",
                        "media": [{"identifier": "https://example.org/aedes.jpg", "type": "StillImage"}],
                    }
                ],
            }
        raise AssertionError(f"unexpected URL: {url}")


class GBIFSourceTests(unittest.TestCase):
    def test_fetch_gbif_records_normalizes_taxonomy_and_occurrences(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_gbif_records(
                ["Aedes aegypti"],
                raw_dir=Path(tmpdir) / "raw" / "gbif",
                occurrence_limit=1,
                fetch_json=FakeGBIFFetcher(),
                retrieved_at="2026-05-23T00:00:00Z",
            )

            self.assertEqual(result.source_id, GBIF_SOURCE_ID)
            self.assertEqual(result.taxon_keys["Aedes aegypti"], 1651891)
            self.assertFalse(result.gaps)
            self.assertEqual(len(result.records), 2)

            taxonomy = next(record for record in result.records if record.lane == "taxonomy")
            self.assertEqual(taxonomy.source, GBIF_SOURCE_ID)
            self.assertEqual(taxonomy.species, "Aedes aegypti")
            self.assertEqual(taxonomy.url, "https://www.gbif.org/species/1651891")
            self.assertIn("GBIF accepted species", taxonomy.text)
            self.assertEqual(taxonomy.provenance.source_id, GBIF_SOURCE_ID)
            self.assertIn("species/match", taxonomy.provenance.locator)

            occurrence = next(record for record in result.records if record.lane == "observations")
            self.assertEqual(occurrence.record_id, "gbif:occurrence:444")
            self.assertEqual(occurrence.media_url, "https://example.org/aedes.jpg")
            self.assertIn("Brazil", occurrence.text)
            self.assertEqual(occurrence.provenance.source_url, "https://www.gbif.org/occurrence/444")

            raw_files = sorted(path.name for path in (Path(tmpdir) / "raw" / "gbif").glob("*.json"))
            self.assertEqual(raw_files, ["Aedes_aegypti_match.json", "Aedes_aegypti_occurrences.json"])
            raw_payload = json.loads((Path(tmpdir) / "raw" / "gbif" / "Aedes_aegypti_match.json").read_text())
            self.assertEqual(raw_payload["usageKey"], 1651891)

    def test_fetch_gbif_records_records_gap_when_species_does_not_match(self):
        def no_match_fetcher(url):
            return {"matchType": "NONE"} if "/species/match" in url else {"count": 0, "results": []}

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_gbif_records(
                ["Imaginary mosquito"],
                raw_dir=Path(tmpdir),
                occurrence_limit=1,
                fetch_json=no_match_fetcher,
                retrieved_at="2026-05-23T00:00:00Z",
            )

            self.assertEqual(result.records, [])
            self.assertEqual(result.gaps[0]["species"], "Imaginary mosquito")
            self.assertEqual(result.gaps[0]["lane"], "taxonomy")


if __name__ == "__main__":
    unittest.main()
