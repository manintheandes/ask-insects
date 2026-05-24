import tempfile
import unittest
from pathlib import Path

from askinsects.answer import answer_question
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from scripts.build_literature_facets import FACET_SOURCE_ID, build_literature_facets


def literature_record(record_id, title, text):
    return EvidenceRecord(
        record_id=record_id,
        lane="literature",
        source="aedes_literature_openalex",
        title=title,
        text=text,
        species="Aedes aegypti",
        url="https://openalex.org/W1",
        media_url=None,
        provenance=Provenance(
            source_id="aedes_literature_openalex",
            locator=f"records#{record_id}",
            retrieved_at="2026-05-24T00:00:00Z",
            license="OpenAlex metadata",
            source_url="https://openalex.org/W1",
        ),
    )


class LiteratureFacetTests(unittest.TestCase):
    def test_builds_behavior_resistance_vector_ecology_and_public_health_facets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    literature_record(
                        "openalex:behavior",
                        "Aedes aegypti host seeking and oviposition behavior",
                        "Host seeking, carbon dioxide, odor, oviposition, and visual cue assays.",
                    ),
                    literature_record(
                        "openalex:resistance",
                        "Aedes aegypti insecticide resistance",
                        "Pyrethroid resistance, kdr, knockdown resistance, bioassay, and permethrin susceptibility.",
                    ),
                    literature_record(
                        "openalex:vector",
                        "Dengue virus vector competence in mosquitoes",
                        "Vector competence, infection rate, dissemination rate, and transmission rate.",
                    ),
                    literature_record(
                        "openalex:ecology",
                        "Urban mosquito ecology",
                        "Larval habitat, breeding site, rainfall, temperature, distribution, and land use.",
                    ),
                    literature_record(
                        "openalex:public",
                        "Mosquito surveillance and vector control",
                        "Public health surveillance, outbreak response, dengue incidence, intervention, and vector control.",
                    ),
                ]
            )

            result = build_literature_facets(artifact_dir, retrieved_at="2026-05-24T00:00:00Z")

            self.assertEqual(result["source"], FACET_SOURCE_ID)
            self.assertGreaterEqual(result["lane_counts"]["behavior"], 1)
            self.assertGreaterEqual(result["lane_counts"]["resistance"], 1)
            self.assertGreaterEqual(result["lane_counts"]["vector_competence"], 1)
            self.assertGreaterEqual(result["lane_counts"]["ecology"], 1)
            self.assertGreaterEqual(result["lane_counts"]["public_health"], 1)

            for lane in ("behavior", "resistance", "vector_competence", "ecology", "public_health"):
                rows = index.search(lane.replace("_", " "), lane=lane, limit=5)
                self.assertTrue(rows, lane)
                self.assertEqual(rows[0].source, FACET_SOURCE_ID)
                payload_rows = index.sql(
                    f"select payload_json from record_payloads where record_id = '{rows[0].record_id}'"
                )
                self.assertTrue(payload_rows, lane)
                self.assertIn("source_record_id", payload_rows[0]["payload_json"])

    def test_answer_routes_resistance_and_behavior_to_facet_lanes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    literature_record(
                        "openalex:resistance",
                        "Aedes aegypti pyrethroid resistance",
                        "Pyrethroid resistance, kdr mutation, knockdown resistance, and bioassay evidence.",
                    ),
                    literature_record(
                        "openalex:behavior",
                        "Aedes aegypti host seeking",
                        "Host seeking uses carbon dioxide, odor, and visual cue evidence.",
                    ),
                ]
            )
            build_literature_facets(artifact_dir, retrieved_at="2026-05-24T00:00:00Z")

            resistance = answer_question("what insecticide resistance data exists for Aedes aegypti?", artifact_dir)
            behavior = answer_question("what host seeking behavior data exists for Aedes aegypti?", artifact_dir)

            self.assertTrue(resistance["ok"])
            self.assertEqual(resistance["answer_shape"], "resistance")
            self.assertEqual(resistance["evidence"][0]["lane"], "resistance")
            self.assertTrue(behavior["ok"])
            self.assertEqual(behavior["answer_shape"], "behavior")
            self.assertEqual(behavior["evidence"][0]["lane"], "behavior")


if __name__ == "__main__":
    unittest.main()
