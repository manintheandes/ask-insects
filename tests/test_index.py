import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from unittest import mock

from askinsects.index import SEARCH_TIMEOUT_SECONDS, SourceIndex, ensure_read_only_sql
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

    def test_search_quotes_fts_reserved_words(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    sample_record(
                        text="A field comparison of DEET and picaridin that excludes citronella."
                    )
                ]
            )

            for query in ("DEET OR picaridin", "NOT citronella", "NEAR field", "OR"):
                with self.subTest(query=query):
                    rows = index.search(query, lane="observations", limit=5)
                    expected = [] if query == "OR" else ["obs:1"]
                    self.assertEqual([row.record_id for row in rows], expected)

    def test_search_fails_closed_when_the_fts_budget_expires(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    sample_record(
                        record_id=f"obs:{row}",
                        text=f"common Aedes aegypti observation {row}",
                    )
                    for row in range(500)
                ]
            )

            with mock.patch("askinsects.index.SEARCH_TIMEOUT_SECONDS", 0), mock.patch(
                "askinsects.index.SEARCH_PROGRESS_STEPS",
                1,
            ):
                rows = index.search("common", lane="observations", limit=5)

            self.assertEqual(rows, [])
            self.assertTrue(index.last_search_timed_out)

    def test_search_fts_budget_is_eight_seconds(self):
        self.assertEqual(SEARCH_TIMEOUT_SECONDS, 8.0)

    def test_search_literature_fulltext_fails_closed_when_budget_expires(self):
        from askinsects.sources.literature import FullTextUnit

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            provenance = Provenance(
                source_id="aedes_literature_openalex",
                locator="raw/literature/page.json#W1",
                retrieved_at="2026-05-23T00:00:00Z",
            )
            index.upsert_records(
                [sample_record(record_id="openalex:W1", lane="literature")]
            )
            index.upsert_fulltext_units(
                [
                    FullTextUnit(
                        unit_id=f"openalex:W1:fulltext:{row}",
                        record_id="openalex:W1",
                        source="aedes_literature_openalex",
                        unit_index=row,
                        text=f"common mosquito odor evidence unit {row}",
                        url="https://example.org/fulltext",
                        license="CC BY",
                        provenance=provenance,
                    )
                    for row in range(500)
                ]
            )

            with mock.patch("askinsects.index.SEARCH_TIMEOUT_SECONDS", 0), mock.patch(
                "askinsects.index.SEARCH_PROGRESS_STEPS",
                1,
            ):
                rows = index.search_literature_fulltext("common", limit=5)

            self.assertEqual(rows, [])
            self.assertTrue(index.last_search_timed_out)

    def test_search_fts_budget_resets_timeout_state_for_every_call(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records([sample_record()])

            index.last_search_timed_out = True
            self.assertEqual(index.search("OR"), [])
            self.assertFalse(index.last_search_timed_out)

            index.last_search_timed_out = True
            self.assertEqual([row.record_id for row in index.search("Brazil")], ["obs:1"])
            self.assertFalse(index.last_search_timed_out)

    def test_search_fts_budget_reraises_other_operational_errors_and_clears_handler(self):
        class FailingConnection:
            def __init__(self, error):
                self.error = error
                self.deadline_expired = False
                self.progress_handler_calls = []

            def set_progress_handler(self, callback, steps):
                self.progress_handler_calls.append((callback, steps))

            def execute(self, _sql, _params):
                self.deadline_expired = bool(self.progress_handler_calls[-1][0]())
                raise self.error

        coded_error = sqlite3.OperationalError("deadline observed but not an interrupt")
        coded_error.sqlite_errorcode = sqlite3.SQLITE_BUSY
        errors = [
            ("non_interrupt_code", coded_error),
            ("missing_error_code", sqlite3.OperationalError("deadline observed but not an interrupt")),
        ]

        for label, error in errors:
            with self.subTest(label=label):
                connection = FailingConnection(error)
                index = SourceIndex(Path("unused.sqlite"))

                @contextmanager
                def failing_connect():
                    yield connection

                with mock.patch.object(index, "connect", failing_connect), mock.patch(
                    "askinsects.index.time.monotonic",
                    side_effect=[10.0, 100.0],
                ):
                    with self.assertRaisesRegex(sqlite3.OperationalError, "not an interrupt"):
                        index.search("common")

                self.assertTrue(connection.deadline_expired)
                self.assertFalse(index.last_search_timed_out)
                self.assertTrue(callable(connection.progress_handler_calls[0][0]))
                self.assertEqual(connection.progress_handler_calls[-1], (None, 0))

    def test_search_fts_budget_clears_progress_handler_after_success(self):
        class EmptyRows:
            @staticmethod
            def fetchall():
                return []

        class SuccessfulConnection:
            def __init__(self):
                self.progress_handler_calls = []

            def set_progress_handler(self, callback, steps):
                self.progress_handler_calls.append((callback, steps))

            @staticmethod
            def execute(_sql, _params):
                return EmptyRows()

        connection = SuccessfulConnection()
        index = SourceIndex(Path("unused.sqlite"))

        @contextmanager
        def successful_connect():
            yield connection

        with mock.patch.object(index, "connect", successful_connect):
            self.assertEqual(index.search("common"), [])

        self.assertTrue(connection.progress_handler_calls)
        self.assertTrue(callable(connection.progress_handler_calls[0][0]))
        self.assertEqual(connection.progress_handler_calls[-1], (None, 0))

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

    def test_replace_source_records_removes_stale_source_rows_atomically(self):
        from askinsects.sources.literature import FullTextUnit

        provenance = Provenance(
            source_id="mosquito_v1_fixtures",
            locator="data/fixtures/mosquito_records.json#obs:1",
            retrieved_at="2026-05-23T00:00:00Z",
        )
        stale_unit = FullTextUnit(
            unit_id="obs:1:fulltext:0",
            record_id="obs:1",
            source="mosquito_v1_fixtures",
            unit_index=0,
            text="staleunique old source text",
            url="https://example.org/fulltext",
            license="CC-BY",
            provenance=provenance,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            other_record = EvidenceRecord(
                record_id="other:1",
                lane="taxonomy",
                source="other_source",
                title="Other source row",
                text="other source row",
                species="Aedes aegypti",
                url="https://example.org/other",
                media_url=None,
                provenance=Provenance(
                    source_id="other_source",
                    locator="other#1",
                    retrieved_at="2026-05-23T00:00:00Z",
                ),
                payload={"version": "other"},
            )
            index.upsert_records(
                [
                    sample_record(record_id="obs:1", payload={"version": "old"}),
                    sample_record(record_id="obs:stale", text="staleunique old row"),
                    other_record,
                ]
            )
            index.upsert_fulltext_units([stale_unit])

            index.replace_source_records(
                "mosquito_v1_fixtures",
                [sample_record(record_id="obs:2", text="replacement row", payload={"version": "new"})],
            )

            self.assertEqual(
                index.sql("select record_id from records order by record_id"),
                [{"record_id": "obs:2"}, {"record_id": "other:1"}],
            )
            self.assertEqual(
                index.sql(
                    "select record_id, json_extract(payload_json, '$.version') as version "
                    "from record_payloads order by record_id"
                ),
                [{"record_id": "obs:2", "version": "new"}, {"record_id": "other:1", "version": "other"}],
            )
            self.assertEqual(
                index.sql("select unit_id from literature_fulltext_units where text like '%staleunique%'"),
                [],
            )
            self.assertEqual(
                index.sql("select record_id from records_fts where records_fts match 'staleunique'"),
                [],
            )

    def test_new_records_do_not_scan_fts_for_rows_that_cannot_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            statements: list[str] = []
            original_connect = index.connect

            @contextmanager
            def traced_connect():
                with original_connect() as conn:
                    conn.set_trace_callback(statements.append)
                    yield conn

            with mock.patch.object(index, "connect", traced_connect):
                index.upsert_records([sample_record(record_id="obs:new")])

            fts_deletes = [
                statement
                for statement in statements
                if statement.lstrip().upper().startswith("DELETE FROM RECORDS_FTS")
            ]
            self.assertEqual(fts_deletes, [])
            self.assertEqual(index.search("Brazil")[0].record_id, "obs:new")

    def test_existing_record_update_replaces_its_search_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records([sample_record(record_id="obs:1", text="oldunique row")])

            index.upsert_records([sample_record(record_id="obs:1", text="newunique row")])

            self.assertEqual(index.search("oldunique"), [])
            self.assertEqual(index.search("newunique")[0].record_id, "obs:1")

    def test_replace_source_records_can_preserve_existing_fts_for_large_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records([sample_record(record_id="obs:1", text="oldunique row")])

            index.replace_source_records(
                "mosquito_v1_fixtures",
                [sample_record(record_id="obs:1", text="replacement row")],
                update_fts=False,
                delete_existing_fts=False,
            )

            self.assertEqual(index.sql("select text from records where record_id='obs:1'"), [{"text": "replacement row"}])
            self.assertEqual(index.sql("select record_id from records_fts where records_fts match 'oldunique'"), [{"record_id": "obs:1"}])

    def test_replace_source_records_preserves_fts_while_cleaning_fulltext_units(self):
        from askinsects.sources.literature import FullTextUnit

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records([sample_record(record_id="obs:1", text="oldunique row")])
            index.upsert_fulltext_units(
                [
                    FullTextUnit(
                        unit_id="obs:1:fulltext:0",
                        record_id="obs:1",
                        source="mosquito_v1_fixtures",
                        unit_index=0,
                        text="stale fulltext unit",
                        url="https://example.org/fulltext",
                        license="CC-BY",
                        provenance=Provenance(
                            source_id="mosquito_v1_fixtures",
                            locator="fulltext#obs:1",
                            retrieved_at="2026-05-23T00:00:00Z",
                        ),
                    )
                ]
            )

            index.replace_source_records(
                "mosquito_v1_fixtures",
                [sample_record(record_id="obs:1", text="replacement row")],
                update_fts=False,
                delete_existing_fts=False,
            )

            self.assertEqual(index.sql("select unit_id from literature_fulltext_units"), [])
            self.assertEqual(
                index.sql("select record_id from records_fts where records_fts match 'oldunique'"),
                [{"record_id": "obs:1"}],
            )

    def test_replace_source_records_rolls_back_failed_replacement(self):
        bad_record = EvidenceRecord(
            record_id="obs:bad",
            lane="observations",
            source="mosquito_v1_fixtures",
            title=None,
            text="bad replacement",
            species="Aedes aegypti",
            url="https://example.org/bad",
            media_url=None,
            provenance=Provenance(
                source_id="mosquito_v1_fixtures",
                locator="bad",
                retrieved_at="2026-05-23T00:00:00Z",
            ),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records([sample_record(record_id="obs:old", payload={"version": "old"})])

            with self.assertRaises(sqlite3.IntegrityError):
                index.replace_source_records("mosquito_v1_fixtures", [bad_record])

            self.assertEqual(
                index.sql("select record_id, title from records"),
                [{"record_id": "obs:old", "title": "Brazil observation"}],
            )
            self.assertEqual(
                index.sql("select json_extract(payload_json, '$.version') as version from record_payloads"),
                [{"version": "old"}],
            )

    def test_replace_source_records_retries_transient_sqlite_locks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records([sample_record(record_id="obs:old", payload={"version": "old"})])
            original_delete = index._delete_source_records
            calls = 0

            def flaky_delete(conn, source, *, delete_fts=True):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise sqlite3.OperationalError("database is locked")
                return original_delete(conn, source, delete_fts=delete_fts)

            with mock.patch.object(index, "_delete_source_records", side_effect=flaky_delete), mock.patch("askinsects.index.time.sleep"):
                index.replace_source_records(
                    "mosquito_v1_fixtures",
                    [sample_record(record_id="obs:new", text="retry replacement", payload={"version": "new"})],
                )

            self.assertEqual(calls, 2)
            self.assertEqual(
                index.sql("select record_id from records"),
                [{"record_id": "obs:new"}],
            )

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
