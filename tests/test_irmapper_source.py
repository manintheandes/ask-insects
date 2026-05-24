import tempfile
import unittest
from pathlib import Path

from askinsects.sources.irmapper import IRMAPPER_SOURCE_ID, fetch_irmapper_records


IRMAPPER_ROWS = [
    {
        "id": 101,
        "country": "Thailand",
        "locality": "Bangkok",
        "latitude": 13.81666667,
        "longitude": 100.65,
        "collection_Year_Start": 1965,
        "collection_Year_End": 1965,
        "vector_Species": "Aedes aegypti",
        "vector_Developmental_Stage": "Adult",
        "iR_Test_Method": "WHO tube assay",
        "chemical_Class": "DDT",
        "chemical_Type": "DDT",
        "insecticide_Dosage": "2.5ppm",
        "iraC_MoA": "Sodium channel modulators",
        "iR_Test_mortality": "undefined",
        "resistance_Status": "Confirmed resistance",
        "iR_Mechanism_Name": "NA",
        "mutation_frequency": "NA",
        "iR_Mechanism_Status": "NA",
        "reference_Type": "Published article",
        "reference_Name": "Neely et al. 1966",
        "url": "http://europepmc.org/articles/pmc2476190",
    },
    {
        "id": 102,
        "country": "United States",
        "locality": "Florida",
        "vector_Species": "Aedes albopictus",
        "chemical_Type": "permethrin",
        "resistance_Status": "Possible resistance",
    },
    {
        "id": 103,
        "country": "Brazil",
        "locality": "Sao Paulo",
        "vector_Species": "Ae. aegypti",
        "chemical_Type": "deltamethrin",
        "resistance_Status": "Susceptibility",
    },
]


class IRMapperSourceTests(unittest.TestCase):
    def test_fetch_irmapper_records_filters_to_aedes_aegypti_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_irmapper_records(
                raw_dir=Path(tmpdir),
                fetch_json=lambda url: IRMAPPER_ROWS,
                retrieved_at="2026-05-24T00:00:00Z",
            )

        self.assertEqual(result.source_id, IRMAPPER_SOURCE_ID)
        self.assertEqual(result.fetched_row_count, 3)
        self.assertEqual(len(result.records), 2)
        record = result.records[0]
        self.assertEqual(record.record_id, "irmapper:aedes:101")
        self.assertEqual(record.lane, "resistance")
        self.assertEqual(record.source, IRMAPPER_SOURCE_ID)
        self.assertEqual(record.species, "Aedes aegypti")
        self.assertEqual(record.url, "http://europepmc.org/articles/pmc2476190")
        self.assertIn("DDT", record.text)
        self.assertIn("Bangkok", record.text)
        self.assertIn("WHO tube assay", record.text)
        self.assertIn("Confirmed resistance", record.text)
        self.assertEqual(record.payload["raw_row"]["id"], 101)
        self.assertIn("#row/1", record.provenance.locator)
        self.assertEqual(result.records[1].species, "Aedes aegypti")
        self.assertEqual(result.records[1].record_id, "irmapper:aedes:103")

    def test_fetch_irmapper_records_records_gap_when_species_is_absent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_irmapper_records(
                raw_dir=Path(tmpdir),
                fetch_json=lambda url: [IRMAPPER_ROWS[1]],
                retrieved_at="2026-05-24T00:00:00Z",
            )

        self.assertEqual(result.records, [])
        self.assertEqual(result.gaps[0]["source"], IRMAPPER_SOURCE_ID)
        self.assertEqual(result.gaps[0]["species"], "Aedes aegypti")
        self.assertEqual(result.gaps[0]["reason"], "irmapper_species_rows_missing")


if __name__ == "__main__":
    unittest.main()
