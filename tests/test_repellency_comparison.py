from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from askinsects.answer import answer_question
from askinsects.cli import render_answer
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.server import dispatch_request
from askinsects.sources.literature import FullTextUnit
from scripts.eval_repellency_comparison import run_evaluation
from askinsects.repellency import (
    REPELLENCY_COMPARISON_CONTRACT_VERSION,
    build_repellency_comparison_answer,
    is_repellency_comparison_question,
)


ROOT = Path(__file__).resolve().parents[1]
EVAL_CASES = json.loads(
    (ROOT / "evals" / "repellency_comparison_v1.json").read_text(encoding="utf-8")
)
PRODUCTION_PATH_CASES = json.loads(
    (ROOT / "evals" / "ask_insects_production_path_v1.json").read_text(encoding="utf-8")
)


def _record(
    record_id: str,
    *,
    source: str,
    title: str,
    lane: str = "literature",
    species: str = "Aedes aegypti",
    text: str | None = None,
    payload: dict[str, object] | None = None,
) -> EvidenceRecord:
    return EvidenceRecord(
        record_id=record_id,
        lane=lane,
        source=source,
        title=title,
        text=text or title,
        species=species,
        url=f"https://example.test/{record_id}",
        media_url=None,
        provenance=Provenance(
            source_id=source,
            locator=f"fixture.json#{record_id}",
            retrieved_at="2026-07-10T12:00:00Z",
            license="test fixture",
            source_url=f"https://example.test/{record_id}",
        ),
        payload=payload,
    )


def _build_index(path: Path) -> SourceIndex:
    index = SourceIndex(path)
    index.initialize()
    records = [
        _record(
            "mosquito_repellent_literature:doi:10_1000_deet",
            source="mosquito_repellent_literature",
            title="Spatial DEET repellency against Aedes aegypti",
            payload={
                "doi": "10.1000/deet",
                "pmid": "1001",
                "title": "Spatial DEET repellency against Aedes aegypti",
                "repellent_terms": ["deet", "spatial repellent"],
                "coverage_status": "repellent_metadata_ingested",
            },
        ),
        _record(
            "mosquito_repellent_external_discovery:doi:10_1000_deet",
            source="mosquito_repellent_external_discovery",
            title="Spatial DEET repellency against Aedes aegypti",
            payload={
                "doi": "https://doi.org/10.1000/DEET",
                "title": "Spatial DEET repellency against Aedes aegypti",
                "source_family": "openalex",
                "artifact_type": "article_metadata",
            },
        ),
        _record(
            "mosquito_repellent_literature:doi:10_1000_picaridin",
            source="mosquito_repellent_literature",
            title="Topical picaridin protection in arm-in-cage assays",
            payload={
                "doi": "10.1000/picaridin",
                "pmid": "1002",
                "title": "Topical picaridin protection in arm-in-cage assays",
                "repellent_terms": ["picaridin", "topical repellent"],
                "coverage_status": "repellent_metadata_ingested",
            },
        ),
        _record(
            "mosquito_repellent_external_discovery:gap:google_scholar:unsupported",
            source="mosquito_repellent_external_discovery",
            title="Mosquito repellent source gap: Google Scholar unsupported",
            lane="source_coverage",
            species="Culicidae",
            payload={
                "artifact_type": "source_gap",
                "source_family": "google_scholar",
                "reason": "no_supported_public_api",
                "detail": "Native Google Scholar search is not available.",
            },
        ),
        _record(
            "mosq_repellent_lit_fact:supplement_audit:deet",
            source="mosquito_repellent_literature_extracted_facts",
            title="DEET paper depth outcome",
            payload={
                "fact_type": "supplement_audit",
                "source_record_id": "mosquito_repellent_literature:doi:10_1000_deet",
                "fields": {"coverage_status": "no_supplement_metadata_found"},
                "confidence": "audit",
            },
        ),
        _record(
            "mosq_repellent_ext_fact:supplement_audit:mosquito_repellent_external_discovery:gap:google_scholar",
            source="mosquito_repellent_external_discovery_extracted_facts",
            title="Depth audit for a source-gap record",
            payload={
                "fact_type": "supplement_audit",
                "source_record_id": "mosquito_repellent_external_discovery:gap:google_scholar:unsupported",
                "fields": {"coverage_status": "supplement_discovery_not_run"},
                "confidence": "audit",
            },
        ),
        _record(
            "mosq_repellent_lit_fact:repellency_assay:deet:1",
            source="mosquito_repellent_literature_extracted_facts",
            title="Extracted spatial repellency assay",
            lane="behavior",
            text=(
                "Adult female Aedes aegypti were tested with 10% DEET in a non-contact "
                "spatial repellency chamber. Landing inhibition was 82% after 30 minutes "
                "versus a solvent control (n=40, p<0.05)."
            ),
            payload={
                "fact_type": "repellency_assay",
                "source_record_id": "mosquito_repellent_literature:doi:10_1000_deet",
                "fields": {
                    "compound": ["deet"],
                    "exposure_mode": ["non-contact", "spatial repellent"],
                    "assay": ["chamber"],
                    "endpoint": ["landing inhibition"],
                    "life_stage": ["adult", "female"],
                },
                "evidence_text": (
                    "Adult female Aedes aegypti were tested with 10% DEET in a non-contact "
                    "spatial repellency chamber. Landing inhibition was 82% after 30 minutes "
                    "versus a solvent control (n=40, p<0.05)."
                ),
                "confidence": "candidate",
            },
        ),
        _record(
            "drosophila_suzukii_core:doi:10_1000_swd",
            source="drosophila_suzukii_core",
            title="Oviposition deterrence in Drosophila suzukii",
            species="Drosophila suzukii",
            payload={
                "doi": "10.1000/swd",
                "title": "Oviposition deterrence in Drosophila suzukii",
            },
        ),
        _record(
            "swd_extracted_fact:repellency_assay:swd:1",
            source="drosophila_suzukii_extracted_facts",
            title="Extracted SWD repellency assay",
            lane="behavior",
            species="Drosophila suzukii",
            text=(
                "Adult female Drosophila suzukii were tested in a two-choice assay. "
                "Oviposition deterrence was 65% after 24 hours (n=30, p<0.05)."
            ),
            payload={
                "fact_type": "repellency_assay",
                "source_record_id": "drosophila_suzukii_core:doi:10_1000_swd",
                "fields": {
                    "assay": ["choice assay"],
                    "endpoint": ["oviposition deterrence"],
                    "life_stage": ["adult", "female"],
                },
                "evidence_text": (
                    "Adult female Drosophila suzukii were tested in a two-choice assay. "
                    "Oviposition deterrence was 65% after 24 hours (n=30, p<0.05)."
                ),
                "confidence": "candidate",
            },
        ),
    ]
    index.upsert_records(records)
    return index


class RepellencyComparisonTest(unittest.TestCase):
    def test_eval_questions_route_only_comparative_repellency_questions(self):
        self.assertEqual(
            EVAL_CASES["contract_version"], REPELLENCY_COMPARISON_CONTRACT_VERSION
        )
        for case in EVAL_CASES["cases"]:
            with self.subTest(case=case["id"]):
                self.assertEqual(
                    is_repellency_comparison_question(case["question"]),
                    case["comparison_route"],
                )

    def test_every_production_comparison_case_uses_the_comparison_route(self):
        cases = [
            case
            for case in PRODUCTION_PATH_CASES["cases"]
            if case["category"] == "repellency_comparison"
        ]

        self.assertEqual(len(cases), 32)
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertTrue(is_repellency_comparison_question(case["question"]))

    def test_comparison_contract_deduplicates_papers_and_reports_depth(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = _build_index(Path(tmp) / "source_index.sqlite")
            result = build_repellency_comparison_answer(
                index,
                "Does anything in the literature beat this spatial-repellency result?",
                limit=10,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["contract_version"], REPELLENCY_COMPARISON_CONTRACT_VERSION
        )
        self.assertEqual(result["answer_shape"], "repellency_comparison")
        self.assertEqual(result["coverage"]["discovered_records"], 3)
        self.assertEqual(result["coverage"]["deduplicated_papers"], 2)
        self.assertEqual(result["coverage"]["papers_with_depth_outcome"], 1)
        self.assertEqual(result["coverage"]["structured_assay_facts"], 1)
        self.assertEqual(result["coverage"]["human_verified_assay_facts"], 0)
        self.assertEqual(result["coverage"]["unresolved_source_gaps"], 1)
        self.assertEqual(len(result["comparison"]["rows"]), 1)
        self.assertTrue(result["evidence"])
        self.assertIn("locator", result["evidence"][0]["provenance"])

    def test_paper_deduplication_uses_identifier_fallbacks_without_merging_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = _build_index(Path(tmp) / "source_index.sqlite")
            index.upsert_records(
                [
                    _record(
                        "mosquito_repellent_external_discovery:title:picaridin-copy",
                        source="mosquito_repellent_external_discovery",
                        title="Topical picaridin protection in arm-in-cage assays",
                        payload={
                            "title": "Topical picaridin protection in arm-in-cage assays"
                        },
                    ),
                    _record(
                        "mosquito_repellent_external_discovery:doi:conflicting-picaridin",
                        source="mosquito_repellent_external_discovery",
                        title="Topical picaridin protection in arm-in-cage assays",
                        payload={
                            "doi": "10.1000/different-paper",
                            "title": "Topical picaridin protection in arm-in-cage assays",
                        },
                    ),
                ]
            )
            result = build_repellency_comparison_answer(
                index,
                "Compare spatial repellent and topical DEET efficacy studies.",
                limit=10,
            )

        self.assertEqual(result["coverage"]["discovered_records"], 5)
        self.assertEqual(result["coverage"]["deduplicated_papers"], 3)

    def test_superlative_is_blocked_with_machine_readable_reasons(self):
        case = next(
            case
            for case in EVAL_CASES["cases"]
            if case["id"] == "unqualified-literature-superlative"
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = build_repellency_comparison_answer(
                _build_index(Path(tmp) / "source_index.sqlite"),
                case["question"],
                limit=10,
            )

        self.assertEqual(result["claim"]["type"], case["claim_type"])
        self.assertEqual(result["claim"]["status"], "insufficient_evidence")
        reason_codes = {reason["code"] for reason in result["claim"]["reasons"]}
        self.assertTrue(set(case["required_reason_codes"]).issubset(reason_codes))
        answer = result["answer"].lower()
        for phrase in case["forbidden_phrases"]:
            self.assertNotIn(phrase, answer)

    def test_normalizes_assay_dimensions_without_promoting_candidate_confidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = build_repellency_comparison_answer(
                _build_index(Path(tmp) / "source_index.sqlite"),
                "Compare contact and non-contact mosquito repellency studies.",
                limit=10,
            )

        row = result["comparison"]["rows"][0]
        self.assertEqual(row["species"], "Aedes aegypti")
        self.assertEqual(row["compounds"], ["deet"])
        self.assertEqual(row["exposure_modes"], ["non-contact", "spatial"])
        self.assertEqual(row["assays"], ["chamber"])
        self.assertEqual(row["endpoints"], ["landing inhibition"])
        self.assertEqual(row["dose"], "10%")
        self.assertEqual(row["duration"], "30 minutes")
        self.assertEqual(row["outcome"], "82% landing inhibition")
        self.assertEqual(row["sample_size"], 40)
        self.assertEqual(row["statistical_result"], "p<0.05")
        self.assertEqual(row["confidence"], "candidate")
        self.assertFalse(row["human_verified"])
        self.assertEqual(
            row["paper_title"], "Spatial DEET repellency against Aedes aegypti"
        )

    def test_answer_question_uses_the_structured_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            _build_index(artifact_dir / "source_index.sqlite")
            result = answer_question(
                "Does anything in the literature beat this spatial-repellency result?",
                artifact_dir=artifact_dir,
                limit=10,
            )

        self.assertEqual(result["answer_shape"], "repellency_comparison")
        self.assertIn("claim", result)
        self.assertIn("comparison", result)
        self.assertIn("coverage", result)
        self.assertEqual(result["claim"]["status"], "insufficient_evidence")

        rendered = render_answer(result)
        self.assertIn("Claim status: insufficient_evidence", rendered)
        self.assertIn("Coverage: 2 deduplicated paper(s)", rendered)
        self.assertIn("Comparison rows:", rendered)
        self.assertIn("10%", rendered)

    def test_every_comparison_eval_case_has_a_calibrated_claim_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = _build_index(Path(tmp) / "source_index.sqlite")
            for case in EVAL_CASES["cases"]:
                if not case["comparison_route"]:
                    continue
                with self.subTest(case=case["id"]):
                    result = build_repellency_comparison_answer(
                        index, case["question"], limit=10
                    )
                    self.assertEqual(result["claim"]["type"], case["claim_type"])
                    self.assertIn(
                        result["claim"]["status"],
                        {"insufficient_evidence", "comparison_ready"},
                    )
                    self.assertIn("coverage", result)
                    self.assertIn("comparison", result)

    def test_swd_question_never_uses_mosquito_comparison_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = build_repellency_comparison_answer(
                _build_index(Path(tmp) / "source_index.sqlite"),
                "Compare Drosophila suzukii repellency assays for oviposition deterrence.",
                limit=10,
            )

        self.assertEqual(result["coverage"]["deduplicated_papers"], 1)
        self.assertEqual(result["comparison"]["scope"]["species"], "Drosophila suzukii")
        self.assertEqual(
            {row["species"] for row in result["comparison"]["rows"]},
            {"Drosophila suzukii"},
        )
        self.assertNotIn(
            "mosquito_repellent_literature", result["coverage"]["searched_sources"]
        )

    def test_swd_comparison_rejects_query_metadata_as_subject_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = _build_index(Path(tmp) / "source_index.sqlite")
            false_parent_id = "swd:openalex_literature:openalex:W2999977662"
            index.upsert_records(
                [
                    _record(
                        false_parent_id,
                        source="drosophila_suzukii_core",
                        title=(
                            "Tracking Short-Range Attraction and Oviposition of European "
                            "Grapevine Moths"
                        ),
                        species="Drosophila suzukii",
                        text=(
                            "Title: Tracking Short-Range Attraction and Oviposition of European "
                            "Grapevine Moths\nAbstract: Female moths were tested in an "
                            "olfactometer and some volatiles could repel egg deposition.\n"
                            "Inclusion paths: openalex_search_candidate\n"
                            "OpenAlex search term: Drosophila suzukii repellent\n"
                            "OpenAlex candidate status: openalex_search_candidate "
                            "Common name: spotted wing drosophila."
                        ),
                        payload={
                            "openalex_search_term": "Drosophila suzukii repellent",
                            "common_name": "spotted wing drosophila",
                        },
                    ),
                    _record(
                        "swd_extracted_fact:repellency_assay:false-positive",
                        source="drosophila_suzukii_extracted_facts",
                        title="Mislabeled SWD repellency assay",
                        lane="behavior",
                        species="Drosophila suzukii",
                        text="Female grapevine moths were tested in an olfactometer.",
                        payload={
                            "fact_type": "repellency_assay",
                            "source_record_id": false_parent_id,
                            "fields": {
                                "assay": ["olfactometer"],
                                "endpoint": ["repellency"],
                            },
                            "evidence_text": (
                                "Female grapevine moths were tested in an olfactometer."
                            ),
                            "confidence": "candidate",
                        },
                    ),
                ]
            )
            result = build_repellency_comparison_answer(
                index,
                "Compare Drosophila suzukii repellency assays for oviposition deterrence.",
                limit=10,
            )

        self.assertEqual(result["coverage"]["deduplicated_papers"], 1)
        self.assertEqual(result["coverage"]["structured_assay_facts"], 1)
        self.assertIn("Drosophila suzukii", result["answer"])
        self.assertNotIn(
            false_parent_id,
            {row["paper_record_id"] for row in result["comparison"]["rows"]},
        )

    def test_pairwise_status_requires_comparable_assays_not_just_both_compounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = _build_index(Path(tmp) / "source_index.sqlite")
            index.upsert_records(
                [
                    _record(
                        "mosq_repellent_lit_fact:repellency_assay:picaridin:1",
                        source="mosquito_repellent_literature_extracted_facts",
                        title="Extracted topical picaridin assay",
                        lane="behavior",
                        text=(
                            "Adult female Aedes aegypti received 10% picaridin in an arm-in-cage topical assay. "
                            "Protection was 90% after 30 minutes (n=40, p<0.05)."
                        ),
                        payload={
                            "fact_type": "repellency_assay",
                            "source_record_id": "mosquito_repellent_literature:doi:10_1000_picaridin",
                            "fields": {
                                "compound": ["picaridin"],
                                "exposure_mode": ["topical"],
                                "assay": ["arm-in-cage"],
                                "endpoint": ["protection"],
                            },
                            "evidence_text": (
                                "Adult female Aedes aegypti received 10% picaridin in an arm-in-cage topical assay. "
                                "Protection was 90% after 30 minutes (n=40, p<0.05)."
                            ),
                            "confidence": "candidate",
                        },
                    )
                ]
            )
            result = build_repellency_comparison_answer(
                index,
                "Does DEET beat icaridin in Aedes arm-in-cage assays?",
                limit=10,
            )

        self.assertEqual(result["claim"]["status"], "insufficient_evidence")
        self.assertIn("DEET", result["answer"])
        self.assertIn("icaridin", result["answer"])
        self.assertIn(
            "no_comparable_pair",
            {reason["code"] for reason in result["claim"]["reasons"]},
        )

    def test_orphan_assay_facts_are_reported_but_never_compared(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = _build_index(Path(tmp) / "source_index.sqlite")
            index.upsert_records(
                [
                    _record(
                        "mosq_repellent_lit_fact:repellency_assay:orphan",
                        source="mosquito_repellent_literature_extracted_facts",
                        title="Orphan picaridin assay",
                        lane="behavior",
                        text=(
                            "Adult female Aedes aegypti received 10% picaridin in a non-contact "
                            "spatial chamber. Landing inhibition was 90% after 30 minutes "
                            "(n=40, p<0.05)."
                        ),
                        payload={
                            "fact_type": "repellency_assay",
                            "source_record_id": "missing:parent",
                            "fields": {
                                "compound": ["picaridin"],
                                "exposure_mode": ["non-contact", "spatial repellent"],
                                "assay": ["chamber"],
                                "endpoint": ["landing inhibition"],
                            },
                            "confidence": "candidate",
                        },
                    )
                ]
            )
            result = build_repellency_comparison_answer(
                index,
                "Does DEET beat picaridin in a non-contact spatial repellent chamber?",
                limit=10,
            )

        self.assertEqual(result["coverage"]["structured_assay_facts"], 1)
        self.assertEqual(result["coverage"]["orphan_structured_assay_facts"], 1)
        self.assertEqual(result["claim"]["status"], "insufficient_evidence")
        self.assertIn(
            "missing_pairwise_evidence",
            {reason["code"] for reason in result["claim"]["reasons"]},
        )

    def test_depth_coverage_is_deduplicated_by_paper(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = _build_index(Path(tmp) / "source_index.sqlite")
            index.upsert_records(
                [
                    _record(
                        "mosq_repellent_ext_fact:supplement_audit:deet",
                        source="mosquito_repellent_external_discovery_extracted_facts",
                        title="Duplicate DEET paper depth outcome",
                        payload={
                            "fact_type": "supplement_audit",
                            "source_record_id": "mosquito_repellent_external_discovery:doi:10_1000_deet",
                            "fields": {
                                "coverage_status": "no_supplement_metadata_found"
                            },
                            "confidence": "audit",
                        },
                    )
                ]
            )
            result = build_repellency_comparison_answer(
                index,
                "Does anything in the literature beat this spatial-repellency result?",
                limit=10,
            )

        self.assertEqual(result["coverage"]["deduplicated_papers"], 2)
        self.assertEqual(result["coverage"]["papers_with_depth_outcome"], 1)
        self.assertIn(
            "incomplete_depth_coverage",
            {reason["code"] for reason in result["claim"]["reasons"]},
        )

    def test_fulltext_coverage_is_deduplicated_and_candidate_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = _build_index(Path(tmp) / "source_index.sqlite")
            provenance = Provenance(
                source_id="mosquito_repellent_literature",
                locator="fixture.json#fulltext",
                retrieved_at="2026-07-10T12:00:00Z",
            )
            index.upsert_fulltext_units(
                [
                    FullTextUnit(
                        unit_id="fulltext:deet:core",
                        record_id="mosquito_repellent_literature:doi:10_1000_deet",
                        source="dedicated_literature_fulltext",
                        unit_index=0,
                        text="DEET assay full text",
                        url=None,
                        license=None,
                        provenance=provenance,
                    ),
                    FullTextUnit(
                        unit_id="fulltext:deet:external",
                        record_id="mosquito_repellent_external_discovery:doi:10_1000_deet",
                        source="mosquito_repellent_external_discovery",
                        unit_index=0,
                        text="Duplicate DEET assay full text",
                        url=None,
                        license=None,
                        provenance=provenance,
                    ),
                    FullTextUnit(
                        unit_id="fulltext:unmapped",
                        record_id="unmapped:record",
                        source="mosquito_repellent_literature",
                        unit_index=0,
                        text="Unmapped source full text",
                        url=None,
                        license=None,
                        provenance=provenance,
                    ),
                ]
            )
            result = build_repellency_comparison_answer(
                index,
                "Compare contact and non-contact mosquito repellency studies.",
                limit=10,
            )

        self.assertEqual(result["coverage"]["papers_with_fulltext"], 1)

    def test_swd_gap_coverage_excludes_bookkeeping_and_unrelated_core_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = _build_index(Path(tmp) / "source_index.sqlite")
            index.upsert_records(
                [
                    _record(
                        "drosophila_suzukii_core:gap:pubmed_skipped:fixture",
                        source="drosophila_suzukii_core",
                        title="PubMed bookkeeping gap",
                        lane="source_coverage",
                        species="Drosophila suzukii",
                        payload={
                            "atom_type": "source_gap",
                            "reason": "pubmed_skipped",
                            "record_id": "openalex:W12345",
                        },
                    ),
                    _record(
                        "drosophila_suzukii_core:gap:bold_fetch_failed:fixture",
                        source="drosophila_suzukii_core",
                        title="Unrelated BOLD gap",
                        lane="source_coverage",
                        species="Drosophila suzukii",
                        payload={
                            "atom_type": "source_gap",
                            "reason": "bold_fetch_failed",
                        },
                    ),
                    _record(
                        "drosophila_suzukii_extracted_facts:gap:fulltext_limit:fixture",
                        source="drosophila_suzukii_extracted_facts",
                        title="Depth limit gap",
                        lane="source_coverage",
                        species="Drosophila suzukii",
                        payload={
                            "atom_type": "source_gap",
                            "reason": "fulltext_prefilter_limit_applied",
                        },
                    ),
                ]
            )
            result = build_repellency_comparison_answer(
                index,
                "Compare Drosophila suzukii repellency assays for oviposition deterrence.",
                limit=10,
            )

        coverage = result["coverage"]
        self.assertEqual(coverage["unresolved_source_gaps"], 1)
        self.assertEqual(coverage["bookkeeping_gap_records_excluded"], 2)
        self.assertEqual(
            coverage["source_gap_reason_counts"],
            {"fulltext_prefilter_limit_applied": 1},
        )

    def test_source_gap_details_are_bounded_and_reason_counts_remain_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = _build_index(Path(tmp) / "source_index.sqlite")
            index.upsert_records(
                [
                    _record(
                        f"mosquito_repellent_external_discovery:gap:fixture:{number}",
                        source="mosquito_repellent_external_discovery",
                        title=f"Discovery gap {number}",
                        lane="source_coverage",
                        species="Culicidae",
                        payload={
                            "artifact_type": "source_gap",
                            "reason": "fixture_discovery_failure",
                        },
                    )
                    for number in range(30)
                ]
            )
            result = build_repellency_comparison_answer(
                index,
                "Does anything in the literature beat this spatial-repellency result?",
                limit=10,
            )

        coverage = result["coverage"]
        self.assertEqual(coverage["unresolved_source_gaps"], 31)
        self.assertEqual(
            coverage["source_gap_reason_counts"]["fixture_discovery_failure"], 30
        )
        self.assertEqual(len(coverage["source_gaps"]), 25)
        self.assertEqual(coverage["source_gap_records_omitted"], 6)

    def test_hosted_ask_surface_preserves_the_comparison_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            _build_index(artifact_dir / "source_index.sqlite")
            response = dispatch_request(
                "POST",
                "/ask",
                {
                    "question": "Does anything in the literature beat this spatial-repellency result?",
                    "limit": 10,
                },
                headers={"Authorization": "Bearer secret"},
                artifact_dir=artifact_dir,
                token="secret",
            )

        self.assertEqual(response.status, 200)
        self.assertEqual(
            response.payload["contract_version"], REPELLENCY_COMPARISON_CONTRACT_VERSION
        )
        self.assertEqual(response.payload["claim"]["status"], "insufficient_evidence")
        self.assertEqual(response.payload["coverage"]["deduplicated_papers"], 2)

    def test_real_question_evaluation_corpus_passes_against_the_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = _build_index(Path(tmp) / "source_index.sqlite")
            result = run_evaluation(
                answer_fn=lambda question: build_repellency_comparison_answer(
                    index, question, limit=100
                )
            )

        self.assertTrue(result["ok"], result["results"])
        self.assertEqual(result["case_count"], 8)
        self.assertEqual(result["passed_count"], 8)


if __name__ == "__main__":
    unittest.main()
