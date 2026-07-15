import json
import tempfile
import unittest
from pathlib import Path

from scripts.eval_production_path import (
    DEFAULT_CASES_PATH,
    CONTRACT_VERSION,
    ExecutionResult,
    evaluate_case,
    load_contract,
    parse_codex_events,
    regrade_evaluation,
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
        self.assertEqual(contract["maximum_seconds"], 60)
        self.assertGreaterEqual(len(contract["cases"]), 200)
        self.assertEqual(
            len({case["id"] for case in contract["cases"]}),
            len(contract["cases"]),
        )
        boundary_questions = {
            case["id"]: case["question"]
            for case in contract["cases"]
            if case["id"] in {"boundary-01", "boundary-02", "boundary-04"}
        }
        self.assertEqual(len(boundary_questions), 3)
        for question in boundary_questions.values():
            self.assertIn("separate private R&D system", question)
            self.assertNotIn("Monarch", question)
        self.assertEqual(
            len({case["question"] for case in contract["cases"]}),
            len(contract["cases"]),
        )
        self.assertGreaterEqual(
            contract["required_categories"].get("broad_natural_language", 0),
            10,
        )
        questions = {case["question"] for case in contract["cases"]}
        self.assertIn(
            "What public evidence does Ask Insects have for non-contact repellency in spotted wing drosophila?",
            questions,
        )
        self.assertIn(
            "What genome assembly does Ask Insects have for Aedes aegypti?",
            questions,
        )

    def test_case_passes_only_with_codex_route_answer_and_provenance(self):
        result = evaluate_case(sample_case(), successful_execution(), maximum_seconds=60)

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

        result = evaluate_case(case, execution, maximum_seconds=60)

        self.assertTrue(result["ok"], result["failures"])

    def test_negated_forbidden_claim_is_not_treated_as_an_unsupported_claim(self):
        case = sample_case()
        case["expect"] = {**case["expect"], "forbidden_terms": ["ready for market"]}
        execution = successful_execution()
        execution.visible_answer += " This is not ready for market."

        negated = evaluate_case(case, execution, maximum_seconds=60)

        self.assertTrue(negated["ok"], negated["failures"])
        execution.visible_answer = execution.visible_answer.replace("not ready", "ready")
        unsupported = evaluate_case(case, execution, maximum_seconds=60)
        self.assertFalse(unsupported["ok"])
        self.assertIn("final answer contains forbidden term: ready for market", unsupported["failures"])

    def test_timeout_is_a_hard_failure(self):
        execution = successful_execution()
        execution.elapsed_seconds = 60.001
        execution.timed_out = True

        result = evaluate_case(sample_case(), execution, maximum_seconds=60)

        self.assertFalse(result["ok"])
        self.assertTrue(any("60" in failure and "time" in failure for failure in result["failures"]))

    def test_missing_final_answer_provenance_fails_even_when_tool_output_had_it(self):
        execution = successful_execution()
        execution.visible_answer = "Diamondback moth has 14 source gaps."
        execution.stdout_jsonl = (
            'tool output: insect_intelligence_programs '
            'config/insect-intelligence-programs.json#species/2'
        )

        result = evaluate_case(sample_case(), execution, maximum_seconds=60)

        self.assertFalse(result["ok"])
        self.assertIn("final answer missing source id: insect_intelligence_programs", result["failures"])
        self.assertIn(
            "final answer missing locator: config/insect-intelligence-programs.json#species/2",
            result["failures"],
        )

    def test_direct_cli_or_wrong_question_does_not_count_as_normal_codex_route(self):
        execution = successful_execution()
        execution.commands = ['ask-insects ask "a different question" --json']

        result = evaluate_case(sample_case(), execution, maximum_seconds=60)

        self.assertFalse(result["ok"])
        self.assertTrue(any("exact question" in failure for failure in result["failures"]))

    def test_question_must_be_one_exact_shell_argument(self):
        question = str(sample_case()["question"])
        wrong_questions = (
            question + " please",
            question.casefold(),
            "prefix " + question,
        )
        for wrong_question in wrong_questions:
            with self.subTest(wrong_question=wrong_question):
                execution = successful_execution()
                execution.commands = [
                    f'ask-insects ask "{wrong_question}" --json --compact'
                ]
                result = evaluate_case(sample_case(), execution, maximum_seconds=60)
                self.assertFalse(result["ok"])
                self.assertTrue(any("exact question" in failure for failure in result["failures"]))

    def test_noncompact_agent_payload_fails_the_normal_route(self):
        execution = successful_execution()
        execution.commands = [
            'ask-insects ask "What is missing from diamondback moth biology coverage?" --json'
        ]

        result = evaluate_case(sample_case(), execution, maximum_seconds=60)

        self.assertFalse(result["ok"])
        self.assertIn("normal Ask Insects call did not use the compact agent payload", result["failures"])

    def test_any_memory_local_alternate_test_or_maintenance_command_fails(self):
        unexpected_commands = [
            "rg diamondback /Users/josh/.codex/memories/MEMORY.md",
            "other-evidence-system answer question",
            "python3 scripts/verify_complete.py",
            "python3 -m pytest tests/test_answer.py",
            "ask-insects setup-agent",
            "ask-insects refresh",
        ]
        for command in unexpected_commands:
            with self.subTest(command=command):
                execution = successful_execution()
                execution.commands.append(command)
                result = evaluate_case(sample_case(), execution, maximum_seconds=60)
                self.assertFalse(result["ok"])

        question = str(sample_case()["question"])
        execution = successful_execution()
        execution.commands = [
            f'ask-insects ask "{question}" --json --compact --local'
        ]
        local = evaluate_case(sample_case(), execution, maximum_seconds=60)
        self.assertFalse(local["ok"])
        self.assertTrue(any("hosted" in failure for failure in local["failures"]))

        for event_type in ("web_search", "web_open", "web.run"):
            with self.subTest(event_type=event_type):
                execution = successful_execution()
                execution.event_types.append(event_type)
                result = evaluate_case(sample_case(), execution, maximum_seconds=60)
                self.assertFalse(result["ok"])
                self.assertTrue(any("web" in failure for failure in result["failures"]))

    def test_second_ask_or_search_call_fails_the_one_call_contract(self):
        for command in (
            'ask-insects ask "another question" --json',
            'ask-insects search insect_intelligence "diamondback moth"',
        ):
            with self.subTest(command=command):
                execution = successful_execution()
                execution.commands.append(command)

                result = evaluate_case(sample_case(), execution, maximum_seconds=60)

                self.assertFalse(result["ok"])

    def test_one_installed_skill_read_is_allowed_but_other_commands_fail(self):
        execution = successful_execution()
        execution.commands.insert(
            0,
            "sed -n '1,160p' /Users/josh/.codex/skills/askinsects/SKILL.md",
        )

        allowed = evaluate_case(sample_case(), execution, maximum_seconds=60)

        self.assertTrue(allowed["ok"], allowed["failures"])

        execution.commands.insert(0, "pwd")
        rejected = evaluate_case(sample_case(), execution, maximum_seconds=60)

        self.assertFalse(rejected["ok"])
        self.assertIn(
            "normal answer used an unexpected command outside the hosted Ask Insects route",
            rejected["failures"],
        )

        execution = successful_execution()
        execution.commands.append(
            "cat /Users/josh/.codex/skills/askinsects/SKILL.md",
        )
        wrong_order = evaluate_case(sample_case(), execution, maximum_seconds=60)
        self.assertFalse(wrong_order["ok"])

        invalid_reads = (
            "cat skills/askinsects/SKILL.md",
            "cat /tmp/other.md /Users/josh/.codex/skills/askinsects/SKILL.md",
            "cat /Users/josh/.codex/skills/askinsects/SKILL.md && pwd",
        )
        for command in invalid_reads:
            with self.subTest(command=command):
                execution = successful_execution()
                execution.commands.insert(0, command)
                result = evaluate_case(sample_case(), execution, maximum_seconds=60)
                self.assertFalse(result["ok"])

        execution = successful_execution()
        skill_read = "cat /Users/josh/.codex/skills/askinsects/SKILL.md"
        execution.commands = [skill_read, skill_read, *execution.commands]
        duplicate_reads = evaluate_case(sample_case(), execution, maximum_seconds=60)
        self.assertFalse(duplicate_reads["ok"])

    def test_compound_or_nonstandard_ask_commands_fail_the_allowlist(self):
        question = str(sample_case()["question"])
        commands = (
            f'ask-insects ask "{question}" --json --compact && pwd',
            f'ask-insects ask "{question}" --json --compact --limit 10',
            f'python3 -m askinsects ask "{question}" --json --compact',
            f'ASK_INSECTS_TOKEN=secret ask-insects ask "{question}" --json --compact',
        )
        for command in commands:
            with self.subTest(command=command):
                execution = successful_execution()
                execution.commands = [command]
                result = evaluate_case(sample_case(), execution, maximum_seconds=60)
                self.assertFalse(result["ok"])

    def test_duplicate_identical_command_events_are_not_collapsed(self):
        command = successful_execution().commands[0]
        stdout = "\n".join(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "command_execution", "command": command},
                }
            )
            for _ in range(2)
        )
        _, commands, _, _ = parse_codex_events(stdout)

        self.assertEqual(commands, [command, command])
        execution = successful_execution()
        execution.commands = commands
        result = evaluate_case(sample_case(), execution, maximum_seconds=60)
        self.assertFalse(result["ok"])
        self.assertTrue(any("exactly one" in failure for failure in result["failures"]))

    def test_parser_preserves_all_web_shaped_item_events(self):
        for item_type in ("web_search", "web_open", "custom_web_fetch"):
            with self.subTest(item_type=item_type):
                stdout = json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": item_type},
                    }
                )
                _, _, event_types, _ = parse_codex_events(stdout)

                self.assertIn(item_type, event_types)
                execution = successful_execution()
                execution.event_types = event_types
                result = evaluate_case(sample_case(), execution, maximum_seconds=60)
                self.assertFalse(result["ok"])
                self.assertTrue(any("web" in failure for failure in result["failures"]))

    def test_evaluator_uses_a_generic_allowlist_not_a_product_blacklist(self):
        source = (Path(__file__).parents[1] / "scripts/eval_production_path.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("BLOCKED_COMMAND_TERMS", source)
        self.assertNotIn("ask-monarch", source.casefold())

    def test_public_answer_leak_markers_fail_every_case(self):
        leaked_answers = (
            "Authorization: Bearer secret-token",
            "experiment:private-assay-123",
            "/Users/researcher/private/results.csv",
            "/home/service/private/results.json",
            "https://source.internal/result/1",
            "-----BEGIN PRIVATE KEY-----",
        )

        for leaked_answer in leaked_answers:
            with self.subTest(leaked_answer=leaked_answer):
                execution = successful_execution()
                execution.visible_answer += f" {leaked_answer}"

                result = evaluate_case(sample_case(), execution, maximum_seconds=60)

                self.assertFalse(result["ok"])
                self.assertTrue(
                    any("public answer leak" in failure for failure in result["failures"]),
                    result["failures"],
                )

    def test_full_gate_requires_every_corpus_case_on_the_unmodified_route(self):
        contract = {
            "contract_version": CONTRACT_VERSION,
            "minimum_case_count": 2,
            "maximum_seconds": 60,
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

    def test_regrade_preserves_execution_and_reapplies_current_grader(self):
        second_case = {
            **sample_case(),
            "id": "diamondback-gap-paraphrase",
            "question": "Which diamondback moth biology areas are still source gaps?",
        }
        contract = {
            "contract_version": CONTRACT_VERSION,
            "minimum_case_count": 2,
            "maximum_seconds": 60,
            "required_categories": {"species_coverage": 2},
            "cases": [sample_case(), second_case],
        }

        def execution_for(case: dict[str, object]) -> ExecutionResult:
            execution = successful_execution()
            execution.commands = [
                f'/bin/zsh -lc \'ask-insects ask "{case["question"]}" --json --compact\''
            ]
            return execution

        source = run_evaluation(contract, execute=execution_for)
        source["results"][0]["ok"] = False
        source["results"][0]["failures"] = ["stale grader failure"]
        source["passed_count"] = 1
        source["failed_count"] = 1
        source["all_cases_passed"] = False
        source["production_gate_passed"] = False

        regraded = regrade_evaluation(contract, source)

        self.assertTrue(regraded["production_gate_passed"])
        self.assertEqual(regraded["passed_count"], 2)
        self.assertEqual(regraded["failed_count"], 0)
        self.assertEqual(regraded["started_at"], source["started_at"])
        self.assertEqual(regraded["finished_at"], source["finished_at"])
        self.assertEqual(
            regraded["results"][0]["commands"],
            source["results"][0]["commands"],
        )
        self.assertIn("regraded_at", regraded)

    def test_regrade_rejects_changed_questions(self):
        contract = {
            "contract_version": CONTRACT_VERSION,
            "minimum_case_count": 1,
            "maximum_seconds": 60,
            "required_categories": {"species_coverage": 1},
            "cases": [sample_case()],
        }
        source = run_evaluation(contract, execute=lambda case: successful_execution())
        source["results"][0]["question"] = "A different question"

        with self.assertRaisesRegex(ValueError, "question mismatch"):
            regrade_evaluation(contract, source)

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
            "maximum_seconds": 60,
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
