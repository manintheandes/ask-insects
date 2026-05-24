import tempfile
import unittest
from pathlib import Path

from askinsects.sources.dryad_behavior_videos import (
    DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
    DryadDatasetSpec,
    fetch_dryad_behavior_video_records,
)


def dryad_payloads():
    dataset = {
        "_links": {
            "stash:version": {"href": "/api/v2/versions/123"},
        },
        "identifier": "doi:10.5061/dryad.example",
        "title": "Data for: Aedes aegypti host seeking videos",
        "abstract": "<p>Aedes aegypti females were recorded during host seeking.</p>",
        "authors": [{"firstName": "Ada", "lastName": "Lovelace"}],
        "license": "https://spdx.org/licenses/CC0-1.0.html",
    }
    version = {
        "_links": {
            "stash:files": {"href": "/api/v2/versions/123/files"},
        }
    }
    files = {
        "_embedded": {
            "stash:files": [
                {
                    "_links": {"stash:download": {"href": "/api/v2/files/10/download"}},
                    "path": "host_seeking_videos.zip",
                    "size": 1234,
                    "mimeType": "application/x-zip-compressed",
                    "digest": "abc",
                    "digestType": "sha-256",
                },
                {
                    "_links": {"stash:download": {"href": "/api/v2/files/11/download"}},
                    "path": "README.md",
                    "size": 234,
                    "mimeType": "text/markdown",
                    "digest": "def",
                    "digestType": "sha-256",
                },
            ]
        }
    }
    return dataset, version, files


class DryadFetcher:
    def __init__(self):
        self.urls = []
        self.dataset, self.version, self.files = dryad_payloads()

    def __call__(self, url):
        self.urls.append(url)
        if "/datasets/" in url:
            return self.dataset
        if url.endswith("/versions/123"):
            return self.version
        if url.endswith("/versions/123/files"):
            return self.files
        raise AssertionError(f"unexpected URL: {url}")


class DryadBehaviorVideoSourceTests(unittest.TestCase):
    def test_fetch_dryad_behavior_video_records_normalizes_dataset_and_file_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = DryadFetcher()
            result = fetch_dryad_behavior_video_records(
                [DryadDatasetSpec(doi="10.5061/dryad.example", behavior_labels=("host seeking", "thermal"))],
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fetcher,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertEqual(result.source_id, DRYAD_BEHAVIOR_VIDEO_SOURCE_ID)
            self.assertEqual(result.dataset_count, 1)
            self.assertEqual(result.file_count, 2)
            self.assertEqual(result.media_file_count, 1)
            self.assertEqual(len(result.records), 3)
            self.assertEqual(len(result.raw_artifacts), 3)
            self.assertTrue(any("/versions/123/files" in url for url in fetcher.urls))

            dataset = next(record for record in result.records if record.record_id.startswith("dryad:dataset:"))
            self.assertEqual(dataset.lane, "behavior")
            self.assertEqual(dataset.source, DRYAD_BEHAVIOR_VIDEO_SOURCE_ID)
            self.assertIn("host seeking", dataset.text)
            self.assertEqual(dataset.provenance.license, "https://spdx.org/licenses/CC0-1.0.html")
            self.assertEqual(dataset.payload["doi"], "10.5061/dryad.example")

            media = next(record for record in result.records if record.lane == "media")
            self.assertEqual(media.media_url, "https://datadryad.org/api/v2/files/10/download")
            self.assertIn("video/archive file", media.title)
            self.assertEqual(media.payload["raw_file"]["digest"], "abc")
            self.assertIn("#file/1", media.provenance.locator)

            readme = next(record for record in result.records if record.title.endswith("README.md"))
            self.assertEqual(readme.lane, "behavior")
            self.assertIsNone(readme.media_url)

    def test_fetch_dryad_behavior_video_records_records_gap_on_fetch_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_dryad_behavior_video_records(
                [DryadDatasetSpec(doi="10.5061/dryad.missing", behavior_labels=("behavior",))],
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertFalse(result.records)
            self.assertEqual(result.gaps[0]["source"], DRYAD_BEHAVIOR_VIDEO_SOURCE_ID)
            self.assertEqual(result.gaps[0]["reason"], "dryad_dataset_fetch_failed")


if __name__ == "__main__":
    unittest.main()
