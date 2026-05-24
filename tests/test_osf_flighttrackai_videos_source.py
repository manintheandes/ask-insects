import tempfile
import unittest
from pathlib import Path

from askinsects.sources.osf_flighttrackai_videos import (
    OSF_FLIGHTTRACKAI_SOURCE_ID,
    fetch_osf_flighttrackai_video_records,
)


def osf_payloads():
    project = {
        "data": {
            "id": "cx762",
            "type": "nodes",
            "attributes": {
                "title": "FlightTrackAI: a robust convolutional neural network-based tool for tracking the flight behaviour of Aedes aegypti mosquitoes",
                "description": "FlightTrackAI tracks Aedes aegypti mosquito flight behaviour from videos.",
                "public": True,
            },
        }
    }
    providers = {
        "data": [
            {
                "id": "cx762:osfstorage",
                "type": "files",
                "attributes": {"kind": "folder", "name": "osfstorage", "provider": "osfstorage"},
            }
        ],
        "links": {"next": None},
    }
    root = {
        "data": [
            {
                "id": "folder-processed",
                "type": "files",
                "attributes": {
                    "kind": "folder",
                    "name": "PROCESSED VIDEOS",
                    "materialized_path": "/PROCESSED VIDEOS/",
                },
                "relationships": {
                    "files": {
                        "links": {
                            "related": {"href": "https://api.osf.io/v2/nodes/cx762/files/osfstorage/folder-processed/"}
                        }
                    }
                },
                "links": {"self": "https://api.osf.io/v2/files/folder-processed/"},
            },
            {
                "id": "instructions",
                "type": "files",
                "attributes": {
                    "kind": "file",
                    "name": "FlightTrackAI Installation Instructions.pdf",
                    "materialized_path": "/FlightTrackAI Installation Instructions.pdf",
                    "size": 100538,
                },
                "links": {
                    "download": "https://osf.io/download/yd5pt/",
                    "info": "https://api.osf.io/v2/files/instructions/",
                },
            },
        ],
        "links": {"next": None},
    }
    processed = {
        "data": [
            {
                "id": "video-a",
                "type": "files",
                "attributes": {
                    "kind": "file",
                    "name": "Video A.mp4",
                    "materialized_path": "/PROCESSED VIDEOS/Video A.mp4",
                    "size": 74364708,
                },
                "links": {
                    "download": "https://osf.io/download/pu8zf/",
                    "info": "https://api.osf.io/v2/files/video-a/",
                },
            }
        ],
        "links": {"next": None},
    }
    return project, providers, root, processed


class OSFFetcher:
    def __init__(self):
        self.project, self.providers, self.root, self.processed = osf_payloads()

    def __call__(self, url):
        if url.endswith("/nodes/cx762/"):
            return self.project
        if url.endswith("/nodes/cx762/files/"):
            return self.providers
        if url.endswith("/nodes/cx762/files/osfstorage/"):
            return self.root
        if url.endswith("/nodes/cx762/files/osfstorage/folder-processed/"):
            return self.processed
        raise AssertionError(f"unexpected OSF URL: {url}")


class OSFFlightTrackAIVideoSourceTests(unittest.TestCase):
    def test_fetch_osf_flighttrackai_video_records_normalizes_project_folders_and_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_osf_flighttrackai_video_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=OSFFetcher(),
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertEqual(result.source_id, OSF_FLIGHTTRACKAI_SOURCE_ID)
            self.assertEqual(result.project_id, "cx762")
            self.assertEqual(result.folder_count, 1)
            self.assertEqual(result.file_count, 2)
            self.assertEqual(result.media_file_count, 1)
            self.assertEqual(result.software_file_count, 1)
            self.assertEqual(len(result.records), 4)
            self.assertEqual(len(result.gaps), 0)
            self.assertTrue(any(path.endswith("cx762_osfstorage_root.json") for path in result.raw_artifacts))

            project = next(record for record in result.records if record.record_id == "osf:flighttrackai:project:cx762")
            self.assertEqual(project.lane, "behavior")
            self.assertIn("Aedes aegypti", project.text)
            self.assertEqual(project.payload["project_api_url"], "https://api.osf.io/v2/nodes/cx762/")

            folder = next(record for record in result.records if record.record_id.startswith("osf:flighttrackai:folder:"))
            self.assertEqual(folder.payload["materialized_path"], "/PROCESSED VIDEOS/")

            media = next(record for record in result.records if record.lane == "media")
            self.assertEqual(media.media_url, "https://osf.io/download/pu8zf/")
            self.assertEqual(media.payload["size"], 74364708)
            self.assertIn("#files/2", media.provenance.locator)

            instructions = next(record for record in result.records if record.title.endswith("Instructions.pdf"))
            self.assertEqual(instructions.lane, "behavior")
            self.assertIsNone(instructions.media_url)
            self.assertTrue(instructions.payload["is_software"])

    def test_fetch_osf_flighttrackai_video_records_records_gap_on_fetch_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_osf_flighttrackai_video_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertFalse(result.records)
            self.assertEqual(result.gaps[0]["source"], OSF_FLIGHTTRACKAI_SOURCE_ID)
            self.assertEqual(result.gaps[0]["reason"], "osf_project_fetch_failed")


if __name__ == "__main__":
    unittest.main()
