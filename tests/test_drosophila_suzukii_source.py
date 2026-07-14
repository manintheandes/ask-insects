import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from askinsects.sources import drosophila_suzukii as drosophila_suzukii_source
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


def fake_alias_literature_fetch(url: str) -> dict[str, object]:
    if "/topics" in url:
        return {"results": []}
    query = parse_qs(urlparse(url).query)
    filter_value = unquote(query.get("filter", [""])[0])
    if '"Drosophila suzukii"' in filter_value:
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
    if '"spotted wing drosophila"' in filter_value:
        return {
            "meta": {"count": 2, "next_cursor": None},
            "results": [
                {
                    "id": "https://openalex.org/W123",
                    "display_name": "Drosophila suzukii host fruit preference",
                    "doi": "https://doi.org/10.1000/swd",
                    "type": "article",
                    "publication_date": "2024-05-01",
                    "abstract_inverted_index": {"Drosophila": [0], "suzukii": [1]},
                    "primary_location": {"source": {"display_name": "Test Journal"}},
                },
                {
                    "id": "https://openalex.org/W999",
                    "display_name": "Organic management of spotted wing drosophila in blueberries",
                    "doi": "https://doi.org/10.1000/swd-blueberry",
                    "type": "article",
                    "publication_date": "2025-07-01",
                    "abstract_inverted_index": {
                        "spotted": [0],
                        "wing": [1],
                        "drosophila": [2],
                        "management": [3],
                        "blueberries": [4],
                    },
                    "primary_location": {"source": {"display_name": "Fruit IPM"}},
                },
            ],
        }
    return {"meta": {"count": 0, "next_cursor": None}, "results": []}


class DrosophilaSuzukiiSourceTests(unittest.TestCase):
    def test_product_topic_search_terms_have_a_consumer_independent_symbol(self):
        self.assertTrue(
            hasattr(
                drosophila_suzukii_source,
                "DROSOPHILA_SUZUKII_PRODUCT_TOPIC_SEARCH_TERMS",
            )
        )
        self.assertFalse(
            hasattr(
                drosophila_suzukii_source,
                "DROSOPHILA_SUZUKII_MONARCH_TOPIC_SEARCH_TERMS",
            )
        )

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

    def test_literature_fetch_uses_swd_aliases_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_records(
                raw_dir=Path(tmpdir) / "raw" / "drosophila_suzukii",
                retrieved_at="2026-06-06T00:00:00Z",
                gbif_occurrence_limit=0,
                inaturalist_observation_limit=0,
                literature_max_works=10,
                include_bold=False,
                gbif_fetch_json=fake_gbif_fetch,
                inaturalist_fetch_json=fake_inaturalist_fetch,
                literature_fetch_json=fake_alias_literature_fetch,
            )

            literature_records = [record for record in result.records if record.lane == "literature"]
            literature_ids = {record.record_id for record in literature_records}

            self.assertEqual(len(literature_records), 2)
            self.assertEqual(
                literature_ids,
                {
                    "swd:openalex_literature:openalex:W123",
                    "swd:openalex_literature:openalex:W999",
                },
            )
            alias_record = next(record for record in literature_records if record.record_id.endswith("W999"))
            self.assertIn("spotted wing drosophila", alias_record.text.lower())
            self.assertIn("abstract_alias", alias_record.payload["inclusion_paths"])
            self.assertIn("spotted wing drosophila", result.upstream_sources["openalex_literature"]["search_terms"])

    def test_literature_fetch_includes_product_topic_openalex_search_terms(self):
        calls: list[str] = []

        def fake_topic_literature_fetch(url: str) -> dict[str, object]:
            calls.append(url)
            if "/topics" in url:
                return {"results": []}
            query = parse_qs(urlparse(url).query)
            if query.get("search") == ["Drosophila suzukii repellent"]:
                return {
                    "meta": {"count": 1, "next_cursor": None},
                    "results": [
                        {
                            "id": "https://openalex.org/W777",
                            "display_name": "Repellent discovery candidate from OpenAlex search",
                            "doi": "https://doi.org/10.1000/swd-repellent-candidate",
                            "type": "article",
                            "publication_date": "2024-05-01",
                            "abstract_inverted_index": {
                                "repellent": [0],
                                "assay": [1],
                                "candidate": [2],
                            },
                            "primary_location": {"source": {"display_name": "Test Journal"}},
                        }
                    ],
                }
            return {"meta": {"count": 0, "next_cursor": None}, "results": []}

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_records(
                raw_dir=Path(tmpdir) / "raw" / "drosophila_suzukii",
                retrieved_at="2026-06-06T00:00:00Z",
                gbif_occurrence_limit=0,
                inaturalist_observation_limit=0,
                literature_max_works=10,
                include_bold=False,
                gbif_fetch_json=fake_gbif_fetch,
                inaturalist_fetch_json=fake_inaturalist_fetch,
                literature_fetch_json=fake_topic_literature_fetch,
            )

            search_urls = [url for url in calls if "/works?" in url and "search=Drosophila+suzukii+repellent" in url]
            self.assertTrue(search_urls)
            terms = result.upstream_sources["openalex_literature"]["search_terms"]
            self.assertIn("Drosophila suzukii repellent", terms)
            modes = result.upstream_sources["openalex_literature"]["search_modes"]
            self.assertIn("search", modes)
            topic_groups = result.upstream_sources["openalex_literature"]["topic_groups"]
            self.assertIn("repellency", topic_groups)

            candidate = next(record for record in result.records if record.record_id.endswith("W777"))
            self.assertEqual(candidate.payload["openalex_search_mode"], "search")
            self.assertEqual(candidate.payload["openalex_topic_group"], "repellency")
            self.assertIn("openalex_search_candidate", candidate.payload["inclusion_paths"])


if __name__ == "__main__":
    unittest.main()
