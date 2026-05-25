import tempfile
import unittest
from pathlib import Path

from askinsects.sources.vectorbyte_traits import fetch_vectorbyte_trait_records


SEARCH_PAYLOAD = {
    "count": 2,
    "hits": [
        {
            "id": "126",
            "db": "vt",
            "title": "Parity and longevity of Aedes aegypti according to temperatures",
            "type": "trait",
            "description": "Traits: transmission potential | Environment: laboratory | Locations: Guadeloupe",
            "doi": "10.1371/journal.pone.0135489",
            "published": "2015-01-01T00:00:00.000Z",
        },
        {
            "id": "474",
            "db": "vt",
            "title": "Assessing the effects of temperature on the population of Aedes aegypti",
            "type": "trait",
            "description": "Traits: fecundity rate | Environment: laboratory | Locations: Marilia Brazil",
            "doi": "10.1017/S0950268809002040",
            "published": "2009-01-01T00:00:00.000Z",
        },
    ],
}

DATASET_126 = {
    "results": [
        {
            "Id": "82835",
            "DatasetID": 126,
            "OriginalTraitName": "transmission potential",
            "OriginalTraitDef": "percent of individuals with transmission potential",
            "OriginalTraitValue": 28.0,
            "OriginalTraitUnit": "percent",
            "Habitat": "terrestrial",
            "LabField": "laboratory",
            "Location": "Guadeloupe French West Indies",
            "LocationType": "field",
            "Latitude": 16.25,
            "Longitude": -61.58,
            "Interactor1": "Aedes aegypti",
            "Interactor1Genus": "Aedes",
            "Interactor1Species": "aegypti",
            "Interactor1Stage": "adult",
            "Interactor1Sex": "female",
            "Interactor1Temp": 24.0,
            "Interactor1TempUnit": "Celsius",
            "Citation": "Goindin et al. 2015. Parity and longevity of Aedes aegypti according to temperatures.",
            "DOI": "10.1371/journal.pone.0135489",
        },
        {
            "Id": "skip-culex",
            "DatasetID": 126,
            "OriginalTraitName": "longevity",
            "OriginalTraitValue": 11.0,
            "OriginalTraitUnit": "day",
            "Interactor1": "Culex pipiens",
            "Interactor1Genus": "Culex",
            "Interactor1Species": "pipiens",
        },
    ]
}

DATASET_474 = {
    "results": [
        {
            "Id": "89092",
            "DatasetID": 474,
            "OriginalTraitName": "fecundity rate",
            "OriginalTraitDef": "mean eggs per unit time",
            "OriginalTraitValue": 0.0,
            "OriginalTraitUnit": "eggs individual-1 day-1",
            "Habitat": "terrestrial",
            "LabField": "laboratory",
            "Location": "Marilia Brazil",
            "LocationType": "field",
            "Latitude": -22.213889,
            "Longitude": -49.945833,
            "Interactor1": "Aedes aegypti",
            "Interactor1Genus": "Aedes",
            "Interactor1Species": "aegypti",
            "Interactor1Stage": "adult",
            "Interactor1Sex": "female",
            "Interactor1Temp": 10.54,
            "Interactor1TempUnit": "Celsius",
            "FigureTable": "table 5",
            "Citation": "Yang et al. 2009. Assessing the effects of temperature on the population of Aedes aegypti.",
            "DOI": "10.1017/S0950268809002040",
        }
    ]
}


class VectorByteTraitsSourceTests(unittest.TestCase):
    def test_fetch_vectorbyte_trait_records_indexes_aedes_trait_rows(self):
        calls = []

        def fake_fetch_json(url):
            calls.append(url)
            if "api.vbdhub.org/search" in url:
                return SEARCH_PAYLOAD
            if "/vectraits-dataset/126/" in url:
                return DATASET_126
            if "/vectraits-dataset/474/" in url:
                return DATASET_474
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_vectorbyte_trait_records(
                raw_dir=Path(tmpdir) / "raw" / "vectorbyte_traits",
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-25T00:00:00Z",
                dataset_limit=2,
                row_limit=100,
                search_limit=10,
            )

        self.assertEqual(result.source_id, "aedes_vectorbyte_traits")
        self.assertEqual(result.gaps, [])
        self.assertEqual(len(result.records), 2)
        self.assertEqual(len(result.raw_artifacts), 3)
        self.assertEqual(len(calls), 3)
        record_ids = {record.record_id for record in result.records}
        self.assertIn("vectorbyte:trait:126:82835", record_ids)
        self.assertIn("vectorbyte:trait:474:89092", record_ids)
        transmission = next(record for record in result.records if record.record_id == "vectorbyte:trait:126:82835")
        self.assertEqual(transmission.lane, "traits")
        self.assertEqual(transmission.source, "aedes_vectorbyte_traits")
        self.assertEqual(transmission.species, "Aedes aegypti")
        self.assertIn("transmission potential", transmission.text)
        self.assertIn("24.0 Celsius", transmission.text)
        self.assertIn("Guadeloupe", transmission.text)
        self.assertEqual(transmission.payload["dataset_id"], "126")
        self.assertEqual(transmission.payload["trait_value"], 28.0)
        self.assertEqual(transmission.payload["temperature"], 24.0)
        self.assertEqual(transmission.provenance.source_id, "aedes_vectorbyte_traits")
        self.assertIn("raw/vectorbyte_traits", transmission.provenance.locator)
        self.assertEqual(transmission.provenance.source_url, "https://vectorbyte.crc.nd.edu/portal/api/vectraits-dataset/126/?format=json")

    def test_fetch_vectorbyte_trait_records_records_search_and_dataset_gaps(self):
        def fake_empty_search(url):
            return {"count": 0, "hits": []}

        with tempfile.TemporaryDirectory() as tmpdir:
            empty = fetch_vectorbyte_trait_records(
                raw_dir=Path(tmpdir) / "raw-empty",
                fetch_json=fake_empty_search,
                retrieved_at="2026-05-25T00:00:00Z",
            )

        self.assertFalse(empty.records)
        self.assertIn("vectorbyte_traits_no_search_hits", {gap["reason"] for gap in empty.gaps})

        def fake_dataset_failure(url):
            if "api.vbdhub.org/search" in url:
                return SEARCH_PAYLOAD
            raise RuntimeError("offline")

        with tempfile.TemporaryDirectory() as tmpdir:
            failed = fetch_vectorbyte_trait_records(
                raw_dir=Path(tmpdir) / "raw-failed",
                fetch_json=fake_dataset_failure,
                retrieved_at="2026-05-25T00:00:00Z",
                dataset_limit=1,
            )

        self.assertFalse(failed.records)
        self.assertIn("vectorbyte_traits_dataset_fetch_failed", {gap["reason"] for gap in failed.gaps})

    def test_fetch_vectorbyte_trait_records_caps_search_limit_to_api_max(self):
        calls = []

        def fake_empty_search(url):
            calls.append(url)
            return {"count": 0, "hits": []}

        with tempfile.TemporaryDirectory() as tmpdir:
            fetch_vectorbyte_trait_records(
                raw_dir=Path(tmpdir) / "raw-capped",
                fetch_json=fake_empty_search,
                retrieved_at="2026-05-25T00:00:00Z",
                search_limit=100,
            )

        self.assertIn("limit=50", calls[0])
        self.assertNotIn("limit=100", calls[0])


if __name__ == "__main__":
    unittest.main()
