import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = REPO_ROOT / "config" / "aedes-source-plane-benchmark.json"
BENCHMARK_DOC_PATH = REPO_ROOT / "docs" / "aedes-source-plane-benchmark.md"

REQUIRED_COMPARATORS = {
    "vectorbase_veupathdb",
    "ncbi_entrez_datasets",
    "gbif",
    "inaturalist",
    "mosquito_alert",
    "vectornet",
    "bold",
    "irmapper",
    "vectorbyte_vectraits",
    "openalex_pubmed_pmc",
    "paho_cdc_public_health",
}


class AedesSourcePlaneBenchmarkTests(unittest.TestCase):
    def load_benchmark(self):
        return json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))

    def test_benchmark_files_exist(self):
        self.assertTrue(BENCHMARK_PATH.is_file())
        self.assertTrue(BENCHMARK_DOC_PATH.is_file())

    def test_benchmark_keeps_world_largest_claim_unproven(self):
        payload = self.load_benchmark()

        self.assertEqual(payload["claim_status"], "not_proven_world_largest")
        self.assertFalse(payload["claim_rules"]["world_largest_claim_allowed"])
        self.assertIn("integrated", payload["recommended_claim"].lower())
        self.assertIn("not a proven world-largest claim", payload["recommended_claim"].lower())

    def test_benchmark_tracks_required_external_comparators(self):
        payload = self.load_benchmark()

        comparators = {source["id"] for source in payload["external_comparators"]}
        self.assertEqual(comparators, REQUIRED_COMPARATORS)
        for source in payload["external_comparators"]:
            self.assertTrue(source["url"], source["id"])
            self.assertTrue(source["benchmark_note"], source["id"])
            self.assertTrue(source["ask_insects_advantage"], source["id"])
            self.assertTrue(source["ask_insects_gap"], source["id"])

    def test_benchmark_records_current_hosted_proof(self):
        payload = self.load_benchmark()
        proof = payload["ask_insects_current"]

        self.assertGreaterEqual(proof["hosted_record_count"], 1415737)
        self.assertGreaterEqual(proof["hosted_trait_records"], 4972)
        self.assertGreaterEqual(proof["hosted_vectorbase_genomics_records"], 872001)
        self.assertGreaterEqual(proof["hosted_video_atom_records"], 46181)
        self.assertGreaterEqual(proof["hosted_video_artifact_records"], 179)
        self.assertGreaterEqual(proof["hosted_video_gap_records"], 330)
        self.assertIn("aedes_vectorbyte_traits", proof["hosted_sources"])
        self.assertIn("vectorbase_aedes_genomics", proof["hosted_sources"])
        self.assertIn("aedes_video_atoms", proof["hosted_sources"])
        self.assertIn("zenodo_aedes_videos", proof["hosted_sources"])
        self.assertIn("figshare_aedes_videos", proof["hosted_sources"])
        self.assertIn("aedes_crossref_literature_audit", proof["hosted_sources"])
        self.assertIn("mosquito_repellent_external_discovery", proof["hosted_sources"])
        self.assertIn("aedes_resistance_table_rows", proof["hosted_sources"])
        self.assertIn("who_malaria_threats_resistance_audit", proof["hosted_sources"])

    def test_benchmark_doc_has_claim_ladder_and_table(self):
        text = BENCHMARK_DOC_PATH.read_text(encoding="utf-8")

        self.assertIn("## Claim Ladder", text)
        self.assertIn("not proven", text.lower())
        self.assertIn("| Source | What It Leads In | Ask Insects Position | Gap |", text)
        self.assertIn("VectorBase", text)
        self.assertIn("VectorByte", text)
        self.assertIn("GBIF", text)


if __name__ == "__main__":
    unittest.main()
