import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from scripts.ingest_drosophila_suzukii_osu_trap_reports import ingest_drosophila_suzukii_osu_trap_reports
from tests.test_drosophila_suzukii_osu_trap_reports_source import RETRIEVED_AT, osu_fetcher


class IngestDrosophilaSuzukiiOsuTrapReportsTests(unittest.TestCase):
    def test_ingest_installs_osu_trap_report_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            result = ingest_drosophila_suzukii_osu_trap_reports(
                artifact_dir=artifact_dir,
                fetch_body=osu_fetcher,
                retrieved_at=RETRIEVED_AT,
            )
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            rows = index.sql(
                "select count(*) as n from record_payloads where source='drosophila_suzukii_osu_trap_reports' and payload_json like '%osu_swd_trap_observation%'"
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["file_count"], 6)
        self.assertGreater(result["parsed_trap_observation_count"], 0)
        self.assertGreater(int(rows[0]["n"]), 0)


if __name__ == "__main__":
    unittest.main()
