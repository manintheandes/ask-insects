import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.sources.drosophila_suzukii import (
    DROSOPHILA_SUZUKII_SOURCE_ID,
    fetch_drosophila_suzukii_records,
)


FAKE_BOLD_TSV = """processid\tspecies_name\tcountry\tprovince\tcollectiondate\tmarkercode\tgenbank_accession\tnucleotides
SWD1\tDrosophila suzukii\tUnited States\tCalifornia\t2024-01-01\tCOI-5P\tPP000001\tATGCATGC
"""


def fake_gbif_fetch(url: str) -> dict[str, object]:
    if "/species/match" in url:
        return {
            "usageKey": 10568202,
            "canonicalName": "Drosophila suzukii",
            "species": "Drosophila suzukii",
            "family": "Drosophilidae",
            "genus": "Drosophila",
            "rank": "SPECIES",
            "status": "ACCEPTED",
        }
    return {
        "count": 1,
        "endOfRecords": True,
        "results": [
            {
                "key": 12345,
                "species": "Drosophila suzukii",
                "scientificName": "Drosophila suzukii (Matsumura, 1931)",
                "country": "United States",
                "eventDate": "2025-08-01",
                "datasetName": "Test GBIF dataset",
                "license": "CC_BY_4_0",
                "media": [{"identifier": "https://example.org/swd.jpg"}],
            }
        ],
    }


def fake_inaturalist_fetch(url: str) -> dict[str, object]:
    return {
        "total_results": 1,
        "results": [
            {
                "id": 987,
                "taxon": {"name": "Drosophila suzukii"},
                "observed_on": "2025-09-01",
                "place_guess": "Oregon, US",
                "uri": "https://www.inaturalist.org/observations/987",
                "license_code": "cc-by",
                "photos": [
                    {
                        "id": 654,
                        "url": "https://static.inaturalist.org/photos/654/square.jpg",
                        "license_code": "cc-by",
                        "attribution": "(c) Test Observer",
                    }
                ],
            }
        ],
    }


def fake_literature_fetch(url: str) -> dict[str, object]:
    if "/topics" in url:
        return {"results": []}
    return {
        "meta": {"count": 1, "next_cursor": None},
        "results": [
            {
                "id": "https://openalex.org/W123",
                "display_name": "Drosophila suzukii host fruit preference",
                "doi": "https://doi.org/10.1000/swd",
                "type": "article",
                "publication_date": "2024-05-01",
                "abstract_inverted_index": {
                    "Drosophila": [0],
                    "suzukii": [1],
                    "damages": [2],
                    "soft": [3],
                    "fruit": [4],
                },
                "primary_location": {"source": {"display_name": "Test Journal"}},
            }
        ],
    }


class DrosophilaSuzukiiSourceTests(unittest.TestCase):
    def test_fetch_builds_queryable_spotted_wing_drosophila_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_records(
                raw_dir=Path(tmpdir) / "raw" / "drosophila_suzukii",
                retrieved_at="2026-05-28T00:00:00Z",
                gbif_occurrence_limit=1,
                inaturalist_observation_limit=1,
                literature_max_works=1,
                bold_limit=1,
                gbif_fetch_json=fake_gbif_fetch,
                inaturalist_fetch_json=fake_inaturalist_fetch,
                literature_fetch_json=fake_literature_fetch,
                bold_fetch_text=lambda url: FAKE_BOLD_TSV,
            )

            self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_SOURCE_ID)
            self.assertTrue(result.raw_artifacts)
            self.assertIn("gbif", result.upstream_sources)
            self.assertIn("openalex_literature", result.upstream_sources)
            self.assertTrue(any(record.lane == "taxonomy" for record in result.records))
            self.assertTrue(any(record.lane == "observations" for record in result.records))
            self.assertTrue(any(record.lane == "media" for record in result.records))
            self.assertTrue(any(record.lane == "literature" for record in result.records))
            self.assertTrue(any(record.lane == "dna_barcodes" for record in result.records))
            self.assertTrue(any(record.lane == "source_coverage" for record in result.records))
            self.assertTrue(all(record.source == DROSOPHILA_SUZUKII_SOURCE_ID for record in result.records))
            self.assertTrue(any("spotted wing drosophila" in record.text.lower() for record in result.records))

    def test_records_are_searchable_from_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_records(
                raw_dir=Path(tmpdir) / "raw" / "drosophila_suzukii",
                retrieved_at="2026-05-28T00:00:00Z",
                gbif_occurrence_limit=1,
                inaturalist_observation_limit=1,
                include_literature=False,
                include_bold=False,
                gbif_fetch_json=fake_gbif_fetch,
                inaturalist_fetch_json=fake_inaturalist_fetch,
            )
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(result.records)

            rows = index.search("spotted wing drosophila", limit=10)

            self.assertTrue(rows)
            self.assertTrue(all(row.source == DROSOPHILA_SUZUKII_SOURCE_ID for row in rows))


if __name__ == "__main__":
    unittest.main()
