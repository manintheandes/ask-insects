import json
import tempfile
import unittest
from pathlib import Path

from askinsects.sources.who_malaria_threats_resistance import (
    WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID,
    fetch_who_malaria_threats_resistance_records,
)


SAMPLE_CSV = (
    "OBJECTID,Code,ISO2,TYPE,ASSAY_TYPE,INSECTICIDE_TYPE,YEAR_START,SPECIES,MORTALITY_ADJUSTED,RESISTANCE_STATUS\n"
    "1,GIL0383,ML,CDC_BOTTLE_ADULTS,BIOCHEMICAL_ASSAY,NA,2016,An. gambiae s.l.,0.88,Confirmed\n"
)


class WhoMalariaThreatsResistanceSourceTests(unittest.TestCase):
    def test_fetch_records_source_availability_and_aedes_gap(self):
        calls = []

        def fake_fetch(url: str) -> bytes:
            calls.append(url)
            if "format=csv" in url:
                return SAMPLE_CSV.encode("utf-8")
            return json.dumps({"value": []}).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_who_malaria_threats_resistance_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_bytes=fake_fetch,
                retrieved_at="2026-05-25T00:00:00Z",
            )

        self.assertEqual(result.source_id, WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID)
        self.assertEqual(result.sample_row_count, 1)
        self.assertEqual(result.aedes_row_count, 0)
        self.assertEqual([gap["reason"] for gap in result.gaps], ["who_malaria_threats_no_aedes_rows"])
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.records[0].record_id, "who:malaria-threats:resistance:source")
        self.assertEqual(result.records[1].lane, "resistance")
        self.assertIn("no rows matching Aedes aegypti", result.records[1].text)
        self.assertTrue(any("FACT_PREVENTION_VIEW" in call for call in calls))

    def test_fetch_records_normalizes_aedes_rows_when_present(self):
        def fake_fetch(url: str) -> bytes:
            if "format=csv" in url:
                return SAMPLE_CSV.encode("utf-8")
            return json.dumps(
                {
                    "value": [
                        {
                            "OBJECTID": 77,
                            "Code": "AED77",
                            "ISO2": "BR",
                            "VILLAGE_NAME": "Rio",
                            "YEAR_START": 2024,
                            "TYPE": "WHO_TEST_KIT_ADULTS",
                            "ASSAY_TYPE": "DISCRIMINATING_CONCENTRATION_BIOASSAY",
                            "INSECTICIDE_CLASS": "PYRETHROIDS",
                            "INSECTICIDE_TYPE": "Deltamethrin",
                            "SPECIES": "Aedes aegypti",
                            "MORTALITY_ADJUSTED": "0.81",
                            "RESISTANCE_STATUS": "Confirmed",
                        }
                    ]
                }
            ).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_who_malaria_threats_resistance_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_bytes=fake_fetch,
                retrieved_at="2026-05-25T00:00:00Z",
            )

        self.assertEqual(result.gaps, [])
        self.assertEqual(result.aedes_row_count, 1)
        record = result.records[1]
        self.assertEqual(record.record_id, "who:malaria-threats:resistance:77")
        self.assertEqual(record.source, WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID)
        self.assertEqual(record.species, "Aedes aegypti")
        self.assertIn("Deltamethrin", record.text)
        self.assertIn("Confirmed", record.text)


if __name__ == "__main__":
    unittest.main()
