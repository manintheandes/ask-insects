import tempfile
import unittest
from pathlib import Path

from askinsects.sources.drosophila_suzukii_dryad_landscape_monitoring import (
    DATASET_API_URL,
    VERSION_API_URL,
    fetch_drosophila_suzukii_dryad_landscape_monitoring_records,
)


RETRIEVED_AT = "2026-05-30T00:00:00Z"


DATASET_FIXTURE = {
    "title": "Data from: Local and landscape-scale heterogeneity shape spotted wing drosophila activity",
    "license": "CC0-1.0",
    "publicationDate": "2019-02-01",
    "storageSize": 51470,
    "usageNotes": "SWD=trap counts for Drosophila suzukii.",
}


FILES_FIXTURE = {
    "_embedded": {
        "stash:files": [
            {
                "path": "schmidtetalAEE_dyrad.csv",
                "mimeType": "text/csv",
                "size": 51470,
                "digest": "2583ef17da0b77c1b4e8139a190d34da",
                "digestType": "md5",
                "description": "SWD=trap counts for Drosophila suzukii; other columns are counts for predator taxa.",
                "_links": {
                    "self": {"href": "https://datadryad.org/api/v2/files/52071"},
                    "stash:download": {"href": "https://datadryad.org/api/v2/files/52071/download"},
                },
            }
        ]
    }
}


PREVIEW_JS = """
$("#preview").html("<table><tr><th>Week</th><th>Gdate</th><th>fieldcd</th><th>Field ID</th><th>Treatment</th><th>Transect</th><th>veg</th><th>PropNoncrop</th><th>PropBBtot</th><th>FRAGEdge</th><th>FRAGSHDI</th><th>chgNP</th><th>chgF</th><th>SWD</th><th>Araneae</th><th>Coccinellidae</th></tr><tr><td>1</td><td>2016-05-19</td><td>AL-01</td><td>Field A</td><td>wooded</td><td>edge</td><td>grass</td><td>0.42</td><td>0.15</td><td>12.3</td><td>1.9</td><td>0.02</td><td>-0.01</td><td>7</td><td>3</td><td>1</td></tr><tr><td>2</td><td>2016-05-26</td><td>AL-01</td><td>Field A</td><td>wooded</td><td>interior</td><td>grass</td><td>0.42</td><td>0.15</td><td>12.3</td><td>1.9</td><td>0.02</td><td>-0.01</td><td>11</td><td>5</td><td>0</td></tr></table>");
"""


def landscape_fetch_json(url: str):
    if url == DATASET_API_URL:
        return DATASET_FIXTURE
    if url == VERSION_API_URL:
        return FILES_FIXTURE
    raise AssertionError(f"unexpected URL: {url}")


def landscape_fetch_text(url: str) -> str:
    if url == "https://datadryad.org/data_file/preview/52071.js":
        return PREVIEW_JS
    raise AssertionError(f"unexpected URL: {url}")


class DrosophilaSuzukiiDryadLandscapeMonitoringSourceTests(unittest.TestCase):
    def test_fetch_parses_preview_rows_and_records_full_csv_gap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_dryad_landscape_monitoring_records(
                raw_dir=Path(tmpdir),
                fetch_json=landscape_fetch_json,
                fetch_text=landscape_fetch_text,
                retrieved_at=RETRIEVED_AT,
            )

        self.assertEqual(result.source_id, "drosophila_suzukii_dryad_landscape_monitoring")
        self.assertEqual(result.file_count, 1)
        self.assertEqual(result.row_count, 2)
        atom_types = [record.payload.get("atom_type") for record in result.records if record.payload]
        self.assertIn("dryad_landscape_dataset_manifest", atom_types)
        self.assertIn("dryad_landscape_file_manifest", atom_types)
        self.assertIn("dryad_landscape_monitoring_row", atom_types)
        self.assertIn("source_gap", atom_types)
        rows = [record for record in result.records if record.payload.get("atom_type") == "dryad_landscape_monitoring_row"]
        self.assertEqual(rows[0].payload["swd_trap_count"], 7)
        self.assertEqual(rows[0].payload["predator_counts"]["Araneae"], 3)
        self.assertEqual(rows[0].payload["landscape_composition_shannon"], 1.9)
        self.assertTrue(
            any(gap["reason"] == "dryad_landscape_full_csv_download_blocked_preview_used" for gap in result.gaps)
        )


if __name__ == "__main__":
    unittest.main()
