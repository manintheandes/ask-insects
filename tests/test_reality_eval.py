import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from askinsects.reality_eval import (
    CONTRACT_VERSION,
    HOLDOUT_BUNDLE_VERSION,
    HOLDOUT_QUESTION_COUNT,
    HOLDOUT_RECEIPT_VERSION,
    PUBLIC_MANIFEST_VERSION,
    PUBLIC_QUESTION_COUNT,
    QUESTION_COUNT,
    RESULTS_VERSION,
    TARGET,
    RealityEvalError,
    assemble_contract,
    build_holdout_receipt,
    load_json_object,
    sha256_bytes,
    summarize_results,
    validate_contract,
    validate_holdout_bundle,
    validate_holdout_receipt,
    validate_public_manifest,
    validate_results,
)


CREATED_AT = "2026-07-16T12:00:00Z"


def truth_packet(case_id):
    return {
        "required_claims": [f"State the measured observation for {case_id}."],
        "forbidden_claims": ["The observation proves commercial efficacy."],
        "reasoning_boundaries": ["Separate observation from mechanism."],
        "sources": [
            {
                "source_id": f"public-source-{case_id}",
                "locator": f"records#{case_id}",
                "public_url": f"https://example.org/sources/{case_id}",
                "supports": f"The measured observation for {case_id}.",
            }
        ],
    }


def question_case(
    case_id,
    *,
    holdout,
    kind="domain",
    category="category-0",
):
    return {
        "id": case_id,
        "question": f"How should a scientist interpret evidence for {case_id}?",
        "category": category,
        "kind": kind,
        "origin": "scientist-workflow",
        "holdout": holdout,
        "why_realistic": "A scientist must interpret evidence before making a decision.",
        "expected_behavior": "State the observation and preserve the reasoning boundary.",
        "truth_source": "Independent review of the cited public source.",
        "truth_packet": truth_packet(case_id),
    }


def public_manifest():
    return {
        "manifest_version": PUBLIC_MANIFEST_VERSION,
        "target": TARGET,
        "maximum_seconds": 60,
        "questions": [
            question_case(
                f"public-{index:02d}",
                holdout=False,
                category=f"category-{index % 6}",
            )
            for index in range(PUBLIC_QUESTION_COUNT)
        ],
    }


def holdout_bundle():
    kinds = ("domain", "boundary", "adversarial")
    return {
        "bundle_version": HOLDOUT_BUNDLE_VERSION,
        "target": TARGET,
        "created_at": CREATED_AT,
        "questions": [
            question_case(
                f"holdout-{index:02d}",
                holdout=True,
                kind=kinds[index % len(kinds)],
                category=f"holdout-category-{index % 2}",
            )
            for index in range(HOLDOUT_QUESTION_COUNT)
        ],
    }


def contract_bytes(contract):
    return json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")


def passing_results(contract=None, contract_hash=None):
    contract = contract or assemble_contract(public_manifest(), holdout_bundle())
    contract_hash = contract_hash or sha256_bytes(contract_bytes(contract))
    return {
        "results_version": RESULTS_VERSION,
        "contract_sha256": contract_hash,
        "target": TARGET,
        "mode": "evaluation",
        "environment": "Codex desktop production route",
        "revision": "revision-123",
        "recording": {
            "recording_path": "/private/tmp/reality-eval-recording.mov",
            "question_count": QUESTION_COUNT,
            "complete_answers_visible": True,
            "privacy_review": "pass",
            "shared_with_josh": True,
        },
        "results": [
            {
                "id": case["id"],
                "question": case["question"],
                "answer": f"Complete source-backed answer for {case['id']}.",
                "elapsed_seconds": index / 10,
                "attempt": 1,
                "interface_observed": "codex-app",
                "answer_systems": [TARGET],
                "fresh_task": True,
                "complete_answer_visible": True,
                "route_verdict": "pass",
                "content_verdict": "pass",
                "source_verdict": "pass",
                "privacy_verdict": "pass",
                "usefulness_verdict": "pass",
                "judge_evidence": "The independent source supports the answer.",
                "provenance": [
                    {
                        "source_id": f"source-{case['id']}",
                        "locator": f"records#{case['id']}",
                    }
                ],
            }
            for index, case in enumerate(contract["questions"])
        ],
    }


class RealityEvalTests(unittest.TestCase):
    def test_sha256_and_json_object_helpers(self):
        payload = b'{"ok": true}'
        self.assertEqual(sha256_bytes(payload), hashlib.sha256(payload).hexdigest())

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "object.json"
            path.write_bytes(payload)
            self.assertEqual(load_json_object(path), {"ok": True})
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(RealityEvalError, "JSON object"):
                load_json_object(path)

    def test_valid_public_manifest(self):
        validated = validate_public_manifest(public_manifest())

        self.assertEqual(len(validated["questions"]), PUBLIC_QUESTION_COUNT)
        self.assertTrue(all(case["holdout"] is False for case in validated["questions"]))
        self.assertTrue(all(case["kind"] == "domain" for case in validated["questions"]))

    def test_public_manifest_rejects_39_and_41_cases(self):
        too_few = public_manifest()
        too_few["questions"].pop()
        too_many = public_manifest()
        too_many["questions"].append(
            question_case("public-40", holdout=False, category="category-0")
        )

        for payload in (too_few, too_many):
            with self.subTest(question_count=len(payload["questions"])):
                with self.assertRaisesRegex(RealityEvalError, "exactly 40"):
                    validate_public_manifest(payload)

    def test_public_manifest_rejects_holdouts_and_non_domain_cases(self):
        mutations = (("holdout", True, "holdout"), ("kind", "boundary", "domain"))

        for field, value, message in mutations:
            with self.subTest(field=field):
                payload = public_manifest()
                payload["questions"][0][field] = value
                with self.assertRaisesRegex(RealityEvalError, message):
                    validate_public_manifest(payload)

    def test_valid_holdout_bundle(self):
        validated = validate_holdout_bundle(holdout_bundle())

        self.assertEqual(len(validated["questions"]), HOLDOUT_QUESTION_COUNT)
        self.assertTrue(all(case["holdout"] is True for case in validated["questions"]))

    def test_holdout_bundle_rejects_non_holdout_case(self):
        payload = holdout_bundle()
        payload["questions"][0]["holdout"] = False

        with self.assertRaisesRegex(RealityEvalError, "holdout"):
            validate_holdout_bundle(payload)

    def test_cases_reject_missing_or_empty_truth_fields(self):
        payload = holdout_bundle()
        del payload["questions"][0]["truth_packet"]
        with self.assertRaisesRegex(RealityEvalError, "truth_packet"):
            validate_holdout_bundle(payload)

        mutations = (
            ("required_claims", []),
            ("required_claims", [" "]),
            ("forbidden_claims", [""]),
            ("reasoning_boundaries", []),
            ("sources", []),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                payload = holdout_bundle()
                payload["questions"][0]["truth_packet"][field] = value
                with self.assertRaisesRegex(RealityEvalError, field):
                    validate_holdout_bundle(payload)

        for field in ("source_id", "locator", "public_url", "supports"):
            with self.subTest(source_field=field):
                payload = holdout_bundle()
                payload["questions"][0]["truth_packet"]["sources"][0][field] = ""
                with self.assertRaisesRegex(RealityEvalError, field):
                    validate_holdout_bundle(payload)

    def test_duplicate_ids_and_normalized_wording_are_rejected(self):
        duplicate_id = public_manifest()
        duplicate_id["questions"][1]["id"] = duplicate_id["questions"][0]["id"]
        with self.assertRaisesRegex(RealityEvalError, "ids must be unique"):
            validate_public_manifest(duplicate_id)

        duplicate_wording = public_manifest()
        question = duplicate_wording["questions"][0]["question"]
        duplicate_wording["questions"][1]["question"] = (
            f"  {question.upper().replace(' ', '   ')}  "
        )
        with self.assertRaisesRegex(RealityEvalError, "wording must be unique"):
            validate_public_manifest(duplicate_wording)

    def test_assembly_rejects_duplicates_across_public_and_holdout_cases(self):
        public = public_manifest()
        holdouts = holdout_bundle()
        holdouts["questions"][0]["id"] = public["questions"][0]["id"]

        with self.assertRaisesRegex(RealityEvalError, "ids must be unique"):
            assemble_contract(public, holdouts)

        holdouts = holdout_bundle()
        holdouts["questions"][0]["question"] = public["questions"][0]["question"]
        with self.assertRaisesRegex(RealityEvalError, "wording must be unique"):
            assemble_contract(public, holdouts)

    def test_domain_cases_reject_product_meta_questions(self):
        payload = public_manifest()
        payload["questions"][0]["question"] = (
            "What does Ask Insects cover for Aedes aegypti?"
        )

        with self.assertRaisesRegex(RealityEvalError, "coverage or status"):
            validate_public_manifest(payload)

    def test_final_contract_requires_six_categories(self):
        contract = assemble_contract(public_manifest(), holdout_bundle())
        for case in contract["questions"]:
            case["category"] = "one-category"

        with self.assertRaisesRegex(RealityEvalError, "at least 6"):
            validate_contract(contract)

    def test_final_contract_requires_exactly_50_cases_and_10_holdouts(self):
        contract = assemble_contract(public_manifest(), holdout_bundle())
        validated = validate_contract(contract)

        self.assertEqual(len(validated["questions"]), QUESTION_COUNT)
        self.assertEqual(sum(case["holdout"] for case in validated["questions"]), 10)
        self.assertGreaterEqual(
            sum(case["kind"] == "domain" for case in validated["questions"]),
            40,
        )
        self.assertTrue(all(not case["holdout"] for case in validated["questions"][:40]))
        self.assertTrue(all(case["holdout"] for case in validated["questions"][40:]))

        missing_case = deepcopy(contract)
        missing_case["questions"].pop()
        with self.assertRaisesRegex(RealityEvalError, "exactly 50"):
            validate_contract(missing_case)

        nine_holdouts = deepcopy(contract)
        nine_holdouts["questions"][-1]["holdout"] = False
        with self.assertRaisesRegex(RealityEvalError, "exactly 10"):
            validate_contract(nine_holdouts)

    def test_assembled_contract_has_installed_validator_shape(self):
        contract = assemble_contract(public_manifest(), holdout_bundle())

        self.assertEqual(
            set(contract),
            {
                "contract_version",
                "target",
                "mode",
                "interface",
                "maximum_seconds",
                "rules",
                "questions",
            },
        )
        self.assertEqual(contract["contract_version"], CONTRACT_VERSION)
        self.assertEqual(contract["target"], TARGET)
        self.assertEqual(contract["mode"], "evaluation")
        self.assertEqual(contract["interface"], "codex-app")
        self.assertEqual(contract["maximum_seconds"], 60)
        self.assertEqual(
            contract["rules"],
            {
                "exact_question_required": True,
                "first_attempt_only": True,
                "full_answer_required": True,
                "fresh_task_per_question": True,
                "sibling_answer_routes_forbidden": True,
            },
        )

    def test_holdout_receipt_allows_only_exact_keys_and_hashes_exact_bytes(self):
        bundle = holdout_bundle()
        bundle_bytes = json.dumps(bundle, indent=2).encode("utf-8")
        receipt = build_holdout_receipt(bundle_bytes)

        self.assertEqual(
            set(receipt),
            {
                "receipt_version",
                "target",
                "bundle_version",
                "created_at",
                "question_count",
                "bundle_sha256",
            },
        )
        self.assertEqual(receipt["receipt_version"], HOLDOUT_RECEIPT_VERSION)
        self.assertEqual(receipt["bundle_version"], HOLDOUT_BUNDLE_VERSION)
        self.assertEqual(receipt["created_at"], CREATED_AT)
        self.assertEqual(receipt["question_count"], HOLDOUT_QUESTION_COUNT)
        self.assertEqual(receipt["bundle_sha256"], hashlib.sha256(bundle_bytes).hexdigest())
        self.assertEqual(validate_holdout_receipt(receipt, bundle_bytes=bundle_bytes), receipt)

        receipt_with_extra = {**receipt, "questions": []}
        with self.assertRaisesRegex(RealityEvalError, "keys"):
            validate_holdout_receipt(receipt_with_extra)

    def test_holdout_receipt_rejects_changed_supplied_bytes(self):
        bundle_bytes = json.dumps(holdout_bundle(), indent=2).encode("utf-8")
        receipt = build_holdout_receipt(bundle_bytes)

        with self.assertRaisesRegex(RealityEvalError, "exact bundle bytes"):
            validate_holdout_receipt(receipt, bundle_bytes=bundle_bytes + b"\n")

    def test_passing_baseline_results(self):
        contract = assemble_contract(public_manifest(), holdout_bundle())
        digest = sha256_bytes(contract_bytes(contract))
        payload = passing_results(contract, digest)

        self.assertEqual(
            validate_results(payload, contract=contract, contract_sha256=digest),
            payload,
        )

    def test_elapsed_time_equal_to_60_is_rejected(self):
        contract = assemble_contract(public_manifest(), holdout_bundle())
        digest = sha256_bytes(contract_bytes(contract))
        payload = passing_results(contract, digest)
        payload["results"][0]["elapsed_seconds"] = 60.0

        with self.assertRaisesRegex(RealityEvalError, "strict time limit"):
            validate_results(payload, contract=contract, contract_sha256=digest)

    def test_missing_recording_is_rejected(self):
        contract = assemble_contract(public_manifest(), holdout_bundle())
        digest = sha256_bytes(contract_bytes(contract))
        payload = passing_results(contract, digest)
        del payload["recording"]

        with self.assertRaisesRegex(RealityEvalError, "recording"):
            validate_results(payload, contract=contract, contract_sha256=digest)

    def test_results_summary_uses_median_and_nearest_rank_p95(self):
        payload = passing_results()
        for index, result in enumerate(payload["results"]):
            result["elapsed_seconds"] = float(index)

        self.assertEqual(
            summarize_results(payload),
            {
                "question_count": 50,
                "passed_count": 50,
                "failed_count": 0,
                "p50_seconds": 24.5,
                "p95_seconds": 47.0,
                "maximum_seconds": 49.0,
                "reality_eval_passed": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
