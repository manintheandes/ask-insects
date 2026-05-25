import tempfile
import unittest
from pathlib import Path

from askinsects.sources.zenodo_aedes_videos import (
    ZENODO_AEDES_VIDEO_SOURCE_ID,
    fetch_zenodo_aedes_video_records,
)


def zenodo_search_payload():
    return {
        "hits": {
            "hits": [
                {
                    "id": 101,
                    "links": {"html": "https://zenodo.org/records/101"},
                    "metadata": {
                        "title": "Aedes aegypti oviposition assay videos",
                        "description": "Aedes aegypti females were recorded during oviposition.",
                        "license": {"id": "cc-by-4.0", "title": "Creative Commons Attribution 4.0"},
                        "keywords": ["Aedes aegypti", "oviposition", "video"],
                    },
                    "files": [
                        {
                            "key": "oviposition.mp4",
                            "size": 123456,
                            "checksum": "md5:0123456789abcdef0123456789abcdef",
                            "links": {"self": "https://zenodo.org/api/records/101/files/oviposition.mp4/content"},
                        }
                    ],
                },
                {
                    "id": 102,
                    "links": {"html": "https://zenodo.org/records/102"},
                    "metadata": {
                        "title": "Culex larval movie",
                        "description": "Culex larvae were recorded.",
                        "license": {"id": "cc-by-4.0"},
                    },
                    "files": [
                        {
                            "key": "larvae.mp4",
                            "size": 12,
                            "checksum": "md5:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                            "links": {"self": "https://zenodo.org/api/records/102/files/larvae.mp4/content"},
                        }
                    ],
                },
            ]
        }
    }


class ZenodoFetcher:
    def __init__(self):
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        return zenodo_search_payload()


class ZenodoAedesVideosSourceTests(unittest.TestCase):
    def test_fetch_zenodo_aedes_video_records_maps_material_video_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = ZenodoFetcher()
            result = fetch_zenodo_aedes_video_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fetcher,
                retrieved_at="2026-05-25T00:00:00Z",
                query='"Aedes aegypti" video',
                size=10,
            )

        self.assertEqual(result.source_id, ZENODO_AEDES_VIDEO_SOURCE_ID)
        self.assertEqual(result.query, '"Aedes aegypti" video')
        self.assertEqual(result.search_result_count, 2)
        self.assertEqual(result.material_record_count, 1)
        self.assertEqual(result.media_file_count, 1)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(len(result.raw_artifacts), 1)
        self.assertTrue(any("size=10" in url for url in fetcher.urls))

        record = next(record for record in result.records if record.payload.get("atom_type") != "video_gap")
        self.assertEqual(record.source, ZENODO_AEDES_VIDEO_SOURCE_ID)
        self.assertEqual(record.lane, "media")
        self.assertEqual(record.species, "Aedes aegypti")
        self.assertEqual(record.media_url, "https://zenodo.org/api/records/101/files/oviposition.mp4/content")
        self.assertEqual(record.provenance.license, "cc-by-4.0")
        self.assertEqual(record.payload["source_byte_size"], 123456)
        self.assertEqual(record.payload["source_hashes"]["md5"], "0123456789abcdef0123456789abcdef")
        self.assertIn("#hits/1/files/1", record.provenance.locator)

        reasons = {gap["reason"] for gap in result.gaps}
        self.assertIn("zenodo_record_not_aedes_scope", reasons)
        gap_record = next(record for record in result.records if record.payload.get("atom_type") == "video_gap")
        self.assertEqual(gap_record.source, ZENODO_AEDES_VIDEO_SOURCE_ID)
        self.assertEqual(gap_record.payload["reason"], "zenodo_record_not_aedes_scope")
        self.assertEqual(gap_record.payload["gap_type"], "zenodo_manifest_gap")

    def test_fetch_zenodo_aedes_video_records_records_search_gap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_zenodo_aedes_video_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=lambda url: {"hits": {"hits": []}},
                retrieved_at="2026-05-25T00:00:00Z",
                query='"Aedes aegypti" video',
                size=10,
            )

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.gaps[0]["source"], ZENODO_AEDES_VIDEO_SOURCE_ID)
        self.assertEqual(result.gaps[0]["reason"], "zenodo_video_search_no_candidates")
        self.assertEqual(result.gaps[0]["query"], '"Aedes aegypti" video')
        self.assertEqual(result.records[0].payload["atom_type"], "video_gap")
        self.assertEqual(result.records[0].payload["reason"], "zenodo_video_search_no_candidates")

    def test_fetch_zenodo_aedes_video_records_records_fetch_failure_gap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            def fail_fetch(url):
                raise RuntimeError("temporary Zenodo failure")

            result = fetch_zenodo_aedes_video_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fail_fetch,
                retrieved_at="2026-05-25T00:00:00Z",
                query='"Aedes aegypti" video',
                size=10,
            )

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.gaps[0]["reason"], "zenodo_search_fetch_failed")
        self.assertEqual(result.records[0].payload["atom_type"], "video_gap")
        self.assertEqual(result.records[0].payload["reason"], "zenodo_search_fetch_failed")
        self.assertIn("temporary Zenodo failure", result.records[0].text)


if __name__ == "__main__":
    unittest.main()
