import json
import tempfile
import unittest
from pathlib import Path

from askinsects.sources.inaturalist import INATURALIST_SOURCE_ID, fetch_inaturalist_records


class FakeINaturalistFetcher:
    def __init__(self, payload):
        self.payload = payload
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        return self.payload


def observation_payload(photo_url="https://static.inaturalist.org/photos/1/medium.jpg"):
    return {
        "total_results": 1,
        "page": 1,
        "per_page": 1,
        "results": [
            {
                "id": 12345,
                "uri": "https://www.inaturalist.org/observations/12345",
                "observed_on": "2021-02-03",
                "place_guess": "Rio de Janeiro, Brazil",
                "license_code": "cc-by",
                "taxon": {
                    "name": "Aedes aegypti",
                    "preferred_common_name": "yellow fever mosquito",
                },
                "photos": [
                    {
                        "id": 99,
                        "url": photo_url,
                        "license_code": "cc-by",
                        "attribution": "(c) Example Observer, some rights reserved",
                    }
                ],
            }
        ],
    }


class INaturalistSourceTests(unittest.TestCase):
    def test_fetch_inaturalist_records_normalizes_observation_and_media(self):
        fetcher = FakeINaturalistFetcher(observation_payload())
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_inaturalist_records(
                ["Aedes aegypti"],
                raw_dir=Path(tmpdir) / "raw" / "inaturalist",
                place="Brazil",
                observation_limit=1,
                fetch_json=fetcher,
                retrieved_at="2026-05-23T00:00:00Z",
            )

            self.assertEqual(result.source_id, INATURALIST_SOURCE_ID)
            self.assertEqual(result.requested_species, ["Aedes aegypti"])
            self.assertEqual(result.place, "Brazil")
            self.assertFalse(result.gaps)
            self.assertEqual(len(result.records), 2)
            self.assertTrue(any("taxon_name=Aedes+aegypti" in url for url in fetcher.urls))
            self.assertTrue(any("photos=true" in url for url in fetcher.urls))

            observation = next(record for record in result.records if record.lane == "observations")
            self.assertEqual(observation.record_id, "inat:observation:12345")
            self.assertEqual(observation.source, INATURALIST_SOURCE_ID)
            self.assertEqual(observation.species, "Aedes aegypti")
            self.assertEqual(observation.url, "https://www.inaturalist.org/observations/12345")
            self.assertEqual(observation.media_url, "https://static.inaturalist.org/photos/1/medium.jpg")
            self.assertIn("Rio de Janeiro", observation.text)
            self.assertEqual(observation.provenance.license, "cc-by")
            self.assertIn("observations", observation.provenance.locator)

            media = next(record for record in result.records if record.lane == "media")
            self.assertEqual(media.record_id, "inat:media:99")
            self.assertEqual(media.media_url, "https://static.inaturalist.org/photos/1/medium.jpg")
            self.assertIn("still image", media.text)
            self.assertEqual(media.provenance.source_url, "https://www.inaturalist.org/observations/12345")

            raw_path = Path(tmpdir) / "raw" / "inaturalist" / "Aedes_aegypti_Brazil_observations.json"
            self.assertTrue(raw_path.exists())
            self.assertEqual(json.loads(raw_path.read_text(encoding="utf-8"))["total_results"], 1)

    def test_fetch_inaturalist_records_records_gap_when_no_photos(self):
        payload = observation_payload(photo_url=None)
        payload["results"][0]["photos"] = []
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_inaturalist_records(
                ["Aedes aegypti"],
                raw_dir=Path(tmpdir),
                place=None,
                observation_limit=1,
                fetch_json=FakeINaturalistFetcher(payload),
                retrieved_at="2026-05-23T00:00:00Z",
            )

            self.assertEqual(result.records, [])
            self.assertEqual(result.gaps[0]["source"], INATURALIST_SOURCE_ID)
            self.assertEqual(result.gaps[0]["lane"], "media")

    def test_fetch_inaturalist_records_records_gap_when_no_observations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_inaturalist_records(
                ["Aedes aegypti"],
                raw_dir=Path(tmpdir),
                place="Brazil",
                observation_limit=1,
                fetch_json=FakeINaturalistFetcher({"total_results": 0, "results": []}),
                retrieved_at="2026-05-23T00:00:00Z",
            )

            self.assertEqual(result.records, [])
            self.assertEqual(result.gaps[0]["lane"], "observations")


if __name__ == "__main__":
    unittest.main()
