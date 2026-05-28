import io
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

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


def tiny_xlsx(rows):
    out = io.BytesIO()
    with ZipFile(out, "w") as zf:
        zf.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""",
        )
        zf.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        zf.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Assay" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        row_xml = []
        for row_index, row in enumerate(rows, start=1):
            cells = []
            for col_index, value in enumerate(row):
                col = chr(ord("A") + col_index)
                cells.append(f'<c r="{col}{row_index}" t="inlineStr"><is><t>{value}</t></is></c>')
            row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>{"".join(row_xml)}</sheetData>
</worksheet>""",
        )
    return out.getvalue()


class DryadTableFetcher(DryadFetcher):
    def __init__(self):
        super().__init__()
        self.files["_embedded"]["stash:files"].extend(
            [
                {
                    "_links": {"stash:download": {"href": "/api/v2/files/12/download"}},
                    "path": "Male_preferences_Ae._aegypti.csv",
                    "size": 34,
                    "mimeType": "text/csv",
                    "digest": "csv-aegypti",
                    "digestType": "sha-256",
                },
                {
                    "_links": {"stash:download": {"href": "/api/v2/files/13/download"}},
                    "path": "SourceData_Figure3.xlsx",
                    "size": 4096,
                    "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "digest": "xlsx-aegypti",
                    "digestType": "sha-256",
                },
                {
                    "_links": {"stash:download": {"href": "/api/v2/files/14/download"}},
                    "path": "Female_preferences_Ae._notoscriptus.csv",
                    "size": 28,
                    "mimeType": "text/csv",
                    "digest": "csv-other-species",
                    "digestType": "sha-256",
                },
            ]
        )

    def bytes_for(self, url):
        if url.endswith("/files/12/download"):
            return b"sex,response\nmale,landing\nfemale,landing\n"
        if url.endswith("/files/13/download"):
            return tiny_xlsx([["stimulus", "response"], ["shadow", "escape"]])
        raise AssertionError(f"unexpected download URL: {url}")


class DryadPreviewFetcher(DryadTableFetcher):
    def bytes_for(self, url):
        raise RuntimeError("download blocked")

    def text_for(self, url):
        if url.endswith("/data_file/preview/12.js"):
            return """
            document.getElementById('file_preview_box').innerHTML = `
            <table>
              <thead><tr><th>Species</th><th>Person</th><th>Number</th></tr></thead>
              <tbody>
                <tr><td>Ae. aegypti</td><td>Subject A</td><td>7</td></tr>
                <tr><td>Ae. aegypti</td><td>Subject B</td><td>11</td></tr>
              </tbody>
            </table>`;
            """
        if url.endswith("/data_file/preview/13.js"):
            return """
            document.getElementById('file_preview_box').innerHTML = `
            <table>
              <thead><tr><th>stimulus</th><th>response</th></tr></thead>
              <tbody><tr><td>shadow</td><td>escape</td></tr></tbody>
            </table>`;
            """
        return "<html></html>"


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
            self.assertEqual(len(result.records), 4)
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

            gap = next(record for record in result.records if record.record_id.startswith("dryad:gap:"))
            self.assertEqual(gap.lane, "media")
            self.assertIsNone(gap.media_url)
            self.assertIn("dryad_archive_contents_not_decoded", gap.text)
            self.assertEqual(gap.payload["atom_type"], "video_gap")
            self.assertEqual(gap.payload["source_video_record_id"], media.record_id)
            self.assertEqual(gap.payload["download_url"], "https://datadryad.org/api/v2/files/10/download")
            self.assertEqual(gap.payload["byte_size"], 1234)

            readme = next(record for record in result.records if record.title.endswith("README.md"))
            self.assertEqual(readme.lane, "behavior")
            self.assertIsNone(readme.media_url)

    def test_fetch_dryad_behavior_video_records_indexes_landing_page_assay_methods(self):
        landing_html = """
        <html><body>
          <a class="js-individual-dl" href="/downloads/file_stream/10">host_seeking_videos.zip</a>
          <h3>Dataset corresponding to host-seeking assays</h3>
          <p>Aedes aegypti mosquitoes were filmed in a tent experiment with human host cues.</p>
          <h5>Repellent response</h5>
          <p>Mosquito landing observations were scored after repellent was applied to human skin.</p>
        </body></html>
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = DryadFetcher()
            result = fetch_dryad_behavior_video_records(
                [DryadDatasetSpec(doi="10.5061/dryad.example", behavior_labels=("host seeking", "repellent response"))],
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fetcher,
                fetch_text=lambda url: landing_html,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertEqual(result.landing_page_count, 1)
            self.assertEqual(result.assay_method_count, 2)
            method_records = [
                record
                for record in result.records
                if record.payload and record.payload.get("record_type") == "dryad_landing_assay_method"
            ]
            self.assertEqual(len(method_records), 2)
            self.assertTrue(any("repellent" in record.text.lower() for record in method_records))
            self.assertTrue(all(record.payload["file_stream_links"] == ["https://datadryad.org/downloads/file_stream/10"] for record in method_records))
            media = next(record for record in result.records if record.lane == "media")
            self.assertEqual(media.payload["file_stream_url"], "https://datadryad.org/downloads/file_stream/10")
            self.assertTrue(any(path.endswith("_landing.html") for path in result.raw_artifacts))

    def test_fetch_dryad_behavior_video_records_parses_downloaded_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = DryadTableFetcher()
            result = fetch_dryad_behavior_video_records(
                [DryadDatasetSpec(doi="10.5061/dryad.example", behavior_labels=("host seeking", "escape"))],
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fetcher,
                fetch_bytes=fetcher.bytes_for,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertEqual(result.table_file_count, 3)
            self.assertEqual(result.parsed_table_file_count, 2)
            self.assertEqual(result.skipped_table_file_count, 1)
            self.assertEqual(result.table_sheet_count, 2)
            self.assertEqual(result.table_row_count, 3)

            sheet = next(record for record in result.records if record.record_id.startswith("dryad:table:"))
            self.assertEqual(sheet.lane, "behavior")
            self.assertEqual(sheet.payload["headers"], ["sex", "response"])
            self.assertEqual(sheet.payload["row_count"], 2)

            rows = [record for record in result.records if record.record_id.startswith("dryad:table-row:")]
            self.assertEqual(len(rows), 3)
            self.assertTrue(any(record.payload["values"].get("response") == "landing" for record in rows))
            self.assertTrue(any("shadow" in record.text and "escape" in record.text for record in rows))
            self.assertFalse(any("notoscriptus" in record.record_id for record in rows))
            self.assertTrue(any(Path(path).name.endswith((".json", ".csv", ".xlsx")) for path in result.raw_artifacts))

    def test_fetch_dryad_behavior_video_records_promotes_table_download_failures_to_gap_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = DryadTableFetcher()
            result = fetch_dryad_behavior_video_records(
                [DryadDatasetSpec(doi="10.5061/dryad.example", behavior_labels=("host seeking", "escape"))],
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fetcher,
                fetch_bytes=lambda url: (_ for _ in ()).throw(RuntimeError("download blocked")),
                retrieved_at="2026-05-24T00:00:00Z",
            )

            gaps = [record for record in result.records if record.record_id.startswith("dryad:table-gap:")]
            self.assertEqual(len(gaps), 2)
            self.assertEqual(result.parsed_table_file_count, 0)
            self.assertEqual(result.skipped_table_file_count, 3)
            self.assertTrue(all(record.payload["reason"] == "dryad_table_file_download_or_parse_failed" for record in gaps))
            self.assertTrue(all("download blocked" in record.text for record in gaps))
            self.assertFalse(any("notoscriptus" in record.record_id for record in gaps))

    def test_fetch_dryad_behavior_video_records_uses_public_preview_when_download_blocked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = DryadPreviewFetcher()
            result = fetch_dryad_behavior_video_records(
                [DryadDatasetSpec(doi="10.5061/dryad.example", behavior_labels=("host seeking", "escape"))],
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fetcher,
                fetch_bytes=fetcher.bytes_for,
                fetch_text=fetcher.text_for,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertEqual(result.table_file_count, 3)
            self.assertEqual(result.parsed_table_file_count, 2)
            self.assertEqual(result.skipped_table_file_count, 1)
            self.assertEqual(result.table_sheet_count, 2)
            self.assertEqual(result.table_row_count, 3)

            rows = [record for record in result.records if record.record_id.startswith("dryad:table-row:")]
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(record.payload["table_source"] == "dryad_preview" for record in rows))
            self.assertTrue(any(record.payload["values"].get("Person") == "Subject A" for record in rows))
            self.assertTrue(any(record.payload["values"].get("response") == "escape" for record in rows))
            self.assertTrue(any("table_previews" in path and path.endswith(".js") for path in result.raw_artifacts))
            self.assertTrue(
                any(gap["reason"] == "dryad_table_file_download_blocked_preview_used" for gap in result.gaps)
            )
            preview_gaps = [
                record
                for record in result.records
                if record.payload.get("reason") == "dryad_table_file_download_blocked_preview_used"
            ]
            self.assertEqual(len(preview_gaps), 2)
            self.assertTrue(all(record.payload.get("preview_url") for record in preview_gaps))
            self.assertTrue(all(gap.get("record_id") and gap.get("locator") for gap in result.gaps))
            self.assertFalse(
                any(record.payload.get("reason") == "dryad_table_file_download_or_parse_failed" for record in result.records)
            )

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
