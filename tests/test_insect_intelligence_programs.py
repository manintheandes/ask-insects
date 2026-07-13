from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from askinsects.answer import answer_question
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


class InsectIntelligenceProgramTests(unittest.TestCase):
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
        for record in domain_records:
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

    def test_planner_routes_every_non_comparison_production_eval_case_to_the_shared_lane(self):
        corpus = json.loads(
            Path("evals/ask_insects_production_path_v1.json").read_text(encoding="utf-8")
        )

        for case in corpus["cases"]:
            if case["category"] == "repellency_comparison":
                continue
            with self.subTest(case_id=case["id"], question=case["question"]):
                plan = plan_question(case["question"])
                self.assertEqual(plan.answer_shape, "insect_intelligence")
                self.assertEqual(plan.lanes, ("insect_intelligence",))

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
                "config/insect-intelligence-programs.json#species/2",
                *{
                    f"config/insect-intelligence-programs.json#species/2/domains/{index}"
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
                "Can the public Ask Insects path expose a private human mosquito repellent formulation while discussing readiness?",
                artifact_dir=artifact_dir,
            )
            transfer_answer = answer_question(
                "Can Aedes evidence be relabeled as direct diamondback moth evidence?",
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

        self.assertIn("public evidence layer", private_answer["answer"])
        self.assertIn("cannot expose or import private Ask Monarch", private_answer["answer"])
        self.assertIn("cannot be relabeled as direct focal-species evidence", transfer_answer["answer"])
        self.assertIn("explicitly labeled inference", transfer_answer["answer"])
        self.assertIn("not proof that a product works", proof_answer["answer"])
        self.assertIn("verification unverified", proof_answer["answer"])
        self.assertIn("Unverified evidence cannot be presented as a settled result", unverified_answer["answer"])
        self.assertIn("does not show that the literature contains no evidence", source_gap_answer["answer"])
        self.assertIn("source gap", source_gap_answer["answer"])

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
