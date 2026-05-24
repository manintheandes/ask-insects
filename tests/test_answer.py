import tempfile
import unittest
from pathlib import Path

from askinsects.answer import answer_question
from askinsects.builder import build_fixture_index, build_source_index
from askinsects.index import SourceIndex
from askinsects.planner import plan_question
from askinsects.records import EvidenceRecord, Provenance
from tests.test_ncbi_genome_source import write_fake_ncbi_package
from tests.test_neurobiology_source import write_fake_neurobiology_artifacts


def fake_inaturalist_fetcher(url):
    return {
        "total_results": 1,
        "results": [
            {
                "id": 12345,
                "uri": "https://www.inaturalist.org/observations/12345",
                "observed_on": "2021-02-03",
                "place_guess": "Rio de Janeiro, Brazil",
                "license_code": "cc-by",
                "taxon": {"name": "Aedes aegypti"},
                "photos": [
                    {
                        "id": 99,
                        "url": "https://static.inaturalist.org/photos/1/medium.jpg",
                        "license_code": "cc-by",
                    }
                ],
            }
        ],
    }


def fake_literature_fetcher(url):
    if "/topics" in url:
        return {"results": []}
    if "esearch.fcgi" in url:
        return {"esearchresult": {"idlist": []}}
    if "api.unpaywall.org" in url:
        return {"doi": "10.1000/wolbachia-aedes", "is_oa": False, "best_oa_location": None}
    if "/works" in url:
        return {
            "meta": {"count": 1, "next_cursor": None},
            "results": [
                {
                    "id": "https://openalex.org/WANSWER",
                    "doi": "https://doi.org/10.1000/wolbachia-aedes",
                    "display_name": "Wolbachia and Aedes aegypti vector control",
                    "publication_date": "2024-03-01",
                    "type": "article",
                    "abstract_inverted_index": {
                        "Wolbachia": [0],
                        "interventions": [1],
                        "in": [2],
                        "Aedes": [3],
                        "aegypti": [4],
                    },
                    "primary_location": {"source": {"display_name": "Journal of Vector Biology"}},
                    "ids": {
                        "openalex": "https://openalex.org/WANSWER",
                        "doi": "https://doi.org/10.1000/wolbachia-aedes",
                    },
                }
            ],
        }
    raise AssertionError(f"unexpected URL: {url}")


def fake_non_wolbachia_literature_fetcher(url):
    if "/topics" in url:
        return {"results": []}
    if "esearch.fcgi" in url:
        return {"esearchresult": {"idlist": []}}
    if "api.unpaywall.org" in url:
        return {"doi": "10.1000/aedes-larval", "is_oa": False, "best_oa_location": None}
    if "/works" in url:
        return {
            "meta": {"count": 1, "next_cursor": None},
            "results": [
                {
                    "id": "https://openalex.org/WNOwol",
                    "doi": "https://doi.org/10.1000/aedes-larval",
                    "display_name": "Aedes aegypti larval ecology",
                    "publication_date": "2024-03-01",
                    "type": "article",
                    "abstract_inverted_index": {
                        "Aedes": [0],
                        "aegypti": [1],
                        "larval": [2],
                        "habitat": [3],
                        "ecology": [4],
                    },
                    "primary_location": {"source": {"display_name": "Journal of Vector Biology"}},
                    "ids": {
                        "openalex": "https://openalex.org/WNOwol",
                        "doi": "https://doi.org/10.1000/aedes-larval",
                    },
                }
            ],
        }
    raise AssertionError(f"unexpected URL: {url}")


def literature_record(record_id, title, text):
    return EvidenceRecord(
        record_id=record_id,
        lane="literature",
        source="aedes_literature_openalex",
        title=title,
        text=text,
        species="Aedes aegypti",
        url=None,
        media_url=None,
        provenance=Provenance(
            source_id="aedes_literature_openalex",
            locator=f"test#{record_id}",
            retrieved_at="2026-05-23T00:00:00Z",
            license="OpenAlex metadata",
        ),
    )


class AnswerTests(unittest.TestCase):
    def test_planner_routes_identity_evidence_action_and_gap(self):
        self.assertEqual(plan_question("what do we know about Aedes aegypti?").answer_shape, "identity")
        self.assertEqual(plan_question("show mosquito observations with images in Brazil").answer_shape, "evidence")
        self.assertEqual(plan_question("what should a scientist inspect next for Culex pipiens?").answer_shape, "action")
        self.assertEqual(plan_question("show mosquito videos from Brazil").answer_shape, "media")
        self.assertEqual(plan_question("what papers discuss mosquito host seeking?").lanes[0], "literature")
        self.assertEqual(plan_question("what neuron data exists for the Aedes aegypti brain?").answer_shape, "neurobiology")
        self.assertEqual(plan_question("what brain regions process smell in mosquitoes?").lanes[0], "neurobiology")
        self.assertEqual(plan_question("what H5AD data exists in the Mosquito Cell Atlas?").lanes[0], "neurobiology")

    def test_answers_include_provenance_or_gap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            identity = answer_question("what do we know about Aedes aegypti?", artifact_dir=artifact_dir)
            self.assertTrue(identity["ok"])
            self.assertEqual(identity["answer_shape"], "identity")
            self.assertTrue(identity["evidence"])
            self.assertIn("provenance", identity["evidence"][0])

            action = answer_question("what should a scientist inspect next for Culex pipiens?", artifact_dir=artifact_dir)
            self.assertTrue(action["ok"])
            self.assertEqual(action["answer_shape"], "action")
            self.assertTrue(action["evidence"])

            media_gap = answer_question("show mosquito videos from Brazil", artifact_dir=artifact_dir)
            self.assertFalse(media_gap["ok"])
            self.assertEqual(media_gap["source_gap"]["lane"], "media")

    def test_literature_questions_prefer_paper_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            answer = answer_question("what papers discuss mosquito host seeking?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["record_id"], "paper:aedes_host_seeking")

    def test_literature_questions_gap_without_literature_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            answer = answer_question("what papers discuss Culex pipiens?", artifact_dir=artifact_dir)

            self.assertFalse(answer["ok"])
            self.assertEqual(answer["source_gap"]["lane"], "literature")

    def test_species_specific_literature_requires_species_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            answer = answer_question("what papers discuss Culex pipiens host seeking?", artifact_dir=artifact_dir)

            self.assertFalse(answer["ok"])
            self.assertEqual(answer["source_gap"]["lane"], "literature")

    def test_literature_question_uses_openalex_source_lane(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "aedes-literature"
            build_source_index(
                include_fixtures=False,
                include_gbif=False,
                include_inaturalist=False,
                include_literature=True,
                artifact_dir=artifact_dir,
                literature_species="Aedes aegypti",
                literature_from_date="2020-01-01",
                literature_to_date="2026-05-23",
                literature_work_type="article",
                include_topic_discovery=True,
                literature_page_size=25,
                literature_delay_seconds=0,
                literature_max_works=1,
                literature_fetch_json=fake_literature_fetcher,
                unpaywall_email="test@example.com",
                retrieved_at="2026-05-23T00:00:00Z",
            )

            payload = answer_question(
                "what papers since 2020 discuss Wolbachia and Aedes aegypti?",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["answer_shape"], "literature")
            self.assertTrue(payload["evidence"])
            self.assertEqual(payload["evidence"][0]["source"], "aedes_literature_openalex")
            self.assertIn("From the Ask Insects literature index", payload["answer"])

    def test_literature_species_fallback_requires_topical_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "aedes-literature"
            build_source_index(
                include_fixtures=False,
                include_gbif=False,
                include_inaturalist=False,
                include_literature=True,
                artifact_dir=artifact_dir,
                literature_species="Aedes aegypti",
                literature_from_date="2020-01-01",
                literature_to_date="2026-05-23",
                literature_work_type="article",
                include_topic_discovery=True,
                literature_page_size=25,
                literature_delay_seconds=0,
                literature_max_works=1,
                literature_fetch_json=fake_non_wolbachia_literature_fetcher,
                unpaywall_email="test@example.com",
                retrieved_at="2026-05-23T00:00:00Z",
            )

            payload = answer_question(
                "what papers since 2020 discuss Wolbachia and Aedes aegypti?",
                artifact_dir=artifact_dir,
            )

            self.assertFalse(payload["ok"])
            self.assertEqual(payload["answer_shape"], "literature")
            self.assertEqual(payload["source_gap"]["lane"], "literature")

    def test_literature_question_uses_topical_query_before_species_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "aedes-literature"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    literature_record(
                        "openalex:non_wolbachia",
                        "Aedes aegypti Aedes aegypti larval ecology",
                        "Aedes aegypti habitat monitoring without symbiont intervention.",
                    ),
                    literature_record(
                        "openalex:wolbachia",
                        "Wolbachia and Aedes aegypti vector control",
                        "Wolbachia interventions in Aedes aegypti populations.",
                    ),
                ]
            )

            payload = answer_question(
                "what papers since 2020 discuss Wolbachia and Aedes aegypti?",
                artifact_dir=artifact_dir,
                limit=1,
            )

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["evidence"][0]["record_id"], "openalex:wolbachia")

    def test_missing_index_returns_source_gap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "empty-mosquito-v1"

            answer = answer_question("what do we know about Aedes aegypti?", artifact_dir=artifact_dir)

            self.assertFalse(answer["ok"])
            self.assertIsNotNone(answer["source_gap"])

    def test_image_questions_use_inaturalist_media_when_available(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_source_index(
                include_fixtures=True,
                include_gbif=False,
                include_inaturalist=True,
                artifact_dir=artifact_dir,
                inaturalist_species=["Aedes aegypti"],
                inaturalist_place="Brazil",
                observation_limit=1,
                inaturalist_fetch_json=fake_inaturalist_fetcher,
                retrieved_at="2026-05-23T00:00:00Z",
            )

            answer = answer_question("show mosquito observations with images in Brazil", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertTrue(any(item["lane"] == "media" for item in answer["evidence"]))
            self.assertTrue(any(item["source"] == "inaturalist_api" for item in answer["evidence"]))

    def test_video_questions_still_gap_with_only_still_images(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_source_index(
                include_fixtures=True,
                include_gbif=False,
                include_inaturalist=True,
                artifact_dir=artifact_dir,
                inaturalist_species=["Aedes aegypti"],
                inaturalist_place="Brazil",
                observation_limit=1,
                inaturalist_fetch_json=fake_inaturalist_fetcher,
                retrieved_at="2026-05-23T00:00:00Z",
            )

            answer = answer_question("show mosquito videos from Brazil", artifact_dir=artifact_dir)

            self.assertFalse(answer["ok"])
            self.assertEqual(answer["source_gap"]["lane"], "media")

    def test_genomics_questions_prefer_genome_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            artifact_dir = tmp_path / "mosquito-v1"
            package_dir = write_fake_ncbi_package(tmp_path)
            build_source_index(
                include_fixtures=True,
                include_gbif=False,
                include_inaturalist=False,
                include_ncbi_genome=True,
                artifact_dir=artifact_dir,
                genome_package_dir=package_dir,
                retrieved_at="2026-05-23T00:00:00Z",
            )

            answer = answer_question("show odorant receptor genes in Aedes aegypti", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["source"], "ncbi_datasets_genome")
            self.assertIn(answer["evidence"][0]["lane"], {"genes", "transcripts", "genome_features", "proteins"})

    def test_neurobiology_questions_prefer_brain_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_source_index(
                include_fixtures=True,
                include_gbif=False,
                include_inaturalist=False,
                include_ncbi_genome=False,
                include_neurobiology=True,
                artifact_dir=artifact_dir,
                retrieved_at="2026-05-23T00:00:00Z",
            )

            answer = answer_question("what neuron data exists for the Aedes aegypti brain?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "neurobiology")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_neurobiology_sources")
            self.assertEqual(answer["evidence"][0]["lane"], "neurobiology")
            self.assertIn("brain", answer["answer"].lower())

    def test_connectome_questions_prefer_source_gap_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            artifact_dir = tmp_path / "mosquito-v1"
            neurobiology_artifact_dir = write_fake_neurobiology_artifacts(tmp_path)
            build_source_index(
                include_fixtures=True,
                include_gbif=False,
                include_inaturalist=False,
                include_ncbi_genome=False,
                include_neurobiology=True,
                artifact_dir=artifact_dir,
                neurobiology_artifact_dir=neurobiology_artifact_dir,
                retrieved_at="2026-05-23T00:00:00Z",
            )

            answer = answer_question("is there a complete Aedes aegypti brain connectome?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["record_id"], "neuro:connectome:wellcome:source-gap")

    def test_h5ad_questions_use_neurobiology_artifact_inventory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            artifact_dir = tmp_path / "mosquito-v1"
            neurobiology_artifact_dir = write_fake_neurobiology_artifacts(tmp_path)
            build_source_index(
                include_fixtures=True,
                include_gbif=False,
                include_inaturalist=False,
                include_ncbi_genome=False,
                include_neurobiology=True,
                artifact_dir=artifact_dir,
                neurobiology_artifact_dir=neurobiology_artifact_dir,
                retrieved_at="2026-05-23T00:00:00Z",
            )

            answer = answer_question("what H5AD data exists in the Mosquito Cell Atlas?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "neurobiology")
            self.assertTrue(any("H5AD" in item["title"] or "h5ad" in item["text"].lower() for item in answer["evidence"]))


if __name__ == "__main__":
    unittest.main()
