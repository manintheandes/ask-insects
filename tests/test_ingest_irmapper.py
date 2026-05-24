import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from scripts.ingest_irmapper import ingest_irmapper


class IngestIRMapperTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        rows = [
            {
                "id": 201,
                "country": "Brazil",
                "locality": "Rio de Janeiro",
                "collection_Year_Start": 2021,
                "collection_Year_End": 2021,
                "vector_Species": "Aedes aegypti",
                "iR_Test_Method": "CDC bottle bioassay",
                "chemical_Class": "Pyrethroid",
                "chemical_Type": "deltamethrin",
                "resistance_Status": "Confirmed resistance",
                "reference_Name": "Example et al. 2021",
                "url": "https://example.org/paper",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            result = ingest_irmapper(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: rows,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["record_count"], 1)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            counts = {
                (row["source"], row["lane"]): row["n"]
                for row in index.sql(
                    "select source, lane, count(*) as n from records group by source, lane order by source, lane",
                    limit=100,
                )
            }
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 4)
            self.assertEqual(counts[("irmapper_aedes", "resistance")], 1)
            payload_rows = index.sql("select record_id from record_payloads where source='irmapper_aedes'")
            self.assertEqual(payload_rows[0]["record_id"], "irmapper:aedes:201")

            status = (artifact_dir / "source_status.json").read_text(encoding="utf-8")
            self.assertIn("irmapper_aedes", status)


if __name__ == "__main__":
    unittest.main()
