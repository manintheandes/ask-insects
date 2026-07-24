import tempfile
import unittest
from pathlib import Path

from askinsects.sources.mosquito_repellent_external_discovery import fetch_mosquito_repellent_external_discovery_records


OPENALEX = {
    "results": [
        {
            "id": "https://openalex.org/W1",
            "title": "OpenAlex mosquito repellent trial against Aedes",
            "doi": "https://doi.org/10.1000/openalex",
            "publication_date": "2026-01-01",
            "publication_year": 2026,
            "cited_by_count": 11,
            "abstract": "Aedes mosquito repellent DEET study.",
            "primary_location": {"source": {"display_name": "Vector Journal"}},
        }
    ]
}
EUROPEPMC = {
    "hitCount": 1,
    "resultList": {
        "result": [
            {
                "id": "P1",
                "source": "MED",
                "title": "Europe PMC mosquito repellency article",
                "abstractText": "Aedes mosquito repellency and picaridin.",
                "doi": "10.1000/europepmc",
                "journalTitle": "Medical Entomology",
                "pubYear": "2025",
                "firstPublicationDate": "2025-05-01",
                "authorString": "Researcher A",
            }
        ]
    },
}
AGRICOLA = {
    "hitCount": 1,
    "resultList": {
        "result": [
            {
                "id": "AGR1",
                "source": "AGR",
                "title": "AGRICOLA mosquito repellent crop-edge study",
                "abstractText": "Mosquito repellent and Aedes field context.",
                "journalTitle": "Agricultural Entomology",
                "pubYear": "2024",
            }
        ]
    },
}
SEMANTIC_SCHOLAR = {
    "data": [
        {
            "paperId": "S1",
            "title": "Semantic Scholar Aedes repellent synthesis",
            "abstract": "Mosquito repellent and spatial repellent evidence.",
            "year": 2023,
            "venue": "Prevention",
            "publicationDate": "2023-04-02",
            "externalIds": {"DOI": "10.1000/s2"},
            "authors": [{"name": "Researcher B"}],
            "url": "https://semanticscholar.org/paper/S1",
            "citationCount": 8,
        }
    ]
}
CROSSREF_PREPRINT = {
    "message": {
        "items": [
            {
                "DOI": "10.1101/preprint",
                "title": ["bioRxiv mosquito repellent preprint"],
                "abstract": "Aedes mosquito repellent preprint.",
                "container-title": ["bioRxiv"],
                "publisher": "Cold Spring Harbor Laboratory",
                "type": "posted-content",
                "issued": {"date-parts": [[2022, 1, 2]]},
                "URL": "https://doi.org/10.1101/preprint",
            }
        ]
    }
}
DATACITE = {
    "data": [
        {
            "id": "10.5061/dryad.repellent",
            "attributes": {
                "doi": "10.5061/dryad.repellent",
                "titles": [{"title": "Dryad mosquito repellent assay dataset"}],
                "descriptions": [{"description": "Aedes mosquito repellent landing assay dataset."}],
                "publisher": "Dryad",
                "published": "2021",
                "clientId": "datacite.dryad",
                "url": "https://doi.org/10.5061/dryad.repellent",
            },
        }
    ]
}
ZENODO = {
    "hits": {
        "hits": [
            {
                "id": 42,
                "doi": "10.5281/zenodo.repellent",
                "links": {"html": "https://zenodo.org/records/42"},
                "metadata": {
                    "title": "Zenodo Aedes mosquito repellent files",
                    "description": "Mosquito repellent field data.",
                    "publication_date": "2020-03-01",
                    "keywords": ["Aedes", "repellent"],
                },
            }
        ]
    }
}
FIGSHARE = [
    {
        "id": 99,
        "title": "Figshare mosquito repellent dataset",
        "description": "Aedes mosquito repellent dose response.",
        "doi": "10.6084/figshare.repellent",
        "published_date": "2026-02-01",
        "url_public_html": "https://figshare.com/articles/dataset/99",
        "tags": ["mosquito", "repellent"],
    }
]


class MosquitoRepellentExternalDiscoverySourceTests(unittest.TestCase):
    def test_fetch_builds_external_records_and_source_gap_records(self):
        calls = []

        def fake_fetch_json(url, body_json=None):
            calls.append((url, body_json))
            if "api.openalex.org" in url:
                return OPENALEX
            if "SRC%3AAGR" in url or "SRC:AGR" in url:
                return AGRICOLA
            if "europepmc" in url:
                return EUROPEPMC
            if "semanticscholar" in url:
                return SEMANTIC_SCHOLAR
            if "api.crossref.org" in url:
                return CROSSREF_PREPRINT
            if "api.datacite.org" in url:
                return DATACITE
            if "zenodo.org" in url:
                return ZENODO
            if "api.figshare.com" in url:
                self.assertIsNotNone(body_json)
                return FIGSHARE
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_mosquito_repellent_external_discovery_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-25T00:00:00Z",
                max_results_per_source=5,
            )

        self.assertEqual(result.source_id, "mosquito_repellent_external_discovery")
        self.assertTrue(result.raw_artifacts)
        self.assertGreaterEqual(result.source_counts["openalex"], 1)
        self.assertGreaterEqual(result.source_counts["europepmc"], 1)
        self.assertGreaterEqual(result.source_counts["semantic_scholar"], 1)
        self.assertGreaterEqual(result.source_counts["crossref_preprint"], 1)
        self.assertGreaterEqual(result.source_counts["datacite"], 1)
        self.assertGreaterEqual(result.source_counts["zenodo"], 1)
        self.assertGreaterEqual(result.source_counts["figshare"], 1)
        self.assertGreaterEqual(result.source_counts["europepmc_agricola"], 1)
        self.assertIn("datasets", result.lane_counts)
        self.assertIn("literature", result.lane_counts)
        self.assertIn("patents", result.lane_counts)
        patent_gap = next(record for record in result.records if record.lane == "patents")
        self.assertEqual(patent_gap.payload["artifact_type"], "source_gap")
        dataset = next(record for record in result.records if record.payload["source_family"] == "datacite")
        self.assertEqual(dataset.lane, "datasets")
        openalex_record = next(record for record in result.records if record.payload["source_family"] == "openalex")
        self.assertEqual(openalex_record.payload["citation_count"], 11)
        semantic_scholar_record = next(record for record in result.records if record.payload["source_family"] == "semantic_scholar")
        self.assertEqual(semantic_scholar_record.payload["citation_count"], 8)
        self.assertIn("datacite_mosquito_repellent.json#data/0", dataset.provenance.locator)
        self.assertTrue(any(body for _, body in calls if body and body.get("search_for") == "mosquito repellent"))


if __name__ == "__main__":
    unittest.main()
