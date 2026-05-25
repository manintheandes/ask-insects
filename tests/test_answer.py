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


def biosample_record(record_id, text):
    return EvidenceRecord(
        record_id=record_id,
        lane="biosamples",
        source="ncbi_biosamples",
        title=f"Aedes aegypti BioSample {record_id}",
        text=text,
        species="Aedes aegypti",
        url="https://www.ncbi.nlm.nih.gov/biosample/SAMN1",
        media_url=None,
        provenance=Provenance(
            source_id="ncbi_biosamples",
            locator=f"raw/ncbi_biosamples/esummary.json#{record_id}",
            retrieved_at="2026-05-24T00:00:00Z",
            license="NCBI BioSample public metadata",
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


def resistance_marker_record(record_id):
    return EvidenceRecord(
        record_id=record_id,
        lane="resistance",
        source="aedes_resistance_markers",
        title="Aedes aegypti resistance marker: V1016G",
        text="Deterministic marker extraction for Aedes aegypti insecticide resistance. Marker: V1016G. Class: target_site. Gene or family: VGSC. Resistance context: kdr, pyrethroid resistance. Insecticide terms: permethrin.",
        species="Aedes aegypti",
        url="https://example.org/resistance-marker",
        media_url=None,
        provenance=Provenance(
            source_id="aedes_resistance_markers",
            locator="records#openalex:WRM1;literature_fulltext_units#openalex:WRM1:fulltext:0",
            retrieved_at="2026-05-24T00:00:00Z",
            license="CC-BY",
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


def expression_record(record_id):
    return EvidenceRecord(
        record_id=record_id,
        lane="expression",
        source="aedes_expression_omics",
        title="GEO expression dataset GSE999999: Aedes aegypti midgut RNA-seq",
        text="GEO Aedes aegypti expression omics dataset GSE999999. Title: Aedes aegypti midgut RNA-seq after dengue exposure. Samples: 12. Summary: infected and control midguts.",
        species="Aedes aegypti",
        url="https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE999999",
        media_url=None,
        provenance=Provenance(
            source_id="aedes_expression_omics",
            locator="raw/expression_omics/gds_esummary.json#result/200000001",
            retrieved_at="2026-05-24T00:00:00Z",
            license="NCBI GEO public metadata",
        ),
    )


def uniprot_record(record_id):
    accession = record_id.rsplit(":", 1)[-1]
    return EvidenceRecord(
        record_id=record_id,
        lane="proteins",
        source="aedes_uniprot_proteins",
        title=f"UniProt protein {accession}: Putative salivary protein 1",
        text=f"UniProt reviewed Aedes aegypti protein record {accession}. Protein: Putative salivary protein 1. Gene names: ptp1. Function: May function during blood feeding. VectorBase cross-references: AAEL012345.",
        species="Aedes aegypti",
        url="https://www.uniprot.org/uniprotkb/A0A6I8TCE0/entry",
        media_url=None,
        provenance=Provenance(
            source_id="aedes_uniprot_proteins",
            locator="raw/uniprot_proteins/uniprotkb_aedes_aegypti.json#results/1",
            retrieved_at="2026-05-24T00:00:00Z",
            license="UniProt public data; CC BY 4.0",
        ),
    )


def trait_record(record_id):
    return EvidenceRecord(
        record_id=record_id,
        lane="traits",
        source="aedes_vectorbyte_traits",
        title="VectorByte trait fecundity rate: dataset 474 row 89092",
        text=(
            "VectorByte VecTraits Aedes aegypti observation for fecundity rate. "
            "Value: 0.0 eggs individual-1 day-1. Temperature: 10.54 Celsius. "
            "Life stage: adult. Sex: female. Location: Marilia Brazil. Citation: Yang et al. 2009."
        ),
        species="Aedes aegypti",
        url="https://doi.org/10.1017/S0950268809002040",
        media_url=None,
        provenance=Provenance(
            source_id="aedes_vectorbyte_traits",
            locator="raw/vectorbyte_traits/vectraits_dataset_474.json#results/89092",
            retrieved_at="2026-05-25T00:00:00Z",
            license="VectorByte/VBD Hub public data; source terms apply",
        ),
    )


def gbif_observation_record(record_id, country):
    return EvidenceRecord(
        record_id=record_id,
        lane="observations",
        source="gbif_api",
        title=f"Aedes aegypti occurrence {record_id}",
        text=f"GBIF occurrence record for Aedes aegypti in {country}, event date 2026-01-18, from iNaturalist research-grade observations.",
        species="Aedes aegypti",
        url="https://www.gbif.org/occurrence/1",
        media_url=None,
        provenance=Provenance(
            source_id="gbif_api",
            locator=f"raw/gbif/page.json#{record_id}",
            retrieved_at="2026-05-24T00:00:00Z",
            license="CC0",
            source_url="https://www.gbif.org/occurrence/1",
        ),
    )


def ecology_record(record_id, source):
    return EvidenceRecord(
        record_id=record_id,
        lane="ecology",
        source=source,
        title=f"Aedes aegypti ecology record from {source}",
        text="Aedes aegypti occurrence ecology range distribution seasonality Brazil January observations.",
        species="Aedes aegypti",
        url="https://example.org/ecology",
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
        self.assertEqual(plan_question("show CYP9J32 metabolic resistance markers in Aedes aegypti").answer_shape, "resistance")
        self.assertEqual(plan_question("what vector competence data exists for dengue?").answer_shape, "vector_competence")
        self.assertEqual(plan_question("what host seeking behavior data exists for Aedes aegypti?").answer_shape, "behavior")
        self.assertEqual(plan_question("what Mendeley table rows mention temperature gradients?").answer_shape, "behavior")
        self.assertEqual(plan_question("show supplement table behavior response rate for Aedes aegypti").answer_shape, "behavior")
        self.assertEqual(plan_question("show BOLD COI barcode records for Aedes aegypti").lanes[0], "dna_barcodes")
        self.assertEqual(plan_question("show Aedes aegypti BioSamples from China").lanes[0], "biosamples")
        self.assertEqual(plan_question("what papers discuss mosquito host seeking?").lanes[0], "literature")
        self.assertEqual(plan_question("what neuron data exists for the Aedes aegypti brain?").answer_shape, "neurobiology")
        self.assertEqual(plan_question("what brain regions process smell in mosquitoes?").lanes[0], "neurobiology")
        self.assertEqual(plan_question("what H5AD data exists in the Mosquito Cell Atlas?").lanes[0], "neurobiology")
        self.assertEqual(plan_question("what SRA raw reads exist for GSE160740?").lanes[0], "neurobiology")
        self.assertEqual(plan_question("what voxel volume files exist in MosquitoBrains?").lanes[0], "neurobiology")
        self.assertEqual(plan_question("where is Aedes aegypti observed by month in Brazil?").answer_shape, "ecology")
        self.assertEqual(plan_question("what range and seasonality evidence exists for Aedes aegypti?").lanes[0], "ecology")
        self.assertEqual(plan_question("show GEO RNA-seq expression data for Aedes aegypti midgut").answer_shape, "expression")
        self.assertEqual(plan_question("show UniProt protein function for AAEL012345").lanes[0], "proteins")
        self.assertEqual(plan_question("show VectorByte temperature trait data for Aedes aegypti fecundity").lanes[0], "traits")
        self.assertEqual(plan_question("show World Mosquito Program Wolbachia intervention evidence from Yogyakarta").answer_shape, "public_health")
        self.assertEqual(plan_question("show CDC ArboNET dengue surveillance current cases").answer_shape, "public_health")

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

    def test_expression_questions_prefer_expression_omics_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records([expression_record("expression:geo:GSE999999")])

            answer = answer_question("show GEO RNA-seq expression data for Aedes aegypti midgut", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "expression")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_expression_omics")

    def test_uniprot_questions_prefer_uniprot_protein_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="vectorbase:protein:AAEL026087-PA",
                        lane="proteins",
                        source="vectorbase_aedes_genomics",
                        title="Aedes aegypti VectorBase protein AAEL026087-PA",
                        text="VectorBase protein annotated as salivary allergen [Source:UniProtKB/Swiss-Prot;Acc:P18153].",
                        species="Aedes aegypti",
                        url="https://vectorbase.org/example",
                        media_url=None,
                        provenance=Provenance(
                            source_id="vectorbase_aedes_genomics",
                            locator="raw/vectorbase_genomics/proteins.fasta#line/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="VectorBase public data",
                        ),
                    ),
                    uniprot_record("uniprot:protein:P18153"),
                ]
            )

            answer = answer_question("show UniProt protein function for P18153", artifact_dir=artifact_dir, limit=1)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_uniprot_proteins")

    def test_uniprot_exact_identifier_questions_gap_without_exact_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records([uniprot_record("uniprot:protein:P18153")])

            answer = answer_question("show UniProt protein function for AAEL999999", artifact_dir=artifact_dir)

            self.assertFalse(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertIn("UniProt lane has no matching record", answer["source_gap"]["reason"])

    def test_wolbachia_questions_prefer_intervention_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    public_health_record(
                        "wolbachia:intervention:yogyakarta",
                        "aedes_wolbachia_interventions",
                        "World Mosquito Program Wolbachia intervention evidence for Aedes aegypti. Topic: Yogyakarta randomized controlled trial. Metrics mentioned: 77%.",
                    ),
                    public_health_record(
                        "public_health:guidance:wolbachia",
                        "aedes_public_health_guidance",
                        "CDC mosquitoes with Wolbachia guidance for Aedes aegypti.",
                    ),
                ]
            )

            answer = answer_question("show World Mosquito Program Wolbachia intervention evidence from Yogyakarta", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "public_health")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_wolbachia_interventions")

    def test_vectorbyte_trait_questions_prefer_trait_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    trait_record("vectorbyte:trait:474:89092"),
                    ecology_record("occurrence_ecology:country:Brazil", "aedes_occurrence_ecology"),
                ]
            )

            answer = answer_question("show VectorByte temperature trait data for Aedes aegypti fecundity", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "traits")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_vectorbyte_traits")
            self.assertEqual(answer["evidence"][0]["lane"], "traits")

    def test_cdc_arbonet_questions_prefer_cdc_surveillance_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    public_health_record(
                        "public_health:surveillance:cdc_dengue:csv:Data_Bites_Current.csv:row:000003:test",
                        "aedes_cdc_dengue_surveillance",
                        "CDC ArboNET dengue surveillance CSV row. Page kind: current_year. Measures: Reported cases: 737. Aedes aegypti relevance.",
                    ),
                    public_health_record(
                        "public_health:guidance:cdc",
                        "aedes_public_health_guidance",
                        "CDC dengue prevention guidance for Aedes aegypti.",
                    ),
                ]
            )

            answer = answer_question("show CDC ArboNET dengue surveillance current cases", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "public_health")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_cdc_dengue_surveillance")

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

    def test_gbif_observation_questions_keep_country_terms_before_species_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    gbif_observation_record("gbif:occurrence:congo", "Congo, Democratic Republic of the"),
                    gbif_observation_record("gbif:occurrence:brazil", "Brazil"),
                ]
            )

            answer = answer_question("show GBIF Aedes aegypti observations in Brazil", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["record_id"], "gbif:occurrence:brazil")
            self.assertIn("Brazil", answer["evidence"][0]["text"])

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

    def test_mendeley_video_questions_prefer_mendeley_behavior_media_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
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
                    EvidenceRecord(
                        record_id="mendeley:file:6gvs94p6r2:v1:file_video",
                        lane="media",
                        source="mendeley_aedes_behavior_media",
                        title="Aedes aegypti Mendeley video/audio/archive file wing-flash-video.mp4",
                        text="Mendeley high-speed video for Aedes aegypti wing flash mate recognition behavior.",
                        species="Aedes aegypti",
                        url="https://data.mendeley.com/datasets/6gvs94p6r2/1",
                        media_url="https://data.mendeley.com/public-files/video/file_downloaded",
                        provenance=Provenance(
                            source_id="mendeley_aedes_behavior_media",
                            locator="raw/mendeley_behavior_media/files.json#files/root/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC BY 4.0",
                            source_url="https://data.mendeley.com/public-files/video/file_downloaded",
                        ),
                    ),
                ]
            )

            answer = answer_question("show Mendeley Aedes aegypti wing flash videos", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "media")
            self.assertEqual(answer["evidence"][0]["source"], "mendeley_aedes_behavior_media")

    def test_osf_flighttrackai_questions_prefer_osf_video_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="mendeley:file:6gvs94p6r2:v1:file_video",
                        lane="media",
                        source="mendeley_aedes_behavior_media",
                        title="Aedes aegypti Mendeley video/audio/archive file wing-flash-video.mp4",
                        text="Mendeley high-speed video for Aedes aegypti wing flash mate recognition behavior.",
                        species="Aedes aegypti",
                        url="https://data.mendeley.com/datasets/6gvs94p6r2/1",
                        media_url="https://data.mendeley.com/public-files/video/file_downloaded",
                        provenance=Provenance(
                            source_id="mendeley_aedes_behavior_media",
                            locator="raw/mendeley_behavior_media/files.json#files/root/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC BY 4.0",
                            source_url="https://data.mendeley.com/public-files/video/file_downloaded",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="osf:flighttrackai:file:video_a",
                        lane="media",
                        source="osf_flighttrackai_aedes_videos",
                        title="Aedes aegypti OSF FlightTrackAI video file Video A.mp4",
                        text="OSF FlightTrackAI video file for Aedes aegypti flight-behavior tracking.",
                        species="Aedes aegypti",
                        url="https://osf.io/cx762/",
                        media_url="https://osf.io/download/pu8zf/",
                        provenance=Provenance(
                            source_id="osf_flighttrackai_aedes_videos",
                            locator="raw/osf_flighttrackai_videos/cx762_folder_processed.json#files/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="OSF project license not supplied",
                            source_url="https://api.osf.io/v2/files/video-a/",
                        ),
                    ),
                ]
            )

            answer = answer_question("show OSF FlightTrackAI Aedes aegypti videos", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "media")
            self.assertEqual(answer["evidence"][0]["source"], "osf_flighttrackai_aedes_videos")

    def test_video_atom_media_questions_prefer_inspectable_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="pmc:video:PMC123:video1.mp4",
                        lane="media",
                        source="pmc_open_access_videos",
                        title="Aedes aegypti PMC supplementary video video1.mp4",
                        text="BiteOscope Aedes aegypti mosquito biting behavior video file.",
                        species="Aedes aegypti",
                        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC123/",
                        media_url="https://example.org/video1.mp4",
                        provenance=Provenance(
                            source_id="pmc_open_access_videos",
                            locator="raw/pmc_videos/PMC123.html#video/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC BY",
                            source_url="https://pmc.ncbi.nlm.nih.gov/articles/PMC123/",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="video_atom:video_keyframe:pmc_video",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video keyframe for BiteOscope",
                        text="Inspectable keyframe derived from an Aedes aegypti video.",
                        species="Aedes aegypti",
                        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC123/",
                        media_url="raw/video_atoms/artifacts/keyframe_000001.jpg",
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="records#pmc:video:PMC123:video1.mp4;raw/video_atoms/artifacts/keyframe_000001.jpg",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC BY",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="video_atom:video_preview_clip:pmc_video",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video preview clip for BiteOscope",
                        text="Inspectable preview clip derived from an Aedes aegypti video.",
                        species="Aedes aegypti",
                        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC123/",
                        media_url="raw/video_atoms/artifacts/preview.mp4",
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="records#pmc:video:PMC123:video1.mp4;raw/video_atoms/artifacts/preview.mp4",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC BY",
                        ),
                    ),
                ]
            )

            answer = answer_question("show Aedes aegypti keyframes and previews", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "media")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_video_atoms")

    def test_video_gap_questions_return_queryable_gap_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="video_atom:gap:pmc_video",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video gap video_probe_failed",
                        text="Aedes aegypti video source gap: video_probe_failed. Source record: pmc:video:PMC123:video1.mp4.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="gaps.json#aedes_video_atoms/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"atom_type": "video_gap"},
                    )
                ]
            )

            answer = answer_question("what Aedes video gaps failed?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "media")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_video_atoms")
            self.assertIn("video_probe_failed", answer["evidence"][0]["text"])

    def test_video_license_gap_questions_prefer_source_hash_gaps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="video_atom:gap:osf:not_video",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video gap video_discovery_not_video_media",
                        text="Aedes aegypti video source gap: video_discovery_not_video_media. Repository: osf.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="gaps.json#aedes_video_atoms/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"atom_type": "video_gap", "reason": "video_discovery_not_video_media", "repository": "osf"},
                    ),
                    EvidenceRecord(
                        record_id="video_atom:gap:osf:license",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video gap video_license_unclear",
                        text=(
                            "Aedes aegypti video source gap: video_license_unclear. Repository: osf. "
                            "Download URL: https://osf.io/download/pu8zf/. Source byte size: 74364708. "
                            "Source SHA-256: 9583fe1cf288f75b3c1be4cb88f045e4b7789747584ebe8dabe47426b8d00b29. "
                            "License: OSF project license not supplied."
                        ),
                        species="Aedes aegypti",
                        url="https://osf.io/cx762/",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="raw/osf/file.json#files/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={
                            "atom_type": "video_gap",
                            "reason": "video_license_unclear",
                            "repository": "osf",
                            "source_hashes": {"sha256": "9583fe1cf288f75b3c1be4cb88f045e4b7789747584ebe8dabe47426b8d00b29"},
                        },
                    ),
                ]
            )

            answer = answer_question("show OSF FlightTrackAI video license gaps with hashes", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["record_id"], "video_atom:gap:osf:license")
            self.assertIn("Source SHA-256", answer["evidence"][0]["text"])

    def test_video_discovery_questions_return_repository_assets_or_gaps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="video_atom:gap:zenodo_pdf",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video gap video_discovery_not_video_media",
                        text="Aedes aegypti video source gap: video_discovery_not_video_media. Repository: zenodo.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="gaps.json#aedes_video_atoms/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"atom_type": "video_gap", "repository": "zenodo"},
                    )
                ]
            )

            answer = answer_question("show Aedes video discovery from Zenodo", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "media")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_video_atoms")
            self.assertIn("video_discovery_not_video_media", answer["evidence"][0]["text"])

    def test_video_atom_motion_questions_prefer_queryable_motion_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="mendeley:table-row:motion",
                        lane="behavior",
                        source="mendeley_aedes_behavior_media",
                        title="Aedes aegypti parsed behavior row",
                        text="Aedes aegypti behavior table row for flight tracking.",
                        species="Aedes aegypti",
                        url="https://data.mendeley.com/datasets/example",
                        media_url=None,
                        provenance=Provenance(
                            source_id="mendeley_aedes_behavior_media",
                            locator="raw/mendeley_behavior_media/table.csv#row/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC BY 4.0",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="video_atom:motion:pmc_video:row1",
                        lane="behavior",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video motion row host seeking",
                        text="Aedes aegypti video motion trajectory row with track id, frame, time range, coordinates, assay, stimulus, arena, velocity, and confidence.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="raw/video_atoms/motion.csv#row/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC BY",
                        ),
                        payload={"atom_type": "video_motion_row", "velocity_mean_cm_s": 3.25, "behavior_type": "Flying"},
                    ),
                    EvidenceRecord(
                        record_id="extracted_fact:behavior:motion",
                        lane="behavior",
                        source="aedes_extracted_facts",
                        title="Aedes aegypti extracted behavior fact",
                        text="Aedes aegypti extracted behavior fact for table rows.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_extracted_facts",
                            locator="records#openalex:W1",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                    ),
                ]
            )

            answer = answer_question("show Aedes aegypti video motion rows", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "behavior")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_video_atoms")

            velocity_answer = answer_question("show Aedes aegypti locomotory video analysis velocity", artifact_dir=artifact_dir)

            self.assertTrue(velocity_answer["ok"])
            self.assertEqual(velocity_answer["answer_shape"], "behavior")
            self.assertEqual(velocity_answer["evidence"][0]["source"], "aedes_video_atoms")

    def test_image_atom_questions_prefer_queryable_image_labels(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="inat:media:99",
                        lane="media",
                        source="inaturalist_api",
                        title="Aedes aegypti iNaturalist still image 99",
                        text="iNaturalist still image for Aedes aegypti.",
                        species="Aedes aegypti",
                        url="https://www.inaturalist.org/observations/12345",
                        media_url="https://static.inaturalist.org/photos/99/medium.jpg",
                        provenance=Provenance(
                            source_id="inaturalist_api",
                            locator="raw/inaturalist/page.json#observations/12345/photos/99",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="cc-by",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="image_atom:label:inat_media_99:adult",
                        lane="media",
                        source="aedes_image_atoms",
                        title="Aedes aegypti image label life_stage: adult",
                        text="Aedes aegypti image label from source metadata: life_stage = adult. Source image record: inat:media:99.",
                        species="Aedes aegypti",
                        url="https://www.inaturalist.org/observations/12345",
                        media_url="https://static.inaturalist.org/photos/99/medium.jpg",
                        provenance=Provenance(
                            source_id="aedes_image_atoms",
                            locator="records#inat:media:99;label/life_stage",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="cc-by",
                        ),
                        payload={
                            "atom_type": "image_label",
                            "label_type": "life_stage",
                            "label_value": "adult",
                            "source_record_id": "inat:media:99",
                        },
                    ),
                ]
            )

            answer = answer_question("show Aedes aegypti adult image labels", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "evidence")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_image_atoms")
            self.assertIn("life_stage = adult", answer["evidence"][0]["text"])

    def test_image_gap_questions_return_queryable_gap_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="image_atom:gap:inaturalist_api:sex",
                        lane="media",
                        source="aedes_image_atoms",
                        title="Aedes aegypti image gap missing sex",
                        text="Aedes aegypti image label gap: inaturalist_api has 10 image asset(s) without source-provided sex metadata.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_image_atoms",
                            locator="gaps.json#aedes_image_atoms/1",
                            retrieved_at="2026-05-25T00:00:00Z",
                        ),
                        payload={"atom_type": "image_gap", "reason": "image_label_missing", "label_type": "sex"},
                    )
                ]
            )

            answer = answer_question("what Aedes image label gaps are missing sex?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "evidence")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_image_atoms")
            self.assertIn("without source-provided sex", answer["evidence"][0]["text"])

    def test_video_discovery_questions_do_not_fall_back_to_other_repositories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="video_atom:gap:dryad",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video gap video_discovery_client_missing",
                        text="Aedes aegypti video source gap: video_discovery_client_missing. Repository: dryad.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="gaps.json#aedes_video_atoms/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"atom_type": "video_gap", "repository": "dryad"},
                    )
                ]
            )

            answer = answer_question("show Aedes video discovery from Zenodo", artifact_dir=artifact_dir)

            self.assertFalse(answer["ok"])
            self.assertIn("no matching records for that repository", answer["source_gap"]["reason"])

    def test_figshare_video_questions_use_figshare_gap_not_other_video_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="osf:flighttrackai:file:video-a",
                        lane="media",
                        source="osf_flighttrackai_aedes_videos",
                        title="Aedes aegypti OSF FlightTrackAI video file Video A.mp4",
                        text="OSF Aedes aegypti video.",
                        species="Aedes aegypti",
                        url="https://osf.io/cx762/",
                        media_url="https://osf.io/download/video-a/",
                        provenance=Provenance(
                            source_id="osf_flighttrackai_aedes_videos",
                            locator="raw/osf/file.json#files/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="video_atom:gap:figshare",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video gap video_discovery_no_candidates",
                        text="Aedes aegypti video source gap: video_discovery_no_candidates. Repository: figshare.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="gaps.json#aedes_video_atoms/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"atom_type": "video_gap", "repository": "figshare"},
                    ),
                ]
            )

            answer = answer_question("show Figshare Aedes aegypti videos", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["record_id"], "video_atom:gap:figshare")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_video_atoms")

    def test_mendeley_table_questions_prefer_parsed_behavior_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="mendeley:table:sg5rrvdzvg:v1:file:sheet1",
                        lane="behavior",
                        source="mendeley_aedes_behavior_media",
                        title="Aedes aegypti Mendeley parsed behavior table Data_VideoAnalysis_temperature gradients_AeAegypti.xlsx sheet Sheet1",
                        text="Parsed Mendeley behavior table for Aedes aegypti locomotory behavior temperature gradients. Rows: 2700.",
                        species="Aedes aegypti",
                        url="https://data.mendeley.com/datasets/sg5rrvdzvg/1",
                        media_url=None,
                        provenance=Provenance(
                            source_id="mendeley_aedes_behavior_media",
                            locator="raw/mendeley_behavior_media/table_files/file.xlsx#sheet/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC BY 4.0",
                            source_url="https://data.mendeley.com/public-files/file_downloaded",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="mendeley:table-row:sg5rrvdzvg:v1:file:sheet1:r2",
                        lane="behavior",
                        source="mendeley_aedes_behavior_media",
                        title="Aedes aegypti Mendeley behavior table row Data_VideoAnalysis_temperature gradients_AeAegypti.xlsx Sheet1 row 2",
                        text="Parsed Mendeley Aedes aegypti behavior table row. File: Data_VideoAnalysis_temperature gradients_AeAegypti.xlsx. Sheet: Sheet1. Row: 2. Values: Temperature: 30; Species: Aedes aegypti; Behavioural_Activity: flight.",
                        species="Aedes aegypti",
                        url="https://data.mendeley.com/datasets/sg5rrvdzvg/1",
                        media_url=None,
                        provenance=Provenance(
                            source_id="mendeley_aedes_behavior_media",
                            locator="raw/mendeley_behavior_media/table_files/file.xlsx#sheet/1/row/2",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC BY 4.0",
                            source_url="https://data.mendeley.com/public-files/file_downloaded",
                        ),
                    ),
                ]
            )

            answer = answer_question("what Mendeley Aedes aegypti table rows mention temperature gradients?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "behavior")
            self.assertEqual(answer["evidence"][0]["record_id"], "mendeley:table-row:sg5rrvdzvg:v1:file:sheet1:r2")
            self.assertEqual(answer["evidence"][0]["source"], "mendeley_aedes_behavior_media")

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

    def test_vector_competence_assay_questions_prefer_structured_assay_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
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
                        ),
                    ),
                    EvidenceRecord(
                        record_id="assay_candidate:vector_competence:WVC0:abc",
                        lane="vector_competence",
                        source="aedes_vector_competence_assays",
                        title="Aedes aegypti vector competence assay candidate: Zika virus",
                        text="Structured assay-candidate extraction for Zika virus. Detected assay fields: infection.",
                        species="Aedes aegypti",
                        url="https://example.org/vector-competence-weak",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_vector_competence_assays",
                            locator="records#openalex:WVC0",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="OpenAlex metadata",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="assay_candidate:vector_competence:WVC1:abc",
                        lane="vector_competence",
                        source="aedes_vector_competence_assays",
                        title="Aedes aegypti vector competence assay candidate: Zika virus",
                        text="Structured assay-candidate extraction for Zika virus. Detected assay fields: infection, dissemination, transmission, dose, temperature.",
                        species="Aedes aegypti",
                        url="https://example.org/vector-competence",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_vector_competence_assays",
                            locator="records#openalex:WVC1;literature_fulltext_units#openalex:WVC1:fulltext:0",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC-BY",
                        ),
                    ),
                ]
            )

            answer = answer_question("show Zika vector competence assay dose and transmission for Aedes aegypti", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "vector_competence")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_vector_competence_assays")
            self.assertEqual(answer["evidence"][0]["record_id"], "assay_candidate:vector_competence:WVC1:abc")

    def test_supplement_table_questions_prefer_extracted_facts(self):
        from scripts.ingest_extracted_facts import ingest_extracted_facts
        from tests.test_extracted_facts_source import write_extracted_facts_fixture

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_extracted_facts_fixture(artifact_dir)
            ingest_extracted_facts(artifact_dir=artifact_dir, retrieved_at="2026-05-24T00:00:00Z")

            answer = answer_question(
                "show dengue vector competence supplement table infection rate for Aedes aegypti",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "vector_competence")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_extracted_facts")
            self.assertEqual(answer["evidence"][0]["lane"], "vector_competence")

    def test_supplement_table_questions_do_not_let_manifests_crowd_out_parsed_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            records = [
                EvidenceRecord(
                    record_id=f"extracted_fact:supplement_manifest:W{i:02d}",
                    lane="literature",
                    source="aedes_extracted_facts",
                    title=f"Aedes aegypti supplement manifest {i}",
                    text="Supplement manifest for an Aedes aegypti table.",
                    species="Aedes aegypti",
                    url="https://example.org/manifest",
                    media_url=None,
                    provenance=Provenance(
                        source_id="aedes_extracted_facts",
                        locator=f"records#W{i:02d};supplement#0",
                        retrieved_at="2026-05-24T00:00:00Z",
                        license="CC-BY",
                        source_url="https://example.org/manifest",
                    ),
                    payload={"confidence": "manifest", "fact_type": "supplement_manifest"},
                )
                for i in range(40)
            ]
            records.append(
                EvidenceRecord(
                    record_id="extracted_fact:vector_competence:WPARSED:abc",
                    lane="vector_competence",
                    source="aedes_extracted_facts",
                    title="Aedes aegypti extracted vector competence fact",
                    text=(
                        "Parsed supplement table row for dengue virus infection rate, "
                        "dissemination rate, and transmission in saliva."
                    ),
                    species="Aedes aegypti",
                    url="https://example.org/parsed",
                    media_url=None,
                    provenance=Provenance(
                        source_id="aedes_extracted_facts",
                        locator="records#WPARSED;supplement#0;row#1",
                        retrieved_at="2026-05-24T00:00:00Z",
                        license="CC-BY",
                        source_url="https://example.org/parsed",
                    ),
                    payload={"confidence": "parsed", "fact_type": "vector_competence"},
                )
            )
            index.upsert_records(records)

            answer = answer_question(
                "show dengue vector competence supplement table infection rate for Aedes aegypti",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["record_id"], "extracted_fact:vector_competence:WPARSED:abc")

    def test_supplement_table_questions_rank_relevant_parsed_rows_after_broad_fetch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            records = [
                EvidenceRecord(
                    record_id=f"extracted_fact:vector_competence:WOTHER:{i:02d}",
                    lane="vector_competence",
                    source="aedes_extracted_facts",
                    title="Aedes aegypti extracted vector competence fact",
                    text="Parsed supplement table row for saliva or midgut without dengue rate terms.",
                    species="Aedes aegypti",
                    url="https://example.org/other",
                    media_url=None,
                    provenance=Provenance(
                        source_id="aedes_extracted_facts",
                        locator=f"records#WOTHER;supplement#0;row#{i}",
                        retrieved_at="2026-05-24T00:00:00Z",
                        license="CC-BY",
                        source_url="https://example.org/other",
                    ),
                    payload={"confidence": "parsed", "fact_type": "vector_competence"},
                )
                for i in range(60)
            ]
            records.append(
                EvidenceRecord(
                    record_id="extracted_fact:vector_competence:WZZZ:dengue",
                    lane="vector_competence",
                    source="aedes_extracted_facts",
                    title="Aedes aegypti extracted vector competence dengue fact",
                    text="Parsed supplement table row: DENV-1 infection rate 80%, dissemination rate 40%, transmission rate 20%.",
                    species="Aedes aegypti",
                    url="https://example.org/dengue",
                    media_url=None,
                    provenance=Provenance(
                        source_id="aedes_extracted_facts",
                        locator="records#WZZZ;supplement#0;row#1",
                        retrieved_at="2026-05-24T00:00:00Z",
                        license="CC-BY",
                        source_url="https://example.org/dengue",
                    ),
                    payload={"confidence": "parsed", "fact_type": "vector_competence"},
                )
            )
            records.append(
                EvidenceRecord(
                    record_id="extracted_fact:vector_competence:WAAA:candidate",
                    lane="vector_competence",
                    source="aedes_extracted_facts",
                    title="Aedes aegypti extracted vector competence dengue candidate",
                    text="Full-text candidate for dengue virus infection rate, not a parsed supplement table row.",
                    species="Aedes aegypti",
                    url="https://example.org/candidate",
                    media_url=None,
                    provenance=Provenance(
                        source_id="aedes_extracted_facts",
                        locator="records#WAAA;literature_fulltext_units#WAAA:fulltext:0",
                        retrieved_at="2026-05-24T00:00:00Z",
                        license="CC-BY",
                        source_url="https://example.org/candidate",
                    ),
                    payload={"confidence": "candidate", "fact_type": "vector_competence"},
                )
            )
            index.upsert_records(records)

            answer = answer_question(
                "show dengue vector competence supplement table infection rate for Aedes aegypti",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["record_id"], "extracted_fact:vector_competence:WZZZ:dengue")

    def test_supplement_table_ranking_prefers_parsed_rows_over_fulltext_candidates(self):
        from askinsects.answer import _prioritize_named_source_records

        candidate = EvidenceRecord(
            record_id="extracted_fact:vector_competence:WAAA:candidate",
            lane="vector_competence",
            source="aedes_extracted_facts",
            title="Aedes aegypti extracted vector competence dengue candidate",
            text="Full-text candidate for dengue virus infection rate.",
            species="Aedes aegypti",
            url="https://example.org/candidate",
            media_url=None,
            provenance=Provenance(
                source_id="aedes_extracted_facts",
                locator="records#WAAA;literature_fulltext_units#WAAA:fulltext:0",
                retrieved_at="2026-05-24T00:00:00Z",
                license="CC-BY",
                source_url="https://example.org/candidate",
            ),
        )
        parsed = EvidenceRecord(
            record_id="extracted_fact:vector_competence:WZZZ:dengue",
            lane="vector_competence",
            source="aedes_extracted_facts",
            title="Aedes aegypti extracted vector competence dengue fact",
            text="Parsed supplement table row: DENV-1 infection rate 80%.",
            species="Aedes aegypti",
            url="https://example.org/dengue",
            media_url=None,
            provenance=Provenance(
                source_id="aedes_extracted_facts",
                locator="records#WZZZ;supplement#0;raw/extracted_facts/supplements/WZZZ.docx;row#1",
                retrieved_at="2026-05-24T00:00:00Z",
                license="CC-BY",
                source_url="https://example.org/dengue",
            ),
        )

        ranked = _prioritize_named_source_records(
            "show dengue vector competence supplement table infection rate for Aedes aegypti",
            [candidate, parsed],
        )

        self.assertEqual(ranked[0].record_id, "extracted_fact:vector_competence:WZZZ:dengue")

    def test_figshare_questions_prefer_figshare_video_source_rows(self):
        from askinsects.answer import _prioritize_named_source_records

        generic = EvidenceRecord(
            record_id="video_atom:asset:figshare:101",
            lane="media",
            source="aedes_video_atoms",
            title="Aedes aegypti derived Figshare video atom",
            text="Derived video atom from a Figshare Aedes aegypti video source.",
            species="Aedes aegypti",
            url="https://figshare.com/articles/dataset/101",
            media_url="https://ndownloader.figshare.com/files/202",
            provenance=Provenance(
                source_id="aedes_video_atoms",
                locator="records#figshare:aedes-video:101:oviposition_mp4",
                retrieved_at="2026-05-24T00:00:00Z",
                license="CC BY 4.0",
                source_url="https://ndownloader.figshare.com/files/202",
            ),
        )
        first_class = EvidenceRecord(
            record_id="figshare:aedes-video:101:oviposition_mp4",
            lane="media",
            source="figshare_aedes_videos",
            title="Aedes aegypti Figshare video file oviposition.mp4",
            text="Figshare video file for Aedes aegypti oviposition behavior.",
            species="Aedes aegypti",
            url="https://figshare.com/articles/dataset/101",
            media_url="https://ndownloader.figshare.com/files/202",
            provenance=Provenance(
                source_id="figshare_aedes_videos",
                locator="raw/figshare_aedes_videos/article_101.json#files/1",
                retrieved_at="2026-05-24T00:00:00Z",
                license="CC BY 4.0",
                source_url="https://ndownloader.figshare.com/files/202",
            ),
        )

        ranked = _prioritize_named_source_records("show Figshare Aedes aegypti videos", [generic, first_class])

        self.assertEqual(ranked[0].source, "figshare_aedes_videos")

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

    def test_vectorbase_genomics_questions_prefer_vectorbase_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="ncbi:gene:AAEL000001",
                        lane="genes",
                        source="ncbi_datasets_genome",
                        title="Aedes aegypti NCBI gene AAEL000001",
                        text="NCBI gene AAEL000001 for Aedes aegypti, annotated as odorant receptor coreceptor.",
                        species="Aedes aegypti",
                        url="https://example.org/ncbi",
                        media_url=None,
                        provenance=Provenance(
                            source_id="ncbi_datasets_genome",
                            locator="raw/ncbi_genome#gff",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="NCBI",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="vectorbase:gene:AAEL000001",
                        lane="genes",
                        source="vectorbase_aedes_genomics",
                        title="Aedes aegypti VectorBase gene AAEL000001",
                        text="VectorBase gene AAEL000001 for Aedes aegypti, annotated as odorant receptor coreceptor.",
                        species="Aedes aegypti",
                        url="https://vectorbase.org/common/downloads/Current_Release/AaegyptiLVP_AGWG/gff/data/VectorBase-68_AaegyptiLVP_AGWG.gff",
                        media_url=None,
                        provenance=Provenance(
                            source_id="vectorbase_aedes_genomics",
                            locator="raw/vectorbase_genomics/VectorBase-68_AaegyptiLVP_AGWG.gff#line/2",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="VectorBase/VEuPathDB public download; source terms apply",
                        ),
                    ),
                ]
            )

            answer = answer_question("show VectorBase AAEL000001 gene annotation for Aedes aegypti", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["source"], "vectorbase_aedes_genomics")

    def test_vectorbase_auxiliary_genomics_questions_route_to_genome_features(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="vectorbase:codon_usage:AUG",
                        lane="genome_features",
                        source="vectorbase_aedes_genomics",
                        title="Aedes aegypti VectorBase codon usage AUG",
                        text="VectorBase codon usage for Aedes aegypti codon AUG: amino acid M, frequency 22.88, relative abundance 1.00.",
                        species="Aedes aegypti",
                        url="https://vectorbase.org/codon.txt",
                        media_url=None,
                        provenance=Provenance(
                            source_id="vectorbase_aedes_genomics",
                            locator="raw/vectorbase_genomics/VectorBase-68_AaegyptiLVP_AGWG_CodonUsage.txt#line/2",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="VectorBase/VEuPathDB public download; source terms apply",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="vectorbase:ncbi_linkout:Nucleotide:AaegL5_1:1",
                        lane="genome_features",
                        source="vectorbase_aedes_genomics",
                        title="Aedes aegypti VectorBase NCBI Nucleotide linkout AaegL5_1",
                        text="VectorBase NCBI LinkOut maps Aedes aegypti Nucleotide query AaegL5_1 to VectorBase base URL https://vectorbase.org/a/app/record/genomic-sequence/.",
                        species="Aedes aegypti",
                        url="https://vectorbase.org/linkout.xml",
                        media_url=None,
                        provenance=Provenance(
                            source_id="vectorbase_aedes_genomics",
                            locator="raw/vectorbase_genomics/VectorBase-68_AaegyptiLVP_AGWG_NCBILinkout_Nucleotide.xml#link/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="VectorBase/VEuPathDB public download; source terms apply",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="vectorbase:id_event:AAEL000355:none:1",
                        lane="genome_features",
                        source="vectorbase_aedes_genomics",
                        title="Aedes aegypti VectorBase ID event AAEL000355 deletion",
                        text="VectorBase identifier event for Aedes aegypti old ID AAEL000355: deletion.",
                        species="Aedes aegypti",
                        url="https://vectorbase.org/id_events.tab",
                        media_url=None,
                        provenance=Provenance(
                            source_id="vectorbase_aedes_genomics",
                            locator="raw/vectorbase_genomics/VectorBase-68_AaegyptiLVP_AGWG_ids_events.tab#line/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="VectorBase/VEuPathDB public download; source terms apply",
                        ),
                    ),
                ]
            )

            answer = answer_question("show VectorBase codon usage AUG for Aedes aegypti", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["record_id"], "vectorbase:codon_usage:AUG")

            answer = answer_question(
                "show VectorBase AAEL000355 identifier event for Aedes aegypti",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["record_id"], "vectorbase:id_event:AAEL000355:none:1")

            answer = answer_question("show VectorBase NCBI LinkOut for AaegL5_1", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["record_id"], "vectorbase:ncbi_linkout:Nucleotide:AaegL5_1:1")

    def test_vectorbase_sequence_questions_route_to_sequence_atoms(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="vectorbase:id_event:AAEL000001:none:1",
                        lane="genome_features",
                        source="vectorbase_aedes_genomics",
                        title="Aedes aegypti VectorBase ID event AAEL000001 deletion",
                        text="VectorBase identifier event for Aedes aegypti AAEL000001.",
                        species="Aedes aegypti",
                        url="https://vectorbase.org/id-events.tab",
                        media_url=None,
                        provenance=Provenance(
                            source_id="vectorbase_aedes_genomics",
                            locator="raw/vectorbase_genomics/id-events.tab#line/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="VectorBase/VEuPathDB public download; source terms apply",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="vectorbase:cds:AAEL000001-RA",
                        lane="genome_features",
                        source="vectorbase_aedes_genomics",
                        title="Aedes aegypti VectorBase CDS sequence AAEL000001-RA",
                        text="VectorBase CDS sequence AAEL000001-RA for Aedes aegypti. Observed FASTA sequence length: 9 nucleotides.",
                        species="Aedes aegypti",
                        url="https://vectorbase.org/cds.fasta",
                        media_url=None,
                        provenance=Provenance(
                            source_id="vectorbase_aedes_genomics",
                            locator="raw/vectorbase_genomics/cds.fasta#line/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="VectorBase/VEuPathDB public download; source terms apply",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="vectorbase:transcript_sequence:AAEL000001-RA",
                        lane="transcripts",
                        source="vectorbase_aedes_genomics",
                        title="Aedes aegypti VectorBase transcript sequence AAEL000001-RA",
                        text="VectorBase transcript sequence AAEL000001-RA for Aedes aegypti. Observed FASTA sequence length: 12 nucleotides.",
                        species="Aedes aegypti",
                        url="https://vectorbase.org/transcripts.fasta",
                        media_url=None,
                        provenance=Provenance(
                            source_id="vectorbase_aedes_genomics",
                            locator="raw/vectorbase_genomics/transcripts.fasta#line/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="VectorBase/VEuPathDB public download; source terms apply",
                        ),
                    ),
                ]
            )

            answer = answer_question("show VectorBase CDS sequence for AAEL000001", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["record_id"], "vectorbase:cds:AAEL000001-RA")

            answer = answer_question("show VectorBase transcript sequence for AAEL000001", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["record_id"], "vectorbase:transcript_sequence:AAEL000001-RA")

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

    def test_biosample_questions_prefer_ncbi_biosamples(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="ncbi:gene:LOC5566000",
                        lane="genes",
                        source="ncbi_datasets_genome",
                        title="Aedes aegypti gene LOC5566000",
                        text="Aedes aegypti genome gene record.",
                        species="Aedes aegypti",
                        url="https://example.org/gene",
                        media_url=None,
                        provenance=Provenance(
                            source_id="ncbi_datasets_genome",
                            locator="raw/ncbi_genome#gff",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="NCBI",
                        ),
                    ),
                    biosample_record(
                        "ncbi:biosample:SAMN2",
                        "NCBI BioSample SAMN2 for Aedes aegypti. Geography: unknown geography. Strain or breed: Liverpool. Linked SRA: SRS2.",
                    ),
                    biosample_record(
                        "ncbi:biosample:SAMN1",
                        "NCBI BioSample SAMN1 for Aedes aegypti. Geography: China: Chongqing. Strain or breed: Rockefeller. Linked SRA: SRS29208944.",
                    ),
                ]
            )

            answer = answer_question("show Aedes aegypti BioSamples from China", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["source"], "ncbi_biosamples")
            self.assertEqual(answer["evidence"][0]["lane"], "biosamples")
            self.assertEqual(answer["evidence"][0]["record_id"], "ncbi:biosample:SAMN1")

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

    def test_marker_resistance_questions_prefer_marker_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    resistance_record("irmapper:aedes:1", "irmapper_aedes"),
                    resistance_marker_record("resistance_marker:V1016G:openalex:WRM1"),
                ]
            )

            answer = answer_question("show kdr V1016G resistance markers in Aedes aegypti", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "resistance")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_resistance_markers")
            self.assertIn("V1016G", answer["evidence"][0]["text"])

    def test_ecology_questions_prefer_occurrence_ecology_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    ecology_record("facet:ecology:1", "aedes_literature_facets"),
                    ecology_record("occurrence_ecology:country_month:Brazil:01", "aedes_occurrence_ecology"),
                    EvidenceRecord(
                        record_id="occurrence_ecology:country:Somalia",
                        lane="ecology",
                        source="aedes_occurrence_ecology",
                        title="Aedes aegypti occurrence ecology in Somalia",
                        text="Aedes aegypti occurrence ecology range distribution seasonality Somalia observations.",
                        species="Aedes aegypti",
                        url="https://example.org/somalia",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_occurrence_ecology",
                            locator="test#somalia",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="test",
                        ),
                    ),
                ]
            )

            answer = answer_question("what seasonality evidence exists for Aedes aegypti in Brazil by month?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "ecology")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_occurrence_ecology")
            self.assertIn("Brazil", answer["evidence"][0]["text"])

    def test_vectornet_questions_prefer_vectornet_surveillance_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    public_health_record(
                        "public_health:surveillance:paho",
                        "aedes_paho_dengue_surveillance",
                        "Official PAHO dengue surveillance evidence for Aedes aegypti public-health intelligence.",
                    ),
                    EvidenceRecord(
                        record_id="vectornet:observation:VNET_1",
                        lane="observations",
                        source="vectornet_aedes_surveillance",
                        title="VectorNet Aedes aegypti surveillance row VNET-1",
                        text="Official VectorNet ECDC/EFSA surveillance occurrence row for Aedes aegypti in Georgia.",
                        species="Aedes aegypti",
                        url="https://ipt.gbif.org/resource?r=vndatabase#occurrence/VNET-1",
                        media_url=None,
                        provenance=Provenance(
                            source_id="vectornet_aedes_surveillance",
                            locator="raw/vectornet_surveillance/dwca-vndatabase-v1.3.zip#occurrence.txt/row/2",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="CC-BY-4.0",
                        ),
                    ),
                ]
            )

            answer = answer_question("show VectorNet Aedes aegypti surveillance evidence", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "public_health")
            self.assertEqual(answer["evidence"][0]["source"], "vectornet_aedes_surveillance")

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

    def test_dengue_prevention_guidance_questions_route_to_public_health(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="public_health:guidance:cdc-preventing-dengue",
                        lane="public_health",
                        source="aedes_public_health_guidance",
                        title="CDC guidance: Preventing Dengue",
                        text="Official CDC public-health guidance for dengue prevention. Aedes mosquitoes spread dengue; prevent mosquito bites and control mosquitoes around the home.",
                        species="Aedes aegypti",
                        url="https://www.cdc.gov/dengue/prevention/index.html",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_public_health_guidance",
                            locator="raw/public_health_guidance/CDC.html#page",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="Public health web guidance; source page terms apply",
                            source_url="https://www.cdc.gov/dengue/prevention/index.html",
                        ),
                    )
                ]
            )

            answer = answer_question("what official Aedes aegypti dengue prevention guidance exists?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "public_health")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_public_health_guidance")

    def test_ecdc_factsheet_questions_route_to_public_health(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="public_health:guidance:cdc-preventing-dengue",
                        lane="public_health",
                        source="aedes_public_health_guidance",
                        title="CDC guidance: Preventing Dengue",
                        text="Official CDC public-health guidance for dengue prevention.",
                        species="Aedes aegypti",
                        url="https://www.cdc.gov/dengue/prevention/index.html",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_public_health_guidance",
                            locator="raw/public_health_guidance/CDC.html#page",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="Public health web guidance; source page terms apply",
                            source_url="https://www.cdc.gov/dengue/prevention/index.html",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="public_health:guidance:ecdc-aedes-factsheet",
                        lane="public_health",
                        source="aedes_public_health_guidance",
                        title="ECDC guidance: Aedes aegypti factsheet",
                        text="Official ECDC public-health factsheet evidence for Aedes aegypti control ecology.",
                        species="Aedes aegypti",
                        url="https://www.ecdc.europa.eu/en/disease-vectors/facts/mosquito-factsheets/aedes-aegypti",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_public_health_guidance",
                            locator="raw/public_health_guidance/ECDC.html#page",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="Public health web guidance; source page terms apply",
                            source_url="https://www.ecdc.europa.eu/en/disease-vectors/facts/mosquito-factsheets/aedes-aegypti",
                        ),
                    )
                ]
            )

            answer = answer_question("show ECDC Aedes aegypti factsheet evidence", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "public_health")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_public_health_guidance")
            self.assertIn("ECDC", answer["evidence"][0]["title"])

    def test_paho_surveillance_questions_prefer_paho_public_health_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    public_health_record(
                        "public_health:guidance:cdc",
                        "aedes_public_health_guidance",
                        "Official public-health guidance for Aedes aegypti vector control from CDC.",
                    ),
                    public_health_record(
                        "public_health:surveillance:paho",
                        "aedes_paho_dengue_surveillance",
                        "Official PAHO dengue surveillance evidence for Aedes aegypti public-health intelligence.",
                    ),
                ]
            )

            answer = answer_question("show PAHO dengue surveillance evidence for Aedes aegypti", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "public_health")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_paho_dengue_surveillance")

    def test_paho_dashboard_questions_prefer_dashboard_locator_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    public_health_record(
                        "public_health:surveillance:paho_dengue:regional_week_summary:2024:week50",
                        "aedes_paho_dengue_surveillance",
                        "Official PAHO dengue surveillance regional week summary for Aedes aegypti public-health intelligence.",
                    ),
                    public_health_record(
                        "public_health:surveillance:paho_dengue:dashboard_locator:abc123",
                        "aedes_paho_dengue_surveillance",
                        "Official PAHO dengue dashboard locator for PAHO/PLISA dashboard iframe evidence. Not a country-week cell row yet.",
                    ),
                ]
            )

            answer = answer_question("show PAHO PLISA dashboard locator evidence for Aedes aegypti", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "public_health")
            self.assertEqual(
                answer["evidence"][0]["record_id"],
                "public_health:surveillance:paho_dengue:dashboard_locator:abc123",
            )

    def test_paho_open_data_questions_prefer_core_indicator_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    public_health_record(
                        "public_health:surveillance:paho_dengue:regional_week_summary:2024:week50",
                        "aedes_paho_dengue_surveillance",
                        "Official PAHO dengue surveillance regional week summary for Aedes aegypti public-health intelligence.",
                    ),
                    public_health_record(
                        "public_health:surveillance:paho_dengue:core_indicator:dengue_cases:BRA:2025",
                        "aedes_paho_dengue_surveillance",
                        "PAHO/EIH Core Indicators annual dengue cases for Brazil in 2025 from a stable machine-readable Open Data CSV row.",
                    ),
                ]
            )

            answer = answer_question("show PAHO Open Data annual dengue cases for Brazil", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "public_health")
            self.assertEqual(
                answer["evidence"][0]["record_id"],
                "public_health:surveillance:paho_dengue:core_indicator:dengue_cases:BRA:2025",
            )

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
