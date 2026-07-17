import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.ingest_runner import run_source_ingest

RID = "2026-05-30T00:00:00Z"
SRC = "demo_source"


def _rec(
    rid,
    *,
    atom="row",
    lane="ecology",
    text="x",
    url=None,
    locator=None,
    payload_version=None,
):
    return EvidenceRecord(
        record_id=rid, lane=lane, source=SRC, title="t", text=text,
        species="Aedes aegypti", url=url, media_url=None,
        provenance=Provenance(source_id=SRC, locator=locator or rid, retrieved_at=RID),
        payload={"atom_type": atom, "version": payload_version},
    )


def _index(tmp):
    idx = SourceIndex(Path(tmp) / "i.sqlite")
    idx.initialize()
    return idx


class RunSourceIngestTests(unittest.TestCase):
    def test_preserving_existing_fts_indexes_new_ids_without_fts_deletes(self):
        with tempfile.TemporaryDirectory() as tmp:
            idx = _index(tmp)
            idx.upsert_records(
                [
                    _rec(
                        f"{SRC}:row:1",
                        text="existingtoken",
                        url="https://example.org/old",
                        locator="source#old",
                        payload_version="old",
                    ),
                    _rec(f"{SRC}:row:stale", text="staletoken"),
                ]
            )
            statements: list[str] = []
            original_connect = idx.connect

            @contextmanager
            def traced_connect():
                with original_connect() as connection:
                    connection.set_trace_callback(statements.append)
                    yield connection

            with mock.patch.object(idx, "connect", traced_connect):
                out = run_source_ingest(
                    index=idx,
                    artifact_dir=Path(tmp),
                    source_id=SRC,
                    records=[
                        _rec(
                            f"{SRC}:row:1",
                            text="updatedtoken",
                            url="https://example.org/new",
                            locator="source#new",
                            payload_version="new",
                        ),
                        _rec(f"{SRC}:row:2", text="newtoken"),
                    ],
                    gaps=[],
                    retrieved_at=RID,
                    preserve_existing_fts=True,
                )

            self.assertTrue(out["ok"])
            self.assertFalse(
                any(
                    statement.lstrip().upper().startswith("DELETE FROM RECORDS_FTS")
                    for statement in statements
                )
            )
            self.assertEqual(len(idx.search("existingtoken")), 1)
            self.assertEqual(idx.search("updatedtoken"), [])
            self.assertEqual(len(idx.search("newtoken")), 1)
            self.assertEqual(idx.search("staletoken"), [])
            self.assertEqual(
                idx.sql(
                    "select text, url, "
                    "json_extract(provenance_json, '$.locator') as locator "
                    f"from records where record_id='{SRC}:row:1'"
                ),
                [
                    {
                        "text": "existingtoken",
                        "url": "https://example.org/new",
                        "locator": "source#new",
                    }
                ],
            )
            self.assertEqual(
                idx.sql(
                    "select json_extract(payload_json, '$.version') as version, "
                    "json_extract(provenance_json, '$.locator') as locator "
                    "from record_payloads "
                    f"where record_id='{SRC}:row:1'"
                ),
                [{"version": "new", "locator": "source#new"}],
            )
            self.assertEqual(
                idx.sql(
                    "select f.record_id, count(*) as n from records_fts f "
                    "join records r on r.record_id=f.record_id "
                    "group by f.record_id order by f.record_id"
                ),
                [
                    {"record_id": f"{SRC}:row:1", "n": 1},
                    {"record_id": f"{SRC}:row:2", "n": 1},
                ],
            )

    def test_success_persists_records_and_gaps_and_reports_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            idx = _index(tmp)
            out = run_source_ingest(
                index=idx, artifact_dir=Path(tmp), source_id=SRC,
                records=[_rec(f"{SRC}:row:1")],
                gaps=[{"lane": "ecology", "reason": "limit_applied"}],
                retrieved_at=RID,
            )
            self.assertTrue(out["ok"])
            self.assertFalse(out["refresh_failed"])
            rows = idx.sql(f"select count(*) as n from records where source='{SRC}'")
            self.assertEqual(int(rows[0]["n"]), 2)

    def test_total_failure_preserves_existing_and_reports_not_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            idx = _index(tmp)
            run_source_ingest(index=idx, artifact_dir=Path(tmp), source_id=SRC,
                              records=[_rec(f"{SRC}:row:1")], gaps=[], retrieved_at=RID)
            out = run_source_ingest(
                index=idx, artifact_dir=Path(tmp), source_id=SRC,
                records=[], gaps=[{"lane": "ecology", "reason": "fetch_failed"}],
                retrieved_at=RID,
            )
            self.assertFalse(out["ok"])
            self.assertTrue(out["refresh_failed"])
            self.assertTrue(out["preserved_existing"])
            rows = idx.sql(f"select count(*) as n from records where source='{SRC}' and record_id='{SRC}:row:1'")
            self.assertEqual(int(rows[0]["n"]), 1)
            g = idx.sql(f"select count(*) as n from record_payloads where source='{SRC}' and payload_json like '%fetch_failed%'")
            self.assertGreater(int(g[0]["n"]), 0)

    def test_gap_only_records_count_as_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            idx = _index(tmp)
            run_source_ingest(index=idx, artifact_dir=Path(tmp), source_id=SRC,
                              records=[_rec(f"{SRC}:row:1")], gaps=[], retrieved_at=RID)
            out = run_source_ingest(
                index=idx, artifact_dir=Path(tmp), source_id=SRC,
                records=[_rec(f"{SRC}:gap:fetch_failed", atom="source_gap")],
                gaps=[{"lane": "ecology", "reason": "fetch_failed"}],
                retrieved_at=RID, persist_gap_records=False,
            )
            self.assertTrue(out["refresh_failed"])
            self.assertEqual(int(idx.sql(f"select count(*) as n from records where source='{SRC}' and record_id='{SRC}:row:1'")[0]["n"]), 1)

    def test_no_double_gap_when_persist_gap_records_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            idx = _index(tmp)
            out = run_source_ingest(
                index=idx, artifact_dir=Path(tmp), source_id=SRC,
                records=[_rec(f"{SRC}:row:1"), _rec(f"{SRC}:gap:x", atom="source_gap")],
                gaps=[{"lane": "ecology", "reason": "x"}],
                retrieved_at=RID, persist_gap_records=False,
            )
            self.assertTrue(out["ok"])
            n = int(idx.sql(f"select count(*) as n from records where source='{SRC}' and record_id like '{SRC}:gap:%'")[0]["n"])
            self.assertEqual(n, 1)

    def test_empty_records_and_gaps_preserves_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            idx = _index(tmp)
            run_source_ingest(index=idx, artifact_dir=Path(tmp), source_id=SRC,
                              records=[_rec(f"{SRC}:row:1")], gaps=[], retrieved_at=RID)
            out = run_source_ingest(
                index=idx, artifact_dir=Path(tmp), source_id=SRC,
                records=[], gaps=[], retrieved_at=RID,
            )
            self.assertTrue(out["refresh_failed"])
            self.assertFalse(out["ok"])
            rows = idx.sql(f"select count(*) as n from records where source='{SRC}' and record_id='{SRC}:row:1'")
            self.assertEqual(int(rows[0]["n"]), 1)


if __name__ == "__main__":
    unittest.main()
