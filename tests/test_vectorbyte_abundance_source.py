import tempfile
import unittest
from pathlib import Path

from askinsects.sources.vectorbyte_abundance import fetch_vectorbyte_abundance_records


SEARCH_PAYLOAD = {
    "data": {
        "count": 1,
        "next": "NULL",
        "results": [
            {
                "Id": 27006,
                "SpeciesName": ["Aedes aegypti"],
                "Title": "Changing dynamics of Aedes aegypti invasion and vector-borne disease risk for rural communities in the Peruvian Amazon",
                "Years": ["2023"],
                "CollectionMethods": ["PROKOPACK aspirator"],
                "Collections": 4344,
                "row_count": 2,
                "ContactName": "Kara Fikrig",
                "doi": "10.1101/2024.09.04.611168",
                "citation": "Fikrig K et al. 2024. Changing dynamics of Aedes aegypti invasion.",
            }
        ],
    }
}

DATASET_27006_PAGE_1 = {
    "count": 2,
    "digitized_from_graph": False,
    "consistent_data": {
        "doi": "10.1101/2024.09.04.611168",
        "title": "Changing dynamics of Aedes aegypti invasion and vector-borne disease risk for rural communities in the Peruvian Amazon",
        "species": "Aedes aegypti",
        "citation": "Fikrig K et al. 2024. Changing dynamics of Aedes aegypti invasion.",
        "datasetid": 27006,
        "sample_unit": "count",
        "sample_stage": "adult",
        "sampling_method": "prokopak aspirator",
        "species_id_method": "morphological examination",
    },
    "results": [
        {
            "sample_start_date": "2023-06-20",
            "sample_start_time": "13:59:00",
            "sample_end_date": "2023-06-20",
            "sample_value": "1.0",
            "sample_sex": "female",
            "sample_lat_dd": "-4.013491376",
            "sample_long_dd": "-73.43223028",
            "additional_location_info": "larval habitat with live larvae present at the property",
            "additional_sample_info": "unfed",
            "sample_name": "13FE006",
            "location_description": "13 de Febrero",
            "linked_assay_id": "A-1",
        },
        {
            "species": "Culex quinquefasciatus",
            "sample_start_date": "2023-06-20",
            "sample_value": "9.0",
        },
    ],
}

DATASET_220_PAGE_1 = {
    "count": 2,
    "consistent_data": {
        "title": "2021-2022 Mosquito Surveillance, Hernando Florida",
        "datasetid": 220,
        "sample_unit": "count",
        "sampling_method": "CDC light trap",
        "citation": "VectorByte VecDyn dataset 220.",
    },
    "results": [
        {
            "species": "Aedes aegypti",
            "sample_start_date": "2021-08-01",
            "sample_value": "3",
            "sample_stage": "adult",
            "sample_sex": "female",
            "sample_lat_dd": "28.5",
            "sample_long_dd": "-82.5",
            "location_description": "Hernando County",
        },
        {
            "species": "Aedes albopictus",
            "sample_start_date": "2021-08-01",
            "sample_value": "7",
        },
    ],
}


class VectorByteAbundanceSourceTests(unittest.TestCase):
    def test_fetch_vectorbyte_abundance_records_indexes_dataset_and_aedes_rows(self):
        calls = []

        def fake_fetch_json(url):
            calls.append(url)
            if "vecdynbyprovider" in url:
                return SEARCH_PAYLOAD
            if "vecdyncsv" in url and "piids=27006" in url:
                return DATASET_27006_PAGE_1
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_vectorbyte_abundance_records(
                raw_dir=Path(tmpdir) / "raw" / "vectorbyte_abundance",
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-26T00:00:00Z",
                dataset_limit=1,
                row_limit=100,
            )

        self.assertEqual(result.source_id, "aedes_vectorbyte_abundance")
        self.assertEqual(result.gaps, [])
        self.assertEqual(len(result.records), 2)
        self.assertEqual(len(result.raw_artifacts), 2)
        self.assertEqual(len(calls), 2)
        dataset = next(record for record in result.records if record.record_id == "vectorbyte:abundance-dataset:27006")
        self.assertEqual(dataset.lane, "ecology")
        self.assertIn("Rows exposed by VecDyn metadata: 2", dataset.text)
        sample = next(record for record in result.records if record.record_id.startswith("vectorbyte:abundance:27006:"))
        self.assertEqual(sample.lane, "observations")
        self.assertEqual(sample.source, "aedes_vectorbyte_abundance")
        self.assertEqual(sample.species, "Aedes aegypti")
        self.assertIn("Sample value: 1.0 count", sample.text)
        self.assertIn("prokopak aspirator", sample.text)
        self.assertEqual(sample.payload["sample_value"], 1.0)
        self.assertEqual(sample.payload["latitude"], -4.013491376)
        self.assertEqual(sample.payload["longitude"], -73.43223028)
        self.assertEqual(sample.provenance.source_id, "aedes_vectorbyte_abundance")
        self.assertIn("raw/vectorbyte_abundance", sample.provenance.locator)

    def test_fetch_vectorbyte_abundance_records_records_gaps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty = fetch_vectorbyte_abundance_records(
                raw_dir=Path(tmpdir) / "raw-empty",
                fetch_json=lambda url: {"data": {"count": 0, "results": []}},
                retrieved_at="2026-05-26T00:00:00Z",
            )

        self.assertFalse(empty.records)
        self.assertIn("vectorbyte_abundance_no_aedes_datasets", {gap["reason"] for gap in empty.gaps})

        def fake_failure(url):
            if "vecdynbyprovider" in url:
                return SEARCH_PAYLOAD
            raise RuntimeError("offline")

        with tempfile.TemporaryDirectory() as tmpdir:
            failed = fetch_vectorbyte_abundance_records(
                raw_dir=Path(tmpdir) / "raw-failed",
                fetch_json=fake_failure,
                retrieved_at="2026-05-26T00:00:00Z",
                dataset_limit=1,
            )

        self.assertIn("vectorbyte_abundance_dataset_page_fetch_failed", {gap["reason"] for gap in failed.gaps})

    def test_fetch_vectorbyte_abundance_records_accepts_explicit_dataset_ids(self):
        calls = []

        def fake_fetch_json(url):
            calls.append(url)
            if "vecdynbyprovider" in url:
                raise AssertionError(f"dataset-id mode should not search metadata: {url}")
            if "vecdyncsv" in url and "piids=27006" in url:
                return DATASET_27006_PAGE_1
            if "vecdyncsv" in url and "piids=220" in url:
                return DATASET_220_PAGE_1
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_vectorbyte_abundance_records(
                raw_dir=Path(tmpdir) / "raw" / "vectorbyte_abundance",
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-26T00:00:00Z",
                dataset_ids=["27006", "220"],
                row_limit=100,
                dataset_page_limit=1,
            )

        self.assertEqual(result.gaps, [])
        self.assertEqual(len(calls), 2)
        dataset_ids = {record.payload.get("dataset_id") for record in result.records if record.payload.get("atom_type") == "vecdyn_dataset"}
        self.assertEqual(dataset_ids, {"27006", "220"})
        samples = [record for record in result.records if record.payload.get("atom_type") == "vecdyn_abundance_sample"]
        self.assertEqual(len(samples), 2)
        self.assertIn("2021-2022 Mosquito Surveillance, Hernando Florida", next(record.text for record in result.records if record.record_id == "vectorbyte:abundance-dataset:220"))


if __name__ == "__main__":
    unittest.main()
