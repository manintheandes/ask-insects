import tempfile
import unittest
from pathlib import Path

from askinsects.sources.figshare_aedes_videos import (
    FIGSHARE_AEDES_VIDEO_SOURCE_ID,
    fetch_figshare_aedes_video_records,
)


def figshare_payloads():
    search = [
        {"id": 201, "title": "Aedes aegypti oviposition video dataset"},
        {"id": 202, "title": "Unrelated Culex movie dataset"},
    ]
    details = {
        201: {
            "id": 201,
            "title": "Aedes aegypti oviposition video dataset",
            "description": "Aedes aegypti females were recorded during oviposition assays.",
            "url_public_html": "https://figshare.com/articles/dataset/aedes_video/201",
            "doi": "10.6084/m9.figshare.201",
            "license": {"name": "CC BY 4.0", "url": "https://creativecommons.org/licenses/by/4.0/"},
            "tags": ["Aedes aegypti", "oviposition", "video"],
            "files": [
                {
                    "id": 501,
                    "name": "oviposition.mp4",
                    "download_url": "https://figshare.com/ndownloader/files/501",
                    "size": 123456,
                    "computed_md5": "0123456789abcdef0123456789abcdef",
                    "mimetype": "video/mp4",
                }
            ],
        },
        202: {
            "id": 202,
            "title": "Culex larval movie dataset",
            "description": "Culex larvae were recorded.",
            "url_public_html": "https://figshare.com/articles/dataset/culex_video/202",
            "license": {"name": "CC BY 4.0"},
            "files": [
                {
                    "id": 502,
                    "name": "larvae.mp4",
                    "download_url": "https://figshare.com/ndownloader/files/502",
                    "size": 12,
                    "computed_md5": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "mimetype": "video/mp4",
                }
            ],
        },
    }
    return search, details


class FigshareFetcher:
    def __init__(self):
        self.urls = []
        self.search, self.details = figshare_payloads()

    def __call__(self, url):
        self.urls.append(url)
        if "/articles?" in url:
            return self.search
        article_id = int(url.rstrip("/").rsplit("/", 1)[-1])
        return self.details[article_id]


class FigshareAedesVideosSourceTests(unittest.TestCase):
    def test_fetch_figshare_aedes_video_records_maps_material_video_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = FigshareFetcher()
            result = fetch_figshare_aedes_video_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fetcher,
                retrieved_at="2026-05-25T00:00:00Z",
                query="Aedes aegypti video",
                page_size=10,
            )

        self.assertEqual(result.source_id, FIGSHARE_AEDES_VIDEO_SOURCE_ID)
        self.assertEqual(result.query, "Aedes aegypti video")
        self.assertEqual(result.search_result_count, 2)
        self.assertEqual(result.material_record_count, 1)
        self.assertEqual(result.media_file_count, 1)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(len(result.raw_artifacts), 3)
        self.assertTrue(any("page_size=10" in url for url in fetcher.urls))

        record = result.records[0]
        self.assertEqual(record.source, FIGSHARE_AEDES_VIDEO_SOURCE_ID)
        self.assertEqual(record.lane, "media")
        self.assertEqual(record.species, "Aedes aegypti")
        self.assertEqual(record.media_url, "https://figshare.com/ndownloader/files/501")
        self.assertEqual(record.provenance.license, "CC BY 4.0")
        self.assertEqual(record.payload["source_byte_size"], 123456)
        self.assertEqual(record.payload["source_hashes"]["md5"], "0123456789abcdef0123456789abcdef")
        self.assertEqual(record.payload["doi"], "10.6084/m9.figshare.201")
        self.assertIn("#files/1", record.provenance.locator)

        reasons = {gap["reason"] for gap in result.gaps}
        self.assertIn("figshare_article_not_aedes_scope", reasons)

    def test_fetch_figshare_aedes_video_records_records_search_gap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_figshare_aedes_video_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=lambda url: [],
                retrieved_at="2026-05-25T00:00:00Z",
                query="Aedes aegypti video",
                page_size=10,
            )

        self.assertFalse(result.records)
        self.assertEqual(result.gaps[0]["source"], FIGSHARE_AEDES_VIDEO_SOURCE_ID)
        self.assertEqual(result.gaps[0]["reason"], "figshare_video_search_no_candidates")
        self.assertEqual(result.gaps[0]["query"], "Aedes aegypti video")


if __name__ == "__main__":
    unittest.main()
