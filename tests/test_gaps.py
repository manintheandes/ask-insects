import tempfile
import unittest
from pathlib import Path

from askinsects.gaps import gap_records_from_dicts, persist_source_gaps
from askinsects.index import SourceIndex


RETRIEVED_AT = "2026-05-30T00:00:00Z"


class GapRecordsTests(unittest.TestCase):
    def test_builds_source_gap_records_preserving_reason_and_lane(self):
        gaps = [
            {"source": "x", "lane": "ecology", "reason": "fetch_failed", "url": "https://e/x"},
            {"source": "x", "reason": "limit_applied"},
        ]
        records = gap_records_from_dicts("x", gaps, retrieved_at=RETRIEVED_AT)
        self.assertEqual(len(records), 2)
        by_reason = {r.payload["reason"]: r for r in records}
        self.assertEqual(by_reason["fetch_failed"].lane, "ecology")
        self.assertEqual(by_reason["fetch_failed"].payload["atom_type"], "source_gap")
        self.assertEqual(by_reason["fetch_failed"].url, "https://e/x")
        # No lane given -> default lane.
        self.assertEqual(by_reason["limit_applied"].lane, "source_coverage")

    def test_duplicate_reasons_get_unique_ids(self):
        gaps = [{"reason": "fetch_failed"}, {"reason": "fetch_failed"}]
        records = gap_records_from_dicts("x", gaps, retrieved_at=RETRIEVED_AT)
        self.assertEqual(len({r.record_id for r in records}), 2)

    def test_non_dict_entries_ignored(self):
        records = gap_records_from_dicts("x", ["oops", None, {"reason": "ok_gap"}], retrieved_at=RETRIEVED_AT)
        self.assertEqual(len(records), 1)

    def test_persist_makes_gaps_queryable_in_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "i.sqlite")
            index.initialize()
            written = persist_source_gaps(
                index,
                "demo_source",
                [{"lane": "ecology", "reason": "preview_blocked"}],
                retrieved_at=RETRIEVED_AT,
            )
            self.assertEqual(written, 1)
            rows = index.sql(
                "select count(*) as n from record_payloads "
                "where source='demo_source' and payload_json like '%source_gap%'"
            )
            self.assertEqual(int(rows[0]["n"]), 1)

    def test_persist_no_gaps_is_noop(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "i.sqlite")
            index.initialize()
            self.assertEqual(persist_source_gaps(index, "demo", [], retrieved_at=RETRIEVED_AT), 0)


if __name__ == "__main__":
    unittest.main()
