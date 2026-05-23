import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex, ensure_read_only_sql
from askinsects.records import EvidenceRecord, Provenance


def sample_record(record_id="obs:1", lane="observations", text="Aedes aegypti observed in Brazil"):
    return EvidenceRecord(
        record_id=record_id,
        lane=lane,
        source="mosquito_v1_fixtures",
        title="Brazil observation",
        text=text,
        species="Aedes aegypti",
        url="https://example.org/obs/1",
        media_url="https://example.org/image.jpg",
        provenance=Provenance(
            source_id="mosquito_v1_fixtures",
            locator=f"data/fixtures/mosquito_records.json#{record_id}",
            retrieved_at="2026-05-23T00:00:00Z",
            license="CC-BY",
        ),
    )


class IndexTests(unittest.TestCase):
    def test_write_search_and_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records([sample_record()])

            rows = index.search("Brazil", lane="observations", limit=5)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].record_id, "obs:1")

            summary = index.summary()
            self.assertEqual(summary["record_count"], 1)
            self.assertEqual(summary["lanes"]["observations"], 1)

    def test_read_only_sql_guard(self):
        self.assertEqual(ensure_read_only_sql("select * from records"), "select * from records")
        with self.assertRaises(ValueError):
            ensure_read_only_sql("delete from records")
        with self.assertRaises(ValueError):
            ensure_read_only_sql("select * from records; drop table records")
        with self.assertRaises(ValueError):
            ensure_read_only_sql("WITH x AS (SELECT 1) DELETE FROM records")


if __name__ == "__main__":
    unittest.main()
