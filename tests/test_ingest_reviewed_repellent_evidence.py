from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from askinsects.index import SourceIndex
from askinsects.sources.reviewed_repellent_evidence import (
    REVIEWED_REPELLENT_SOURCE_ID,
    build_reviewed_repellent_records,
)
from scripts.ingest_reviewed_repellent_evidence import (
    _can_preserve_existing_fts,
    ingest_reviewed_repellent_evidence,
)


class ReviewedRepellentEvidenceIngestTests(unittest.TestCase):
    def test_additive_catalog_refresh_preserves_existing_fts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "artifacts"
            records = build_reviewed_repellent_records()
            initial_records = records[:-2]
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.replace_source_records(
                REVIEWED_REPELLENT_SOURCE_ID,
                initial_records,
            )

            self.assertTrue(_can_preserve_existing_fts(index, records))
            with mock.patch.object(
                SourceIndex,
                "replace_source_records_preserving_existing_fts",
                autospec=True,
                wraps=SourceIndex.replace_source_records_preserving_existing_fts,
            ) as preserve:
                result = ingest_reviewed_repellent_evidence(
                    artifact_dir=artifact_dir,
                )

            self.assertTrue(result["preserved_existing_fts"])
            preserve.assert_called_once()
            self.assertEqual(
                index.sql(
                    "SELECT count(*) AS n FROM records "
                    f"WHERE source='{REVIEWED_REPELLENT_SOURCE_ID}'"
                ),
                [{"n": len(records)}],
            )
            self.assertEqual(
                index.search("physicochemical masking", limit=5)[0].record_id,
                "reviewed_repellent_evidence:deet_anopheles_odor_masking_2019",
            )

    def test_changed_search_text_requires_full_fts_replacement(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            records = build_reviewed_repellent_records()
            index.replace_source_records(
                REVIEWED_REPELLENT_SOURCE_ID,
                records,
            )
            changed = list(records)
            changed[0] = changed[0].__class__(
                **{
                    **changed[0].__dict__,
                    "text": changed[0].text + " changed",
                }
            )

            self.assertFalse(_can_preserve_existing_fts(index, changed))


if __name__ == "__main__":
    unittest.main()
