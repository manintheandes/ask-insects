from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.sources.harvard_dataverse_suitability import HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID
from scripts.ingest_harvard_dataverse_suitability import ingest_harvard_dataverse_suitability
from tests.test_harvard_dataverse_suitability_source import dataset_detail, search_payload


class IngestHarvardDataverseSuitabilityTests(unittest.TestCase):
    def test_ingest_updates_sqlite_metadata_and_queryable_gaps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"

            def fake_json(url: str) -> dict[str, object]:
                if "/api/search?" in url:
                    return search_payload()
                if "/api/datasets/:persistentId/" in url:
                    return dataset_detail()
                raise AssertionError(url)

            result = ingest_harvard_dataverse_suitability(
                artifact_dir=artifact_dir,
                queries=('"Aedes aegypti" suitability',),
                per_page=10,
                dataset_limit=2,
                fetch_json=fake_json,
                retrieved_at="2026-05-25T00:00:00Z",
            )

            index = SourceIndex(artifact_dir / "source_index.sqlite")
            rows = index.sql(
                "select lane, count(*) as n from records where source='harvard_dataverse_aedes_suitability' group by lane",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID)
        self.assertEqual(result["file_record_count"], 1)
        self.assertEqual(result["gap_count"], 1)
        self.assertEqual(rows, [{"lane": "ecology", "n": 2}])
        self.assertEqual(result["source_counts"][HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID], 2)


if __name__ == "__main__":
    unittest.main()
