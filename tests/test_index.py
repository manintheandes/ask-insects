import tempfile
import unittest
from pathlib import Path
import sqlite3

from askinsects.index import SourceIndex, ensure_read_only_sql
from askinsects.records import EvidenceRecord, Provenance


def sample_record(record_id="obs:1", lane="observations", text="Aedes aegypti observed in Brazil", payload=None):
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
        payload=payload,
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

    def test_payloads_are_queryable_from_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "source_index.sqlite"
            index = SourceIndex(db_path)
            index.initialize()
            index.upsert_records(
                [
                    sample_record(
                        payload={
                            "raw_observation": {"id": 12345, "place_guess": "Rio de Janeiro, Brazil"},
                            "raw_photo": {"id": 99, "url": "https://static.inaturalist.org/photos/99/medium.jpg"},
                        }
                    )
                ]
            )

            conn = sqlite3.connect(db_path)
            row = conn.execute(
                """
                SELECT record_id, source, lane, json_extract(payload_json, '$.raw_observation.id') AS observation_id
                FROM record_payloads
                WHERE record_id = ?
                """,
                ("obs:1",),
            ).fetchone()

            self.assertEqual(row, ("obs:1", "mosquito_v1_fixtures", "observations", 12345))

    def test_read_only_sql_guard(self):
        self.assertEqual(ensure_read_only_sql("select * from records"), "select * from records")
        with self.assertRaises(ValueError):
            ensure_read_only_sql("delete from records")
        with self.assertRaises(ValueError):
            ensure_read_only_sql("select * from records; drop table records")
        with self.assertRaises(ValueError):
            ensure_read_only_sql("WITH x AS (SELECT 1) DELETE FROM records")
        with self.assertRaises(ValueError):
            ensure_read_only_sql("pragma user_version")
        with self.assertRaises(ValueError):
            ensure_read_only_sql("pragma user_version=7")
        with self.assertRaises(ValueError):
            ensure_read_only_sql("pragma journal_mode=WAL")
        with self.assertRaises(ValueError):
            ensure_read_only_sql("pragma writable_schema=ON")
        with self.assertRaises(ValueError):
            ensure_read_only_sql("select * from pragma_table_info('records')")
        with self.assertRaises(ValueError):
            ensure_read_only_sql("select name from pragma_database_list")


if __name__ == "__main__":
    unittest.main()
