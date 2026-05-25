import tempfile
import unittest
from pathlib import Path

from askinsects.sources.uniprot_proteins import fetch_uniprot_protein_records


UNIPROTKB_PAYLOAD = {
    "results": [
        {
            "entryType": "UniProtKB reviewed (Swiss-Prot)",
            "primaryAccession": "A0A6I8TCE0",
            "uniProtkbId": "PTP1_AEDAE",
            "proteinDescription": {"recommendedName": {"fullName": {"value": "Putative salivary protein 1"}}},
            "genes": [{"geneName": {"value": "ptp1"}}],
            "organism": {"scientificName": "Aedes aegypti", "taxonId": 7159},
            "comments": [{"commentType": "FUNCTION", "texts": [{"value": "May function during blood feeding."}]}],
            "uniProtKBCrossReferences": [
                {"database": "VectorBase", "id": "AAEL012345"},
                {"database": "GO", "id": "GO:0005576"},
            ],
            "keywords": [{"name": "Secreted"}],
        }
    ]
}

PROTEOME_PAYLOAD = {
    "results": [
        {
            "id": "UP000008820",
            "description": "Aedes aegypti reference proteome",
            "taxonomy": {"taxonId": 7159, "scientificName": "Aedes aegypti"},
            "proteinCount": 28317,
        }
    ]
}


class UniProtProteinSourceTests(unittest.TestCase):
    def test_fetch_uniprot_protein_records_indexes_proteome_and_protein_atoms(self):
        def fake_fetch_json(url):
            if "/uniprotkb/search" in url:
                return UNIPROTKB_PAYLOAD
            if "/proteomes/search" in url:
                return PROTEOME_PAYLOAD
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_uniprot_protein_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-24T00:00:00Z",
                protein_limit=25,
                proteome_limit=5,
            )
            self.assertTrue(Path(result.raw_artifacts[0]).exists())

        self.assertEqual(result.source_id, "aedes_uniprot_proteins")
        self.assertEqual(result.gaps, [])
        record_ids = {record.record_id for record in result.records}
        self.assertIn("uniprot:protein:A0A6I8TCE0", record_ids)
        self.assertIn("uniprot:proteome:UP000008820", record_ids)
        protein = next(record for record in result.records if record.record_id == "uniprot:protein:A0A6I8TCE0")
        self.assertEqual(protein.lane, "proteins")
        self.assertEqual(protein.source, "aedes_uniprot_proteins")
        self.assertIn("AAEL012345", protein.text)
        self.assertIn("blood feeding", protein.text)
        self.assertEqual(protein.payload["accession"], "A0A6I8TCE0")

    def test_fetch_uniprot_protein_records_reports_fetch_gaps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_uniprot_protein_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-24T00:00:00Z",
            )

        self.assertFalse(result.records)
        self.assertEqual({gap["reason"] for gap in result.gaps}, {"uniprot_proteins_fetch_failed", "uniprot_proteome_fetch_failed"})


if __name__ == "__main__":
    unittest.main()
