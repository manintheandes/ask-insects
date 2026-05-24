import tempfile
import unittest
from pathlib import Path

from askinsects.sources.mendeley_behavior_media import (
    MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
    MendeleyDatasetSpec,
    fetch_mendeley_behavior_media_records,
)


def mendeley_payloads():
    snapshot = {
        "id": "6gvs94p6r2",
        "version": 1,
        "name": "R modeling code, high-speed video, sound files and other data from yellow fever mosquitoes",
        "description": "Aedes aegypti high-speed video demonstrates wing flash mate-recognition behavior.",
        "doi": "10.17632/6gvs94p6r2.1",
        "licence": {"short_name": "CC BY 4.0", "url": "http://creativecommons.org/licenses/by/4.0"},
        "contributors": [{"first_name": "Ada", "last_name": "Lovelace"}],
        "categories": [{"label": "Mosquito"}, {"label": "Behavioral Ecology"}],
        "related_links": [{"relation_type": "is_supplement_to", "href": "https://doi.org/10.1098/example"}],
    }
    folders = [
        {"id": "folder-1", "name": "High-speed video", "parent_id": None, "created_date": "2021-01-01T00:00:00Z"},
        {"id": "folder-2", "name": "Analysis", "parent_id": "folder-1", "created_date": "2021-01-01T00:00:00Z"},
    ]
    files_by_folder = {
        "root": [
            {
                "filename": "read me.txt",
                "id": "file-readme",
                "folder_id": None,
                "status": "COMPLETED",
                "content_details": {
                    "content_type": "text/plain",
                    "size": 512,
                    "sha256_hash": "readme-hash",
                    "download_url": "https://data.mendeley.com/public-files/readme/file_downloaded",
                    "view_url": "https://data.mendeley.com/public-files/readme/file_viewed",
                },
            }
        ],
        "folder-1": [
            {
                "filename": "wing-flash-video.mp4",
                "id": "file-video",
                "folder_id": "folder-1",
                "status": "COMPLETED",
                "content_details": {
                    "content_type": "video/mp4",
                    "size": 4096,
                    "sha256_hash": "video-hash",
                    "download_url": "https://data.mendeley.com/public-files/video/file_downloaded",
                    "view_url": "https://data.mendeley.com/public-files/video/file_viewed",
                },
            }
        ],
        "folder-2": [],
    }
    return snapshot, folders, files_by_folder


class MendeleyFetcher:
    def __init__(self):
        self.urls = []
        self.snapshot, self.folders, self.files_by_folder = mendeley_payloads()

    def __call__(self, url):
        self.urls.append(url)
        if "/snapshot/" in url:
            return self.snapshot
        if "/folders/" in url:
            return self.folders
        if "folder_id=root" in url:
            return self.files_by_folder["root"]
        if "folder_id=folder-1" in url:
            return self.files_by_folder["folder-1"]
        if "folder_id=folder-2" in url:
            return self.files_by_folder["folder-2"]
        raise AssertionError(f"unexpected URL: {url}")


class MendeleyBehaviorMediaSourceTests(unittest.TestCase):
    def test_fetch_mendeley_behavior_media_records_normalizes_dataset_folders_and_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = MendeleyFetcher()
            result = fetch_mendeley_behavior_media_records(
                [MendeleyDatasetSpec(dataset_id="6gvs94p6r2", version=1, behavior_labels=("mating", "wing flash"))],
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fetcher,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertEqual(result.source_id, MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID)
            self.assertEqual(result.dataset_count, 1)
            self.assertEqual(result.folder_count, 2)
            self.assertEqual(result.file_count, 2)
            self.assertEqual(result.media_file_count, 1)
            self.assertEqual(len(result.records), 5)
            self.assertEqual(len(result.raw_artifacts), 3)
            self.assertTrue(any("/files?folder_id=folder-1&version=1" in url for url in fetcher.urls))

            dataset = next(record for record in result.records if record.record_id.startswith("mendeley:dataset:"))
            self.assertEqual(dataset.lane, "behavior")
            self.assertEqual(dataset.source, MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID)
            self.assertIn("Aedes aegypti", dataset.text)
            self.assertIn("wing flash", dataset.text)
            self.assertEqual(dataset.provenance.license, "CC BY 4.0 http://creativecommons.org/licenses/by/4.0")
            self.assertEqual(dataset.payload["doi"], "10.17632/6gvs94p6r2.1")

            folder = next(record for record in result.records if record.record_id.startswith("mendeley:folder:") and "Analysis" in record.title)
            self.assertEqual(folder.lane, "behavior")
            self.assertEqual(folder.payload["folder_path"], "High-speed video/Analysis")

            media = next(record for record in result.records if record.lane == "media")
            self.assertEqual(media.media_url, "https://data.mendeley.com/public-files/video/file_downloaded")
            self.assertIn("video/audio/archive file", media.title)
            self.assertEqual(media.payload["sha256_hash"], "video-hash")
            self.assertIn("#files/folder-1/1", media.provenance.locator)

            readme = next(record for record in result.records if record.title.endswith("read me.txt"))
            self.assertEqual(readme.lane, "behavior")
            self.assertIsNone(readme.media_url)

    def test_fetch_mendeley_behavior_media_records_records_gap_on_fetch_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_mendeley_behavior_media_records(
                [MendeleyDatasetSpec(dataset_id="missing", version=1, behavior_labels=("behavior",))],
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertFalse(result.records)
            self.assertEqual(result.gaps[0]["source"], MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID)
            self.assertEqual(result.gaps[0]["reason"], "mendeley_dataset_fetch_failed")


if __name__ == "__main__":
    unittest.main()
