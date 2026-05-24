import tempfile
import unittest
from pathlib import Path

from askinsects.answer import answer_question
from askinsects.builder import build_fixture_index, build_source_index
from askinsects.index import SourceIndex
from askinsects.planner import plan_question
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.literature import FullTextUnit
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


def barcode_record(record_id, marker):
    return EvidenceRecord(
        record_id=record_id,
        lane="dna_barcodes",
        source="bold_api",
        title=f"BOLD DNA barcode {record_id} for Aedes aegypti",
        text=(
            f"BOLD barcode specimen {record_id} identifies Aedes aegypti. "
            f"Marker: {marker}. Country/province: Honduras. Collection date: unknown date."
        ),
        species="Aedes aegypti",
        url=f"https://portal.boldsystems.org/record/{record_id}",
        media_url=None,
        provenance=Provenance(
            source_id="bold_api",
            locator=f"test#{record_id}",
            retrieved_at="2026-05-24T00:00:00Z",
            license="BOLD public data",
        ),
    )


def resistance_record(record_id, source):
    return EvidenceRecord(
        record_id=record_id,
        lane="resistance",
        source=source,
        title=f"Aedes aegypti resistance record from {source}",
        text="Aedes aegypti insecticide resistance pyrethroid deltamethrin confirmed resistance Brazil.",
        species="Aedes aegypti",
        url="https://example.org/resistance",
        media_url=None,
        provenance=Provenance(
            source_id=source,
            locator=f"test#{record_id}",
            retrieved_at="2026-05-24T00:00:00Z",
            license="test",
        ),
    )


def public_health_record(record_id, source, text):
    return EvidenceRecord(
        record_id=record_id,
        lane="public_health",
        source=source,
        title=f"Aedes aegypti public health record from {source}",
        text=text,
        species="Aedes aegypti",
        url="https://example.org/public-health",
        media_url=None,
        provenance=Provenance(
            source_id=source,
            locator=f"test#{record_id}",
            retrieved_at="2026-05-24T00:00:00Z",
            license="test",
        ),
    )


class AnswerTests(unittest.TestCase):
    def test_planner_routes_identity_evidence_action_and_gap(self):
        self.assertEqual(plan_question("what do we know about Aedes aegypti?").answer_shape, "identity")
        self.assertEqual(plan_question("show mosquito observations with images in Brazil").answer_shape, "evidence")
        self.assertEqual(plan_question("what should a scientist inspect next for Culex pipiens?").answer_shape, "action")
        self.assertEqual(plan_question("show mosquito videos from Brazil").answer_shape, "media")
        self.assertEqual(plan_question("what insecticide resistance data exists for Aedes aegypti?").answer_shape, "resistance")
        self.assertEqual(plan_question("what vector competence data exists for dengue?").answer_shape, "vector_competence")
        self.assertEqual(plan_question("what host seeking behavior data exists for Aedes aegypti?").answer_shape, "behavior")
        self.assertEqual(plan_question("show BOLD COI barcode records for Aedes aegypti").lanes[0], "dna_barcodes")
        self.assertEqual(plan_question("what papers discuss mosquito host seeking?").lanes[0], "literature")
        self.assertEqual(plan_question("what neuron data exists for the Aedes aegypti brain?").answer_shape, "neurobiology")
        self.assertEqual(plan_question("what brain regions process smell in mosquitoes?").lanes[0], "neurobiology")
        self.assertEqual(plan_question("what H5AD data exists in the Mosquito Cell Atlas?").lanes[0], "neurobiology")
        self.assertEqual(plan_question("what SRA raw reads exist for GSE160740?").lanes[0], "neurobiology")
        self.assertEqual(plan_question("what voxel volume files exist in MosquitoBrains?").lanes[0], "neurobiology")

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

    def test_literature_question_falls_back_to_legal_fulltext_units(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "aedes-literature"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            provenance = Provenance(
                source_id="aedes_literature_openalex",
                locator="raw/literature/page.json#WFT",
                retrieved_at="2026-05-23T00:00:00Z",
                license="CC BY",
                source_url="https://example.org/paper",
            )
            index.upsert_records_and_fulltext_units(
                [
                    literature_record(
                        "openalex:WFT",
                        "Aedes aegypti symbiont study",
                        "Aedes aegypti paper metadata without the topical term.",
                    )
                ],
                [
                    FullTextUnit(
                        unit_id="openalex:WFT:fulltext:0",
                        record_id="openalex:WFT",
                        source="aedes_literature_openalex",
                        unit_index=0,
                        text="The legal open full text reports microbiota changes in Aedes aegypti larvae.",
                        url="https://example.org/fulltext",
                        license="CC BY",
                        provenance=provenance,
                    )
                ],
            )

            payload = answer_question(
                "what papers since 2020 discuss microbiota and Aedes aegypti?",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["answer_shape"], "literature")
            self.assertEqual(payload["evidence"][0]["lane"], "literature_fulltext")
            self.assertIn("microbiota", payload["evidence"][0]["text"])

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

    def test_mosquito_alert_image_questions_use_media_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="inat:media:1",
                        lane="media",
                        source="inaturalist_api",
                        title="Aedes aegypti iNaturalist still image 1",
                        text="iNaturalist still image for Aedes aegypti from Brazil.",
                        species="Aedes aegypti",
                        url="https://www.inaturalist.org/observations/1",
                        media_url="https://static.inaturalist.org/photos/1/medium.jpg",
                        provenance=Provenance(
                            source_id="inaturalist_api",
                            locator="raw/inaturalist/page.json#observations/1/photos/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="cc0",
                            source_url="https://www.inaturalist.org/observations/1",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="mosquito_alert:media:4909387174:example",
                        lane="media",
                        source="mosquito_alert_gbif",
                        title="Aedes aegypti Mosquito Alert still image 4909387174",
                        text="Mosquito Alert still image for Aedes aegypti from citizen-science observation in Brazil.",
                        species="Aedes aegypti",
                        url="https://www.gbif.org/occurrence/4909387174",
                        media_url="http://webserver.mosquitoalert.com/media/tigapics/example.jpg",
                        provenance=Provenance(
                            source_id="mosquito_alert_gbif",
                            locator="raw/mosquito_alert/aedes_aegypti_occurrences_offset_000000.json#occurrence/4909387174/media/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="Anonymous, CC by Mosquito Alert",
                            source_url="http://webserver.mosquitoalert.com/media/tigapics/example.jpg",
                        ),
                    )
                ]
            )

            answer = answer_question("show Mosquito Alert Aedes aegypti images from Brazil", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["source"], "mosquito_alert_gbif")
            self.assertEqual(answer["evidence"][0]["lane"], "media")

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

    def test_video_questions_use_pmc_video_media_when_available(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="pmc:video:PMC1:video1.mp4",
                        lane="media",
                        source="pmc_open_access_videos",
                        title="Aedes aegypti PMC supplementary video video1.mp4",
                        text="PMC open-access supplementary video for Aedes aegypti behavior.",
                        species="Aedes aegypti",
                        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC1/",
                        media_url="https://pmc.ncbi.nlm.nih.gov/articles/instance/1/bin/video1.mp4",
                        provenance=Provenance(
                            source_id="pmc_open_access_videos",
                            locator="raw/pmc_videos/PMC1.html#video/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC BY",
                            source_url="https://pmc.ncbi.nlm.nih.gov/articles/PMC1/",
                        ),
                    )
                ]
            )

            answer = answer_question("show mosquito videos", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "media")
            self.assertEqual(answer["evidence"][0]["source"], "pmc_open_access_videos")

    def test_dryad_video_questions_prefer_dryad_behavior_video_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="pmc:video:PMC1:video1.mp4",
                        lane="media",
                        source="pmc_open_access_videos",
                        title="Aedes aegypti PMC supplementary video video1.mp4",
                        text="PMC open-access supplementary video for Aedes aegypti behavior.",
                        species="Aedes aegypti",
                        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC1/",
                        media_url="https://pmc.ncbi.nlm.nih.gov/articles/instance/1/bin/video1.mp4",
                        provenance=Provenance(
                            source_id="pmc_open_access_videos",
                            locator="raw/pmc_videos/PMC1.html#video/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC BY",
                            source_url="https://pmc.ncbi.nlm.nih.gov/articles/PMC1/",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="dryad:file:10_5061_dryad_example:host_seeking_videos_zip",
                        lane="media",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti Dryad video/archive file host_seeking_videos.zip",
                        text="Dryad video archive for Aedes aegypti host seeking behavior.",
                        species="Aedes aegypti",
                        url="https://datadryad.org/dataset/doi%3A10.5061%2Fdryad.example",
                        media_url="https://datadryad.org/api/v2/files/10/download",
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad_behavior_videos/files.json#file/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC0",
                            source_url="https://datadryad.org/api/v2/files/10/download",
                        ),
                    ),
                ]
            )

            answer = answer_question("show Dryad Aedes aegypti behavior videos", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "media")
            self.assertEqual(answer["evidence"][0]["source"], "dryad_aedes_behavior_videos")

    def test_pathogen_questions_prefer_taxonomy_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="facet:vector:1",
                        lane="vector_competence",
                        source="aedes_literature_facets",
                        title="Aedes aegypti vector competence Zika literature facet",
                        text="Aedes aegypti vector competence literature facet mentions Zika virus.",
                        species="Aedes aegypti",
                        url="https://example.org/paper",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_literature_facets",
                            locator="literature#facet/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="test",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="pathogen:ncbi_taxonomy:59301",
                        lane="vector_competence",
                        source="aedes_pathogen_taxonomy",
                        title="Aedes aegypti pathogen taxonomy Mayaro virus",
                        text="NCBI Taxonomy pathogen record for Mayaro virus (taxid 59301).",
                        species="Aedes aegypti",
                        url="https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=59301",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_pathogen_taxonomy",
                            locator="raw/pathogen_taxonomy/esummary.json#taxonomy/59301",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="NCBI Taxonomy public data",
                            source_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="pathogen:ncbi_taxonomy:64320",
                        lane="vector_competence",
                        source="aedes_pathogen_taxonomy",
                        title="Aedes aegypti pathogen taxonomy Zika virus",
                        text="NCBI Taxonomy pathogen record for Zika virus (taxid 64320).",
                        species="Aedes aegypti",
                        url="https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=64320",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_pathogen_taxonomy",
                            locator="raw/pathogen_taxonomy/esummary.json#taxonomy/64320",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="NCBI Taxonomy public data",
                            source_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                        ),
                    ),
                ]
            )

            answer = answer_question("show Zika pathogen taxonomy for Aedes aegypti", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "vector_competence")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_pathogen_taxonomy")
            self.assertEqual(answer["evidence"][0]["record_id"], "pathogen:ncbi_taxonomy:64320")

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

    def test_coi_barcode_questions_prefer_coi_marker_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    barcode_record("GBFSB7979-24", "ITS2"),
                    barcode_record("GBAAW12253-24", "COI-5P"),
                ]
            )

            answer = answer_question("show BOLD COI barcode records for Aedes aegypti", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["record_id"], "GBAAW12253-24")
            self.assertIn("Marker: COI-5P", answer["evidence"][0]["text"])

    def test_resistance_questions_prefer_dedicated_irmapper_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    resistance_record("facet:resistance:1", "aedes_literature_facets"),
                    resistance_record("irmapper:aedes:1", "irmapper_aedes"),
                ]
            )

            answer = answer_question("what insecticide resistance data exists for Aedes aegypti?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "resistance")
            self.assertEqual(answer["evidence"][0]["source"], "irmapper_aedes")

    def test_guidance_questions_prefer_official_public_health_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    public_health_record(
                        "facet:public-health:1",
                        "aedes_literature_facets",
                        "Aedes aegypti dengue vector control literature facet.",
                    ),
                    public_health_record(
                        "public_health:guidance:cdc",
                        "aedes_public_health_guidance",
                        "Official public-health guidance for Aedes aegypti vector control from CDC.",
                    ),
                ]
            )

            answer = answer_question("what vector control guidance exists for Aedes aegypti?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "public_health")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_public_health_guidance")

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

    def test_public_catmaid_questions_prefer_indexed_em_records(self):
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

            answer = answer_question("what public CATMAID EM data exists for Aedes aegypti?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["record_id"], "neuro:connectome:catmaid:project:1")

    def test_catmaid_skeleton_export_questions_prefer_skeleton_manifest(self):
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

            answer = answer_question("can we bulk download CATMAID skeleton IDs for Aedes aegypti?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["record_id"], "neuro:connectome:catmaid:skeleton-manifest")

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

    def test_sra_and_volume_questions_use_deep_neurobiology_records(self):
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

            sra = answer_question("what SRA raw reads exist for GSE160740?", artifact_dir=artifact_dir)
            sra_workflow = answer_question("what raw SRA reanalysis workflow exists for GSE160740?", artifact_dir=artifact_dir)
            volume = answer_question("what voxel volume files exist in MosquitoBrains?", artifact_dir=artifact_dir)

            self.assertTrue(sra["ok"])
            self.assertTrue(any(item["record_id"].startswith("neuro:sra:SRP290992") for item in sra["evidence"]))
            self.assertTrue(sra_workflow["ok"])
            self.assertEqual(sra_workflow["evidence"][0]["record_id"], "neuro:sra:SRP290992:reanalysis-workflow")
            self.assertTrue(volume["ok"])
            self.assertTrue(any("volume" in item["record_id"] for item in volume["evidence"]))


if __name__ == "__main__":
    unittest.main()
