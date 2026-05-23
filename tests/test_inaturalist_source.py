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


class PagedINaturalistFetcher:
    def __init__(self, pages):
        self.pages = pages
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        page_marker = "page="
        page = 1
        if page_marker in url:
            page = int(url.split(page_marker, 1)[1].split("&", 1)[0])
        return self.pages[page]


def observation(observation_id, photo_id, place="Brazil"):
    return {
        "id": observation_id,
        "uri": f"https://www.inaturalist.org/observations/{observation_id}",
        "observed_on": "2021-02-03",
        "place_guess": place,
        "license_code": "cc-by",
        "taxon": {"name": "Aedes aegypti"},
        "photos": [
            {
                "id": photo_id,
                "url": f"https://static.inaturalist.org/photos/{photo_id}/medium.jpg",
                "license_code": "cc-by",
            }
        ],
    }


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

            raw_path = Path(tmpdir) / "raw" / "inaturalist" / "Aedes_aegypti_Brazil_page_001.json"
            self.assertTrue(raw_path.exists())
            self.assertEqual(json.loads(raw_path.read_text(encoding="utf-8"))["total_results"], 1)

    def test_fetch_inaturalist_records_paginates_and_dedupes(self):
        fetcher = PagedINaturalistFetcher(
            {
                1: {
                    "total_results": 4,
                    "page": 1,
                    "per_page": 2,
                    "results": [observation(1, 101), observation(2, 102)],
                },
                2: {
                    "total_results": 4,
                    "page": 2,
                    "per_page": 2,
                    "results": [observation(2, 102), observation(3, 103)],
                },
            }
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_inaturalist_records(
                ["Aedes aegypti"],
                raw_dir=Path(tmpdir) / "raw" / "inaturalist",
                place=None,
                observation_limit=4,
                page_size=2,
                delay_seconds=0,
                fetch_json=fetcher,
                retrieved_at="2026-05-23T00:00:00Z",
            )

            self.assertEqual(result.total_results["Aedes aegypti"], 4)
            self.assertEqual(result.page_size, 2)
            self.assertEqual(result.delay_seconds, 0)
            self.assertEqual(len(fetcher.urls), 2)
            self.assertTrue(any("page=1" in url and "per_page=2" in url for url in fetcher.urls))
            self.assertTrue(any("page=2" in url for url in fetcher.urls))

            observation_ids = sorted(record.record_id for record in result.records if record.lane == "observations")
            media_ids = sorted(record.record_id for record in result.records if record.lane == "media")
            self.assertEqual(observation_ids, ["inat:observation:1", "inat:observation:2", "inat:observation:3"])
            self.assertEqual(media_ids, ["inat:media:101", "inat:media:102", "inat:media:103"])

            raw_files = sorted(path.name for path in (Path(tmpdir) / "raw" / "inaturalist").glob("*.json"))
            self.assertEqual(
                raw_files,
                ["Aedes_aegypti_anywhere_page_001.json", "Aedes_aegypti_anywhere_page_002.json"],
            )

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
