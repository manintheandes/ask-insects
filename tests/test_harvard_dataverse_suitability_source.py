from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from askinsects.sources.harvard_dataverse_suitability import (
    HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID,
    HarvardDataverseSuitabilityResult,
    fetch_harvard_dataverse_suitability_records,
)


def search_payload() -> dict[str, object]:
    return {
        "data": {
            "items": [
                {
                    "name": "TCurMean30Sum_97ae.tif",
                    "url": "https://dataverse.harvard.edu/api/access/datafile/3623893",
                    "file_id": "3623893",
                    "description": "Updated baseline current data for Aedes aegypti.",
                    "file_type": "TIFF Image",
                    "file_content_type": "image/tiff",
                    "size_in_bytes": 1646929,
                    "md5": "23924b189272364f95d6cd64c39dd38c",
                    "checksum": {"type": "MD5", "value": "23924b189272364f95d6cd64c39dd38c"},
                    "file_persistent_id": "doi:10.7910/DVN/NSG5UH/RVCMZT",
                    "dataset_name": "Global current Aedes aegypti suitability for dengue transmission at 97.5% CI (5 arc minutes)",
                    "dataset_id": "3392254",
                    "dataset_persistent_id": "doi:10.7910/DVN/NSG5UH",
                    "dataset_citation": 'Ryan, Sadie, 2019, "Global current Aedes aegypti suitability for dengue transmission"',
                    "restricted": False,
                    "canDownloadFile": False,
                    "publicationStatuses": ["Published"],
                    "releaseOrCreateDate": "2019-11-11T20:09:30Z",
                },
                {
                    "name": "unrelated_movie.mp4",
                    "url": "https://dataverse.harvard.edu/api/access/datafile/9",
                    "file_id": "9",
                    "file_content_type": "video/mp4",
                    "dataset_name": "Synthetic media narratives",
                    "description": "A video result polluted by search terms.",
                    "restricted": False,
                    "canDownloadFile": True,
                },
            ]
        }
    }


def dataset_detail() -> dict[str, object]:
    return {
        "data": {
            "persistentUrl": "https://doi.org/10.7910/DVN/NSG5UH",
            "latestVersion": {
                "license": {
                    "name": "CC0 1.0",
                    "uri": "http://creativecommons.org/publicdomain/zero/1.0",
                    "rightsIdentifier": "CC0-1.0",
                },
                "metadataBlocks": {
                    "citation": {
                        "fields": [
                            {
                                "typeName": "dsDescription",
                                "value": [
                                    {
                                        "dsDescriptionValue": {
                                            "value": "Current global predicted months suitable for dengue transmission by Aedes aegypti."
                                        }
                                    }
                                ],
                            },
                            {
                                "typeName": "publication",
                                "value": [
                                    {
                                        "publicationCitation": {
                                            "value": "Ryan SJ et al. Global expansion and redistribution of Aedes-borne virus transmission risk with climate change."
                                        }
                                    }
                                ],
                            },
                        ]
                    }
                },
            }
        }
    }


class HarvardDataverseSuitabilitySourceTests(unittest.TestCase):
    def test_fetch_records_normalizes_suitability_raster_manifest_and_download_gap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_dir = Path(tmpdir)
            requested_urls: list[str] = []

            def fake_json(url: str) -> dict[str, object]:
                requested_urls.append(url)
                if "/api/search?" in url:
                    return search_payload()
                if "/api/datasets/:persistentId/" in url:
                    self.assertEqual(parse_qs(urlparse(url).query)["persistentId"], ["doi:10.7910/DVN/NSG5UH"])
                    return dataset_detail()
                raise AssertionError(url)

            result = fetch_harvard_dataverse_suitability_records(
                raw_dir=raw_dir,
                queries=('"Aedes aegypti" suitability',),
                per_page=10,
                dataset_limit=3,
                fetch_json=fake_json,
                retrieved_at="2026-05-25T00:00:00Z",
            )

        self.assertIsInstance(result, HarvardDataverseSuitabilityResult)
        self.assertEqual(result.source_id, HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID)
        self.assertEqual(result.query_count, 1)
        self.assertEqual(result.search_item_count, 2)
        self.assertEqual(result.dataset_count, 1)
        self.assertEqual(result.file_record_count, 1)
        self.assertGreaterEqual(len(result.raw_artifacts), 2)
        manifest = next(record for record in result.records if record.payload.get("filename") == "TCurMean30Sum_97ae.tif")
        self.assertEqual(manifest.lane, "ecology")
        self.assertEqual(manifest.source, HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID)
        self.assertEqual(manifest.payload["checksum"]["md5"], "23924b189272364f95d6cd64c39dd38c")
        self.assertEqual(manifest.payload["byte_size"], 1646929)
        self.assertEqual(manifest.payload["license"], "CC0 1.0 CC0-1.0 http://creativecommons.org/publicdomain/zero/1.0")
        self.assertIn("current", manifest.payload["scenario_terms"])
        self.assertTrue(any(gap["reason"] == "dataverse_file_download_not_public" for gap in result.gaps))
        gap_record = next(record for record in result.records if record.payload.get("gap", {}).get("reason") == "dataverse_file_download_not_public")
        self.assertIn("Download URL: https://dataverse.harvard.edu/api/access/datafile/3623893", gap_record.text)


if __name__ == "__main__":
    unittest.main()
