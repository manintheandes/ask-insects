import tempfile
import unittest
from pathlib import Path

from scripts.eval_production_path import (
    DEFAULT_CASES_PATH,
    CONTRACT_VERSION,
    ExecutionResult,
    evaluate_case,
    load_contract,
    run_evaluation,
)


def sample_case() -> dict[str, object]:
    return {
        "id": "diamondback-gap",
        "category": "species_coverage",
        "question": "What is missing from diamondback moth biology coverage?",
        "expect": {
            "behavior": "source_gap",
            "required_terms": ["diamondback moth", "14", "source gap"],
            "forbidden_terms": ["product works", "best in the literature"],
            "source_ids": ["insect_intelligence_programs"],
            "locator_patterns": [
                "config/insect-intelligence-programs.json#species/2"
            ],
        },
    }


def successful_execution() -> ExecutionResult:
    question = "What is missing from diamondback moth biology coverage?"
    answer = (
        "Diamondback moth has 14 source gaps. Source ID: "
        "`insect_intelligence_programs`. Locator: "
        "`config/insect-intelligence-programs.json#species/2`."
    )
    return ExecutionResult(
        elapsed_seconds=12.5,
        exit_code=0,
        timed_out=False,
        turn_completed=True,
        visible_answer=answer,
        agent_messages=[answer],
        commands=[f'/bin/zsh -lc \'ask-insects ask "{question}" --json --compact\''],
        event_types=["thread.started", "turn.started", "turn.completed"],
        stdout_jsonl="",
        stderr="",
    )


class ProductionPathEvalTests(unittest.TestCase):
    def test_canonical_contract_has_at_least_200_unique_questions(self):
        contract = load_contract(DEFAULT_CASES_PATH)

        self.assertEqual(contract["contract_version"], CONTRACT_VERSION)
        self.assertEqual(contract["maximum_seconds"], 30)
        self.assertGreaterEqual(len(contract["cases"]), 200)
        self.assertEqual(
            len({case["id"] for case in contract["cases"]}),
            len(contract["cases"]),
        )
        self.assertEqual(
            len({case["question"] for case in contract["cases"]}),
            len(contract["cases"]),
        )

    def test_case_passes_only_with_codex_route_answer_and_provenance(self):
        result = evaluate_case(sample_case(), successful_execution(), maximum_seconds=30)

        self.assertTrue(result["ok"], result["failures"])
        self.assertEqual(result["provenance"]["source_ids"], ["insect_intelligence_programs"])
        self.assertEqual(
            result["provenance"]["locators"],
            ["config/insect-intelligence-programs.json#species/2"],
        )

    def test_equivalent_species_domain_and_status_labels_are_accepted(self):
        question = "What is the sensory world evidence status for spotted wing drosophila?"
        case = {
            **sample_case(),
            "question": question,
            "expect": {
                **sample_case()["expect"],
                "behavior": "bounded_answer",
                "required_terms": ["Drosophila suzukii", "Sensory world", "partial source grade"],
                "locator_patterns": [
                    "config/insect-intelligence-programs.json#species/0/domains/0"
                ],
            },
        }
        answer = (
            "Spotted wing drosophila sensory-world evidence is partial_source_grade. "
            "Source: insect_intelligence_programs. Locator: "
            "config/insect-intelligence-programs.json#species/0/domains/0."
        )
        execution = successful_execution()
        execution.visible_answer = answer
        execution.agent_messages = [answer]
        execution.commands = [f'ask-insects ask "{question}" --json --compact']

        result = evaluate_case(case, execution, maximum_seconds=30)

        self.assertTrue(result["ok"], result["failures"])

    def test_negated_forbidden_claim_is_not_treated_as_an_unsupported_claim(self):
        case = sample_case()
        case["expect"] = {**case["expect"], "forbidden_terms": ["ready for market"]}
        execution = successful_execution()
        execution.visible_answer += " This is not ready for market."

        negated = evaluate_case(case, execution, maximum_seconds=30)

        self.assertTrue(negated["ok"], negated["failures"])
        execution.visible_answer = execution.visible_answer.replace("not ready", "ready")
        unsupported = evaluate_case(case, execution, maximum_seconds=30)
        self.assertFalse(unsupported["ok"])
        self.assertIn("final answer contains forbidden term: ready for market", unsupported["failures"])

    def test_timeout_is_a_hard_failure(self):
        execution = successful_execution()
        execution.elapsed_seconds = 30.001
        execution.timed_out = True

        result = evaluate_case(sample_case(), execution, maximum_seconds=30)

        self.assertFalse(result["ok"])
        self.assertTrue(any("30" in failure and "time" in failure for failure in result["failures"]))

    def test_missing_final_answer_provenance_fails_even_when_tool_output_had_it(self):
        execution = successful_execution()
        execution.visible_answer = "Diamondback moth has 14 source gaps."
        execution.stdout_jsonl = (
            'tool output: insect_intelligence_programs '
            'config/insect-intelligence-programs.json#species/2'
        )

        result = evaluate_case(sample_case(), execution, maximum_seconds=30)

        self.assertFalse(result["ok"])
        self.assertIn("final answer missing source id: insect_intelligence_programs", result["failures"])
        self.assertIn(
            "final answer missing locator: config/insect-intelligence-programs.json#species/2",
            result["failures"],
        )

    def test_direct_cli_or_wrong_question_does_not_count_as_normal_codex_route(self):
        execution = successful_execution()
        execution.commands = ['ask-insects ask "a different question" --json']

        result = evaluate_case(sample_case(), execution, maximum_seconds=30)

        self.assertFalse(result["ok"])
        self.assertTrue(any("exact question" in failure for failure in result["failures"]))

    def test_noncompact_agent_payload_fails_the_normal_route(self):
        execution = successful_execution()
        execution.commands = [
            'ask-insects ask "What is missing from diamondback moth biology coverage?" --json'
        ]

        result = evaluate_case(sample_case(), execution, maximum_seconds=30)

        self.assertFalse(result["ok"])
        self.assertIn("normal Ask Insects call did not use the compact agent payload", result["failures"])

    def test_memory_web_local_private_and_maintenance_fallbacks_fail(self):
        blocked_commands = [
            "rg diamondback /Users/josh/.codex/memories/MEMORY.md",
            "ask-insects ask question --local",
            "ask-monarch answer question",
            "python3 scripts/verify_complete.py",
        ]
        for command in blocked_commands:
            with self.subTest(command=command):
                execution = successful_execution()
                execution.commands.append(command)
                result = evaluate_case(sample_case(), execution, maximum_seconds=30)
                self.assertFalse(result["ok"])
        execution = successful_execution()
        execution.event_types.append("web_search")
        result = evaluate_case(sample_case(), execution, maximum_seconds=30)
        self.assertFalse(result["ok"])

    def test_second_ask_or_search_call_fails_the_one_call_contract(self):
        for command in (
            'ask-insects ask "another question" --json',
            'ask-insects search insect_intelligence "diamondback moth"',
        ):
            with self.subTest(command=command):
                execution = successful_execution()
                execution.commands.append(command)

                result = evaluate_case(sample_case(), execution, maximum_seconds=30)

                self.assertFalse(result["ok"])

    def test_installed_skill_reads_and_other_extra_commands_fail(self):
        execution = successful_execution()
        execution.commands.insert(
            0,
            "sed -n '1,160p' /Users/josh/.codex/skills/askinsects/SKILL.md",
        )

        rejected = evaluate_case(sample_case(), execution, maximum_seconds=30)

        self.assertFalse(rejected["ok"])
        self.assertIn(
            "normal answer used an unexpected command outside the hosted Ask Insects route",
            rejected["failures"],
        )

        for command in ("pwd", "cat /Users/josh/.codex/skills/askinsects/SKILL.md"):
            with self.subTest(command=command):
                execution = successful_execution()
                execution.commands.append(command)
                result = evaluate_case(sample_case(), execution, maximum_seconds=30)
                self.assertFalse(result["ok"])

    def test_full_gate_requires_every_corpus_case_on_the_unmodified_route(self):
        contract = {
            "contract_version": CONTRACT_VERSION,
            "minimum_case_count": 2,
            "maximum_seconds": 30,
            "required_categories": {"species_coverage": 2},
            "cases": [
                sample_case(),
                {
                    **sample_case(),
                    "id": "diamondback-gap-paraphrase",
                    "question": "Which diamondback moth biology areas are still source gaps?",
                },
            ],
        }

        result = run_evaluation(
            contract,
            execute=lambda case: successful_execution(),
            selected_case_ids={"diamondback-gap"},
            route_overrides=False,
        )

        self.assertFalse(result["production_gate_passed"])
        self.assertFalse(result["gate_eligible"])
        self.assertEqual(result["selected_case_count"], 1)

    def test_invalid_contract_rejects_category_shortfall(self):
        cases = []
        for index in range(200):
            case = sample_case()
            case["id"] = f"case-{index:03d}"
            case["question"] = f"Question {index:03d}"
            cases.append(case)
        cases[-1]["category"] = "product_readiness"
        payload = {
            "contract_version": CONTRACT_VERSION,
            "minimum_case_count": 200,
            "maximum_seconds": 30,
            "required_categories": {
                "species_coverage": 200,
                "product_readiness": 1,
            },
            "cases": cases,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "contract.json"
            path.write_text(__import__("json").dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "category species_coverage"):
                load_contract(path)


if __name__ == "__main__":
    unittest.main()
