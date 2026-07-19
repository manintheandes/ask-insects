from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from askinsects.answer import answer_question
from askinsects.index import SourceIndex
from askinsects.planner import plan_question
from askinsects.sources.insect_intelligence_programs import (
    DEFAULT_PROGRAM_LEDGER,
    INSECT_INTELLIGENCE_SOURCE_ID,
    REQUIRED_KNOWLEDGE_DOMAINS,
    REQUIRED_READINESS_DIMENSIONS,
    build_insect_intelligence_records,
    load_program_ledger,
    validate_program_ledger,
)
from scripts.ingest_insect_intelligence_programs import ingest_insect_intelligence_programs


RETRIEVED_AT = "2026-07-13T00:00:00Z"
REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_PRODUCT_SURFACES = (
    "AGENTS.md",
    "README.md",
    "docs/source-lanes.md",
    "docs/querying-ask-insects.md",
    "config/source-map.yaml",
    "config/insect-intelligence-programs.json",
    "skills/askinsects/SKILL.md",
    "askinsects/answer.py",
    "askinsects/planner.py",
    "askinsects/sources/drosophila_suzukii.py",
)
CONSUMER_COUPLING_PATTERNS = {
    "named private consumer": re.compile(r"\bmonarch(?:'s)?\b", re.IGNORECASE),
    "legacy consumer config": re.compile(r"ask-monarch-context-package", re.IGNORECASE),
    "consumer-specific SWD symbol": re.compile(r"DROSOPHILA_SUZUKII_MONARCH_TOPIC_SEARCH_TERMS"),
    "private assay fields": re.compile(r"private_assay_(?:families|modes)"),
    "private assay names": re.compile(
        r"\b(?:contact_no_contact|dart_choice|fly_repellency_dart|fly_contact_dart|mosquito_dart|"
        r"fly_oviposition|dbm_oviposition|arm_in_cage|spatial_affect|mosquito_post_exposure)\b"
    ),
    "private machine or data path": re.compile(r"(?:/home/|/Users/|file://|gs://)"),
}
INDEPENDENT_PUBLIC_OBJECTIVE = (
    "Deeply understand insects and accelerate effective, safe repellents that protect people and crops "
    "without killing insects."
)


class InsectIntelligenceProgramTests(unittest.TestCase):
    @staticmethod
    def _resolve_jsonpath(root: object, expression: str) -> object:
        if not expression.startswith("$"):
            raise AssertionError(f"not a JSONPath expression: {expression}")
        current = root
        offset = 1
        token_pattern = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]")
        while offset < len(expression):
            match = token_pattern.match(expression, offset)
            if match is None:
                raise AssertionError(f"unsupported JSONPath token: {expression[offset:]}")
            key, index = match.groups()
            current = current[int(index)] if index is not None else current[key]
            offset = match.end()
        return current

    def test_owned_public_product_surfaces_are_consumer_independent(self):
        for relative_path in PUBLIC_PRODUCT_SURFACES:
            text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
            for label, pattern in CONSUMER_COUPLING_PATTERNS.items():
                with self.subTest(path=relative_path, coupling=label):
                    self.assertIsNone(pattern.search(text))

    def test_active_product_surfaces_state_the_generic_public_contract(self):
        agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        skill = (REPO_ROOT / "skills/askinsects/SKILL.md").read_text(encoding="utf-8")

        for label, text in (("AGENTS", agents), ("README", readme), ("skill", skill)):
            with self.subTest(surface=label):
                self.assertIn("public", text.lower())
                self.assertIn("insect science", text.lower())
                self.assertIn("generic public evidence package", text.lower())
                self.assertIn("any downstream tool", text.lower())

    def test_source_map_declares_the_generic_v3_evidence_package(self):
        source_map = (REPO_ROOT / "config/source-map.yaml").read_text(encoding="utf-8")
        export_block = source_map.split("      - id: ask_insects_context_package", 1)[1]
        export_block = export_block.split("\n  - id:", 1)[0]

        self.assertIn("config: config/insect-evidence-package.json", export_block)
        self.assertIn("schema_version: ask-insects-evidence-package.v3", export_block)
        self.assertIn("generic public insect evidence package", export_block.lower())
        self.assertIn("any downstream tool", export_block.lower())

    def test_real_ledger_uses_the_independent_public_objective(self):
        payload = load_program_ledger(DEFAULT_PROGRAM_LEDGER)

        self.assertEqual(payload["objective"], INDEPENDENT_PUBLIC_OBJECTIVE)

    def test_real_ledger_defines_two_products_and_three_initial_species(self):
        payload = load_program_ledger(DEFAULT_PROGRAM_LEDGER)

        validate_program_ledger(payload)

        products = {item["id"] for item in payload["products"]}
        species = {item["id"] for item in payload["species"]}
        domains = {item["id"] for item in payload["knowledge_domains"]}
        readiness = {item["id"] for item in payload["readiness_dimensions"]}

        self.assertEqual(products, {"swd_crop_repellent", "human_mosquito_repellent"})
        self.assertEqual(species, {"drosophila_suzukii", "aedes_aegypti", "plutella_xylostella"})
        self.assertEqual(domains, REQUIRED_KNOWLEDGE_DOMAINS)
        self.assertEqual(readiness, REQUIRED_READINESS_DIMENSIONS)

    def test_validation_fails_closed_when_a_species_omits_a_domain(self):
        payload = deepcopy(load_program_ledger(DEFAULT_PROGRAM_LEDGER))
        payload["species"][0]["domains"].pop()

        with self.assertRaisesRegex(ValueError, "missing knowledge domains"):
            validate_program_ledger(payload)

    def test_validation_rejects_one_way_product_species_relationships(self):
        payload = deepcopy(load_program_ledger(DEFAULT_PROGRAM_LEDGER))
        swd = next(item for item in payload["species"] if item["id"] == "drosophila_suzukii")
        swd["product_ids"] = []

        with self.assertRaisesRegex(ValueError, "must reference each other"):
            validate_program_ledger(payload)

    def test_builder_emits_shared_domain_and_explicit_gap_records(self):
        records = build_insect_intelligence_records(retrieved_at=RETRIEVED_AT)

        self.assertEqual(records[0].record_id, "insect_intelligence_programs:portfolio")
        self.assertTrue(all(record.source == INSECT_INTELLIGENCE_SOURCE_ID for record in records))
        atom_types = [record.payload["atom_type"] for record in records if record.payload]
        self.assertEqual(atom_types.count("portfolio_overview"), 1)
        self.assertEqual(atom_types.count("product_program"), 2)
        self.assertEqual(atom_types.count("species_profile"), 3)
        self.assertEqual(atom_types.count("knowledge_domain"), 3 * len(REQUIRED_KNOWLEDGE_DOMAINS))
        self.assertEqual(atom_types.count("readiness_dimension"), 2 * len(REQUIRED_READINESS_DIMENSIONS))
        self.assertIn("knowledge_gap", atom_types)
        self.assertIn("readiness_gap", atom_types)
        self.assertTrue(all(record.provenance.locator.startswith("config/insect-intelligence-programs.json#") for record in records))
        self.assertTrue(
            all(
                str(record.provenance.source_url).startswith("https://github.com/")
                for record in records
            )
        )

    def test_repo_relative_default_ledger_keeps_public_source_url(self):
        records = build_insect_intelligence_records(
            Path("config/insect-intelligence-programs.json"),
            retrieved_at=RETRIEVED_AT,
        )

        self.assertTrue(
            all(
                str(record.provenance.source_url).startswith("https://github.com/")
                for record in records
            )
        )

    def test_every_program_record_locator_resolves_to_one_source_value(self):
        ledger = load_program_ledger(DEFAULT_PROGRAM_LEDGER)
        records = build_insect_intelligence_records(retrieved_at=RETRIEVED_AT)

        for record in records:
            with self.subTest(record_id=record.record_id):
                fragment = record.provenance.locator.split("#", 1)[1]
                self.assertTrue(fragment.startswith("jsonpath="))
                resolved = self._resolve_jsonpath(ledger, fragment.removeprefix("jsonpath="))
                self.assertIsNot(resolved, ledger)

    def test_ingest_skips_the_full_text_index_used_by_large_evidence_lanes(self):
        calls: list[dict[str, object]] = []
        original = SourceIndex.replace_source_records

        def tracked_replace(
            index: SourceIndex,
            source: str,
            records: list[object],
            **kwargs: object,
        ) -> None:
            calls.append(kwargs)
            original(index, source, records, **kwargs)

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            with patch.object(SourceIndex, "replace_source_records", new=tracked_replace):
                ingest_insect_intelligence_programs(
                    artifact_dir=artifact_dir,
                    retrieved_at=RETRIEVED_AT,
                )

        self.assertEqual(
            calls,
            [{"update_fts": False, "delete_existing_fts": False}],
        )

    def test_diamondback_moth_is_structured_without_borrowed_evidence(self):
        records = build_insect_intelligence_records(retrieved_at=RETRIEVED_AT)
        domain_records = [
            record
            for record in records
            if record.species == "Plutella xylostella"
            and record.payload
            and record.payload["atom_type"] == "knowledge_domain"
        ]
        gap_records = [
            record
            for record in records
            if record.species == "Plutella xylostella"
            and record.payload
            and record.payload["atom_type"] == "knowledge_gap"
        ]

        self.assertEqual(len(domain_records), len(REQUIRED_KNOWLEDGE_DOMAINS))
        self.assertGreaterEqual(len(gap_records), len(REQUIRED_KNOWLEDGE_DOMAINS))
        direct_domains = {
            "sensory_world",
            "receptors_signaling",
            "genetics_gene_activity",
            "life_cycle_development",
            "behavior",
            "reproduction_oviposition",
            "feeding_host_finding",
            "movement_flight_navigation",
            "learning_memory_internal_state",
            "ecology_interactions",
            "chemical_responses_metabolism",
            "adaptation_resistance",
        }
        for record in domain_records:
            domain = record.payload["domain"]
            if domain in direct_domains:
                self.assertEqual(record.payload["status"], "partial_source_grade")
                self.assertEqual(record.payload["evidence_scope"], "direct")
                self.assertEqual(
                    record.payload["current_sources"],
                    ["plutella_xylostella_literature"],
                )
            else:
                self.assertEqual(record.payload["status"], "source_gap")
                self.assertEqual(record.payload["evidence_scope"], "none")
                self.assertEqual(record.payload["current_sources"], [])
            self.assertNotIn("Aedes", record.text)
            self.assertNotIn("Drosophila", record.text)

    def test_planner_routes_program_questions_to_the_shared_lane(self):
        questions = (
            "What does Ask Insects need to understand about diamondback moth?",
            "What is missing from SWD biology coverage?",
            "What is the product readiness status of the human mosquito repellent?",
            "What are the two product programs Ask Insects supports?",
            "Which evidence about Aedes is direct, inferred, or unverified?",
        )

        for question in questions:
            with self.subTest(question=question):
                plan = plan_question(question)
                self.assertEqual(plan.answer_shape, "insect_intelligence")
                self.assertEqual(plan.lanes, ("insect_intelligence",))

    def test_planner_routes_plain_diamondback_moth_readiness_wording(self):
        plan = plan_question(
            "Is diamondback moth already covered well enough to support product R&D questions?"
        )

        self.assertEqual(plan.answer_shape, "insect_intelligence")
        self.assertEqual(plan.lanes, ("insect_intelligence",))

    def test_planner_routes_generic_public_private_boundary_questions(self):
        plan = plan_question(
            "Can Ask Insects fill a public evidence gap with experiments or results from a separate private system?"
        )

        self.assertEqual(plan.answer_shape, "insect_intelligence")
        self.assertEqual(plan.lanes, ("insect_intelligence",))

    def test_planner_routes_program_ledger_eval_cases_to_the_shared_lane(self):
        corpus = json.loads(
            Path("evals/ask_insects_production_path_v1.json").read_text(encoding="utf-8")
        )

        for case in corpus["cases"]:
            if case["category"] in {"repellency_comparison", "broad_natural_language"}:
                continue
            with self.subTest(case_id=case["id"], question=case["question"]):
                plan = plan_question(case["question"])
                self.assertEqual(plan.answer_shape, "insect_intelligence")
                self.assertEqual(plan.lanes, ("insect_intelligence",))

    def test_broad_natural_language_eval_cases_use_their_real_answer_lanes(self):
        corpus = json.loads(
            Path("evals/ask_insects_production_path_v1.json").read_text(encoding="utf-8")
        )
        expected_shapes = {
            "broad-swd-noncontact-repellency-01": "behavior",
            "broad-aedes-reference-genome-01": "genomics",
            "broad-aedes-reference-brain-01": "neurobiology",
            "broad-swd-row-level-flight-01": "behavior",
            "broad-dbm-readiness-gap-01": "insect_intelligence",
            "broad-mosquito-repellent-formulations-01": "literature",
            "broad-swd-oviposition-deterrence-01": "behavior",
            "broad-swd-cross-domain-rd-01": "insect_intelligence",
            "broad-aedes-cross-domain-rd-01": "insect_intelligence",
            "broad-aedes-ecology-rd-01": "insect_intelligence",
        }
        broad_cases = {
            case["id"]: case
            for case in corpus["cases"]
            if case["category"] == "broad_natural_language"
        }

        self.assertEqual(set(broad_cases), set(expected_shapes))
        for case_id, expected_shape in expected_shapes.items():
            with self.subTest(case_id=case_id, question=broad_cases[case_id]["question"]):
                self.assertEqual(plan_question(broad_cases[case_id]["question"]).answer_shape, expected_shape)

    def test_production_eval_program_locators_match_generated_records_exactly(self):
        corpus = json.loads(
            Path("evals/ask_insects_production_path_v1.json").read_text(encoding="utf-8")
        )
        canonical_locators = {
            record.provenance.locator
            for record in build_insect_intelligence_records(retrieved_at=RETRIEVED_AT)
        }

        for case in corpus["cases"]:
            if INSECT_INTELLIGENCE_SOURCE_ID not in case["expect"]["source_ids"]:
                continue
            for locator in case["expect"]["locator_patterns"]:
                with self.subTest(case_id=case["id"], locator=locator):
                    self.assertIn(locator, canonical_locators)

    def test_plain_source_coverage_question_keeps_the_existing_coverage_lane(self):
        plan = plan_question("What is missing from Aedes source coverage?")

        self.assertEqual(plan.answer_shape, "evidence")
        self.assertEqual(plan.lanes, ("source_coverage",))

    def test_direct_scientific_evidence_question_is_not_hijacked_by_program_routing(self):
        plan = plan_question("What direct evidence shows that DEET repels Aedes aegypti?")

        self.assertNotEqual(plan.answer_shape, "insect_intelligence")
        self.assertNotEqual(plan.lanes, ("insect_intelligence",))

    def test_answers_diamondback_moth_gaps_and_product_readiness_plainly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            ingest_insect_intelligence_programs(artifact_dir=artifact_dir, retrieved_at=RETRIEVED_AT)

            dbm_answer = answer_question(
                "What is missing from diamondback moth biology coverage?",
                artifact_dir=artifact_dir,
                limit=4,
            )
            product_answer = answer_question(
                "What is the product readiness status of the human mosquito repellent?",
                artifact_dir=artifact_dir,
                limit=4,
            )

        self.assertTrue(dbm_answer["ok"])
        self.assertIn("diamondback moth", dbm_answer["answer"].lower())
        self.assertIn("14", dbm_answer["answer"])
        self.assertGreater(dbm_answer["insect_intelligence"]["gap_count"], 0)
        self.assertEqual(dbm_answer["evidence"][0]["species"], "Plutella xylostella")
        self.assertTrue(product_answer["ok"])
        self.assertIn("human mosquito repellent", product_answer["answer"].lower())
        self.assertIn("8", product_answer["answer"])
        self.assertGreater(product_answer["insect_intelligence"]["gap_count"], 0)

    def test_plain_diamondback_moth_readiness_answer_exposes_source_gap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            ingest_insect_intelligence_programs(artifact_dir=artifact_dir, retrieved_at=RETRIEVED_AT)

            answer = answer_question(
                "Is diamondback moth already covered well enough to support product R&D questions?",
                artifact_dir=artifact_dir,
            )

        self.assertTrue(answer["ok"])
        self.assertEqual(answer["answer_shape"], "insect_intelligence")
        self.assertIn("Plutella xylostella", answer["answer"])
        self.assertIn("source gap", answer["answer"].lower())
        self.assertEqual(answer["evidence"][0]["source"], "insect_intelligence_programs")
        self.assertEqual(
            answer["evidence"][0]["provenance"]["locator"],
            "config/insect-intelligence-programs.json#jsonpath=$.species[2]",
        )

    def test_broad_program_answers_are_complete_in_the_first_call(self):
        ledger = load_program_ledger(DEFAULT_PROGRAM_LEDGER)
        domain_names = [item["name"] for item in ledger["knowledge_domains"]]
        readiness_names = [item["name"] for item in ledger["readiness_dimensions"]]
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            ingest_insect_intelligence_programs(artifact_dir=artifact_dir, retrieved_at=RETRIEVED_AT)

            dbm_answer = answer_question(
                "What is missing from diamondback moth biology coverage?",
                artifact_dir=artifact_dir,
                limit=4,
            )
            product_answer = answer_question(
                "What is the product readiness status of the human mosquito repellent?",
                artifact_dir=artifact_dir,
                limit=4,
            )

        for name in domain_names:
            self.assertIn(name, dbm_answer["answer"])
        self.assertEqual(len(dbm_answer["evidence"]), 15)
        self.assertEqual(
            {item["provenance"]["locator"] for item in dbm_answer["evidence"]},
            {
                "config/insect-intelligence-programs.json#jsonpath=$.species[2]",
                *{
                    "config/insect-intelligence-programs.json"
                    f"#jsonpath=$.species[2].domains[{index}]"
                    for index in range(14)
                },
            },
        )
        for name in readiness_names:
            self.assertIn(name, product_answer["answer"])
        self.assertEqual(len(product_answer["evidence"]), 9)

    def test_answers_state_evidence_boundaries_and_calibration_explicitly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            ingest_insect_intelligence_programs(artifact_dir=artifact_dir, retrieved_at=RETRIEVED_AT)

            private_answer = answer_question(
                "Can Ask Insects fill a public evidence gap with experiments or results from a separate private system?",
                artifact_dir=artifact_dir,
            )
            transfer_answer = answer_question(
                "Can evidence from another species be relabeled as direct Aedes evidence?",
                artifact_dir=artifact_dir,
            )
            proof_answer = answer_question(
                "Does public literature metadata alone prove human mosquito repellent efficacy?",
                artifact_dir=artifact_dir,
            )
            unverified_answer = answer_question(
                "Can unverified SWD crop repellent efficacy extraction be presented as a settled result?",
                artifact_dir=artifact_dir,
            )
            source_gap_answer = answer_question(
                "Does a source gap in spotted wing drosophila ecology mean the literature itself contains no evidence?",
                artifact_dir=artifact_dir,
            )
            uncertainty_answer = answer_question(
                "Does partial Aedes genetics coverage remove all uncertainty?",
                artifact_dir=artifact_dir,
            )
            verification_answer = answer_question(
                "Is unverified Aedes brain evidence the same as human-verified proof?",
                artifact_dir=artifact_dir,
            )

        self.assertIn("public evidence layer", private_answer["answer"])
        self.assertIn(
            "Private experiments and results belong in a separate private system",
            private_answer["answer"],
        )
        self.assertIn(
            "private evidence cannot be imported to fill gaps in public evidence",
            private_answer["answer"],
        )
        self.assertIn("cannot be relabeled as direct focal-species evidence", transfer_answer["answer"])
        self.assertIn("explicitly labeled inference", transfer_answer["answer"])
        self.assertIn("not proof that a product works", proof_answer["answer"])
        self.assertIn("verification unverified", proof_answer["answer"])
        self.assertIn("Unverified evidence cannot be presented as a settled result", unverified_answer["answer"])
        self.assertIn("does not show that the literature contains no evidence", source_gap_answer["answer"])
        self.assertIn("source gap", source_gap_answer["answer"])
        self.assertTrue(uncertainty_answer["answer"].startswith("No."))
        self.assertIn(
            "partial coverage does not remove uncertainty",
            uncertainty_answer["answer"].lower(),
        )
        self.assertTrue(verification_answer["answer"].startswith("No."))
        self.assertIn(
            "is not the same as human-verified proof",
            verification_answer["answer"],
        )

    def test_next_insect_question_returns_the_portfolio_and_diamondback_moth(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            ingest_insect_intelligence_programs(artifact_dir=artifact_dir, retrieved_at=RETRIEVED_AT)

            answer = answer_question(
                "Which insect is next after SWD and mosquitoes?",
                artifact_dir=artifact_dir,
                limit=6,
            )

        self.assertTrue(answer["ok"])
        self.assertEqual(answer["insect_intelligence"]["subject_type"], "portfolio")
        self.assertIn("diamondback moth", answer["answer"].lower())

    def test_a_fourth_species_uses_the_same_answer_path_without_code_changes(self):
        payload = deepcopy(load_program_ledger(DEFAULT_PROGRAM_LEDGER))
        fourth = deepcopy(next(item for item in payload["species"] if item["id"] == "plutella_xylostella"))
        fourth.update(
            {
                "id": "bombyx_mori",
                "scientific_name": "Bombyx mori",
                "common_name": "silkworm",
                "aliases": ["silkworm", "Bombyx mori"],
                "role": "expansion test fixture",
                "product_ids": [],
            }
        )
        payload["species"].append(fourth)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ledger_path = tmp / "programs.json"
            ledger_path.write_text(json.dumps(payload), encoding="utf-8")
            artifact_dir = tmp / "mosquito-v1"
            ingest_insect_intelligence_programs(
                artifact_dir=artifact_dir,
                program_path=ledger_path,
                retrieved_at=RETRIEVED_AT,
            )

            answer = answer_question(
                "What is missing from silkworm biology coverage?",
                artifact_dir=artifact_dir,
                limit=3,
            )

        self.assertTrue(answer["ok"])
        self.assertIn("silkworm", answer["answer"].lower())
        self.assertEqual(answer["evidence"][0]["species"], "Bombyx mori")


if __name__ == "__main__":
    unittest.main()
