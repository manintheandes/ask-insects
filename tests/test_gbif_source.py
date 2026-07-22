import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest import mock

from askinsects.sources import gbif as gbif_module
from askinsects.sources.gbif import GBIFClient, GBIF_SOURCE_ID, fetch_gbif_records


class FakeGBIFFetcher:
    def __init__(self):
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        if "/v1/species/match" in url:
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
    def test_default_fetcher_retries_temporary_gbif_503(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"ok": true}'

        calls = {"n": 0}

        def flaky_urlopen(_request, timeout):
            self.assertEqual(timeout, 30)
            calls["n"] += 1
            if calls["n"] == 1:
                raise HTTPError("https://api.gbif.org/example", 503, "Backend fetch failed", hdrs=None, fp=io.BytesIO())
            return Response()

        with mock.patch.object(gbif_module, "urlopen", side_effect=flaky_urlopen), mock.patch.object(gbif_module.time, "sleep") as sleep:
            payload = GBIFClient._fetch_json("https://api.gbif.org/example")

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(calls["n"], 2)
        sleep.assert_called_once_with(1)

    def test_fetch_gbif_records_normalizes_taxonomy_and_occurrences(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = FakeGBIFFetcher()
            result = fetch_gbif_records(
                ["Aedes aegypti"],
                raw_dir=Path(tmpdir) / "raw" / "gbif",
                occurrence_limit=1,
                fetch_json=fetcher,
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
            self.assertTrue(any("/v1/species/match" in url for url in fetcher.urls))

            occurrence = next(record for record in result.records if record.lane == "observations")
            self.assertEqual(occurrence.record_id, "gbif:occurrence:444")
            self.assertEqual(occurrence.media_url, "https://example.org/aedes.jpg")
            self.assertIn("Brazil", occurrence.text)
            self.assertEqual(occurrence.provenance.source_url, "https://www.gbif.org/occurrence/444")
            self.assertEqual(occurrence.payload["raw_occurrence"]["key"], 444)
            self.assertEqual(taxonomy.payload["raw_match"]["usageKey"], 1651891)

            raw_files = sorted(path.name for path in (Path(tmpdir) / "raw" / "gbif").glob("*.json"))
            self.assertEqual(raw_files, ["Aedes_aegypti_match.json", "Aedes_aegypti_occurrences_offset_000000.json"])
            raw_payload = json.loads((Path(tmpdir) / "raw" / "gbif" / "Aedes_aegypti_match.json").read_text())
            self.assertEqual(raw_payload["usageKey"], 1651891)
            self.assertEqual(result.total_results["Aedes aegypti"], 1)
            self.assertEqual(result.page_count, 1)

    def test_fetch_gbif_records_accepts_source_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = FakeGBIFFetcher()
            result = fetch_gbif_records(
                ["Aedes aegypti"],
                raw_dir=Path(tmpdir) / "raw" / "gbif",
                occurrence_limit=1,
                fetch_json=fetcher,
                retrieved_at="2026-05-23T00:00:00Z",
                source_id="custom_gbif_source",
                record_prefix="custom_gbif",
            )

            self.assertEqual(result.source_id, "custom_gbif_source")
            self.assertEqual(result.gaps, [])
            taxonomy = next(record for record in result.records if record.lane == "taxonomy")
            self.assertEqual(taxonomy.record_id, "custom_gbif:taxon:1651891")
            self.assertEqual(taxonomy.source, "custom_gbif_source")
            self.assertEqual(taxonomy.provenance.source_id, "custom_gbif_source")
            occurrence = next(record for record in result.records if record.lane == "observations")
            self.assertEqual(occurrence.record_id, "custom_gbif:occurrence:444")
            self.assertEqual(occurrence.source, "custom_gbif_source")
            self.assertEqual(occurrence.provenance.source_id, "custom_gbif_source")

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

    def test_fetch_gbif_records_paginates_occurrences(self):
        def paged_fetcher(url):
            if "/v1/species/match" in url:
                return {"usageKey": 1651891, "canonicalName": "Aedes aegypti"}
            if "offset=0" in url:
                return {"count": 3, "endOfRecords": False, "results": [{"key": 1}, {"key": 2}]}
            if "offset=2" in url:
                return {"count": 3, "endOfRecords": True, "results": [{"key": 3}]}
            raise AssertionError(f"unexpected URL: {url}")

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_gbif_records(
                ["Aedes aegypti"],
                raw_dir=Path(tmpdir),
                occurrence_limit=3,
                occurrence_page_size=2,
                fetch_json=paged_fetcher,
                retrieved_at="2026-05-23T00:00:00Z",
            )

            self.assertEqual([record.record_id for record in result.records if record.lane == "observations"], [
                "gbif:occurrence:1",
                "gbif:occurrence:2",
                "gbif:occurrence:3",
            ])
            self.assertEqual(result.page_count, 2)
            self.assertEqual(result.total_results["Aedes aegypti"], 3)


if __name__ == "__main__":
    unittest.main()
