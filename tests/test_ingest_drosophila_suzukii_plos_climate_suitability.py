import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from scripts.ingest_drosophila_suzukii_plos_climate_suitability import ingest_drosophila_suzukii_plos_climate_suitability
from tests.test_drosophila_suzukii_plos_climate_suitability_source import RETRIEVED_AT, plos_fetcher


class IngestDrosophilaSuzukiiPlosClimateSuitabilityTests(unittest.TestCase):
    def test_ingest_installs_climate_suitability_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            result = ingest_drosophila_suzukii_plos_climate_suitability(
                artifact_dir=artifact_dir,
                fetch_body=plos_fetcher,
                retrieved_at=RETRIEVED_AT,
            )
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            counts = {
                (row["source"], row["lane"]): int(row["n"])
                for row in index.sql("select source, lane, count(*) as n from records group by source, lane")
            }
            payload_rows = index.sql(
                "select payload_json from record_payloads where source='drosophila_suzukii_plos_climate_suitability' and payload_json like '%plos_climate_moran_i_row%'"
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["file_count"], 4)
        self.assertEqual(result["parsed_table_row_count"], 3)
        self.assertGreaterEqual(counts[("drosophila_suzukii_plos_climate_suitability", "ecology")], 9)
        self.assertEqual(len(payload_rows), 1)


if __name__ == "__main__":
    unittest.main()
