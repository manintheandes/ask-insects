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


def snp_variation_record(record_id, text):
    return EvidenceRecord(
        record_id=record_id,
        lane="genome_features",
        source="aedes_ncbi_snp_variation",
        title=f"Aedes aegypti dbSNP audit {record_id}",
        text=text,
        species="Aedes aegypti",
        url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        media_url=None,
        provenance=Provenance(
            source_id="aedes_ncbi_snp_variation",
            locator=f"raw/ncbi_snp_variation/esearch.json#{record_id}",
            retrieved_at="2026-05-25T00:00:00Z",
            license="NCBI dbSNP public metadata",
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


def resistance_table_row_record(record_id):
    return EvidenceRecord(
        record_id=record_id,
        lane="resistance",
        source="aedes_resistance_table_rows",
        title="Aedes aegypti parsed resistance table row: deltamethrin V1016G",
        text=(
            "Schema-validated parsed supplement table row for Aedes aegypti resistance. "
            "Insecticide terms: deltamethrin. Marker terms: V1016G. "
            "Metric fields: mortality, genotype_frequency. Table row: Mortality %: 43. V1016G allele frequency: 0.72."
        ),
        species="Aedes aegypti",
        url="https://example.org/resistance-supplement.csv",
        media_url=None,
        provenance=Provenance(
            source_id="aedes_resistance_table_rows",
            locator="aedes_extracted_facts#extracted_fact:resistance:openalex:WRTABLE1:row7;records#openalex:WRTABLE1;row#7",
            retrieved_at="2026-05-24T00:00:00Z",
            license="CC-BY",
        ),
        payload={"confidence": "parsed_table_schema_validated", "marker_terms": ["V1016G"], "metric_fields": ["mortality", "genotype_frequency"]},
    )


def swd_susceptibility_record(record_id):
    return EvidenceRecord(
        record_id=record_id,
        lane="resistance",
        source="drosophila_suzukii_susceptibility_assay_rows",
        title="Drosophila suzukii susceptibility evidence: spinosad",
        text=(
            "Candidate literature evidence for Drosophila suzukii insecticide susceptibility or resistance. "
            "Insecticide terms: spinosad. Assay terms: bioassay. Metric fields: mortality. "
            "Evidence: spinosad caused greater than 90% adult mortality in a bioassay."
        ),
        species="Drosophila suzukii",
        url="https://example.org/swd-susceptibility",
        media_url=None,
        provenance=Provenance(
            source_id="drosophila_suzukii_susceptibility_assay_rows",
            locator="drosophila_suzukii_extracted_facts#swd_extracted_fact:resistance:W1",
            retrieved_at="2026-05-29T00:00:00Z",
            license="OpenAlex metadata",
        ),
        payload={
            "confidence": "candidate_literature_evidence",
            "validation_status": "candidate_not_table_validated",
            "insecticide_terms": ["spinosad"],
            "assay_terms": ["bioassay"],
            "metric_fields": ["mortality"],
        },
    )


def swd_biocontrol_outcome_record(record_id):
    return EvidenceRecord(
        record_id=record_id,
        lane="biocontrol",
        source="drosophila_suzukii_biocontrol_outcome_rows",
        title="Drosophila suzukii biocontrol outcome evidence: parasitoid, trichopria",
        text=(
            "Candidate literature evidence for Drosophila suzukii biological-control outcomes. "
            "Agent terms: parasitoid, trichopria. Assay terms: laboratory. "
            "Effect metric terms: parasitism, emergence. Evidence: Trichopria parasitized Drosophila suzukii pupae."
        ),
        species="Drosophila suzukii",
        url="https://example.org/swd-biocontrol",
        media_url=None,
        provenance=Provenance(
            source_id="drosophila_suzukii_biocontrol_outcome_rows",
            locator="drosophila_suzukii_extracted_facts#swd_extracted_fact:biocontrol:W1",
            retrieved_at="2026-05-29T00:00:00Z",
            license="OpenAlex metadata",
        ),
        payload={
            "confidence": "candidate_literature_evidence",
            "validation_status": "candidate_not_table_validated",
            "agent_terms": ["parasitoid", "trichopria"],
            "assay_terms": ["laboratory"],
            "effect_metric_terms": ["parasitism", "emergence"],
        },
    )


def swd_extracted_biocontrol_record(record_id):
    return EvidenceRecord(
        record_id=record_id,
        lane="biocontrol",
        source="drosophila_suzukii_extracted_facts",
        title="Drosophila suzukii extracted biocontrol fact",
        text="Drosophila suzukii extracted biocontrol candidate row. Trichopria parasitoid parasitism evidence.",
        species="Drosophila suzukii",
        url="https://example.org/swd-extracted-biocontrol",
        media_url=None,
        provenance=Provenance(
            source_id="drosophila_suzukii_extracted_facts",
            locator="records#swd:openalex_literature:openalex:W2",
            retrieved_at="2026-05-29T00:00:00Z",
            license="OpenAlex metadata",
        ),
        payload={"confidence": "candidate", "fact_type": "biocontrol"},
    )


def swd_extracted_resistance_record(record_id):
    return EvidenceRecord(
        record_id=record_id,
        lane="resistance",
        source="drosophila_suzukii_extracted_facts",
        title="Drosophila suzukii extracted resistance fact",
        text="Drosophila suzukii extracted resistance fact. Spinosad bioassay mortality evidence.",
        species="Drosophila suzukii",
        url="https://example.org/swd-extracted",
        media_url=None,
        provenance=Provenance(
            source_id="drosophila_suzukii_extracted_facts",
            locator="records#swd:openalex_literature:openalex:W2",
            retrieved_at="2026-05-29T00:00:00Z",
            license="OpenAlex metadata",
        ),
        payload={"confidence": "candidate", "fact_type": "resistance"},
    )


def swd_resistance_gene_record(record_id):
    return EvidenceRecord(
        record_id=record_id,
        lane="genes",
        source="drosophila_suzukii_genome_files",
        title="Drosophila suzukii gene Mdr49",
        text="NCBI genome gene Mdr49 for Drosophila suzukii, annotated as Multi drug resistance 49.",
        species="Drosophila suzukii",
        url="https://www.ncbi.nlm.nih.gov/datasets/genome/GCF_043229965.1/",
        media_url=None,
        provenance=Provenance(
            source_id="drosophila_suzukii_genome_files",
            locator="raw/drosophila_suzukii_genome_files/GCF_043229965.1/genomic.gff#line/79569",
            retrieved_at="2026-05-29T00:00:00Z",
            license="NCBI public data metadata",
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


def expression_gap_record(record_id, text, reason="raw_sra_reanalysis_not_performed"):
    return EvidenceRecord(
        record_id=record_id,
        lane="expression",
        source="aedes_expression_omics",
        title="Aedes aegypti expression omics source gap",
        text=text,
        species="Aedes aegypti",
        url="https://www.ncbi.nlm.nih.gov/sra",
        media_url=None,
        provenance=Provenance(
            source_id="aedes_expression_omics",
            locator=f"raw/expression_omics/source_boundary.json#gap/{reason}",
            retrieved_at="2026-05-24T00:00:00Z",
            license="Ask Insects source boundary audit",
        ),
        payload={"atom_type": "source_gap", "reason": reason},
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


def vectorbyte_abundance_record(record_id):
    return EvidenceRecord(
        record_id=record_id,
        lane="observations",
        source="aedes_vectorbyte_abundance",
        title="VectorByte VecDyn abundance sample 27006 p1-r0",
        text=(
            "VectorByte VecDyn Aedes aegypti abundance sample from dataset 27006. "
            "Sample value: 1.0 count. Sample date: 2023-06-20. Sampling method: prokopak aspirator. "
            "Life stage: adult. Sex: female. Coordinates: -4.013491376, -73.43223028. "
            "Dataset title: Changing dynamics of Aedes aegypti invasion and vector-borne disease risk for rural communities in the Peruvian Amazon."
        ),
        species="Aedes aegypti",
        url="https://doi.org/10.1101/2024.09.04.611168",
        media_url=None,
        provenance=Provenance(
            source_id="aedes_vectorbyte_abundance",
            locator="raw/vectorbyte_abundance/vecdyn_dataset_27006_page_1.json#results/p1-r0",
            retrieved_at="2026-05-26T00:00:00Z",
            license="VectorByte/VecDyn public data; source terms apply",
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


def who_malaria_threats_record(record_id, text):
    return EvidenceRecord(
        record_id=record_id,
        lane="resistance",
        source="who_malaria_threats_resistance_audit",
        title="WHO Malaria Threats Map resistance audit",
        text=text,
        species="Aedes aegypti",
        url="https://apps.who.int/malaria/maps/threats/",
        media_url=None,
        provenance=Provenance(
            source_id="who_malaria_threats_resistance_audit",
            locator=f"raw/who_malaria_threats_resistance/aedes.json#{record_id}",
            retrieved_at="2026-05-25T00:00:00Z",
            license="WHO public data",
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
        self.assertEqual(plan_question("show parsed resistance table V1016G frequency for Aedes aegypti").answer_shape, "resistance")
        self.assertEqual(plan_question("show resistance copy number amplification evidence from openalex W3208836499 CCEAE3A").answer_shape, "resistance")
        self.assertEqual(plan_question("show schema-validated Aedes aegypti resistance supplement table rows").answer_shape, "resistance")
        self.assertEqual(plan_question("what vector competence data exists for dengue?").answer_shape, "vector_competence")
        self.assertEqual(plan_question("what host seeking behavior data exists for Aedes aegypti?").answer_shape, "behavior")
        self.assertEqual(plan_question("what Mendeley table rows mention temperature gradients?").answer_shape, "behavior")
        self.assertEqual(plan_question("show Mendeley acoustic wingbeat audio files").answer_shape, "behavior")
        self.assertEqual(plan_question("show supplement table behavior response rate for Aedes aegypti").answer_shape, "behavior")
        self.assertEqual(plan_question("what crop damage evidence exists for spotted wing drosophila?").answer_shape, "crop_damage")
        self.assertEqual(plan_question("show Drosophila suzukii pest management evidence").answer_shape, "management")
        self.assertEqual(plan_question("show Drosophila suzukii extension IPM guidance").answer_shape, "management")
        self.assertEqual(plan_question("show Drosophila suzukii trap capture monitoring evidence").answer_shape, "ecology")
        self.assertEqual(plan_question("show Drosophila suzukii biocontrol parasitoid evidence").answer_shape, "biocontrol")
        self.assertEqual(plan_question("show Drosophila suzukii nuclear marker review").lanes[0], "dna_barcodes")
        self.assertEqual(plan_question("show BOLD COI barcode records for Aedes aegypti").lanes[0], "dna_barcodes")
        self.assertEqual(plan_question("show Aedes aegypti BioSamples from China").lanes[0], "biosamples")
        self.assertEqual(plan_question("what papers discuss mosquito host seeking?").lanes[0], "literature")
        self.assertEqual(plan_question("what Aedes aegypti olfaction figure caption mentions elevated CO2?").answer_shape, "literature")
        self.assertEqual(plan_question("what neuron data exists for the Aedes aegypti brain?").answer_shape, "neurobiology")
        self.assertEqual(plan_question("what brain regions process smell in mosquitoes?").lanes[0], "neurobiology")
        self.assertEqual(plan_question("what H5AD data exists in the Mosquito Cell Atlas?").lanes[0], "neurobiology")
        self.assertEqual(plan_question("what SRA raw reads exist for GSE160740?").lanes[0], "neurobiology")
        self.assertEqual(plan_question("what voxel volume files exist in MosquitoBrains?").lanes[0], "neurobiology")
        self.assertEqual(plan_question("where is Aedes aegypti observed by month in Brazil?").answer_shape, "ecology")
        self.assertEqual(plan_question("what range and seasonality evidence exists for Aedes aegypti?").lanes[0], "ecology")
        self.assertEqual(plan_question("show GEO RNA-seq expression data for Aedes aegypti midgut").answer_shape, "expression")
        self.assertEqual(plan_question("show Aedes aegypti expression matrix differential expression data").answer_shape, "expression")
        self.assertEqual(plan_question("show Aedes aegypti raw SRA reanalysis count matrix").answer_shape, "expression")
        self.assertEqual(plan_question("show UniProt protein function for AAEL012345").lanes[0], "proteins")
        self.assertEqual(plan_question("show VectorByte temperature trait data for Aedes aegypti fecundity").lanes[0], "traits")
        self.assertEqual(plan_question("show World Mosquito Program Wolbachia intervention evidence from Yogyakarta").answer_shape, "public_health")
        self.assertEqual(plan_question("show CDC ArboNET dengue surveillance current cases").answer_shape, "public_health")
        self.assertEqual(plan_question("show Aedes aegypti taxonomy synonyms from authority sources").lanes[0], "taxonomy")
        self.assertEqual(plan_question("show WorldClim climate context for Aedes aegypti ecology").answer_shape, "ecology")
        self.assertEqual(plan_question("show Harvard Dataverse suitability rasters for Aedes aegypti dengue transmission").answer_shape, "ecology")
        self.assertEqual(plan_question("show global Aedes aegypti occurrence compendium rows for Brazil").answer_shape, "ecology")
        self.assertEqual(plan_question("show Aedes aegypti population genomics BioProject evidence").lanes[0], "genome_features")
        self.assertEqual(plan_question("show NCBI dbSNP variant records for Aedes aegypti").lanes[0], "genome_features")
        self.assertEqual(
            plan_question("show Aedes aegypti orthogroups coorthologs inparalogs current ID resolution").answer_shape,
            "genomics",
        )
        self.assertEqual(plan_question("show WHO Aedes insecticide resistance bioassay guidance").answer_shape, "resistance")

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

    def test_expression_matrix_questions_prefer_queryable_source_gap_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    expression_gap_record(
                        "expression:gap:raw_sra_reanalysis_not_performed",
                        "Aedes aegypti expression omics source gap: raw SRA reanalysis, count matrices, normalized expression matrices, and differential-expression outputs are not yet indexed as source-grade rows.",
                    ),
                    EvidenceRecord(
                        record_id="video_atom:asset:irrelevant",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video asset irrelevant",
                        text="Aedes aegypti video asset with a source table.",
                        species="Aedes aegypti",
                        url="https://example.org/video",
                        media_url="https://example.org/video.mp4",
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="raw/video_atoms/assets.json#asset/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="test",
                        ),
                    ),
                ]
            )

            answer = answer_question("show Aedes aegypti raw SRA reanalysis count matrix", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "expression")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_expression_omics")
            self.assertEqual(answer["evidence"][0]["record_id"], "expression:gap:raw_sra_reanalysis_not_performed")
            self.assertIn("count matrices", answer["answer"])

    def test_differential_expression_questions_prefer_computed_output_gap_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    expression_record("expression:geo:GSE999999"),
                    expression_gap_record(
                        "expression:gap:differential_expression_outputs_not_indexed",
                        "Aedes aegypti expression omics source gap: differential-expression outputs and normalized expression matrices are not yet indexed as source-grade rows.",
                        reason="differential_expression_outputs_not_indexed",
                    ),
                ]
            )

            answer = answer_question("show Aedes aegypti expression matrix differential expression data", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "expression")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_expression_omics")
            self.assertEqual(answer["evidence"][0]["record_id"], "expression:gap:differential_expression_outputs_not_indexed")
            self.assertIn("differential-expression outputs", answer["answer"])

    def test_exact_proteomexchange_expression_questions_prefer_parsed_matrix_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            supplement = {
                "title": "PXD030925 expression matrix",
                "url": "https://example.org/PXD030925/matrix.xlsx",
                "file_type": "xlsx",
                "source": "proteomexchange",
                "accession": "PXD030925",
            }
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="extracted_fact:supplement_manifest:openalex:W4319295297:p",
                        lane="literature",
                        source="aedes_extracted_facts",
                        title="Aedes aegypti supplement manifest: ProteomeXchange PXD030925",
                        text="Supplement manifest for ProteomeXchange PXD030925.",
                        species="Aedes aegypti",
                        url="https://example.org/PXD030925",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_extracted_facts",
                            locator="records#openalex:W4319295297;supplement#40",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={
                            "fact_type": "supplement_manifest",
                            "fields": {"accession": "PXD030925"},
                            "source_record_id": "openalex:W4319295297",
                            "supplement": supplement,
                            "confidence": "manifest",
                        },
                    ),
                    EvidenceRecord(
                        record_id="extracted_fact:expression_omics:openalex:W4319295297:r1",
                        lane="expression",
                        source="aedes_extracted_facts",
                        title="Aedes aegypti extracted expression omics fact",
                        text="Parsed PXD030925 expression matrix row. IDs: AAEL000001. Fe_Ov_NBF_1_TPM: 12.4. T: Protein IDs: AAEL000001-PA.",
                        species="Aedes aegypti",
                        url="https://example.org/PXD030925/matrix.xlsx",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_extracted_facts",
                            locator="records#openalex:W4319295297;supplement#40;matrix.xlsx;row#1",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={
                            "fact_type": "expression_omics",
                            "fields": {
                                "expression_metric": ["tpm"],
                                "protein_identifier": ["protein ids"],
                                "table_row": {"IDs": "AAEL000001", "Fe_Ov_NBF_1_TPM": "12.4"},
                            },
                            "source_record_id": "openalex:W4319295297",
                            "confidence": "parsed",
                        },
                    ),
                ]
            )

            answer = answer_question("show PXD030925 TPM expression matrix rows for Aedes aegypti", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "expression")
            self.assertEqual(answer["evidence"][0]["record_id"], "extracted_fact:expression_omics:openalex:W4319295297:r1")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_extracted_facts")

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

    def test_vectorbyte_abundance_questions_prefer_vecdyn_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    vectorbyte_abundance_record("vectorbyte:abundance:27006:p1-r0"),
                    ecology_record("occurrence_ecology:country:Brazil", "aedes_occurrence_ecology"),
                    trait_record("vectorbyte:trait:474:89092"),
                ]
            )

            answer = answer_question("show VectorByte VecDyn Aedes aegypti abundance trap counts in the Peruvian Amazon", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "ecology")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_vectorbyte_abundance")
            self.assertEqual(answer["evidence"][0]["lane"], "observations")

    def test_crossref_literature_audit_questions_prefer_crossref_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    literature_record(
                        "literature:openalex:W123",
                        "Aedes aegypti larval habitat surveillance",
                        "OpenAlex Aedes aegypti literature metadata.",
                    ),
                    EvidenceRecord(
                        record_id="aedes_crossref_literature_audit:doi:10.1016_j.example.2025.01.001",
                        lane="literature",
                        source="aedes_crossref_literature_audit",
                        title="Aedes aegypti larval habitat surveillance in Brazil",
                        text="Aedes aegypti Crossref literature audit candidate since 2020. coverage_status=crossref_metadata_ingested doi=10.1016/j.example.2025.01.001 publisher=Example Publisher",
                        species="Aedes aegypti",
                        url="https://doi.org/10.1016/j.example.2025.01.001",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_crossref_literature_audit",
                            locator="raw/aedes_crossref_literature_audit/crossref_works_0001.json#items/0",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="Crossref public metadata; source terms apply",
                        ),
                    ),
                ]
            )

            self.assertEqual(plan_question("show Crossref DOI audit literature for Aedes aegypti").answer_shape, "literature")
            answer = answer_question("show Crossref DOI audit literature for Aedes aegypti", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "literature")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_crossref_literature_audit")

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

    def test_olfaction_literature_questions_require_audit_lane(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            answer = answer_question("what PubMed papers discuss Aedes aegypti olfaction since 2020?", artifact_dir=artifact_dir)

            self.assertFalse(answer["ok"])
            self.assertIn("olfaction literature audit lane is not installed", answer["source_gap"]["reason"])

    def test_olfaction_literature_questions_prefer_pubmed_audit_lane(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="literature:openalex:odor",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Aedes aegypti odor paper",
                        text="OpenAlex paper about Aedes aegypti odor and olfaction.",
                        species="Aedes aegypti",
                        url="https://example.org/openalex",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_literature_openalex",
                            locator="openalex#odor",
                            retrieved_at="2026-05-25T00:00:00Z",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="aedes_olfaction_literature:pubmed:37874813",
                        lane="literature",
                        source="aedes_olfaction_literature",
                        title="Odor-evoked transcriptomics of Aedes aegypti mosquitoes.",
                        text="Aedes aegypti olfaction literature audit candidate from PubMed since 2020. coverage_status=already_indexed pmid=37874813 odor olfaction",
                        species="Aedes aegypti",
                        url="https://pubmed.ncbi.nlm.nih.gov/37874813/",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_olfaction_literature",
                            locator="raw/aedes_olfaction_literature/pubmed_esummary_0001.json#result/37874813",
                            retrieved_at="2026-05-25T00:00:00Z",
                        ),
                        payload={"pmid": "37874813", "coverage_status": "already_indexed"},
                    ),
                ]
            )

            answer = answer_question("what PubMed papers discuss Aedes aegypti olfaction since 2020?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["source"], "aedes_olfaction_literature")
            self.assertEqual(answer["evidence"][0]["record_id"], "aedes_olfaction_literature:pubmed:37874813")

    def test_swd_pubmed_questions_prefer_pubmed_reconciliation_lane(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd:literature:openalex:W123456789",
                        lane="literature",
                        source="drosophila_suzukii_core",
                        title="Drosophila suzukii crop damage paper",
                        text="OpenAlex paper about Drosophila suzukii crop damage.",
                        species="Drosophila suzukii",
                        url="https://openalex.org/W123456789",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_core",
                            locator="raw/drosophila_suzukii/openalex_0001.json#results/0",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="swd:pubmed:42000001",
                        lane="literature",
                        source="drosophila_suzukii_pubmed_literature",
                        title="Drosophila suzukii PubMed audit candidate",
                        text="Drosophila suzukii PubMed literature reconciliation candidate since 2020. coverage_status=already_indexed pmid=42000001",
                        species="Drosophila suzukii",
                        url="https://pubmed.ncbi.nlm.nih.gov/42000001/",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_pubmed_literature",
                            locator="raw/drosophila_suzukii_pubmed_literature/pubmed_esummary_0001.json#result/42000001",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={"pmid": "42000001", "coverage_status": "already_indexed"},
                    ),
                ]
            )

            answer = answer_question(
                "show Drosophila suzukii PubMed coverage status",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_pubmed_literature")
            self.assertEqual(answer["evidence"][0]["record_id"], "swd:pubmed:42000001")

    def test_olfaction_figure_questions_prefer_fulltext_caption_units(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            paper = EvidenceRecord(
                record_id="aedes_olfaction_literature:pubmed:40275031",
                lane="literature",
                source="aedes_olfaction_literature",
                title="Impact of elevated CO2 on Aedes aegypti olfactory organs.",
                text="Aedes aegypti olfaction literature audit candidate from PubMed since 2020.",
                species="Aedes aegypti",
                url="https://pubmed.ncbi.nlm.nih.gov/40275031/",
                media_url=None,
                provenance=Provenance(
                    source_id="aedes_olfaction_literature",
                    locator="raw/aedes_olfaction_literature/pubmed_esummary_0001.json#result/40275031",
                    retrieved_at="2026-05-25T00:00:00Z",
                ),
            )
            index.upsert_records([paper])
            index.upsert_fulltext_units(
                [
                    FullTextUnit(
                        unit_id="aedes_olfaction_literature:pubmed:40275031:figure-caption:0",
                        record_id=paper.record_id,
                        source="aedes_olfaction_literature",
                        unit_index=0,
                        text="Figure caption: Elevated CO2 changes gene expression in the peripheral olfactory organs of Aedes aegypti.",
                        url="https://example.org/paper.pdf",
                        license="cc-by",
                        provenance=Provenance(
                            source_id="aedes_olfaction_literature",
                            locator="raw/aedes_olfaction_literature/fulltext/paper.pdf#figure-caption/0",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="cc-by",
                            source_url="https://example.org/paper.pdf",
                        ),
                    )
                ]
            )

            answer = answer_question(
                "what Aedes aegypti olfaction figure caption mentions elevated CO2?",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "literature")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_olfaction_literature")
            self.assertEqual(answer["evidence"][0]["lane"], "literature_fulltext")
            self.assertIn("Figure caption", answer["evidence"][0]["text"])

    def test_repellent_literature_questions_prefer_repellent_lane(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    literature_record(
                        "literature:openalex:repellent",
                        "Aedes aegypti repellent review",
                        "OpenAlex paper about repellents.",
                    ),
                    EvidenceRecord(
                        record_id="mosquito_repellent_literature:pubmed:42000001",
                        lane="literature",
                        source="mosquito_repellent_literature",
                        title="Spatial repellent protection against Aedes mosquito host seeking",
                        text="Mosquito repellent literature candidate since 2020. coverage_status=repellent_metadata_ingested candidate_sources=pubmed_esearch_esummary pmid=42000001 repellent_terms=repellent mosquito_terms=aedes; mosquito",
                        species="Culicidae",
                        url="https://pubmed.ncbi.nlm.nih.gov/42000001/",
                        media_url=None,
                        provenance=Provenance(
                            source_id="mosquito_repellent_literature",
                            locator="raw/mosquito_repellent_literature/pubmed_esummary_0001.json#result/42000001",
                            retrieved_at="2026-05-25T00:00:00Z",
                        ),
                    ),
                ]
            )

            answer = answer_question("what mosquito repellent papers since 2020 are in the database?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "literature")
            self.assertEqual(answer["evidence"][0]["source"], "mosquito_repellent_literature")

    def test_repellent_patent_questions_include_external_discovery_gap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            records = [
                EvidenceRecord(
                    record_id="mosquito_repellent_literature:pubmed:42000001",
                    lane="literature",
                    source="mosquito_repellent_literature",
                    title="Mosquito repellent article",
                    text="Mosquito repellent literature candidate since 2020.",
                    species="Culicidae",
                    url="https://pubmed.ncbi.nlm.nih.gov/42000001/",
                    media_url=None,
                    provenance=Provenance(
                        source_id="mosquito_repellent_literature",
                        locator="raw/mosquito_repellent_literature/pubmed_esummary_0001.json#result/42000001",
                        retrieved_at="2026-05-25T00:00:00Z",
                    ),
                )
            ]
            for offset in range(6):
                records.append(
                    EvidenceRecord(
                        record_id=f"mosquito_repellent_external_discovery:doi:10.5281/zenodo.{offset}",
                        lane="datasets",
                        source="mosquito_repellent_external_discovery",
                        title=f"DataCite mosquito repellent dataset {offset}",
                        text="Mosquito repellent external discovery source candidate. source_family=datacite artifact_type=dataset_manifest.",
                        species="Culicidae",
                        url=f"https://doi.org/10.5281/zenodo.{offset}",
                        media_url=None,
                        provenance=Provenance(
                            source_id="mosquito_repellent_external_discovery",
                            locator=f"raw/mosquito_repellent_external_discovery/datacite_0001.json#data/{offset}",
                            retrieved_at="2026-05-25T00:00:00Z",
                        ),
                    )
                )
            records.append(
                EvidenceRecord(
                    record_id="mosquito_repellent_external_discovery:gap:patentsview:patentsview_migrated_or_unavailable_json_api",
                    lane="patents",
                    source="mosquito_repellent_external_discovery",
                    title="Mosquito repellent source gap: patentsview patentsview_migrated_or_unavailable_json_api",
                    text="Mosquito repellent source gap for patent metadata.",
                    species="Culicidae",
                    url="https://patentsview.org/apis/api-endpoints",
                    media_url=None,
                    provenance=Provenance(
                        source_id="mosquito_repellent_external_discovery",
                        locator="https://patentsview.org/apis/api-endpoints",
                        retrieved_at="2026-05-25T00:00:00Z",
                    ),
                )
            )
            index.upsert_records(records)

            answer = answer_question("show mosquito repellent patent sources", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "literature")
            self.assertEqual(answer["evidence"][0]["source"], "mosquito_repellent_external_discovery")
            self.assertEqual(answer["evidence"][0]["lane"], "patents")

    def test_repellent_dataset_questions_prefer_external_discovery_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="mosquito_repellent_literature:pubmed:42000001",
                        lane="literature",
                        source="mosquito_repellent_literature",
                        title="Mosquito repellent article",
                        text="Mosquito repellent literature candidate since 2020.",
                        species="Culicidae",
                        url="https://pubmed.ncbi.nlm.nih.gov/42000001/",
                        media_url=None,
                        provenance=Provenance(
                            source_id="mosquito_repellent_literature",
                            locator="raw/mosquito_repellent_literature/pubmed_esummary_0001.json#result/42000001",
                            retrieved_at="2026-05-25T00:00:00Z",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="mosquito_repellent_external_discovery:datacite:10.5281/zenodo.123",
                        lane="datasets",
                        source="mosquito_repellent_external_discovery",
                        title="DataCite mosquito repellent dataset",
                        text="Mosquito repellent external discovery candidate. source_family=datacite artifact_type=dataset repository=Zenodo.",
                        species="Culicidae",
                        url="https://doi.org/10.5281/zenodo.123",
                        media_url=None,
                        provenance=Provenance(
                            source_id="mosquito_repellent_external_discovery",
                            locator="raw/mosquito_repellent_external_discovery/datacite_0001.json#data/0",
                            retrieved_at="2026-05-25T00:00:00Z",
                        ),
                    ),
                ]
            )

            answer = answer_question("show mosquito repellent datasets from DataCite or Zenodo", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "literature")
            self.assertEqual(answer["evidence"][0]["source"], "mosquito_repellent_external_discovery")
            self.assertEqual(answer["evidence"][0]["lane"], "datasets")

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

    def test_species_specific_video_questions_do_not_borrow_aedes_media(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="video_atom:asset:aedes",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video keyframe",
                        text="Inspectable Aedes aegypti video keyframe.",
                        species="Aedes aegypti",
                        url="https://example.org/aedes-video",
                        media_url="raw/video_atoms/aedes.jpg",
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="records#aedes",
                            retrieved_at="2026-05-28T00:00:00Z",
                            license="CC BY 4.0",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="swd:figshare:video:1",
                        lane="media",
                        source="drosophila_suzukii_deep_sources",
                        title="Drosophila suzukii Figshare video file",
                        text="Figshare video candidate for Drosophila suzukii.",
                        species="Drosophila suzukii",
                        url="https://example.org/swd-video",
                        media_url="https://example.org/swd-video.mp4",
                        provenance=Provenance(
                            source_id="drosophila_suzukii_deep_sources",
                            locator="raw/drosophila_suzukii_deep_sources/figshare/article.json#files/1",
                            retrieved_at="2026-05-28T00:00:00Z",
                            license="CC BY 4.0",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="swd:video_atom:video_keyframe:1",
                        lane="media",
                        source="drosophila_suzukii_video_atoms",
                        title="Drosophila suzukii video keyframe",
                        text="Inspectable spotted wing drosophila video keyframe from Figshare.",
                        species="Drosophila suzukii",
                        url="https://example.org/swd-video",
                        media_url="raw/drosophila_suzukii_video_atoms/artifacts/keyframe_000001.jpg",
                        provenance=Provenance(
                            source_id="drosophila_suzukii_video_atoms",
                            locator="raw/drosophila_suzukii_video_atoms/artifacts/keyframe_000001.jpg",
                            retrieved_at="2026-05-28T00:00:00Z",
                            license="CC BY 4.0",
                        ),
                        payload={"atom_type": "video_keyframe"},
                    ),
                ]
            )

            answer = answer_question("show Drosophila suzukii videos", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "media")
            self.assertEqual(answer["evidence"][0]["species"], "Drosophila suzukii")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_video_atoms")

    def test_swd_abbreviation_video_gap_questions_use_swd_video_atoms(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd:video_atom:gap:dryad:1",
                        lane="media",
                        source="drosophila_suzukii_video_atoms",
                        title="Drosophila suzukii video source gap: dryad_frame_archive_download_failed",
                        text="Ask Insects video gap for SWD: Dryad archive download failed with HTTP 403 and 401 route attempts.",
                        species="Drosophila suzukii",
                        url="https://datadryad.org/dataset/doi:10.5061/dryad.8vd762q",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_video_atoms",
                            locator="raw/drosophila_suzukii_video_atoms/dryad_8vd762q/files_9818.json#files/41801",
                            retrieved_at="2026-05-29T00:00:00Z",
                            license="CC0-1.0",
                        ),
                        payload={"atom_type": "video_gap", "reason": "dryad_frame_archive_download_failed", "file_id": "41801"},
                    ),
                    EvidenceRecord(
                        record_id="video_atom:gap:aedes:1",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video source gap",
                        text="Aedes video gap.",
                        species="Aedes aegypti",
                        url="https://example.org/aedes",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="raw/video_atoms/gap.json#1",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={"atom_type": "video_gap", "reason": "video_download_failed"},
                    ),
                ]
            )

            answer = answer_question("what SWD video sources are still missing or blocked?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "media")
            self.assertEqual(answer["evidence"][0]["species"], "Drosophila suzukii")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_video_atoms")

    def test_spotted_wing_dryad_frame_archive_questions_prefer_video_atom_archives(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd:video_atom:asset:figshare",
                        lane="media",
                        source="drosophila_suzukii_video_atoms",
                        title="Drosophila suzukii Figshare video atom",
                        text="Figshare video asset for Drosophila suzukii.",
                        species="Drosophila suzukii",
                        url="https://example.org/swd-video",
                        media_url="https://example.org/swd-video.mp4",
                        provenance=Provenance(
                            source_id="drosophila_suzukii_video_atoms",
                            locator="raw/drosophila_suzukii_video_atoms/figshare.json#file",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={"atom_type": "video_asset"},
                    ),
                    EvidenceRecord(
                        record_id="swd:video_atom:asset:dryad_avi",
                        lane="media",
                        source="drosophila_suzukii_video_atoms",
                        title="Drosophila suzukii video atom: Dryad video/archive file DC-19.avi",
                        text="spotted wing drosophila video asset from drosophila_suzukii_deep_sources.",
                        species="Drosophila suzukii",
                        url="https://datadryad.org/api/v2/files/4124325/download",
                        media_url="https://datadryad.org/api/v2/files/4124325/download",
                        provenance=Provenance(
                            source_id="drosophila_suzukii_video_atoms",
                            locator="raw/drosophila_suzukii_deep_sources/dryad/files.json#files/11",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={"atom_type": "video_asset"},
                    ),
                    EvidenceRecord(
                        record_id="swd:dryad_8vd762q:frame_archive:41799",
                        lane="media",
                        source="drosophila_suzukii_video_atoms",
                        title="Drosophila suzukii Dryad frame archive Video images of copulating Dsuz_TMUS8-1.zip",
                        text="Dryad SWD-involved TIFF frame archive for spotted wing drosophila. The source describes video images as 5 frames per second TIFF sequences of copulating individuals.",
                        species="Drosophila suzukii",
                        url="https://datadryad.org/dataset/doi:10.5061/dryad.8vd762q",
                        media_url="https://datadryad.org/downloads/file_stream/41799",
                        provenance=Provenance(
                            source_id="drosophila_suzukii_video_atoms",
                            locator="raw/drosophila_suzukii_video_atoms/dryad_8vd762q/files_9818.json#files/41799",
                            retrieved_at="2026-05-29T00:00:00Z",
                            license="CC0-1.0",
                        ),
                        payload={"atom_type": "video_frame_archive", "file_id": "41799"},
                    ),
                ]
            )

            answer = answer_question("show Drosophila suzukii Dryad frame archive copulation video evidence", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "media")
            self.assertEqual(answer["evidence"][0]["record_id"], "swd:dryad_8vd762q:frame_archive:41799")

    def test_spotted_wing_genomics_questions_use_swd_deep_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="aedes:assembly:1",
                        lane="genome_assemblies",
                        source="ncbi_datasets_genome",
                        title="Aedes aegypti assembly",
                        text="Aedes aegypti genome assembly.",
                        species="Aedes aegypti",
                        url="https://example.org/aedes-assembly",
                        media_url=None,
                        provenance=Provenance(
                            source_id="ncbi_datasets_genome",
                            locator="raw/ncbi/aedes.json#1",
                            retrieved_at="2026-05-28T00:00:00Z",
                            license="NCBI public metadata",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="swd:assembly:GCF_1",
                        lane="genome_assemblies",
                        source="drosophila_suzukii_deep_sources",
                        title="Drosophila suzukii assembly GCF_1",
                        text="NCBI Assembly record GCF_1 for Drosophila suzukii.",
                        species="Drosophila suzukii",
                        url="https://example.org/swd-assembly",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_deep_sources",
                            locator="raw/drosophila_suzukii_deep_sources/ncbi/assembly.json#1",
                            retrieved_at="2026-05-28T00:00:00Z",
                            license="NCBI public metadata",
                        ),
                    ),
                ]
            )

            answer = answer_question("show Drosophila suzukii genomics", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["species"], "Drosophila suzukii")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_deep_sources")

    def test_spotted_wing_genome_file_questions_prefer_parsed_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd:assembly:GCF_1",
                        lane="genome_assemblies",
                        source="drosophila_suzukii_deep_sources",
                        title="Drosophila suzukii assembly GCF_1",
                        text="NCBI Assembly record GCF_1 for Drosophila suzukii.",
                        species="Drosophila suzukii",
                        url="https://example.org/swd-assembly",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_deep_sources",
                            locator="raw/drosophila_suzukii_deep_sources/ncbi/assembly.json#1",
                            retrieved_at="2026-05-28T00:00:00Z",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="swd:genome_files:gene:gene-Orco",
                        lane="genes",
                        source="drosophila_suzukii_genome_files",
                        title="Drosophila suzukii gene Orco",
                        text="NCBI genome gene Orco for Drosophila suzukii, annotated as odorant receptor co-receptor.",
                        species="Drosophila suzukii",
                        url="https://example.org/swd-genome-files",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_genome_files",
                            locator="raw/drosophila_suzukii_genome_files/GCF_1/genomic.gff#line/2",
                            retrieved_at="2026-05-28T00:00:00Z",
                        ),
                    ),
                ]
            )

            answer = answer_question("show Drosophila suzukii genome file genes orco", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_genome_files")
            self.assertEqual(answer["evidence"][0]["lane"], "genes")

    def test_spotted_wing_crop_management_questions_prefer_extracted_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd:gbif:taxon",
                        lane="taxonomy",
                        source="drosophila_suzukii_core",
                        title="Drosophila suzukii",
                        text="GBIF accepted species match for Drosophila suzukii.",
                        species="Drosophila suzukii",
                        url="https://example.org/swd",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_core",
                            locator="raw/drosophila_suzukii/gbif/match.json",
                            retrieved_at="2026-05-28T00:00:00Z",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="swd_extracted_fact:crop_damage:paper1",
                        lane="crop_damage",
                        source="drosophila_suzukii_extracted_facts",
                        title="Drosophila suzukii crop damage fact",
                        text="Drosophila suzukii crop damage fact for blueberry fruit infestation and yield loss.",
                        species="Drosophila suzukii",
                        url="https://doi.org/10.1000/swd-crop",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_extracted_facts",
                            locator="records#swd:paper1",
                            retrieved_at="2026-05-28T00:00:00Z",
                        ),
                    ),
                ]
            )

            answer = answer_question("what do we know about spotted wing drosophila crop damage?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "crop_damage")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_extracted_facts")
            self.assertEqual(answer["evidence"][0]["lane"], "crop_damage")

    def test_spotted_wing_management_guidance_questions_prefer_extension_guidance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd_extracted_fact:management:paper1",
                        lane="management",
                        source="drosophila_suzukii_extracted_facts",
                        title="Drosophila suzukii management fact",
                        text="Drosophila suzukii literature-derived pest management candidate row.",
                        species="Drosophila suzukii",
                        url="https://doi.org/10.1000/swd-management",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_extracted_facts",
                            locator="records#swd:paper1",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="swd_extension_guidance:abc123",
                        lane="management",
                        source="drosophila_suzukii_extension_guidance",
                        title="Extension SWD guidance",
                        text="Extension/IPM guidance for Drosophila suzukii. Topic: monitoring, trapping, sanitation, and insecticide rotation.",
                        species="Drosophila suzukii",
                        url="https://extension.example/swd",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_extension_guidance",
                            locator="raw/drosophila_suzukii_extension_guidance/page.html#page",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                    ),
                ]
            )

            answer = answer_question("show Drosophila suzukii extension IPM guidance", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "management")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_extension_guidance")

    def test_spotted_wing_ecology_questions_prefer_occurrence_summaries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd_occurrence_ecology:country_month:United_States_of_America:09",
                        lane="ecology",
                        source="drosophila_suzukii_occurrence_ecology",
                        title="Drosophila suzukii seasonality in United States of America: September",
                        text="Drosophila suzukii country-month seasonality record for United States of America in September.",
                        species="Drosophila suzukii",
                        url="https://example.org/swd-us-september",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_occurrence_ecology",
                            locator="source_index.sqlite#swd-observation-ecology/country-month/United_States_of_America/09",
                            retrieved_at="2026-05-28T00:00:00Z",
                        ),
                        payload={"aggregation_type": "country_month_summary", "observation_count": 76},
                    ),
                    EvidenceRecord(
                        record_id="swd_extracted_fact:ecology:paper1",
                        lane="ecology",
                        source="drosophila_suzukii_extracted_facts",
                        title="Drosophila suzukii extracted ecology fact",
                        text="Drosophila suzukii ecology candidate row from a paper.",
                        species="Drosophila suzukii",
                        url="https://example.org/swd-paper",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_extracted_facts",
                            locator="records#swd:paper1",
                            retrieved_at="2026-05-28T00:00:00Z",
                        ),
                    ),
                ]
            )

            answer = answer_question("where is Drosophila suzukii observed by month?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "ecology")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_occurrence_ecology")
            self.assertEqual(answer["evidence"][0]["record_id"], "swd_occurrence_ecology:country_month:United_States_of_America:09")

    def test_spotted_wing_trap_questions_prefer_jki_drosomon_monitoring_lane(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd_jki_drosomon_trap_captures:dataset:openagrar_mods_00041381",
                        lane="ecology",
                        source="drosophila_suzukii_jki_drosomon_trap_captures",
                        title="JKI DrosoMon SWD trap-capture dataset",
                        text="JKI DrosoMon trap-capture monitoring dataset for Drosophila suzukii. Reported 9967 trap-deployment records and 756717 captured adults.",
                        species="Drosophila suzukii",
                        url="https://www.openagrar.de/receive/openagrar_mods_00041381",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_jki_drosomon_trap_captures",
                            locator="raw/drosophila_suzukii_jki_drosomon_trap_captures/data_europa_dataset.json#result",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={
                            "atom_type": "jki_drosomon_trap_dataset",
                            "deployment_count_reported": 9967,
                            "adult_captures_reported": 756717,
                        },
                    ),
                    EvidenceRecord(
                        record_id="swd_jki_drosomon_trap_captures:trap_location:DA_BE1",
                        lane="ecology",
                        source="drosophila_suzukii_jki_drosomon_trap_captures",
                        title="JKI DrosoMon SWD trap location DA_BE1",
                        text="JKI DrosoMon trap DA_BE1 for Drosophila suzukii. Coordinates: 49.800277, 8.648321. Immediate habitat: mixed forest with blackberry.",
                        species="Drosophila suzukii",
                        url="https://www.openagrar.de/receive/openagrar_mods_00041381",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_jki_drosomon_trap_captures",
                            locator="raw/drosophila_suzukii_jki_drosomon_trap_captures/trap_description.csv#row/1",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={
                            "atom_type": "jki_drosomon_trap_location_row",
                            "trap_name": "DA_BE1",
                            "latitude": 49.800277,
                            "longitude": 8.648321,
                            "immediate_habitat_english": "mixed forest with blackberry",
                        },
                    ),
                    EvidenceRecord(
                        record_id="swd_occurrence_ecology:country:Germany",
                        lane="ecology",
                        source="drosophila_suzukii_occurrence_ecology",
                        title="Drosophila suzukii occurrence ecology in Germany",
                        text="Drosophila suzukii occurrence ecology country summary for Germany.",
                        species="Drosophila suzukii",
                        url="https://example.org/swd-germany",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_occurrence_ecology",
                            locator="source_index.sqlite#swd-observation-ecology/country/Germany",
                            retrieved_at="2026-05-28T00:00:00Z",
                        ),
                        payload={"aggregation_type": "country_summary", "observation_count": 200},
                    ),
                ]
            )

            answer = answer_question("show Drosophila suzukii trap capture monitoring evidence", artifact_dir=artifact_dir)
            location_answer = answer_question("show Drosophila suzukii JKI trap coordinates and habitat", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "ecology")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_jki_drosomon_trap_captures")
            self.assertTrue(location_answer["ok"])
            self.assertEqual(location_answer["answer_shape"], "ecology")
            self.assertEqual(location_answer["evidence"][0]["record_id"], "swd_jki_drosomon_trap_captures:trap_location:DA_BE1")

    def test_spotted_wing_climate_suitability_questions_prefer_plos_model_lane(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd_plos_climate_suitability:000_summary",
                        lane="ecology",
                        source="drosophila_suzukii_plos_climate_suitability",
                        title="Drosophila suzukii global climate-suitability model summary",
                        text="PLOS climate-suitability model for Drosophila suzukii. MaxEnt AUC 0.97 and GARP AUC 0.87.",
                        species="Drosophila suzukii",
                        url="https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0174318",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_plos_climate_suitability",
                            locator="plos#abstract",
                            retrieved_at="2026-05-30T00:00:00Z",
                        ),
                        payload={"atom_type": "plos_climate_model_summary"},
                    ),
                    EvidenceRecord(
                        record_id="swd_occurrence_ecology:country:Germany",
                        lane="ecology",
                        source="drosophila_suzukii_occurrence_ecology",
                        title="Drosophila suzukii occurrence ecology in Germany",
                        text="Drosophila suzukii occurrence ecology country summary for Germany.",
                        species="Drosophila suzukii",
                        url="https://example.org/swd-germany",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_occurrence_ecology",
                            locator="source_index.sqlite#swd-observation-ecology/country/Germany",
                            retrieved_at="2026-05-28T00:00:00Z",
                        ),
                        payload={"aggregation_type": "country_summary", "observation_count": 200},
                    ),
                ]
            )

            answer = answer_question("show Drosophila suzukii climate suitability evidence", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "ecology")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_plos_climate_suitability")

    def test_spotted_wing_flight_questions_prefer_umn_assay_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd_umn_flight_assay:row:2",
                        lane="behavior",
                        source="drosophila_suzukii_umn_flight_assay_rows",
                        title="Drosophila suzukii UMN flight assay row 2: free-flight chamber",
                        text="UMN Drosophila suzukii flight behavior row 2: free-flight chamber. Sex: F. Flight propensity: 1. Phototactic response: 1. Duration: 21.84.",
                        species="Drosophila suzukii",
                        url="https://hdl.handle.net/11299/227164",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_umn_flight_assay_rows",
                            locator="raw/drosophila_suzukii_umn_flight_assay_rows/data_archival.csv#row/2",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={"atom_type": "umn_flight_assay_row", "assay": "free-flight chamber", "duration": 21.84},
                    ),
                    EvidenceRecord(
                        record_id="swd_umn_flight_assay:row:4",
                        lane="behavior",
                        source="drosophila_suzukii_umn_flight_assay_rows",
                        title="Drosophila suzukii UMN flight assay row 4: tethered flight mill",
                        text="UMN Drosophila suzukii flight behavior row 4: tethered flight mill. Sex: F. Flight propensity: 0.",
                        species="Drosophila suzukii",
                        url="https://hdl.handle.net/11299/227164",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_umn_flight_assay_rows",
                            locator="raw/drosophila_suzukii_umn_flight_assay_rows/data_archival.csv#row/4",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={"atom_type": "umn_flight_assay_row", "assay": "tethered flight mill"},
                    ),
                    EvidenceRecord(
                        record_id="swd_core:literature:flight-paper",
                        lane="literature",
                        source="drosophila_suzukii_core",
                        title="Drosophila suzukii flight paper",
                        text="Generic literature record about Drosophila suzukii flight.",
                        species="Drosophila suzukii",
                        url="https://example.org/swd-flight-paper",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_core",
                            locator="source_index.sqlite#literature/flight-paper",
                            retrieved_at="2026-05-28T00:00:00Z",
                        ),
                    ),
                ]
            )

            answer = answer_question("show Drosophila suzukii flight behavior in the free-flight chamber", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "behavior")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_umn_flight_assay_rows")
            self.assertEqual(answer["evidence"][0]["record_id"], "swd_umn_flight_assay:row:2")

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

    def test_mendeley_acoustic_questions_prefer_decoded_audio_metadata_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="mendeley:file:6gvs94p6r2:v1:file_audio",
                        lane="media",
                        source="mendeley_aedes_behavior_media",
                        title="Aedes aegypti Mendeley video/audio/archive file File 10.wav",
                        text="Mendeley wingbeat sound file for Aedes aegypti acoustic behavior.",
                        species="Aedes aegypti",
                        url="https://data.mendeley.com/datasets/6gvs94p6r2/1",
                        media_url="https://data.mendeley.com/public-files/audio/file_downloaded",
                        provenance=Provenance(
                            source_id="mendeley_aedes_behavior_media",
                            locator="raw/mendeley_behavior_media/files.json#files/audio/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC BY 4.0",
                            source_url="https://data.mendeley.com/public-files/audio/file_downloaded",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="mendeley:audio-assay:6gvs94p6r2:v1:file_audio",
                        lane="behavior",
                        source="mendeley_aedes_behavior_media",
                        title="Aedes aegypti Mendeley acoustic behavior file File 10.wav",
                        text="Mendeley source-provided audio/acoustic file metadata for Aedes aegypti. Frequency label 665 Hz. Comparison stimulus white noise. Waveform features have not been decoded.",
                        species="Aedes aegypti",
                        url="https://data.mendeley.com/datasets/6gvs94p6r2/1",
                        media_url="https://data.mendeley.com/public-files/audio/file_downloaded",
                        provenance=Provenance(
                            source_id="mendeley_aedes_behavior_media",
                            locator="raw/mendeley_behavior_media/files.json#audio-assay/audio/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC BY 4.0",
                            source_url="https://data.mendeley.com/public-files/audio/file_downloaded",
                        ),
                        payload={
                            "record_type": "mendeley_audio_assay_metadata",
                            "frequency_hz": ["665 Hz"],
                            "comparison_stimulus": "white noise",
                        },
                    ),
                    EvidenceRecord(
                        record_id="mendeley:audio-metadata:6gvs94p6r2:v1:file_audio",
                        lane="behavior",
                        source="mendeley_aedes_behavior_media",
                        title="Aedes aegypti Mendeley decoded WAV metadata File 10.wav",
                        text="Decoded Mendeley WAV metadata for Aedes aegypti acoustic behavior. Duration seconds: 1.0. Sample rate Hz: 44100. Channels: 2.",
                        species="Aedes aegypti",
                        url="https://data.mendeley.com/datasets/6gvs94p6r2/1",
                        media_url="https://data.mendeley.com/public-files/audio/file_downloaded",
                        provenance=Provenance(
                            source_id="mendeley_aedes_behavior_media",
                            locator="raw/mendeley_behavior_media/audio_files/file_audio.wav#audio-metadata/audio/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC BY 4.0",
                            source_url="https://data.mendeley.com/public-files/audio/file_downloaded",
                        ),
                        payload={
                            "record_type": "mendeley_audio_waveform_metadata",
                            "duration_seconds": 1.0,
                            "sample_rate_hz": 44100,
                            "channels": 2,
                            "frequency_hz": ["665 Hz"],
                            "comparison_stimulus": "white noise",
                        },
                    ),
                ]
            )

            answer = answer_question("show Mendeley Aedes wingbeat acoustic audio files", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "behavior")
            self.assertEqual(answer["evidence"][0]["record_id"], "mendeley:audio-metadata:6gvs94p6r2:v1:file_audio")

    def test_mendeley_acoustic_questions_use_direct_audio_metadata_rows_without_fts_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="mendeley:audio-metadata:6gvs94p6r2:v1:file_audio",
                        lane="behavior",
                        source="mendeley_aedes_behavior_media",
                        title="File 10.wav measurements",
                        text="Duration seconds: 1.0. Sample rate Hz: 44100. Channels: 2.",
                        species="Aedes aegypti",
                        url="https://data.mendeley.com/datasets/6gvs94p6r2/1",
                        media_url="https://data.mendeley.com/public-files/audio/file_downloaded",
                        provenance=Provenance(
                            source_id="mendeley_aedes_behavior_media",
                            locator="raw/mendeley_behavior_media/audio_files/file_audio.wav#audio-metadata/audio/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC BY 4.0",
                            source_url="https://data.mendeley.com/public-files/audio/file_downloaded",
                        ),
                    )
                ]
            )

            answer = answer_question("show Mendeley Aedes wingbeat acoustic audio metadata", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "behavior")
            self.assertEqual(answer["evidence"][0]["record_id"], "mendeley:audio-metadata:6gvs94p6r2:v1:file_audio")

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
                        payload={"atom_type": "video_keyframe"},
                    ),
                    EvidenceRecord(
                        record_id="video_atom:video_keyframe:pmc_video_2",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video keyframe for BiteOscope second",
                        text="Second inspectable keyframe derived from an Aedes aegypti video.",
                        species="Aedes aegypti",
                        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC123/",
                        media_url="raw/video_atoms/artifacts/keyframe_000002.jpg",
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="records#pmc:video:PMC123:video1.mp4;raw/video_atoms/artifacts/keyframe_000002.jpg",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC BY",
                        ),
                        payload={"atom_type": "video_keyframe"},
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
                        payload={"atom_type": "video_preview_clip"},
                    ),
                    EvidenceRecord(
                        record_id="video_atom:video_frame_manifest:pmc_video",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video frame manifest for BiteOscope",
                        text="Inspectable frame manifest derived from an Aedes aegypti video.",
                        species="Aedes aegypti",
                        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC123/",
                        media_url="raw/video_atoms/artifacts/frames.json",
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="records#pmc:video:PMC123:video1.mp4;raw/video_atoms/artifacts/frames.json",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC BY",
                        ),
                        payload={"atom_type": "video_frame_manifest"},
                    ),
                ]
            )

            answer = answer_question("show Aedes aegypti keyframes previews and frame manifests", artifact_dir=artifact_dir, limit=3)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "media")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_video_atoms")
            self.assertEqual(
                [item["record_id"] for item in answer["evidence"]],
                [
                    "video_atom:video_keyframe:pmc_video",
                    "video_atom:video_preview_clip:pmc_video",
                    "video_atom:video_frame_manifest:pmc_video",
                ],
            )

    def test_verified_video_questions_filter_to_verified_assets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="video_atom:asset:gapped",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video asset gapped",
                        text="Aedes aegypti video asset without a verified probe.",
                        species="Aedes aegypti",
                        url="https://example.org/gapped",
                        media_url="https://example.org/gapped.mp4",
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="records#gapped",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC BY",
                        ),
                        payload={"atom_type": "video_asset", "verification_status": "gapped_download_failed"},
                    ),
                    EvidenceRecord(
                        record_id="video_atom:asset:verified",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video asset verified",
                        text="Aedes aegypti verified video asset. Duration 12 seconds, 30 fps, 640x480, codec h264.",
                        species="Aedes aegypti",
                        url="https://example.org/verified",
                        media_url="raw/video_atoms/assets/verified.mp4",
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="records#verified",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC BY",
                        ),
                        payload={
                            "atom_type": "video_asset",
                            "verification_status": "verified",
                            "duration_seconds": 12,
                            "fps": 30,
                            "width": 640,
                            "height": 480,
                            "codec": "h264",
                        },
                    ),
                ]
            )

            answer = answer_question("show verified Aedes aegypti videos with duration fps resolution and codec", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(len(answer["evidence"]), 1)
            self.assertEqual(answer["evidence"][0]["record_id"], "video_atom:asset:verified")

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

    def test_specific_video_gap_questions_filter_to_requested_reason(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="video_atom:gap:manifest",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video gap video_manifest_gap",
                        text="Aedes aegypti video source gap: video_manifest_gap. Repository: figshare.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="raw/video_atoms/discovery_sweeps.json#figshare/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"atom_type": "video_gap", "reason": "video_manifest_gap", "repository": "figshare"},
                    ),
                    EvidenceRecord(
                        record_id="video_atom:gap:motion-unmatched",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video gap video_motion_unmatched_source_video",
                        text="Aedes aegypti video source gap: video_motion_unmatched_source_video.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="raw/mendeley_behavior_media/table_files/tracks.csv#row/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"atom_type": "video_gap", "reason": "video_motion_unmatched_source_video"},
                    ),
                    EvidenceRecord(
                        record_id="video_atom:gap:not-aedes",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video gap video_discovery_not_aedes_scope",
                        text="Aedes aegypti video source gap: video_discovery_not_aedes_scope. Repository: institutional.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="raw/video_atoms/discovery_sweeps.json#institutional/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"atom_type": "video_gap", "reason": "video_discovery_not_aedes_scope", "repository": "institutional"},
                    ),
                ]
            )

            answer = answer_question("show Aedes video manifest gaps", artifact_dir=artifact_dir, limit=3)

            self.assertTrue(answer["ok"])
            self.assertEqual([item["record_id"] for item in answer["evidence"]], ["video_atom:gap:manifest"])

            motion_answer = answer_question("show Aedes video motion unmatched source video gaps", artifact_dir=artifact_dir, limit=3)

            self.assertTrue(motion_answer["ok"])
            self.assertEqual([item["record_id"] for item in motion_answer["evidence"]], ["video_atom:gap:motion-unmatched"])

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

    def test_plain_missing_license_video_questions_return_gap_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
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
                    EvidenceRecord(
                        record_id="video_atom:gap:osf:license",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video gap video_license_unclear",
                        text=(
                            "Aedes aegypti video source gap: video_license_unclear. Repository: osf. "
                            "Download URL: https://osf.io/download/pu8zf/. Source byte size: 74364708. "
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
                        payload={"atom_type": "video_gap", "reason": "video_license_unclear", "repository": "osf"},
                    ),
                ]
            )

            answer = answer_question(
                "What OSF Aedes aegypti videos are missing because the license is unclear?",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["record_id"], "video_atom:gap:osf:license")
            self.assertIn("video_license_unclear", answer["evidence"][0]["text"])

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

    def test_repository_video_gap_questions_prefer_gap_rows_over_sweeps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="video_atom:sweep:dryad",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video discovery sweep: dryad",
                        text="Aedes aegypti video discovery sweep for dryad: status accepted_candidates.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="raw/video_atoms/discovery_sweeps.json#dryad",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"atom_type": "video_sweep", "repository": "dryad"},
                    ),
                    EvidenceRecord(
                        record_id="video_atom:gap:dryad",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video gap video_download_failed",
                        text="Aedes aegypti video source gap: video_download_failed. Repository: dryad.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="gaps.json#aedes_video_atoms/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"atom_type": "video_gap", "repository": "dryad", "reason": "video_download_failed"},
                    ),
                ]
            )

            answer = answer_question("show Dryad Aedes video gaps", artifact_dir=artifact_dir, limit=1)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["record_id"], "video_atom:gap:dryad")

    def test_named_dryad_video_questions_return_dryad_media_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="video_atom:sweep:dryad",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video discovery sweep: dryad",
                        text="Aedes aegypti video discovery sweep for dryad.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="raw/video_atoms/discovery_sweeps.json#dryad",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"atom_type": "video_sweep", "repository": "dryad"},
                    ),
                    EvidenceRecord(
                        record_id="dryad:dataset:host-seeking",
                        lane="behavior",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti Dryad behavior dataset",
                        text="Dryad behavior dataset for Aedes aegypti host seeking.",
                        species="Aedes aegypti",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/example",
                        media_url=None,
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad_behavior_videos/dataset.json#dataset",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC0",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="dryad:file:host-seeking-videos",
                        lane="media",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti Dryad video/archive file host_seeking_videos.zip",
                        text="Dryad video archive for Aedes aegypti host seeking behavior.",
                        species="Aedes aegypti",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/example",
                        media_url="https://datadryad.org/api/v2/files/10/download",
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad_behavior_videos/files.json#file/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC0",
                        ),
                        payload={"download_url": "https://datadryad.org/api/v2/files/10/download"},
                    ),
                ]
            )

            answer = answer_question("show Dryad Aedes aegypti behavior videos", artifact_dir=artifact_dir, limit=2)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "media")
            self.assertEqual(answer["evidence"][0]["source"], "dryad_aedes_behavior_videos")
            self.assertEqual(answer["evidence"][0]["media_url"], "https://datadryad.org/api/v2/files/10/download")

    def test_specific_dryad_assay_questions_prefer_matching_assay_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="dryad:assay-method:mating",
                        lane="behavior",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti Dryad assay metadata courtship",
                        text=(
                            "Dryad landing-page assay metadata for Aedes aegypti. "
                            "Section: courtship. Behavior labels: mating, hearing. "
                            "Method text: male and female mosquitoes were recorded during courtship and mating."
                        ),
                        species="Aedes aegypti",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/mating",
                        media_url=None,
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad_behavior_videos/mating_landing.html#assay-method/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC0",
                        ),
                        payload={"record_type": "dryad_landing_assay_method"},
                    ),
                    EvidenceRecord(
                        record_id="dryad:assay-method:repellent",
                        lane="behavior",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti Dryad assay metadata repellent response",
                        text=(
                            "Dryad landing-page assay metadata for Aedes aegypti. "
                            "Section: host attraction and repellent response. Behavior labels: host seeking, repellent response. "
                            "Method text: male Aedes aegypti mosquitoes were tested for human host attraction, "
                            "landing observations, and repellent response in tent assays."
                        ),
                        species="Aedes aegypti",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/repellent",
                        media_url=None,
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad_behavior_videos/repellent_landing.html#assay-method/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC0",
                        ),
                        payload={"record_type": "dryad_landing_assay_method"},
                    ),
                ]
            )

            answer = answer_question(
                "show Dryad male host attraction repellent response assay metadata",
                artifact_dir=artifact_dir,
                limit=1,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "behavior")
            self.assertEqual(answer["evidence"][0]["record_id"], "dryad:assay-method:repellent")
            self.assertIn("repellent response", answer["evidence"][0]["text"])

    def test_named_dryad_gap_questions_return_dryad_archive_gap_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="dryad:file:host-seeking-videos",
                        lane="media",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti Dryad video/archive file host_seeking_videos.zip",
                        text="Dryad video archive for Aedes aegypti host seeking behavior.",
                        species="Aedes aegypti",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/example",
                        media_url="https://datadryad.org/api/v2/files/10/download",
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad_behavior_videos/files.json#file/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC0",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="dryad:gap:host-seeking-videos:archive_contents_not_decoded",
                        lane="media",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti Dryad video gap archive contents not decoded host_seeking_videos.zip",
                        text="Aedes aegypti Dryad video source gap: dryad_archive_contents_not_decoded. Source file: host_seeking_videos.zip.",
                        species="Aedes aegypti",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/example",
                        media_url=None,
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad_behavior_videos/files.json#file/1/gap/archive_contents_not_decoded",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC0",
                        ),
                        payload={
                            "atom_type": "video_gap",
                            "reason": "dryad_archive_contents_not_decoded",
                            "repository": "dryad",
                        },
                    ),
                ]
            )

            answer = answer_question("show Dryad archive contents not decoded gaps", artifact_dir=artifact_dir, limit=1)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "media")
            self.assertEqual(answer["evidence"][0]["record_id"], "dryad:gap:host-seeking-videos:archive_contents_not_decoded")
            self.assertIn("dryad_archive_contents_not_decoded", answer["evidence"][0]["text"])

    def test_specific_dryad_archive_gap_questions_prefer_matching_gap_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="dryad:file:figure_s7_zip",
                        lane="media",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti Dryad video/archive file Figure_S7.zip",
                        text="Dryad video archive for Aedes aegypti TRPV mating behavior.",
                        species="Aedes aegypti",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/example",
                        media_url="https://datadryad.org/api/v2/files/3544388/download",
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad_behavior_videos/files.json#file/14",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC0",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="dryad:gap:figure_s7_zip:archive_contents_not_decoded",
                        lane="media",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti Dryad video gap archive contents not decoded Figure_S7.zip",
                        text="Aedes aegypti Dryad video source gap: dryad_archive_contents_not_decoded. Source file: Figure_S7.zip.",
                        species="Aedes aegypti",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/example",
                        media_url=None,
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad_behavior_videos/files.json#file/14/gap/archive_contents_not_decoded",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC0",
                        ),
                        payload={
                            "atom_type": "video_gap",
                            "reason": "dryad_archive_contents_not_decoded",
                            "repository": "dryad",
                        },
                    ),
                    EvidenceRecord(
                        record_id="dryad:gap:figure_1f_zip:archive_contents_not_decoded",
                        lane="media",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti Dryad video gap archive contents not decoded Figure_1F.zip",
                        text="Aedes aegypti Dryad video source gap: dryad_archive_contents_not_decoded. Source file: Figure_1F.zip.",
                        species="Aedes aegypti",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/example",
                        media_url=None,
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad_behavior_videos/files.json#file/1/gap/archive_contents_not_decoded",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC0",
                        ),
                        payload={
                            "atom_type": "video_gap",
                            "reason": "dryad_archive_contents_not_decoded",
                            "repository": "dryad",
                        },
                    ),
                ]
            )

            answer = answer_question("show Dryad Figure_S7 archive gap", artifact_dir=artifact_dir, limit=1)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "media")
            self.assertEqual(answer["evidence"][0]["record_id"], "dryad:gap:figure_s7_zip:archive_contents_not_decoded")

    def test_named_dryad_table_gap_questions_return_table_gap_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="dryad:dataset:host-seeking",
                        lane="behavior",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti Dryad behavior dataset",
                        text="Dryad behavior dataset for Aedes aegypti host seeking.",
                        species="Aedes aegypti",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/example",
                        media_url=None,
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad_behavior_videos/dataset.json#dataset",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC0",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="dryad:table-gap:host-seeking-table:download",
                        lane="behavior",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti Dryad behavior table gap host_seeking.csv",
                        text="Aedes aegypti Dryad table source gap: dryad_table_file_download_or_parse_failed. Source file: host_seeking.csv.",
                        species="Aedes aegypti",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/example",
                        media_url=None,
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad_behavior_videos/files.json#file/1/gap/dryad_table_file_download_or_parse_failed",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC0",
                        ),
                        payload={
                            "atom_type": "table_gap",
                            "reason": "dryad_table_file_download_or_parse_failed",
                            "download_url": "https://datadryad.org/api/v2/files/10/download",
                        },
                    ),
                ]
            )

            answer = answer_question("show Dryad behavior table gaps", artifact_dir=artifact_dir, limit=1)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "behavior")
            self.assertEqual(answer["evidence"][0]["record_id"], "dryad:table-gap:host-seeking-table:download")
            self.assertIn("dryad_table_file_download_or_parse_failed", answer["evidence"][0]["text"])

    def test_named_dryad_preview_table_questions_return_preview_rows_and_gaps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="extracted_fact:behavior:generic",
                        lane="behavior",
                        source="aedes_extracted_facts",
                        title="Aedes aegypti extracted behavior fact",
                        text="Aedes aegypti extracted behavior fact from older literature.",
                        species="Aedes aegypti",
                        url="https://example.org/paper",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_extracted_facts",
                            locator="records#openalex:W1",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="dryad:table-row:10_5061_dryad_tb2rbp04x:female_preferences_ae_aegypti_csv:dryad_preview:r2",
                        lane="behavior",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti Dryad behavior table row Female_preferences_Ae._aegypti.csv dryad_preview row 2",
                        text="Parsed Dryad Aedes aegypti behavior table row. File: Female_preferences_Ae._aegypti.csv. Sheet: dryad_preview. Row: 2. Table source: dryad_preview.",
                        species="Aedes aegypti",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/dryad.tb2rbp04x",
                        media_url=None,
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad_behavior_videos/table_previews/10_5061_dryad_tb2rbp04x_2671955.js#sheet/1/row/2",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC0",
                        ),
                        payload={
                            "table_source": "dryad_preview",
                            "filename": "Female_preferences_Ae._aegypti.csv",
                            "row_number": 2,
                        },
                    ),
                    EvidenceRecord(
                        record_id="dryad:table-gap:10_5061_dryad_tb2rbp04x:female_preferences_ae_aegypti_csv:dryad_table_file_download_blocked_preview_used",
                        lane="behavior",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti Dryad behavior table gap Female_preferences_Ae._aegypti.csv",
                        text="Aedes aegypti Dryad table source gap: dryad_table_file_download_blocked_preview_used. Source file: Female_preferences_Ae._aegypti.csv.",
                        species="Aedes aegypti",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/dryad.tb2rbp04x",
                        media_url=None,
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad_behavior_videos/files.json#file/1/gap/dryad_table_file_download_blocked_preview_used",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC0",
                        ),
                        payload={
                            "atom_type": "table_gap",
                            "reason": "dryad_table_file_download_blocked_preview_used",
                            "preview_url": "https://datadryad.org/data_file/preview/2671955.js",
                        },
                    ),
                    EvidenceRecord(
                        record_id="dryad:table-gap:aaa_parse_failed",
                        lane="behavior",
                        source="dryad_aedes_behavior_videos",
                        title="Aedes aegypti Dryad behavior table gap BehaviorVideoList.xlsx",
                        text="Aedes aegypti Dryad table source gap: dryad_table_file_download_or_parse_failed. Source file: BehaviorVideoList.xlsx.",
                        species="Aedes aegypti",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/dryad.j6q573nr3",
                        media_url=None,
                        provenance=Provenance(
                            source_id="dryad_aedes_behavior_videos",
                            locator="raw/dryad_behavior_videos/files.json#file/1/gap/dryad_table_file_download_or_parse_failed",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="CC0",
                        ),
                        payload={
                            "atom_type": "table_gap",
                            "reason": "dryad_table_file_download_or_parse_failed",
                        },
                    ),
                ]
            )

            row_answer = answer_question(
                "Dryad Female_preferences_Ae._aegypti.csv dryad_preview row 2",
                artifact_dir=artifact_dir,
                limit=1,
            )
            gap_answer = answer_question(
                "show Dryad table gaps where preview was used",
                artifact_dir=artifact_dir,
                limit=1,
            )

            self.assertTrue(row_answer["ok"])
            self.assertEqual(row_answer["evidence"][0]["record_id"], "dryad:table-row:10_5061_dryad_tb2rbp04x:female_preferences_ae_aegypti_csv:dryad_preview:r2")
            self.assertTrue(gap_answer["ok"])
            self.assertEqual(gap_answer["evidence"][0]["record_id"], "dryad:table-gap:10_5061_dryad_tb2rbp04x:female_preferences_ae_aegypti_csv:dryad_table_file_download_blocked_preview_used")

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

    def test_spotted_wing_video_motion_questions_prefer_swd_atoms_not_aedes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="video_atom:motion:aedes:row1",
                        lane="behavior",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video motion row",
                        text="Aedes video motion row with tracking coordinates.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="raw/video_atoms/motion.csv#row/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"atom_type": "video_motion_row", "velocity_mean_cm_s": 2.0},
                    ),
                    EvidenceRecord(
                        record_id="swd:video_atom:motion:row1",
                        lane="behavior",
                        source="drosophila_suzukii_video_atoms",
                        title="Drosophila suzukii video motion row",
                        text="Spotted wing drosophila video motion row with tracking coordinates and confidence.",
                        species="Drosophila suzukii",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_video_atoms",
                            locator="raw/drosophila_suzukii_video_atoms/motion.csv#row/1",
                            retrieved_at="2026-05-28T00:00:00Z",
                        ),
                        payload={"atom_type": "video_motion_row", "velocity_mean_cm_s": 1.5},
                    ),
                    EvidenceRecord(
                        record_id="swd:extracted:behavior:motion",
                        lane="behavior",
                        source="drosophila_suzukii_extracted_facts",
                        title="Drosophila suzukii behavior fact",
                        text="Spotted wing drosophila extracted behavior fact mentioning movement.",
                        species="Drosophila suzukii",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_extracted_facts",
                            locator="records#swd:openalex:W1",
                            retrieved_at="2026-05-28T00:00:00Z",
                        ),
                    ),
                ]
            )

            answer = answer_question("show spotted wing drosophila video motion evidence", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "behavior")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_video_atoms")
            self.assertEqual(answer["evidence"][0]["species"], "Drosophila suzukii")

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
                    EvidenceRecord(
                        record_id="image_atom:label:inat_media_99:alive",
                        lane="media",
                        source="aedes_image_atoms",
                        title="Aedes aegypti image label alive_or_dead: alive",
                        text="Aedes aegypti image label from source metadata: alive_or_dead = alive. Source image record: inat:media:99.",
                        species="Aedes aegypti",
                        url="https://www.inaturalist.org/observations/12345",
                        media_url="https://static.inaturalist.org/photos/99/medium.jpg",
                        provenance=Provenance(
                            source_id="aedes_image_atoms",
                            locator="records#inat:media:99;label/alive_or_dead",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="cc-by",
                        ),
                        payload={
                            "atom_type": "image_label",
                            "label_type": "alive_or_dead",
                            "label_value": "alive",
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

            alive_answer = answer_question("show Aedes aegypti alive image labels", artifact_dir=artifact_dir)

            self.assertTrue(alive_answer["ok"])
            self.assertEqual(alive_answer["evidence"][0]["source"], "aedes_image_atoms")
            self.assertIn("alive_or_dead = alive", alive_answer["evidence"][0]["text"])

    def test_image_atom_questions_can_return_combined_observation_summaries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="image_atom:observation:aaa_dead",
                        lane="media",
                        source="aedes_image_atoms",
                        title="Aedes aegypti image observation summary from inaturalist_api",
                        text=(
                            "Aedes aegypti image observation summary for inat:media:01. "
                            "place: Brazil; observed on: 2026-05-01; life_stage: adult; sex: female; alive_or_dead: dead."
                        ),
                        species="Aedes aegypti",
                        url="https://www.inaturalist.org/observations/1",
                        media_url="raw/image_atoms/assets/inat_media_01.jpg",
                        provenance=Provenance(
                            source_id="aedes_image_atoms",
                            locator="records#inat:media:01;image_observation_summary",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="cc-by",
                        ),
                        payload={
                            "atom_type": "image_observation",
                            "source_record_id": "inat:media:01",
                            "source": "inaturalist_api",
                            "input_source": "inaturalist_api",
                            "place": "Brazil",
                            "label_values": {"life_stage": ["adult"], "sex": ["female"], "alive_or_dead": ["dead"]},
                        },
                    ),
                    EvidenceRecord(
                        record_id="image_atom:observation:inat_media_99",
                        lane="media",
                        source="aedes_image_atoms",
                        title="Aedes aegypti image observation summary from inaturalist_api",
                        text=(
                            "Aedes aegypti image observation summary for inat:media:99. "
                            "place: Brazil; observed on: 2026-05-01; life_stage: adult; sex: female; alive_or_dead: alive."
                        ),
                        species="Aedes aegypti",
                        url="https://www.inaturalist.org/observations/12345",
                        media_url="raw/image_atoms/assets/inat_media_99.jpg",
                        provenance=Provenance(
                            source_id="aedes_image_atoms",
                            locator="records#inat:media:99;image_observation_summary",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="cc-by",
                        ),
                        payload={
                            "atom_type": "image_observation",
                            "source_record_id": "inat:media:99",
                            "source": "inaturalist_api",
                            "input_source": "inaturalist_api",
                            "place": "Brazil",
                            "label_values": {"life_stage": ["adult"], "sex": ["female"], "alive_or_dead": ["alive"]},
                        },
                    ),
                    EvidenceRecord(
                        record_id="image_atom:label:inat_media_99:alive",
                        lane="media",
                        source="aedes_image_atoms",
                        title="Aedes aegypti image label alive_or_dead: alive",
                        text="Aedes aegypti image label from source metadata: alive_or_dead = alive. Source image record: inat:media:99.",
                        species="Aedes aegypti",
                        url="https://www.inaturalist.org/observations/12345",
                        media_url="https://static.inaturalist.org/photos/99/medium.jpg",
                        provenance=Provenance(
                            source_id="aedes_image_atoms",
                            locator="records#inat:media:99;label/alive_or_dead",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="cc-by",
                        ),
                        payload={"atom_type": "image_label", "label_type": "alive_or_dead", "label_value": "alive"},
                    ),
                ]
            )

            answer = answer_question("show Aedes aegypti Brazil female alive image evidence", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["record_id"], "image_atom:observation:inat_media_99")
            self.assertIn("place: Brazil", answer["evidence"][0]["text"])
            self.assertIn("sex: female", answer["evidence"][0]["text"])

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

    def test_image_coverage_questions_return_summary_records(self):
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
                        text="Aedes aegypti image label gap: inaturalist_api has 4 image asset(s) without source-provided sex metadata.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_image_atoms",
                            locator="gaps.json#aedes_image_atoms/1",
                            retrieved_at="2026-05-25T00:00:00Z",
                        ),
                        payload={"atom_type": "image_gap", "reason": "image_label_missing", "label_type": "sex"},
                    ),
                    EvidenceRecord(
                        record_id="image_atom:coverage:inaturalist_api",
                        lane="media",
                        source="aedes_image_atoms",
                        title="Aedes aegypti image label coverage: inaturalist_api",
                        text=(
                            "Aedes aegypti image-label coverage summary for inaturalist_api: 10 image asset(s). "
                            "life_stage: 6 present, 4 missing; sex: 2 present, 8 missing."
                        ),
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_image_atoms",
                            locator="records#aedes_image_atoms/image_label_coverage/inaturalist_api",
                            retrieved_at="2026-05-25T00:00:00Z",
                        ),
                        payload={
                            "atom_type": "image_coverage",
                            "input_source": "inaturalist_api",
                            "asset_count": 10,
                            "label_counts": {"life_stage": 6, "sex": 2},
                            "missing_counts": {"life_stage": 4, "sex": 8},
                        },
                    ),
                ]
            )

            answer = answer_question("show Aedes image label coverage summary", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "evidence")
            self.assertEqual(answer["evidence"][0]["record_id"], "image_atom:coverage:inaturalist_api")
            self.assertIn("10 image asset", answer["evidence"][0]["text"])

    def test_image_checksum_questions_prefer_verified_image_assets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="image_atom:label:inat_media_99:quality",
                        lane="media",
                        source="aedes_image_atoms",
                        title="Aedes aegypti image label quality_grade: research",
                        text="Aedes aegypti image label from source metadata: quality_grade = research.",
                        species="Aedes aegypti",
                        url="https://www.inaturalist.org/observations/12345",
                        media_url="https://static.inaturalist.org/photos/99/medium.jpg",
                        provenance=Provenance(
                            source_id="aedes_image_atoms",
                            locator="records#inat:media:99;label/quality_grade",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="cc-by",
                        ),
                        payload={"atom_type": "image_label", "label_type": "quality_grade", "label_value": "research"},
                    ),
                    EvidenceRecord(
                        record_id="image_atom:asset:inat_media_99",
                        lane="media",
                        source="aedes_image_atoms",
                        title="Aedes aegypti image asset from inaturalist_api",
                        text="Aedes aegypti source image asset with SHA-256 checksum, byte size, and 1x1 dimensions.",
                        species="Aedes aegypti",
                        url="https://www.inaturalist.org/observations/12345",
                        media_url="raw/image_atoms/assets/inat_media_99.png",
                        provenance=Provenance(
                            source_id="aedes_image_atoms",
                            locator="records#inat:media:99",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="cc-by",
                        ),
                        payload={
                            "atom_type": "image_asset",
                            "verification_status": "verified",
                            "sha256": "abc123",
                            "byte_size": 67,
                            "width": 1,
                            "height": 1,
                            "raw_asset_path": "raw/image_atoms/assets/inat_media_99.png",
                        },
                    ),
                ]
            )

            answer = answer_question("show Aedes aegypti images with checksum and dimensions", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "evidence")
            self.assertEqual(answer["evidence"][0]["record_id"], "image_atom:asset:inat_media_99")

    def test_image_source_questions_filter_to_named_upstream_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="image_atom:asset:inat_media_01",
                        lane="media",
                        source="aedes_image_atoms",
                        title="Aedes aegypti image asset from inaturalist_api",
                        text="Aedes aegypti source image asset derived from inaturalist_api.",
                        species="Aedes aegypti",
                        url="https://www.inaturalist.org/observations/1",
                        media_url="raw/image_atoms/assets/inat_media_01.jpg",
                        provenance=Provenance(
                            source_id="aedes_image_atoms",
                            locator="records#inat:media:1",
                            retrieved_at="2026-05-25T00:00:00Z",
                        ),
                        payload={
                            "atom_type": "image_asset",
                            "source": "inaturalist_api",
                            "input_source": "inaturalist_api",
                            "verification_status": "verified",
                            "sha256": "inat",
                            "width": 75,
                            "height": 75,
                        },
                    ),
                    EvidenceRecord(
                        record_id="image_atom:asset:mosquito_alert_media_01",
                        lane="media",
                        source="aedes_image_atoms",
                        title="Aedes aegypti image asset from mosquito_alert_gbif",
                        text="Aedes aegypti source image asset derived from mosquito_alert_gbif.",
                        species="Aedes aegypti",
                        url="https://www.gbif.org/occurrence/1",
                        media_url="raw/image_atoms/assets/mosquito_alert_media_01.jpg",
                        provenance=Provenance(
                            source_id="aedes_image_atoms",
                            locator="records#mosquito_alert:media:1",
                            retrieved_at="2026-05-25T00:00:00Z",
                        ),
                        payload={
                            "atom_type": "image_asset",
                            "source": "mosquito_alert_gbif",
                            "input_source": "mosquito_alert_gbif",
                            "verification_status": "verified",
                            "sha256": "mosquito-alert",
                            "width": 75,
                            "height": 75,
                        },
                    ),
                ]
            )

            answer = answer_question("show Mosquito Alert Aedes image mirrors with checksum and dimensions", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "evidence")
            self.assertEqual(answer["evidence"][0]["record_id"], "image_atom:asset:mosquito_alert_media_01")

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

    def test_supplement_table_questions_prefer_promoted_vector_assay_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            records = [
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
                        locator="records#WZZZ;supplement#0;raw/extracted_facts/supplements/WZZZ.csv;row#1",
                        retrieved_at="2026-05-24T00:00:00Z",
                        license="CC-BY",
                        source_url="https://example.org/dengue",
                    ),
                ),
                EvidenceRecord(
                    record_id="assay_table:vector_competence:WZZZ:dengue",
                    lane="vector_competence",
                    source="aedes_vector_competence_assays",
                    title="Aedes aegypti parsed vector competence table row: dengue virus",
                    text=(
                        "Schema-validated parsed supplement table row for dengue virus in Aedes aegypti. "
                        "Validation status: schema_validated, not human_validated. "
                        "Table row: DENV-1 infection rate 80%, dissemination rate 40%, transmission rate 20%."
                    ),
                    species="Aedes aegypti",
                    url="https://example.org/dengue",
                    media_url=None,
                    provenance=Provenance(
                        source_id="aedes_vector_competence_assays",
                        locator="aedes_extracted_facts#extracted_fact:vector_competence:WZZZ:dengue;records#WZZZ;row#1",
                        retrieved_at="2026-05-24T00:00:00Z",
                        license="CC-BY",
                        source_url="https://example.org/dengue",
                    ),
                    payload={"confidence": "parsed_table_schema_validated", "pathogen": "dengue virus"},
                ),
            ]
            records.extend(
                EvidenceRecord(
                    record_id=f"assay_candidate:vector_competence:WBROAD:{i:02d}",
                    lane="vector_competence",
                    source="aedes_vector_competence_assays",
                    title="Aedes aegypti vector competence assay candidate: dengue virus",
                    text="Structured assay-candidate extraction for dengue virus. Infection rate and transmission in a broad full-text chunk.",
                    species="Aedes aegypti",
                    url="https://example.org/broad",
                    media_url=None,
                    provenance=Provenance(
                        source_id="aedes_vector_competence_assays",
                        locator=f"records#WBROAD{i};literature_fulltext_units#WBROAD{i}:fulltext:0",
                        retrieved_at="2026-05-24T00:00:00Z",
                        license="CC-BY",
                        source_url="https://example.org/broad",
                    ),
                )
                for i in range(60)
            )
            index.upsert_records(records)

            answer = answer_question(
                "show dengue vector competence supplement table infection rate for Aedes aegypti",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["source"], "aedes_vector_competence_assays")
            self.assertEqual(answer["evidence"][0]["record_id"], "assay_table:vector_competence:WZZZ:dengue")

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

    def test_vectorbase_ortholog_questions_route_to_orthomcl_pairs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="vectorbase:ortholog:aaeg-old_AAEL000076:aaeo_O67680:1",
                        lane="genome_features",
                        source="vectorbase_aedes_genomics",
                        title="Aedes aegypti OrthoMCL ortholog AAEL000076 to aaeo|O67680",
                        text="OrthoMCL CURRENT ortholog pair for Aedes aegypti gene AAEL000076 (aaeg-old|AAEL000076) with partner aaeo|O67680, score 0.352.",
                        species="Aedes aegypti",
                        url="https://orthomcl.org/common/downloads/release-6.21/corePairs_OrthoMCL-CURRENT/orthologs.txt.gz",
                        media_url=None,
                        provenance=Provenance(
                            source_id="vectorbase_aedes_genomics",
                            locator="raw/vectorbase_genomics/orthologs.txt.gz#line/1",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="OrthoMCL public download; source terms apply",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="ncbi:gene:AAEL000076",
                        lane="genes",
                        source="ncbi_datasets_genome",
                        title="Aedes aegypti NCBI gene AAEL000076",
                        text="NCBI gene AAEL000076 for Aedes aegypti.",
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
                ]
            )

            answer = answer_question("show AAEL000076 orthologs for Aedes aegypti", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["record_id"], "vectorbase:ortholog:aaeg-old_AAEL000076:aaeo_O67680:1")

    def test_vectorbase_coortholog_inparalog_questions_route_to_orthomcl_pairs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="vectorbase:ortholog:aaeg-old_AAEL000076:aaeo_O67680:1",
                        lane="genome_features",
                        source="vectorbase_aedes_genomics",
                        title="Aedes aegypti OrthoMCL ortholog AAEL000076 to aaeo|O67680",
                        text="OrthoMCL CURRENT ortholog pair for Aedes aegypti gene AAEL000076 (aaeg-old|AAEL000076) with partner aaeo|O67680, score 0.352.",
                        species="Aedes aegypti",
                        url="https://orthomcl.org/common/downloads/release-6.21/corePairs_OrthoMCL-CURRENT/orthologs.txt.gz",
                        media_url=None,
                        provenance=Provenance(
                            source_id="vectorbase_aedes_genomics",
                            locator="raw/vectorbase_genomics/orthologs.txt.gz#line/1",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="OrthoMCL public download; source terms apply",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="vectorbase:coortholog:aaeg-old_AAEL000076:aaec_C076:1",
                        lane="genome_features",
                        source="vectorbase_aedes_genomics",
                        title="Aedes aegypti OrthoMCL coortholog AAEL000076 to aaec|C076",
                        text="OrthoMCL CURRENT coortholog pair for Aedes aegypti gene AAEL000076 (aaeg-old|AAEL000076) with partner aaec|C076, score 0.500.",
                        species="Aedes aegypti",
                        url="https://orthomcl.org/common/downloads/release-6.21/corePairs_OrthoMCL-CURRENT/coorthologs.txt.gz",
                        media_url=None,
                        provenance=Provenance(
                            source_id="vectorbase_aedes_genomics",
                            locator="raw/vectorbase_genomics/coorthologs.txt.gz#line/1",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="OrthoMCL public download; source terms apply",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="vectorbase:inparalog:aaeg-old_AAEL000076:aaeg-old_AAEL999999:1",
                        lane="genome_features",
                        source="vectorbase_aedes_genomics",
                        title="Aedes aegypti OrthoMCL inparalog AAEL000076 to aaeg-old|AAEL999999",
                        text="OrthoMCL CURRENT inparalog pair for Aedes aegypti gene AAEL000076 (aaeg-old|AAEL000076) with partner aaeg-old|AAEL999999, score 0.900.",
                        species="Aedes aegypti",
                        url="https://orthomcl.org/common/downloads/release-6.21/corePairs_OrthoMCL-CURRENT/inparalogs.txt.gz",
                        media_url=None,
                        provenance=Provenance(
                            source_id="vectorbase_aedes_genomics",
                            locator="raw/vectorbase_genomics/inparalogs.txt.gz#line/1",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="OrthoMCL public download; source terms apply",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="vectorbase:gap:advanced_orthology_current_id_resolution",
                        lane="genome_features",
                        source="vectorbase_aedes_genomics",
                        title="Aedes aegypti VectorBase advanced orthology source gap",
                        text="VectorBase genomics source gap: Ask Insects currently indexes first-pass OrthoMCL CURRENT ortholog, coortholog, and inparalog pair rows in the old AAEL namespace, not orthogroups.",
                        species="Aedes aegypti",
                        url="https://orthomcl.org/common/downloads/release-6.21/corePairs_OrthoMCL-CURRENT",
                        media_url=None,
                        provenance=Provenance(
                            source_id="vectorbase_aedes_genomics",
                            locator="raw/vectorbase_genomics/source_boundary.json#gap/advanced_orthology_current_id_resolution",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="Ask Insects source boundary audit",
                        ),
                        payload={"atom_type": "source_gap", "reason": "orthogroups_not_indexed"},
                    ),
                ]
            )

            answer = answer_question("show AAEL000076 coorthologs and inparalogs for Aedes aegypti", artifact_dir=artifact_dir)
            evidence_ids = [item["record_id"] for item in answer["evidence"]]

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertTrue(answer["evidence"][0]["record_id"].startswith("vectorbase:coortholog:"))
            self.assertIn("vectorbase:coortholog:aaeg-old_AAEL000076:aaec_C076:1", evidence_ids)
            self.assertIn("vectorbase:inparalog:aaeg-old_AAEL000076:aaeg-old_AAEL999999:1", evidence_ids)
            self.assertNotEqual(answer["evidence"][0]["record_id"], "vectorbase:gap:advanced_orthology_current_id_resolution")

    def test_vectorbase_broad_relationship_questions_use_indexed_prefix_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="vectorbase:ortholog:aaeg-old_AAEL000001:aast-old_H257_01817:385",
                        lane="genome_features",
                        source="vectorbase_aedes_genomics",
                        title="Aedes aegypti OrthoMCL ortholog AAEL000001 to aast-old|H257_01817",
                        text="OrthoMCL CURRENT ortholog pair for Aedes aegypti gene AAEL000001.",
                        species="Aedes aegypti",
                        url="https://orthomcl.org/orthologs.txt.gz",
                        media_url=None,
                        provenance=Provenance(source_id="vectorbase_aedes_genomics", locator="orthologs.txt.gz#line/385", retrieved_at="2026-05-25T00:00:00Z"),
                    ),
                    EvidenceRecord(
                        record_id="vectorbase:coortholog:aaeg-old_AAEL000001:acas-old_ACA1_188870:1853",
                        lane="genome_features",
                        source="vectorbase_aedes_genomics",
                        title="Aedes aegypti OrthoMCL coortholog AAEL000001 to acas-old|ACA1_188870",
                        text="OrthoMCL CURRENT coortholog pair for Aedes aegypti gene AAEL000001.",
                        species="Aedes aegypti",
                        url="https://orthomcl.org/coorthologs.txt.gz",
                        media_url=None,
                        provenance=Provenance(source_id="vectorbase_aedes_genomics", locator="coorthologs.txt.gz#line/1853", retrieved_at="2026-05-25T00:00:00Z"),
                    ),
                    EvidenceRecord(
                        record_id="vectorbase:inparalog:aaeg-old_AAEL000006:aaeg-old_AAEL000025:1",
                        lane="genome_features",
                        source="vectorbase_aedes_genomics",
                        title="Aedes aegypti OrthoMCL inparalog AAEL000006 to aaeg-old|AAEL000025",
                        text="OrthoMCL CURRENT inparalog pair for Aedes aegypti gene AAEL000006.",
                        species="Aedes aegypti",
                        url="https://orthomcl.org/inparalogs.txt.gz",
                        media_url=None,
                        provenance=Provenance(source_id="vectorbase_aedes_genomics", locator="inparalogs.txt.gz#line/1", retrieved_at="2026-05-25T00:00:00Z"),
                    ),
                ]
            )

            coortholog_answer = answer_question("show Aedes aegypti coortholog records from OrthoMCL", artifact_dir=artifact_dir)
            inparalog_answer = answer_question("show Aedes aegypti inparalog records from OrthoMCL", artifact_dir=artifact_dir)

            self.assertTrue(coortholog_answer["evidence"][0]["record_id"].startswith("vectorbase:coortholog:"))
            self.assertTrue(inparalog_answer["evidence"][0]["record_id"].startswith("vectorbase:inparalog:"))

    def test_orthogroup_questions_prefer_queryable_orthogroup_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="vectorbase:orthogroup:OG6_100000:aaeg_AAEL000076",
                        lane="genome_features",
                        source="vectorbase_aedes_genomics",
                        title="Aedes aegypti OrthoMCL orthogroup OG6_100000 member AAEL000076",
                        text="OrthoMCL orthogroup OG6_100000 contains Aedes aegypti member aaeg|AAEL000076; the group has 3 total members and 2 Aedes members.",
                        species="Aedes aegypti",
                        url="https://orthomcl.org/common/downloads/release-6.21/groups_OrthoMCL-6.21.txt.gz",
                        media_url=None,
                        provenance=Provenance(
                            source_id="vectorbase_aedes_genomics",
                            locator="raw/vectorbase_genomics/groups_OrthoMCL-6.21.txt.gz#line/1",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="OrthoMCL public download; source terms apply",
                        ),
                        payload={
                            "atom_type": "orthogroup_membership",
                            "orthogroup_id": "OG6_100000",
                            "aedes_gene_id": "AAEL000076",
                        },
                    ),
                    EvidenceRecord(
                        record_id="vectorbase:orthogroup:OG6_999999:aaeg_AAEL999999",
                        lane="genome_features",
                        source="vectorbase_aedes_genomics",
                        title="Aedes aegypti OrthoMCL orthogroup OG6_999999 member AAEL999999",
                        text="OrthoMCL orthogroup OG6_999999 contains Aedes aegypti member aaeg|AAEL999999.",
                        species="Aedes aegypti",
                        url="https://orthomcl.org/common/downloads/release-6.21/groups_OrthoMCL-6.21.txt.gz",
                        media_url=None,
                        provenance=Provenance(
                            source_id="vectorbase_aedes_genomics",
                            locator="raw/vectorbase_genomics/groups_OrthoMCL-6.21.txt.gz#line/999",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="OrthoMCL public download; source terms apply",
                        ),
                        payload={
                            "atom_type": "orthogroup_membership",
                            "orthogroup_id": "OG6_999999",
                            "aedes_gene_id": "AAEL999999",
                        },
                    ),
                    EvidenceRecord(
                        record_id="video_atom:asset:irrelevant",
                        lane="media",
                        source="aedes_video_atoms",
                        title="Aedes aegypti video asset irrelevant",
                        text="Aedes aegypti video asset with a source table.",
                        species="Aedes aegypti",
                        url="https://example.org/video",
                        media_url="https://example.org/video.mp4",
                        provenance=Provenance(
                            source_id="aedes_video_atoms",
                            locator="raw/video_atoms/assets.json#asset/1",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="test",
                        ),
                    ),
                ]
            )

            answer = answer_question(
                "show Aedes aegypti orthogroups current ID resolution",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["source"], "vectorbase_aedes_genomics")
            self.assertEqual(answer["evidence"][0]["record_id"], "vectorbase:orthogroup:OG6_100000:aaeg_AAEL000076")
            self.assertIn("orthogroup OG6_100000", answer["answer"])

            exact_answer = answer_question(
                "show Aedes aegypti OrthoMCL orthogroup for AAEL999999",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(exact_answer["ok"])
            self.assertEqual(exact_answer["evidence"][0]["record_id"], "vectorbase:orthogroup:OG6_999999:aaeg_AAEL999999")

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
                    EvidenceRecord(
                        record_id="vectorbase:current_id:AAEL000905",
                        lane="genome_features",
                        source="vectorbase_aedes_genomics",
                        title="Aedes aegypti VectorBase current ID resolution AAEL000905 to AAEL123456",
                        text="VectorBase current identifier resolution for Aedes aegypti AAEL000905: current ID AAEL123456, event merge, release VB-2026-05, date 2026-05.",
                        species="Aedes aegypti",
                        url="https://vectorbase.org/id_events.tab",
                        media_url=None,
                        provenance=Provenance(
                            source_id="vectorbase_aedes_genomics",
                            locator="raw/vectorbase_genomics/VectorBase-68_AaegyptiLVP_AGWG_ids_events.tab#line/2",
                            retrieved_at="2026-05-24T00:00:00Z",
                            license="VectorBase/VEuPathDB public download; source terms apply",
                        ),
                        payload={
                            "atom_type": "current_id_resolution",
                            "old_id": "AAEL000905",
                            "current_id": "AAEL123456",
                            "resolution_status": "successor",
                        },
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

            answer = answer_question(
                "show VectorBase current ID resolution for AAEL000905",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["record_id"], "vectorbase:current_id:AAEL000905")

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

    def test_swd_genbank_nucleotide_questions_prefer_ncbi_crosscheck_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd:genome:gff:gene:orco",
                        lane="genes",
                        source="drosophila_suzukii_genome_files",
                        title="Drosophila suzukii gene Orco",
                        text="Drosophila suzukii genome GFF gene row.",
                        species="Drosophila suzukii",
                        url="https://example.org/gff",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_genome_files",
                            locator="raw/gff#gene/orco",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="swd_ncbi_nucleotide:nuccore:PV080836.1",
                        lane="dna_barcodes",
                        source="drosophila_suzukii_ncbi_nucleotide",
                        title="Drosophila suzukii voucher UHIM.BRU_04107 cytochrome oxidase subunit 1 (COI) gene",
                        text="Drosophila suzukii NCBI GenBank nucleotide cross-check. accession=PV080836.1 marker=COI/COX1 bold_match_status=bold_accession_matched sequence_length=659 bp",
                        species="Drosophila suzukii",
                        url="https://www.ncbi.nlm.nih.gov/nuccore/PV080836.1",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_ncbi_nucleotide",
                            locator="raw/drosophila_suzukii_ncbi_nucleotide/nuccore_esummary_0001.json#result/3040293388",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={"accession": "PV080836", "bold_match_status": "bold_accession_matched"},
                    ),
                ]
            )

            answer = answer_question(
                "show Drosophila suzukii GenBank COI nucleotide cross-check",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_ncbi_nucleotide")
            self.assertEqual(answer["evidence"][0]["record_id"], "swd_ncbi_nucleotide:nuccore:PV080836.1")

    def test_swd_variant_questions_prefer_swd_dbsnp_audit_gap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd:genome:gff:gene:variantlike",
                        lane="genome_features",
                        source="drosophila_suzukii_genome_files",
                        title="Drosophila suzukii genome feature",
                        text="Drosophila suzukii genome GFF feature row.",
                        species="Drosophila suzukii",
                        url="https://example.org/gff",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_genome_files",
                            locator="raw/gff#feature",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="swd_ncbi_snp_variation:gap:drosophila_suzukii:ncbi_snp_no_swd_records",
                        lane="genome_features",
                        source="drosophila_suzukii_ncbi_snp_variation",
                        title="Drosophila suzukii NCBI dbSNP variation source gap",
                        text="NCBI dbSNP returned zero records for Drosophila suzukii using the bounded organism query.",
                        species="Drosophila suzukii",
                        url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_ncbi_snp_variation",
                            locator="raw/drosophila_suzukii_ncbi_snp_variation/Drosophila_suzukii_snp_esearch_000000.json#gap/ncbi_snp_no_swd_records",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={"gap": {"reason": "ncbi_snp_no_swd_records"}},
                    ),
                ]
            )

            answer = answer_question(
                "show Drosophila suzukii dbSNP variant records",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_ncbi_snp_variation")

    def test_swd_mk_selection_questions_prefer_figshare_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd:genome:gff:gene:DS20_00004020",
                        lane="genes",
                        source="drosophila_suzukii_genome_files",
                        title="Drosophila suzukii gene DS20_00004020",
                        text="Genome gene metadata, not MK table evidence.",
                        species="Drosophila suzukii",
                        url="https://example.org/gff",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_genome_files",
                            locator="raw/gff#gene",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="swd_figshare_mk_selection:DS20_00004020:r1",
                        lane="genome_features",
                        source="drosophila_suzukii_figshare_mk_selection",
                        title="Drosophila suzukii Figshare MK selection row: DS20_00004020",
                        text="Figshare McDonald-Kreitman selection row for Drosophila suzukii gene DS20_00004020. D. melanogaster homolog: FBgn0037025. Method 1 alpha: 0.297292584. Method 1 Fisher exact p value: 0.01017457.",
                        species="Drosophila suzukii",
                        url="https://figshare.com/articles/dataset/Suzukii_Subpulchrella_Sig_MK_two_methods_csv/13366079/3",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_figshare_mk_selection",
                            locator="raw/drosophila_suzukii_figshare_mk_selection/Suzukii.Subpulchrella.Sig.MK_two_methods.csv#row/1",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={
                            "atom_type": "figshare_mk_selection_row",
                            "d_suzukii_gene": "DS20_00004020",
                            "d_melanogaster_gene": "FBgn0037025",
                            "method_1": {"FETpval": 0.01017457, "alpha": 0.297292584},
                            "method_2": {"P-value": 0.0424, "Alpha": 0.301},
                        },
                    ),
                ]
            )

            from unittest.mock import patch

            with patch("askinsects.answer.SourceIndex.search") as search:
                search.side_effect = AssertionError("SWD MK questions should answer from the direct Figshare MK lane")
                answer = answer_question(
                    "show Drosophila suzukii Figshare MK test rows for DS20_00004020",
                    artifact_dir=artifact_dir,
                )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_figshare_mk_selection")

            answer = answer_question(
                "which spotted wing drosophila MK test rows have significant alpha or positive selection evidence?",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["record_id"], "swd_figshare_mk_selection:DS20_00004020:r1")

    def test_swd_population_genomics_questions_prefer_bioproject_lane(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd:genome_files:gene:gene-128up",
                        lane="genes",
                        source="drosophila_suzukii_genome_files",
                        title="Drosophila suzukii gene 128up",
                        text="Generic genome gene metadata, not population genomics evidence.",
                        species="Drosophila suzukii",
                        url="https://example.org/gff",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_genome_files",
                            locator="raw/gff#gene",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="swd_population_genomics:bioproject:PRJNA1289399",
                        lane="genome_features",
                        source="drosophila_suzukii_population_genomics",
                        title="Drosophila suzukii population genomics BioProject PRJNA1289399",
                        text="NCBI BioProject population-genomics record PRJNA1289399 for Drosophila suzukii. Title: Pool-seq data from 3 Drosophila suzukii populations collected in Northern Portugal.",
                        species="Drosophila suzukii",
                        url="https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1289399",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_population_genomics",
                            locator="raw/drosophila_suzukii_population_genomics/summary.json#result/1289399",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                    ),
                ]
            )

            answer = answer_question(
                "show Drosophila suzukii population genomics BioProject records",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_population_genomics")

    def test_swd_non_dbsnp_variant_questions_prefer_dryad_vcf_lane(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd_ncbi_snp_variation:gap:drosophila_suzukii:ncbi_snp_no_swd_records",
                        lane="genome_features",
                        source="drosophila_suzukii_ncbi_snp_variation",
                        title="Drosophila suzukii NCBI dbSNP variation source gap",
                        text="NCBI dbSNP returned zero records for Drosophila suzukii.",
                        species="Drosophila suzukii",
                        url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_ncbi_snp_variation",
                            locator="raw/dbsnp#gap",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="swd_dryad_population_variants:file:620083",
                        lane="genome_features",
                        source="drosophila_suzukii_dryad_population_variants",
                        title="Drosophila suzukii Dryad population variant file SNPs-q30-original-SWD.vcf.gz",
                        text="Dryad file manifest for Drosophila suzukii population variants. File: SNPs-q30-original-SWD.vcf.gz. Size: 18752495016 bytes.",
                        species="Drosophila suzukii",
                        url="https://doi.org/10.25338/B89P86",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_dryad_population_variants",
                            locator="raw/dryad/files.json#files/2",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                    ),
                ]
            )

            answer = answer_question(
                "show Drosophila suzukii non-dbSNP variant table evidence",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_dryad_population_variants")
            self.assertEqual(answer["evidence"][0]["record_id"], "swd_dryad_population_variants:file:620083")

            dbsnp = answer_question("show Drosophila suzukii dbSNP variant records", artifact_dir=artifact_dir)

            self.assertTrue(dbsnp["ok"])
            self.assertEqual(dbsnp["evidence"][0]["source"], "drosophila_suzukii_ncbi_snp_variation")

    def test_swd_expression_matrix_questions_prefer_geo_matrix_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd:sra:1",
                        lane="expression",
                        source="drosophila_suzukii_deep_sources",
                        title="Drosophila suzukii SRA run",
                        text="NCBI SRA run metadata for Drosophila suzukii.",
                        species="Drosophila suzukii",
                        url="https://example.org/sra",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_deep_sources",
                            locator="raw/sra.json#1",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="swd_geo_expression:GSE126708:file:r1",
                        lane="expression",
                        source="drosophila_suzukii_geo_expression_matrices",
                        title="Drosophila suzukii GEO differential expression: GSE126708 DS10_00000001",
                        text="GEO differential-expression row for Drosophila suzukii gene DS10_00000001. Accession: GSE126708. log2 fold change: -0.47. q value: 0.02. Significant: yes.",
                        species="Drosophila suzukii",
                        url="https://example.org/GSE126708.txt.gz",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_geo_expression_matrices",
                            locator="raw/geo/GSE126708.txt.gz#row/1",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={
                            "atom_type": "geo_differential_expression_row",
                            "accession": "GSE126708",
                            "gene": "DS10_00000001",
                            "significant": True,
                        },
                    ),
                    EvidenceRecord(
                        record_id="swd_geo_expression:GSE73595:file:r1",
                        lane="expression",
                        source="drosophila_suzukii_geo_expression_matrices",
                        title="Drosophila suzukii GEO differential expression: GSE73595 DS10_00000002",
                        text="GEO differential-expression row for Drosophila suzukii gene DS10_00000002. Accession: GSE73595. Significant: yes.",
                        species="Drosophila suzukii",
                        url="https://example.org/GSE73595.txt.gz",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_geo_expression_matrices",
                            locator="raw/geo/GSE73595.txt.gz#row/1",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={
                            "atom_type": "geo_differential_expression_row",
                            "accession": "GSE73595",
                            "gene": "DS10_00000002",
                            "significant": True,
                        },
                    ),
                ]
            )

            from unittest.mock import patch

            with patch("askinsects.answer._exact_extracted_fact_identifier_records") as exact_records:
                exact_records.side_effect = AssertionError("SWD GEO expression questions should use the direct matrix lane")
                answer = answer_question(
                    "show Drosophila suzukii GSE126708 differential expression matrix rows",
                    artifact_dir=artifact_dir,
                )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "expression")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_geo_expression_matrices")

            with patch("askinsects.answer._exact_extracted_fact_identifier_records") as exact_records:
                exact_records.side_effect = AssertionError("SWD GEO expression questions should use the direct matrix lane")
                answer = answer_question(
                    "show significant Drosophila suzukii GSE73595 differential expression matrix rows",
                    artifact_dir=artifact_dir,
                )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["record_id"], "swd_geo_expression:GSE73595:file:r1")

    def test_swd_marker_review_questions_prefer_marker_review_lane(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd:genome:gff:gene:orco",
                        lane="genes",
                        source="drosophila_suzukii_genome_files",
                        title="Drosophila suzukii gene Orco",
                        text="Drosophila suzukii genome GFF gene row.",
                        species="Drosophila suzukii",
                        url="https://example.org/gff",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_genome_files",
                            locator="raw/gff#gene/orco",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="swd_ncbi_marker_review:nuccore:PV000002.1",
                        lane="dna_barcodes",
                        source="drosophila_suzukii_ncbi_marker_review",
                        title="Drosophila suzukii internal transcribed spacer 2",
                        text="Drosophila suzukii NCBI broader marker-review record. accession=PV000002.1 marker_group=nuclear_ribosomal_or_its sequence_length=420 bp",
                        species="Drosophila suzukii",
                        url="https://www.ncbi.nlm.nih.gov/nuccore/PV000002.1",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_ncbi_marker_review",
                            locator="raw/drosophila_suzukii_ncbi_marker_review/Drosophila_suzukii_marker_review_esummary_000000.json#result/2",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={"atom_type": "ncbi_marker_review", "marker_group": "nuclear_ribosomal_or_its"},
                    ),
                    EvidenceRecord(
                        record_id="swd_ncbi_marker_review:nuccore:PV000003.1",
                        lane="dna_barcodes",
                        source="drosophila_suzukii_ncbi_marker_review",
                        title="Drosophila suzukii cytochrome oxidase subunit I",
                        text="Drosophila suzukii NCBI broader marker-review record. accession=PV000003.1 marker_group=mitochondrial_coi_barcode sequence_length=658 bp",
                        species="Drosophila suzukii",
                        url="https://www.ncbi.nlm.nih.gov/nuccore/PV000003.1",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_ncbi_marker_review",
                            locator="raw/drosophila_suzukii_ncbi_marker_review/Drosophila_suzukii_marker_review_esummary_000000.json#result/3",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={"atom_type": "ncbi_marker_review", "marker_group": "mitochondrial_coi_barcode"},
                    ),
                ]
            )

            answer = answer_question(
                "show Drosophila suzukii nuclear marker review",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_ncbi_marker_review")
            self.assertEqual(answer["evidence"][0]["record_id"], "swd_ncbi_marker_review:nuccore:PV000002.1")

    def test_swd_ortholog_questions_prefer_ncbi_gene_orthologs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd:genome_files:gene:gene-Orco",
                        lane="genes",
                        source="drosophila_suzukii_genome_files",
                        title="Drosophila suzukii gene Orco",
                        text="Drosophila suzukii genome GFF gene row for odorant receptor co-receptor.",
                        species="Drosophila suzukii",
                        url="https://example.org/gff",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_genome_files",
                            locator="raw/gff#gene/orco",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="swd_ncbi_gene_ortholog:108011252:7227:40650:2",
                        lane="genome_features",
                        source="drosophila_suzukii_ncbi_gene_orthologs",
                        title="Drosophila suzukii NCBI Gene ortholog: Orco to Drosophila melanogaster GeneID 40650",
                        text="NCBI Gene ortholog row for Drosophila suzukii GeneID 108011252 (Orco, odorant receptor co-receptor) links by Ortholog to Drosophila melanogaster GeneID 40650.",
                        species="Drosophila suzukii",
                        url="https://www.ncbi.nlm.nih.gov/gene/108011252",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_ncbi_gene_orthologs",
                            locator="raw/drosophila_suzukii_ncbi_gene_orthologs/gene_orthologs.gz#line/2",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={"atom_type": "ncbi_gene_ortholog_pair", "relationship": "Ortholog"},
                    ),
                ]
            )

            answer = answer_question(
                "show Drosophila suzukii Orco orthologs",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_ncbi_gene_orthologs")

    def test_swd_ensembl_questions_prefer_ensembl_metazoa_orthology(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd_ncbi_gene_ortholog:108018010:7227:40650:2",
                        lane="genome_features",
                        source="drosophila_suzukii_ncbi_gene_orthologs",
                        title="Drosophila suzukii NCBI Gene ortholog: Dpit47 to Drosophila melanogaster GeneID 40650",
                        text="NCBI Gene ortholog row for Dpit47.",
                        species="Drosophila suzukii",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_ncbi_gene_orthologs",
                            locator="raw/ncbi#line/2",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="swd_ensembl_dmel_homolog:2:FBgn0266518:1",
                        lane="genome_features",
                        source="drosophila_suzukii_ensembl_metazoa_orthology",
                        title="Drosophila suzukii Ensembl Metazoa homolog: Dpit47 to Dmel FBgn0266518",
                        text="Ensembl Metazoa homolog row links Drosophila suzukii Dpit47 to Drosophila melanogaster gene FBgn0266518 with relationship ortholog_one2one.",
                        species="Drosophila suzukii",
                        url="https://metazoa.ensembl.org/Drosophila_melanogaster/Gene/Summary?g=FBgn0266518",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_ensembl_metazoa_orthology",
                            locator="raw/ensembl/homolog.txt.gz#line/1",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={"atom_type": "ensembl_metazoa_dmel_homolog", "relationship": "ortholog_one2one"},
                    ),
                ]
            )

            answer = answer_question(
                "show Drosophila suzukii Ensembl Dmel homologs for Dpit47",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_ensembl_metazoa_orthology")

    def test_swd_ensembl_stable_history_questions_use_gap_rows_directly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd_ensembl_current_gene:000001",
                        lane="genome_features",
                        source="drosophila_suzukii_ensembl_metazoa_orthology",
                        title="Drosophila suzukii Ensembl Metazoa current gene: example",
                        text="Ensembl Metazoa current gene row for Drosophila suzukii example.",
                        species="Drosophila suzukii",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_ensembl_metazoa_orthology",
                            locator="raw/ensembl/gene.txt.gz#line/1",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={"atom_type": "ensembl_metazoa_current_gene"},
                    ),
                    EvidenceRecord(
                        record_id="swd_ensembl_history_gap:swd_ensembl_metazoa_stable_id_event_empty",
                        lane="genome_features",
                        source="drosophila_suzukii_ensembl_metazoa_orthology",
                        title="Drosophila suzukii Ensembl Metazoa stable-ID event table is empty",
                        text="Ensembl Metazoa release 62 provides stable_id_event.txt.gz for Drosophila suzukii, but it has zero rows.",
                        species="Drosophila suzukii",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_ensembl_metazoa_orthology",
                            locator="raw/ensembl/stable_id_event.txt.gz#empty",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={"atom_type": "ensembl_metazoa_stable_id_history_gap"},
                    ),
                ]
            )

            answer = answer_question(
                "show Drosophila suzukii Ensembl stable ID history",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["record_id"], "swd_ensembl_history_gap:swd_ensembl_metazoa_stable_id_event_empty")

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

    def test_variant_questions_prefer_ncbi_snp_variation_audit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="ncbi:gene:LOC5566000",
                        lane="genome_features",
                        source="ncbi_datasets_genome",
                        title="Aedes aegypti genome feature LOC5566000",
                        text="Aedes aegypti genome feature record.",
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
                    snp_variation_record(
                        "ncbi_snp_variation:gap:aedes_aegypti:ncbi_snp_no_aedes_records",
                        "NCBI dbSNP returned zero records for Aedes aegypti using the bounded organism query.",
                    ),
                ]
            )

            answer = answer_question("show NCBI dbSNP variant records for Aedes aegypti", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_ncbi_snp_variation")
            self.assertEqual(answer["evidence"][0]["lane"], "genome_features")
            self.assertIn("zero records", answer["answer"])

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

    def test_spotted_wing_susceptibility_questions_prefer_susceptibility_lane_over_genes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    swd_resistance_gene_record("swd:genome_files:gene:Mdr49"),
                    swd_susceptibility_record("swd_susceptibility_candidate:W1"),
                ]
            )

            answer = answer_question("what insecticide susceptibility data exists for Drosophila suzukii?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "resistance")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_susceptibility_assay_rows")
            self.assertIn("spinosad", answer["evidence"][0]["text"])

    def test_spotted_wing_susceptibility_questions_fallback_to_extracted_facts_before_genes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    swd_resistance_gene_record("swd:genome_files:gene:Mdr49"),
                    swd_extracted_resistance_record("swd_extracted_fact:resistance:W2"),
                ]
            )

            answer = answer_question("what insecticide susceptibility data exists for Drosophila suzukii?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "resistance")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_extracted_facts")
            self.assertIn("Spinosad", answer["evidence"][0]["text"])

    def test_spotted_wing_biocontrol_questions_prefer_biocontrol_outcome_lane(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    swd_extracted_biocontrol_record("swd_extracted_fact:biocontrol:W2"),
                    swd_biocontrol_outcome_record("swd_biocontrol_candidate:W1"),
                ]
            )

            answer = answer_question("show Drosophila suzukii parasitoid biocontrol outcomes", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "biocontrol")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_biocontrol_outcome_rows")
            self.assertIn("Trichopria", answer["evidence"][0]["text"])

    def test_spotted_wing_biocontrol_questions_fallback_to_extracted_facts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records([swd_extracted_biocontrol_record("swd_extracted_fact:biocontrol:W2")])

            answer = answer_question("show Drosophila suzukii parasitoid biocontrol outcomes", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "biocontrol")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_extracted_facts")
            self.assertIn("Trichopria", answer["evidence"][0]["text"])

    def test_who_database_resistance_questions_prefer_malaria_threats_audit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    resistance_record("irmapper:aedes:1", "irmapper_aedes"),
                    who_malaria_threats_record(
                        "who:malaria-threats:resistance:gap:aedes_aegypti:who_malaria_threats_no_aedes_rows",
                        "WHO Malaria Threats Map resistance audit found no rows matching Aedes aegypti.",
                    ),
                ]
            )

            answer = answer_question("show the WHO insecticide resistance database rows for Aedes aegypti", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "resistance")
            self.assertEqual(answer["evidence"][0]["source"], "who_malaria_threats_resistance_audit")
            self.assertIn("no rows matching Aedes aegypti", answer["answer"])

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

    def test_resistance_table_questions_prefer_schema_validated_table_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    resistance_record("irmapper:aedes:1", "irmapper_aedes"),
                    resistance_marker_record("resistance_marker:V1016G:openalex:WRM1"),
                    resistance_table_row_record("resistance_table:openalex:WRTABLE1:row7"),
                ]
            )

            answer = answer_question("show parsed resistance table V1016G frequency for Aedes aegypti", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "resistance")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_resistance_table_rows")
            self.assertIn("0.72", answer["evidence"][0]["text"])

    def test_resistance_table_questions_prefer_named_openalex_source_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="resistance_table:extracted_fact:resistance:openalex:W3208836499:row49",
                        lane="resistance",
                        source="aedes_resistance_table_rows",
                        title="Aedes aegypti parsed resistance table row: temephos",
                        text="Schema-validated parsed supplement table row. Source record: openalex:W3208836499. Insecticide terms: temephos. Metric fields: mortality.",
                        species="Aedes aegypti",
                        url="https://example.org/w320",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_resistance_table_rows",
                            locator="records#openalex:W3208836499;row#49",
                            retrieved_at="2026-05-27T00:00:00Z",
                            license="CC-BY",
                        ),
                        payload={"confidence": "parsed_table_schema_validated"},
                    ),
                    EvidenceRecord(
                        record_id="resistance_table:extracted_fact:resistance:openalex:W3208836499:row21",
                        lane="resistance",
                        source="aedes_resistance_table_rows",
                        title="Aedes aegypti parsed resistance table row: organophosphate CCEAE3A",
                        text=(
                            "Schema-validated parsed supplement table row. Source record: openalex:W3208836499. "
                            "Insecticide terms: organophosphate. Marker terms: cceae3a, carboxylesterase. "
                            "Metric fields: amplification, copy_number. Table row: gene: CCEAE3A. CNV: 18.32505. amplification: YES."
                        ),
                        species="Aedes aegypti",
                        url="https://example.org/w320-cnv",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_resistance_table_rows",
                            locator="records#openalex:W3208836499;row#21",
                            retrieved_at="2026-05-27T00:00:00Z",
                            license="CC-BY",
                        ),
                        payload={"confidence": "parsed_table_schema_validated"},
                    ),
                    EvidenceRecord(
                        record_id="resistance_table:extracted_fact:resistance:openalex:W7128925281:row3",
                        lane="resistance",
                        source="aedes_resistance_table_rows",
                        title="Aedes aegypti parsed resistance table row: deltamethrin",
                        text="Schema-validated parsed supplement table row. Source record: openalex:W7128925281. Insecticide terms: deltamethrin. Metric fields: discriminating_concentration. Table row: Discriminating concentration s: Deltamethrin.",
                        species="Aedes aegypti",
                        url="https://ndownloader.figshare.com/files/61896451",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_resistance_table_rows",
                            locator="records#openalex:W7128925281;row#3",
                            retrieved_at="2026-05-27T00:00:00Z",
                            license="CC BY + CC0",
                        ),
                        payload={"confidence": "parsed_table_schema_validated"},
                    ),
                ]
            )

            answer = answer_question(
                "show Aedes aegypti resistance evidence from openalex W7128925281 discriminating concentrations",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["record_id"], "resistance_table:extracted_fact:resistance:openalex:W7128925281:row3")
            self.assertIn("Deltamethrin", answer["evidence"][0]["text"])

            cnv_answer = answer_question(
                "show resistance copy number amplification evidence from openalex W3208836499 CCEAE3A",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(cnv_answer["ok"])
            self.assertEqual(cnv_answer["answer_shape"], "resistance")
            self.assertEqual(cnv_answer["evidence"][0]["record_id"], "resistance_table:extracted_fact:resistance:openalex:W3208836499:row21")
            self.assertIn("copy_number", cnv_answer["evidence"][0]["text"])
            self.assertIn("CCEAE3A", cnv_answer["evidence"][0]["text"])

    def test_resistance_table_questions_return_table_gap_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    resistance_record(
                        "resistance_table:gap:no_resistance_table_rows_detected",
                        "aedes_resistance_table_rows",
                    )
                ]
            )

            answer = answer_question("show parsed resistance table V1016G frequency for Aedes aegypti", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "resistance")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_resistance_table_rows")

    def test_schema_validated_resistance_supplement_questions_return_table_gap_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    resistance_record("behavior:noise", "aedes_extracted_facts"),
                    resistance_record(
                        "resistance_table:gap:no_resistance_table_rows_detected",
                        "aedes_resistance_table_rows",
                    ),
                ]
            )

            answer = answer_question(
                "show schema-validated Aedes aegypti resistance supplement table rows",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "resistance")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_resistance_table_rows")

    def test_who_resistance_method_questions_prefer_who_guidance_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    resistance_record("irmapper:aedes:1", "irmapper_aedes"),
                    EvidenceRecord(
                        record_id="resistance:who_guidance:bioassay",
                        lane="resistance",
                        source="aedes_who_resistance_guidance",
                        title="WHO Aedes resistance guidance: bioassays",
                        text="WHO Aedes insecticide-resistance method source with test procedures, discriminating concentrations, filter paper and bottle bioassays.",
                        species="Aedes aegypti",
                        url="https://www.who.int/publications-detail-redirect/monitoring-and-managing-insecticide-resistance-in-aedes-mosquito-populations",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_who_resistance_guidance",
                            locator="raw/aedes_deep_sources/who_resistance_guidance/page.html#page",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="WHO public web page; source terms apply",
                        ),
                    ),
                    resistance_record("extracted_fact:resistance:who-bioassay", "aedes_extracted_facts"),
                ]
            )

            answer = answer_question("show WHO Aedes insecticide resistance bioassay guidance", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "resistance")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_who_resistance_guidance")

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

    def test_deep_source_questions_prefer_taxonomy_climate_compendium_and_population_lanes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="taxonomy:authority:aedes_aegypti:test",
                        lane="taxonomy",
                        source="aedes_taxonomy_authorities",
                        title="Aedes aegypti taxonomy authority",
                        text="Aedes aegypti taxonomy authority. Synonym/name evidence: Stegomyia aegypti. Classification terms: Diptera, Culicidae.",
                        species="Aedes aegypti",
                        url="https://example.org/taxonomy",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_taxonomy_authorities",
                            locator="raw/aedes_deep_sources/taxonomy_authorities/source.html#page",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="test",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="ecology:worldclim:source:test",
                        lane="ecology",
                        source="aedes_worldclim_climate",
                        title="WorldClim climate source",
                        text="WorldClim climate source for Aedes aegypti ecology joins. Variables mentioned: temperature, precipitation, GeoTiff.",
                        species="Aedes aegypti",
                        url="https://www.worldclim.org/data/worldclim21.html",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_worldclim_climate",
                            locator="raw/aedes_deep_sources/worldclim/page.html#page",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="test",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="ecology:worldclim:sample:global_compendium:402",
                        lane="ecology",
                        source="aedes_worldclim_climate",
                        title="WorldClim climate sample for Aedes aegypti occurrence row 402",
                        text="WorldClim 10-minute bioclim raster sample joined to a global Aedes aegypti occurrence compendium row. Country: Brazil. Annual mean temperature: 18.5 deg C. Annual precipitation: 1272 mm.",
                        species="Aedes aegypti",
                        url="https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_bio.zip",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_worldclim_climate",
                            locator="raw/aedes_deep_sources/worldclim/wc2.1_10m_bio.zip#occurrence/occurrence:global_compendium:aedes_aegypti:402",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="test",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="ecology:observation_climate:inaturalist_api:inat:observation:1",
                        lane="ecology",
                        source="aedes_observation_climate_join",
                        title="Aedes aegypti observation climate sample: inat:observation:1",
                        text="WorldClim v2.1 10-minute bioclim raster values joined to an indexed Aedes aegypti observation. Input source: inaturalist_api. Country/place: Brazil; Rio de Janeiro, Brazil. Coordinates: -22.9, -43.17. Annual mean temperature: 24.0 deg C. Annual precipitation: 1432.0 mm.",
                        species="Aedes aegypti",
                        url="https://example.org/inat/1",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_observation_climate_join",
                            locator="raw/aedes_deep_sources/worldclim/wc2.1_10m_bio.zip#observation/inat:observation:1",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="test",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="ecology:dataverse_suitability:3623893",
                        lane="ecology",
                        source="harvard_dataverse_aedes_suitability",
                        title="Aedes aegypti Dataverse suitability raster TCurMean30Sum_97ae.tif",
                        text="Harvard Dataverse Aedes aegypti suitability raster manifest. Dataset: Global current Aedes aegypti suitability for dengue transmission at 97.5% CI. File: TCurMean30Sum_97ae.tif. Scenario terms: current, 97.5% ci.",
                        species="Aedes aegypti",
                        url="https://doi.org/10.7910/DVN/NSG5UH",
                        media_url="https://dataverse.harvard.edu/api/access/datafile/3623893",
                        provenance=Provenance(
                            source_id="harvard_dataverse_aedes_suitability",
                            locator="raw/harvard_dataverse_suitability/search.json#data/items/1",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="CC0 1.0",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="occurrence:global_compendium:aedes_aegypti:1",
                        lane="observations",
                        source="aedes_global_compendium_occurrence",
                        title="Global compendium Aedes aegypti occurrence row 1",
                        text="Global Aedes occurrence compendium row for Aedes aegypti. Country: Brazil. Coordinates: -12.1, -44.2. Year: 2014.",
                        species="Aedes aegypti",
                        url="https://zenodo.org/records/4946792",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_global_compendium_occurrence",
                            locator="raw/aedes_deep_sources/global_compendium_occurrence/aegypti_albopictus.csv#row/1",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="test",
                        ),
                    ),
                    ecology_record("extracted_fact:ecology:global-compendium-row", "aedes_extracted_facts"),
                    EvidenceRecord(
                        record_id="population_genomics:bioproject:PRJNA1090933",
                        lane="genome_features",
                        source="aedes_population_genomics",
                        title="Aedes population genomics BioProject PRJNA1090933",
                        text="NCBI BioProject population-genomics record PRJNA1090933 for Aedes aegypti. Description: divergence and introgression in population genomics.",
                        species="Aedes aegypti",
                        url="https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1090933",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_population_genomics",
                            locator="raw/aedes_deep_sources/population_genomics/summary.json#result/PRJNA1090933",
                            retrieved_at="2026-05-25T00:00:00Z",
                            license="test",
                        ),
                    ),
                ]
            )

            taxonomy = answer_question("show Aedes aegypti taxonomy synonyms from authority sources", artifact_dir=artifact_dir)
            worldclim = answer_question("show WorldClim climate context for Aedes aegypti ecology", artifact_dir=artifact_dir)
            worldclim_brazil = answer_question("show WorldClim annual mean temperature and precipitation samples for Aedes aegypti Brazil", artifact_dir=artifact_dir)
            observation_climate = answer_question("show climate-linked Aedes aegypti observation ecology in Brazil", artifact_dir=artifact_dir)
            source_grade_ecology = answer_question("What source-grade Aedes ecology evidence do we have?", artifact_dir=artifact_dir)
            dataverse = answer_question("show Harvard Dataverse suitability rasters for Aedes aegypti dengue transmission", artifact_dir=artifact_dir)
            compendium = answer_question("show global Aedes aegypti occurrence compendium rows for Brazil", artifact_dir=artifact_dir)
            population = answer_question("show Aedes aegypti population genomics BioProject evidence", artifact_dir=artifact_dir)

            self.assertEqual(taxonomy["evidence"][0]["source"], "aedes_taxonomy_authorities")
            self.assertEqual(worldclim["evidence"][0]["source"], "aedes_worldclim_climate")
            self.assertEqual(worldclim_brazil["evidence"][0]["record_id"], "ecology:worldclim:sample:global_compendium:402")
            self.assertEqual(observation_climate["evidence"][0]["source"], "aedes_observation_climate_join")
            self.assertTrue(source_grade_ecology["ok"])
            self.assertEqual(source_grade_ecology["answer_shape"], "ecology")
            self.assertEqual(dataverse["evidence"][0]["source"], "harvard_dataverse_aedes_suitability")
            self.assertEqual(compendium["evidence"][0]["source"], "aedes_global_compendium_occurrence")
            self.assertEqual(population["evidence"][0]["source"], "aedes_population_genomics")

    def test_exact_bioproject_questions_prefer_extracted_fact_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="population_genomics:bioproject:PRJNA1090933",
                        lane="genome_features",
                        source="aedes_population_genomics",
                        title="Aedes population genomics BioProject PRJNA1090933",
                        text="NCBI BioProject population-genomics record PRJNA1090933 for Aedes aegypti.",
                        species="Aedes aegypti",
                        url="https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1090933",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_population_genomics",
                            locator="raw/aedes_deep_sources/population_genomics/summary.json#result/PRJNA1090933",
                            retrieved_at="2026-05-25T00:00:00Z",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="extracted_fact:supplement_manifest:openalex_W4226382829:prjna789580",
                        lane="literature",
                        source="aedes_extracted_facts",
                        title="NCBI BioProject PRJNA789580: Mosquito transcriptomics",
                        text="Aedes aegypti supplement manifest. Repository: ncbi_bioproject. Accession: PRJNA789580. Project title: Mosquito transcriptomics.",
                        species="Aedes aegypti",
                        url="https://www.ncbi.nlm.nih.gov/bioproject/PRJNA789580",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_extracted_facts",
                            locator="records#openalex:W4226382829;supplement#PRJNA789580",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={
                            "confidence": "manifest",
                            "fact_type": "supplement_manifest",
                            "fields": {"repository": "ncbi_bioproject", "accession": "PRJNA789580"},
                        },
                    ),
                ]
            )

            answer = answer_question("Do we have NCBI BioProject PRJNA789580 for Aedes aegypti?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["source"], "aedes_extracted_facts")
            self.assertIn("PRJNA789580", answer["answer"])

    def test_exact_protocols_io_questions_prefer_extracted_fact_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="extracted_fact:supplement_manifest:openalex_W3091230652:bddhi236",
                        lane="literature",
                        source="aedes_extracted_facts",
                        title="protocols.io 10.17504/protocols.io.bddhi236: Competition in Aedes aegypti larvae",
                        text="Aedes aegypti supplement manifest. Repository: protocols.io. Accession: 10.17504/protocols.io.bddhi236. Protocol title: Competition in Aedes aegypti larvae.",
                        species="Aedes aegypti",
                        url="https://www.protocols.io/view/competition-in-aedes-aegypti-larvae-the-effects-of-8epv51e45l1b/v1",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_extracted_facts",
                            locator="records#openalex:W3091230652;supplement#bddhi236",
                            retrieved_at="2026-05-28T00:00:00Z",
                        ),
                        payload={
                            "confidence": "manifest",
                            "fact_type": "supplement_manifest",
                            "fields": {
                                "repository": "protocols.io",
                                "accession": "10.17504/protocols.io.bddhi236",
                                "protocol_doi": "10.17504/protocols.io.bddhi236",
                            },
                        },
                    )
                ]
            )

            answer = answer_question("Do we have protocols.io protocol bddhi236 for Aedes aegypti?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["source"], "aedes_extracted_facts")
            self.assertIn("bddhi236", answer["answer"])

    def test_exact_github_questions_prefer_extracted_fact_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="extracted_fact:supplement_manifest:openalex_W4280523569:optothermocycler",
                        lane="literature",
                        source="aedes_extracted_facts",
                        title="GitHub repository trevorsorrells/Optothermocycler",
                        text="Aedes aegypti supplement manifest. Repository: github. Accession: trevorsorrells/Optothermocycler.",
                        species="Aedes aegypti",
                        url="https://github.com/trevorsorrells/Optothermocycler",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_extracted_facts",
                            locator="records#openalex:W4280523569;supplement#trevorsorrells/Optothermocycler",
                            retrieved_at="2026-05-28T00:00:00Z",
                        ),
                        payload={
                            "confidence": "manifest",
                            "fact_type": "supplement_manifest",
                            "fields": {
                                "repository": "github",
                                "accession": "trevorsorrells/Optothermocycler",
                                "github_full_name": "trevorsorrells/Optothermocycler",
                            },
                        },
                    )
                ]
            )

            answer = answer_question(
                "Do we have GitHub repository trevorsorrells/Optothermocycler for Aedes aegypti?",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["evidence"][0]["source"], "aedes_extracted_facts")
            self.assertIn("trevorsorrells/Optothermocycler", answer["answer"])

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

    def test_public_health_source_locator_questions_prefer_extracted_fact_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    public_health_record(
                        "public_health:guidance:cdc",
                        "aedes_public_health_guidance",
                        "Official public-health guidance for Aedes aegypti dengue travelers from CDC.",
                    ),
                    public_health_record(
                        "extracted_fact:public_health:openalex:W3019929805:row3",
                        "aedes_extracted_facts",
                        (
                            "Aedes aegypti extracted public health fact. "
                            "Source record: openalex:W3019929805. "
                            "Source URL: https://www.forth.go.jp/ihr/fragment2/index.html. "
                            "Information: quarantine vector surveillance data report."
                        ),
                    ),
                ]
            )

            answer = answer_question(
                "show Aedes aegypti public health evidence from openalex W3019929805",
                artifact_dir=artifact_dir,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "public_health")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_extracted_facts")

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

    def test_india_dengue_death_questions_prefer_ncvbdc_recent_summary(self):
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
                        "public_health:surveillance:ncvbdc_dengue:country:india:2024",
                        "aedes_ncvbdc_dengue_surveillance",
                        "Official NCVBDC dengue surveillance row for India, 2024. Dengue cases: 233519. Dengue deaths: 297.",
                    ),
                    public_health_record(
                        "public_health:surveillance:ncvbdc_dengue:country:last_two_complete_years:2024-2025",
                        "aedes_ncvbdc_dengue_surveillance",
                        "Official NCVBDC India dengue surveillance summary for the two latest complete calendar years in the table, 2024-2025. Year details: 2024: 233519 cases, 297 deaths; 2025: 121824 cases, 131 deaths. Total dengue deaths: 428.",
                    ),
                ]
            )

            answer = answer_question("what were dengue deaths in India over the last two years as a result of Aedes?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "public_health")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_ncvbdc_dengue_surveillance")
            self.assertIn("last_two_complete_years", answer["evidence"][0]["record_id"])
            self.assertIn("428", answer["answer"])

    def test_brazil_dengue_questions_prefer_opendatasus_surveillance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    public_health_record(
                        "public_health:surveillance:paho_dengue:core_indicator:dengue_cases:BRA:2025",
                        "aedes_paho_dengue_surveillance",
                        "PAHO/EIH Core Indicators annual dengue cases for Brazil in 2025 from a stable machine-readable Open Data CSV row.",
                    ),
                    public_health_record(
                        "public_health:surveillance:opendatasus_dengue:country:brazil:2025",
                        "aedes_opendatasus_dengue_surveillance",
                        "Official Brazil OpenDataSUS SINAN dengue aggregate for 2025. Notifications: 3. Deaths coded as death by disease in EVOLUCAO=2: 1.",
                    ),
                    public_health_record(
                        "public_health:surveillance:opendatasus_dengue:country:brazil:2015",
                        "aedes_opendatasus_dengue_surveillance",
                        "Official Brazil OpenDataSUS SINAN dengue aggregate for 2015. Notifications: 9. Deaths coded as death by disease in EVOLUCAO=2: 4.",
                    ),
                ]
            )

            answer = answer_question("show Brazil OpenDataSUS dengue deaths and notifications for 2025", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "public_health")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_opendatasus_dengue_surveillance")
            self.assertIn("Deaths coded as death by disease in EVOLUCAO=2: 1", answer["answer"])

            historical = answer_question("show Brazil OpenDataSUS dengue deaths and notifications for 2015", artifact_dir=artifact_dir)

            self.assertTrue(historical["ok"])
            self.assertEqual(historical["evidence"][0]["record_id"], "public_health:surveillance:opendatasus_dengue:country:brazil:2015")
            self.assertIn("Notifications: 9", historical["answer"])

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

    def test_who_surveillance_questions_prefer_who_public_health_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    public_health_record(
                        "public_health:guidance:who-dengue",
                        "aedes_public_health_guidance",
                        "Official WHO dengue guidance for Aedes aegypti prevention.",
                    ),
                    public_health_record(
                        "public_health:surveillance:who_dengue:wer_global_update:abc123",
                        "aedes_who_dengue_surveillance",
                        "Official WHO WER dengue global situation, surveillance and progress update for Aedes aegypti public-health intelligence.",
                    ),
                ]
            )

            answer = answer_question("show WHO dengue surveillance evidence for Aedes aegypti", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "public_health")
            self.assertEqual(answer["evidence"][0]["source"], "aedes_who_dengue_surveillance")

    def test_who_dashboard_questions_prefer_dashboard_locator_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    public_health_record(
                        "public_health:surveillance:who_dengue:wer_global_update:abc123",
                        "aedes_who_dengue_surveillance",
                        "Official WHO WER dengue global situation, surveillance and progress update.",
                    ),
                    public_health_record(
                        "public_health:surveillance:who_dengue:dashboard_locator:def456",
                        "aedes_who_dengue_surveillance",
                        "Official WHO dengue dashboard locator for Western Pacific Health Data Platform. Not a country-time cell row yet.",
                    ),
                ]
            )

            answer = answer_question("show WHO dengue dashboard locator evidence for Aedes aegypti", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "public_health")
            self.assertEqual(
                answer["evidence"][0]["record_id"],
                "public_health:surveillance:who_dengue:dashboard_locator:def456",
            )

    def test_who_fact_sheet_questions_still_prefer_guidance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    public_health_record(
                        "public_health:surveillance:who_dengue:wer_global_update:abc123",
                        "aedes_who_dengue_surveillance",
                        "Official WHO WER dengue global situation, surveillance and progress update.",
                    ),
                    public_health_record(
                        "public_health:guidance:who-dengue",
                        "aedes_public_health_guidance",
                        "Official WHO dengue fact sheet and prevention guidance for Aedes aegypti.",
                    ),
                ]
            )

            answer = answer_question("show WHO dengue fact sheet guidance for Aedes aegypti", artifact_dir=artifact_dir)

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

    def test_supplement_audit_questions_return_counts_without_broad_search(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="extracted_fact:supplement_audit:paper1",
                        lane="literature",
                        source="aedes_extracted_facts",
                        title="Aedes aegypti supplement audit",
                        text=(
                            "Aedes aegypti supplement audit for paper One. "
                            "Coverage status: supplement_rows_promoted. Supplement manifests: 1. "
                            "Parsed supplement rows: 3. Promoted structured supplement rows: 2."
                        ),
                        species="Aedes aegypti",
                        url="https://doi.org/10.1000/paper1",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_extracted_facts",
                            locator="records#paper1;supplement_audit",
                            retrieved_at="2026-05-27T00:00:00Z",
                        ),
                        payload={
                            "fact_type": "supplement_audit",
                            "confidence": "audit",
                            "fields": {
                                "coverage_status": "supplement_rows_promoted",
                                "supplement_candidate_count": 1,
                                "parsed_supplement_row_count": 3,
                                "promoted_supplement_row_count": 2,
                            },
                        },
                    ),
                    EvidenceRecord(
                        record_id="extracted_fact:supplement_audit:paper2",
                        lane="literature",
                        source="aedes_extracted_facts",
                        title="Aedes aegypti supplement audit",
                        text=(
                            "Aedes aegypti supplement audit for paper Two. "
                            "Coverage status: no_supplement_metadata_found. Supplement manifests: 0. "
                            "Parsed supplement rows: 0. Promoted structured supplement rows: 0."
                        ),
                        species="Aedes aegypti",
                        url="https://doi.org/10.1000/paper2",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_extracted_facts",
                            locator="records#paper2;supplement_audit",
                            retrieved_at="2026-05-27T00:00:00Z",
                        ),
                        payload={
                            "fact_type": "supplement_audit",
                            "confidence": "audit",
                            "fields": {
                                "coverage_status": "no_supplement_metadata_found",
                                "supplement_candidate_count": 0,
                                "parsed_supplement_row_count": 0,
                                "promoted_supplement_row_count": 0,
                            },
                        },
                    ),
                    EvidenceRecord(
                        record_id="extracted_fact:supplement_file_gap:paper2:repo",
                        lane="literature",
                        source="aedes_extracted_facts",
                        title="Aedes aegypti supplement file gap: external repository reference",
                        text=(
                            "Aedes aegypti supplement file gap for paper Two. "
                            "Reason: external_repository_reference_not_expanded. "
                            "Repository: ncbi_bioproject. Accession: PRJNA612100."
                        ),
                        species="Aedes aegypti",
                        url="PRJNA612100",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_extracted_facts",
                            locator="records#paper2;supplement#0",
                            retrieved_at="2026-05-27T00:00:00Z",
                            source_url="PRJNA612100",
                        ),
                        payload={
                            "fact_type": "supplement_file_gap",
                            "confidence": "gap",
                            "fields": {
                                "reason": "external_repository_reference_not_expanded",
                                "source_record_id": "paper2",
                                "url": "PRJNA612100",
                                "source": "crossref_relation",
                                "repository": "ncbi_bioproject",
                                "reference_type": "bioproject",
                                "accession": "PRJNA612100",
                            },
                        },
                    ),
                    EvidenceRecord(
                        record_id="extracted_fact:supplement_file_gap:paper2:crossref-unsupported",
                        lane="literature",
                        source="aedes_extracted_facts",
                        title="Aedes aegypti supplement file gap: unsupported type",
                        text="Aedes aegypti supplement file gap. Reason: unsupported_supplement_type. Source: crossref_relation.",
                        species="Aedes aegypti",
                        url="https://doi.org/10.1107/example/file.dat",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_extracted_facts",
                            locator="records#paper2;supplement#1",
                            retrieved_at="2026-05-27T00:00:00Z",
                        ),
                        payload={
                            "fact_type": "supplement_file_gap",
                            "confidence": "gap",
                            "fields": {
                                "reason": "unsupported_supplement_type",
                                "source_record_id": "paper2",
                                "url": "https://doi.org/10.1107/example/file.dat",
                                "source": "crossref_relation",
                            },
                        },
                    ),
                    EvidenceRecord(
                        record_id="extracted_fact:supplement_file_gap:paper2:unpaywall-unsupported",
                        lane="literature",
                        source="aedes_extracted_facts",
                        title="Aedes aegypti supplement file gap: unsupported type",
                        text="Aedes aegypti supplement file gap. Reason: unsupported_supplement_type. Source: unpaywall_oa_location.",
                        species="Aedes aegypti",
                        url="https://example.org/supplement",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_extracted_facts",
                            locator="records#paper2;supplement#2",
                            retrieved_at="2026-05-27T00:00:00Z",
                        ),
                        payload={
                            "fact_type": "supplement_file_gap",
                            "confidence": "gap",
                            "fields": {
                                "reason": "unsupported_supplement_type",
                                "source_record_id": "paper2",
                                "url": "https://example.org/supplement",
                                "source": "unpaywall_oa_location",
                            },
                        },
                    ),
                ]
            )

            answer = answer_question("show Aedes aegypti supplement audit coverage status", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["supplement_audit"]["audited_papers"], 2)
            self.assertEqual(answer["supplement_audit"]["supplement_manifest_count"], 1)
            self.assertEqual(answer["supplement_audit"]["parsed_supplement_row_count"], 3)
            self.assertEqual(answer["supplement_audit"]["promoted_supplement_row_count"], 2)
            self.assertEqual(answer["status_counts"]["supplement_rows_promoted"], 1)
            self.assertEqual(answer["supplement_file_gap_counts"][0]["reason"], "external_repository_reference_not_expanded")
            self.assertEqual(answer["supplement_file_gap_counts"][0]["repository"], "ncbi_bioproject")
            unsupported_routes = {
                row["source"]
                for row in answer["supplement_file_gap_counts"]
                if row["reason"] == "unsupported_supplement_type"
            }
            self.assertEqual(unsupported_routes, {"crossref_relation", "unpaywall_oa_location"})
            self.assertIn("Top supplement file gap reasons", answer["answer"])
            self.assertEqual(answer["evidence"][0]["record_id"], "extracted_fact:supplement_audit:paper1")

    def test_swd_supplement_audit_questions_use_swd_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd_extracted_fact:supplement_audit:paper1",
                        lane="literature",
                        source="drosophila_suzukii_extracted_facts",
                        title="Drosophila suzukii supplement audit",
                        text=(
                            "Drosophila suzukii supplement audit for paper One. "
                            "Coverage status: supplement_manifest_found_table_download_not_run. "
                            "Supplement manifests: 1. Parsed supplement rows: 0. Promoted structured supplement rows: 0."
                        ),
                        species="Drosophila suzukii",
                        url="https://doi.org/10.1000/swd1",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_extracted_facts",
                            locator="records#swd:paper1;supplement_audit",
                            retrieved_at="2026-05-28T00:00:00Z",
                        ),
                        payload={
                            "fact_type": "supplement_audit",
                            "confidence": "audit",
                            "fields": {
                                "coverage_status": "supplement_manifest_found_table_download_not_run",
                                "supplement_candidate_count": 1,
                                "parsed_supplement_row_count": 0,
                                "promoted_supplement_row_count": 0,
                            },
                        },
                    ),
                    EvidenceRecord(
                        record_id="extracted_fact:supplement_audit:aedes",
                        lane="literature",
                        source="aedes_extracted_facts",
                        title="Aedes aegypti supplement audit",
                        text="Aedes aegypti supplement audit. Coverage status: supplement_rows_promoted.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_extracted_facts",
                            locator="records#aedes;supplement_audit",
                            retrieved_at="2026-05-28T00:00:00Z",
                        ),
                        payload={
                            "fact_type": "supplement_audit",
                            "confidence": "audit",
                            "fields": {
                                "coverage_status": "supplement_rows_promoted",
                                "supplement_candidate_count": 5,
                                "parsed_supplement_row_count": 10,
                                "promoted_supplement_row_count": 10,
                            },
                        },
                    ),
                ]
            )

            answer = answer_question("what is Drosophila suzukii supplement audit coverage?", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertIn("Drosophila suzukii", answer["answer"])
            self.assertEqual(answer["supplement_audit"]["audited_papers"], 1)
            self.assertEqual(answer["supplement_audit"]["supplement_manifest_count"], 1)
            self.assertEqual(answer["supplement_audit"]["parsed_supplement_row_count"], 0)
            self.assertEqual(answer["evidence"][0]["record_id"], "swd_extracted_fact:supplement_audit:paper1")

    def test_swd_dryad_table_row_questions_use_swd_table_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd:dryad:dataset:doi:10.5061_dryad.example",
                        lane="behavior",
                        source="drosophila_suzukii_deep_sources",
                        title="Drosophila suzukii Dryad dataset doi:10.5061/dryad.example",
                        text="Dryad dataset candidate for Drosophila suzukii with broad behavior metadata.",
                        species="Drosophila suzukii",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/dryad.example",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_deep_sources",
                            locator="raw/drosophila_suzukii_deep_sources/dryad/search.json#datasets/1",
                            retrieved_at="2026-05-29T00:00:00Z",
                            license="CC0",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="swd:dryad_table:row:swd:dryad:file:doi:10.5061_dryad.example:mean_distance_dryad.csv:11",
                        lane="behavior",
                        source="drosophila_suzukii_dryad_table_rows",
                        title="Drosophila suzukii Dryad table row mean_distance_dryad.csv row 11",
                        text=(
                            "Parsed Drosophila suzukii Dryad table row. File: mean_distance_dryad.csv. "
                            "Row: 11. Values: treatment=forest; distance=<200; pesticide=no; total=7943."
                        ),
                        species="Drosophila suzukii",
                        url="https://datadryad.org/stash/dataset/doi:10.5061/dryad.example",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_dryad_table_rows",
                            locator="raw/drosophila_suzukii_dryad_table_rows/previews/1.js#sheet/1/row/11",
                            retrieved_at="2026-05-29T00:00:00Z",
                            license="CC0",
                        ),
                        payload={
                            "atom_type": "dryad_table_row",
                            "file_path": "mean_distance_dryad.csv",
                            "row_number": 11,
                            "values": {
                                "treatment": "forest",
                                "distance": "<200",
                                "pesticide": "no",
                                "total": "7943",
                            },
                        },
                    ),
                ]
            )

            answer = answer_question(
                "what Dryad table rows mention spotted wing drosophila distance?",
                artifact_dir=artifact_dir,
                limit=1,
            )

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "behavior")
            self.assertEqual(answer["evidence"][0]["source"], "drosophila_suzukii_dryad_table_rows")
            self.assertEqual(
                answer["evidence"][0]["record_id"],
                "swd:dryad_table:row:swd:dryad:file:doi:10.5061_dryad.example:mean_distance_dryad.csv:11",
            )

    def test_swd_missing_source_questions_return_plain_coverage_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd:coverage:overview",
                        lane="source_coverage",
                        source="drosophila_suzukii_core",
                        title="Spotted wing drosophila source-plane overview",
                        text="Ask Insects boundary for Drosophila suzukii.",
                        species="Drosophila suzukii",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_core",
                            locator="repo:drosophila_suzukii_core#coverage/overview",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={
                            "atom_type": "source_coverage_overview",
                            "primary_taxon": "Drosophila suzukii",
                        },
                    ),
                    EvidenceRecord(
                        record_id="swd:coverage:taxonomy",
                        lane="source_coverage",
                        source="drosophila_suzukii_core",
                        title="Spotted wing drosophila coverage: taxonomy",
                        text="Source coverage for Drosophila suzukii, domain taxonomy. Missing or next source work: none recorded.",
                        species="Drosophila suzukii",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_core",
                            locator="repo:drosophila_suzukii_core#coverage/1",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={
                            "atom_type": "source_coverage_domain",
                            "domain": "taxonomy",
                            "status": "mapped_queryable",
                            "current_sources": ["GBIF species match"],
                            "missing_sources": [],
                        },
                    ),
                    EvidenceRecord(
                        record_id="swd:coverage:literature",
                        lane="source_coverage",
                        source="drosophila_suzukii_core",
                        title="Spotted wing drosophila coverage: literature",
                        text="Source coverage for Drosophila suzukii, domain literature. Missing or next source work: PubMed reconciliation.",
                        species="Drosophila suzukii",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_core",
                            locator="repo:drosophila_suzukii_core#coverage/2",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={
                            "atom_type": "source_coverage_domain",
                            "domain": "literature",
                            "status": "partial_source_grade",
                            "current_sources": ["OpenAlex metadata"],
                            "missing_sources": ["PubMed reconciliation", "legal full-text extraction"],
                        },
                    ),
                ]
            )

            answer = answer_question("what are we missing for spotted wing drosophila?", artifact_dir=artifact_dir, limit=2)

            self.assertTrue(answer["ok"])
            self.assertIn("not complete yet for spotted wing drosophila", answer["answer"])
            self.assertIn("literature: PubMed reconciliation", answer["answer"])
            self.assertEqual(answer["source_coverage"]["coverage_gap_count"], 2)
            self.assertEqual(answer["evidence"][0]["record_id"], "swd:coverage:literature")


if __name__ == "__main__":
    unittest.main()
