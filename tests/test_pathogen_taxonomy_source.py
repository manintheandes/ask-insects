import tempfile
import unittest
from pathlib import Path

from askinsects.sources.pathogen_taxonomy import PATHOGEN_TAXONOMY_SOURCE_ID, fetch_pathogen_taxonomy_records


def taxonomy_payload():
    return {
        "result": {
            "uids": ["12637", "64320"],
            "12637": {
                "uid": "12637",
                "taxid": 12637,
                "scientificname": "Dengue virus",
                "rank": "isolate",
                "division": "viruses",
                "genbankdivision": "Viruses",
            },
            "64320": {
                "uid": "64320",
                "taxid": 64320,
                "scientificname": "Zika virus",
                "rank": "isolate",
                "division": "viruses",
                "genbankdivision": "Viruses",
            },
        }
    }


class PathogenTaxonomySourceTests(unittest.TestCase):
    def test_fetch_pathogen_taxonomy_records_normalizes_ncbi_summaries(self):
        urls = []

        def fetch_json(url):
            urls.append(url)
            return taxonomy_payload()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_pathogen_taxonomy_records(raw_dir=Path(tmpdir) / "raw", fetch_json=fetch_json, retrieved_at="2026-05-24T00:00:00Z")

            self.assertEqual(result.source_id, PATHOGEN_TAXONOMY_SOURCE_ID)
            self.assertEqual(result.pathogen_count, 2)
            self.assertEqual(len(result.raw_artifacts), 1)
            self.assertIn("esummary.fcgi", urls[0])
            dengue = next(record for record in result.records if "Dengue" in record.title)
            self.assertEqual(dengue.lane, "vector_competence")
            self.assertEqual(dengue.source, PATHOGEN_TAXONOMY_SOURCE_ID)
            self.assertIn("taxid 12637", dengue.text)
            self.assertEqual(dengue.payload["raw_summary"]["scientificname"], "Dengue virus")
            self.assertIn("#taxonomy/12637", dengue.provenance.locator)

    def test_fetch_pathogen_taxonomy_records_records_gap_on_fetch_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_pathogen_taxonomy_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertFalse(result.records)
            self.assertEqual(result.gaps[0]["source"], PATHOGEN_TAXONOMY_SOURCE_ID)
            self.assertEqual(result.gaps[0]["reason"], "ncbi_taxonomy_fetch_failed")


if __name__ == "__main__":
    unittest.main()
