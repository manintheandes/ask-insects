import json
import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from scripts.ingest_who_malaria_threats_resistance import ingest_who_malaria_threats_resistance
from tests.test_who_malaria_threats_resistance_source import SAMPLE_CSV


class IngestWhoMalariaThreatsResistanceTests(unittest.TestCase):
    def test_ingest_preserves_existing_sources_and_records_aedes_gap(self):
        def fake_fetch(url: str) -> bytes:
            if "format=csv" in url:
                return SAMPLE_CSV.encode("utf-8")
            return json.dumps({"value": []}).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            result = ingest_who_malaria_threats_resistance(
                artifact_dir=artifact_dir,
                fetch_bytes=fake_fetch,
                retrieved_at="2026-05-25T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["record_count"], 2)
            self.assertEqual(result["sample_row_count"], 1)
            self.assertEqual(result["aedes_row_count"], 0)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql("select source, count(*) as n from records group by source")
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["mosquito_v1_fixtures"], 7)
            self.assertEqual(counts["who_malaria_threats_resistance_audit"], 2)
            gaps = json.loads((artifact_dir / "gaps.json").read_text(encoding="utf-8"))
            self.assertEqual(
                [gap["reason"] for gap in gaps if gap.get("source") == "who_malaria_threats_resistance_audit"],
                ["who_malaria_threats_no_aedes_rows"],
            )
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn("who_malaria_threats_resistance_audit", status["sources"])
            self.assertEqual(status["who_malaria_threats_resistance_audit"]["gap_count"], 1)


if __name__ == "__main__":
    unittest.main()
