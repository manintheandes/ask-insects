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

    def test_upserts_literature_fulltext_units(self):
        from askinsects.sources.literature import FullTextUnit

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            provenance = Provenance(
                source_id="aedes_literature_openalex",
                locator="raw/openalex/page.json#W1",
                retrieved_at="2026-05-23T00:00:00Z",
            )
            unit = FullTextUnit(
                unit_id="openalex:W1:fulltext:0",
                record_id="openalex:W1",
                source="aedes_literature_openalex",
                unit_index=0,
                text="Aedes aegypti legal open full text",
                url="https://example.org/fulltext",
                license="cc-by",
                provenance=provenance,
            )
            index.upsert_fulltext_units([unit])
            rows = index.sql("select unit_id, text from literature_fulltext_units")
            self.assertEqual(rows[0]["unit_id"], "openalex:W1:fulltext:0")
            self.assertIn("Aedes aegypti", rows[0]["text"])
            fts_rows = index.sql(
                "select unit_id, record_id from literature_fulltext_fts where literature_fulltext_fts match 'aegypti'"
            )
            self.assertEqual(fts_rows[0]["record_id"], "openalex:W1")

    def test_search_literature_fulltext_returns_provenance_bearing_records(self):
        from askinsects.sources.literature import FullTextUnit

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            provenance = Provenance(
                source_id="aedes_literature_openalex",
                locator="raw/literature/page.json#W1",
                retrieved_at="2026-05-23T00:00:00Z",
                license="CC BY",
                source_url="https://example.org/paper",
            )
            index.upsert_records(
                [
                    sample_record(
                        record_id="openalex:W1",
                        lane="literature",
                        text="Aedes aegypti paper metadata.",
                        payload=None,
                    )
                ]
            )
            index.upsert_fulltext_units(
                [
                    FullTextUnit(
                        unit_id="openalex:W1:fulltext:0",
                        record_id="openalex:W1",
                        source="aedes_literature_openalex",
                        unit_index=0,
                        text="The legal full text discusses microbiota effects in Aedes aegypti mosquitoes.",
                        url="https://example.org/fulltext",
                        license="CC BY",
                        provenance=provenance,
                    )
                ]
            )

            rows = index.search_literature_fulltext("microbiota", limit=3)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].record_id, "openalex:W1:fulltext:0")
            self.assertEqual(rows[0].lane, "literature_fulltext")
            self.assertEqual(rows[0].source, "aedes_literature_openalex")
            self.assertIn("microbiota", rows[0].text)
            self.assertIn("literature_fulltext_units#openalex:W1:fulltext:0", rows[0].provenance.locator)

    def test_replaces_fulltext_units_for_affected_records(self):
        from askinsects.sources.literature import FullTextUnit

        provenance = Provenance(
            source_id="aedes_literature_openalex",
            locator="raw/openalex/page.json#W1",
            retrieved_at="2026-05-23T00:00:00Z",
        )

        def fulltext_unit(unit_index, text):
            return FullTextUnit(
                unit_id=f"openalex:W1:fulltext:{unit_index}",
                record_id="openalex:W1",
                source="aedes_literature_openalex",
                unit_index=unit_index,
                text=text,
                url="https://example.org/fulltext",
                license="cc-by",
                provenance=provenance,
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_fulltext_units(
                [
                    fulltext_unit(0, "Aedes aegypti current chunk"),
                    fulltext_unit(1, "staleunique old chunk"),
                ]
            )
            index.upsert_fulltext_units([fulltext_unit(0, "Aedes aegypti rewritten shorter text")])

            rows = index.sql("select unit_id, text from literature_fulltext_units order by unit_id")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["unit_id"], "openalex:W1:fulltext:0")
            self.assertNotIn("staleunique", rows[0]["text"])

            stale_base_rows = index.sql(
                "select unit_id from literature_fulltext_units where text like '%staleunique%'"
            )
            stale_fts_rows = index.sql(
                "select unit_id from literature_fulltext_fts where literature_fulltext_fts match 'staleunique'"
            )
            self.assertEqual(stale_base_rows, [])
            self.assertEqual(stale_fts_rows, [])

    def test_records_and_fulltext_units_write_atomically(self):
        from askinsects.sources.literature import FullTextUnit

        provenance = Provenance(
            source_id="aedes_literature_openalex",
            locator="raw/openalex/page.json#W1",
            retrieved_at="2026-05-23T00:00:00Z",
        )
        bad_unit = FullTextUnit(
            unit_id="openalex:W1:fulltext:0",
            record_id="openalex:W1",
            source="aedes_literature_openalex",
            unit_index=0,
            text=None,
            url="https://example.org/fulltext",
            license="cc-by",
            provenance=provenance,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()

            with self.assertRaises(sqlite3.IntegrityError):
                index.upsert_records_and_fulltext_units(
                    [sample_record(record_id="openalex:W1", lane="literature")],
                    [bad_unit],
                )

            self.assertEqual(index.sql("select record_id from records"), [])
            self.assertEqual(index.sql("select unit_id from literature_fulltext_units"), [])

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
