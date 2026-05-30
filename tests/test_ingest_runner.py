import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.ingest_runner import run_source_ingest

RID = "2026-05-30T00:00:00Z"
SRC = "demo_source"


def _rec(rid, *, atom="row", lane="ecology"):
    return EvidenceRecord(
        record_id=rid, lane=lane, source=SRC, title="t", text="x",
        species="Aedes aegypti", url=None, media_url=None,
        provenance=Provenance(source_id=SRC, locator=rid, retrieved_at=RID),
        payload={"atom_type": atom},
    )


def _index(tmp):
    idx = SourceIndex(Path(tmp) / "i.sqlite")
    idx.initialize()
    return idx


class RunSourceIngestTests(unittest.TestCase):
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
