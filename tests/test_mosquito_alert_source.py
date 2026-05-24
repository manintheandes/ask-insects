import tempfile
import unittest
from pathlib import Path

from askinsects.sources.mosquito_alert import (
    AEDES_AEGYPTI_TAXON_KEY,
    MOSQUITO_ALERT_DATASET_KEY,
    MOSQUITO_ALERT_SOURCE_ID,
    fetch_mosquito_alert_records,
)


def mosquito_alert_dataset_payload():
    return {
        "key": MOSQUITO_ALERT_DATASET_KEY,
        "title": "Mosquito Alert Dataset",
        "doi": "10.15470/t5a1os",
        "license": "http://creativecommons.org/publicdomain/zero/1.0/legalcode",
        "citation": {"text": "Mosquito Alert Dataset citation"},
    }


def mosquito_alert_occurrence_payload(results=None, count=1):
    return {
        "count": count,
        "limit": 1,
        "offset": 0,
        "results": results
        if results is not None
        else [
            {
                "key": 4909387174,
                "datasetKey": MOSQUITO_ALERT_DATASET_KEY,
                "datasetName": "Mosquito Alert Dataset",
                "species": "Aedes aegypti",
                "scientificName": "Aedes aegypti (Linnaeus, 1762)",
                "country": "Brazil",
                "eventDate": "2023-01-24",
                "license": "http://creativecommons.org/publicdomain/zero/1.0/legalcode",
                "basisOfRecord": "HUMAN_OBSERVATION",
                "identifiedBy": "Example expert",
                "media": [
                    {
                        "type": "StillImage",
                        "format": "image/jpeg",
                        "license": "Anonymous, CC by Mosquito Alert",
                        "rightsHolder": "Mosquito Alert",
                        "creator": "Anonymous Mosquito Alert citizen scientist",
                        "identifier": "http://webserver.mosquitoalert.com/media/tigapics/example.jpg",
                    }
                ],
            }
        ],
    }


class FakeMosquitoAlertFetcher:
    def __init__(self, occurrence_payload=None):
        self.occurrence_payload = occurrence_payload or mosquito_alert_occurrence_payload()
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        if "/dataset/" in url:
            return mosquito_alert_dataset_payload()
        return self.occurrence_payload


class MosquitoAlertSourceTests(unittest.TestCase):
    def test_fetch_mosquito_alert_records_normalizes_observation_and_media(self):
        fetcher = FakeMosquitoAlertFetcher()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_mosquito_alert_records(
                raw_dir=Path(tmpdir) / "raw" / "mosquito_alert",
                occurrence_limit=1,
                occurrence_page_size=1,
                fetch_json=fetcher,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertEqual(result.source_id, MOSQUITO_ALERT_SOURCE_ID)
            self.assertEqual(result.dataset_key, MOSQUITO_ALERT_DATASET_KEY)
            self.assertEqual(result.taxon_key, AEDES_AEGYPTI_TAXON_KEY)
            self.assertEqual(result.total_results, 1)
            self.assertFalse(result.gaps)
            self.assertEqual(len(result.records), 2)
            self.assertTrue(any("datasetKey=1fef1ead" in url for url in fetcher.urls))
            self.assertTrue(any("taxonKey=1651891" in url for url in fetcher.urls))
            self.assertTrue(any("mediaType=StillImage" in url for url in fetcher.urls))
            self.assertTrue(any("basisOfRecord=HUMAN_OBSERVATION" in url for url in fetcher.urls))

            observation = next(record for record in result.records if record.lane == "observations")
            self.assertEqual(observation.record_id, "mosquito_alert:observation:4909387174")
            self.assertEqual(observation.source, MOSQUITO_ALERT_SOURCE_ID)
            self.assertEqual(observation.species, "Aedes aegypti")
            self.assertEqual(observation.url, "https://www.gbif.org/occurrence/4909387174")
            self.assertEqual(observation.media_url, "http://webserver.mosquitoalert.com/media/tigapics/example.jpg")
            self.assertIn("Mosquito Alert", observation.text)
            self.assertIn("Brazil", observation.text)
            self.assertIn("occurrence/4909387174", observation.provenance.locator)
            self.assertEqual(observation.payload["raw_occurrence"]["key"], 4909387174)

            media = next(record for record in result.records if record.lane == "media")
            self.assertEqual(media.source, MOSQUITO_ALERT_SOURCE_ID)
            self.assertEqual(media.media_url, "http://webserver.mosquitoalert.com/media/tigapics/example.jpg")
            self.assertIn("still image", media.text)
            self.assertEqual(media.provenance.license, "Anonymous, CC by Mosquito Alert")
            self.assertEqual(media.provenance.source_url, "http://webserver.mosquitoalert.com/media/tigapics/example.jpg")
            self.assertEqual(media.payload["raw_media"]["rightsHolder"], "Mosquito Alert")

    def test_fetch_mosquito_alert_records_records_gap_when_no_occurrences(self):
        fetcher = FakeMosquitoAlertFetcher(mosquito_alert_occurrence_payload(results=[], count=0))
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_mosquito_alert_records(
                raw_dir=Path(tmpdir) / "raw" / "mosquito_alert",
                occurrence_limit=1,
                fetch_json=fetcher,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertEqual(result.records, [])
            self.assertEqual(result.gaps[0]["source"], MOSQUITO_ALERT_SOURCE_ID)
            self.assertEqual(result.gaps[0]["reason"], "Mosquito Alert GBIF dataset returned no Aedes aegypti occurrence records.")


if __name__ == "__main__":
    unittest.main()
