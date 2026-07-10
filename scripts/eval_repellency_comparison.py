#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.answer import answer_question  # noqa: E402
from askinsects.builder import DEFAULT_ARTIFACT_DIR  # noqa: E402
from askinsects.hosted import hosted_request, load_config  # noqa: E402
from askinsects.repellency import (  # noqa: E402
    REPELLENCY_COMPARISON_CONTRACT_VERSION,
    is_repellency_comparison_question,
)


DEFAULT_CASES_PATH = REPO_ROOT / "evals" / "repellency_comparison_v1.json"


def load_cases(path: Path = DEFAULT_CASES_PATH) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("contract_version") != REPELLENCY_COMPARISON_CONTRACT_VERSION
    ):
        raise ValueError("repellency evaluation contract version mismatch")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not all(isinstance(case, dict) for case in cases):
        raise ValueError("repellency evaluation cases must be a list of objects")
    return cases


def evaluate_case(
    case: dict[str, object], payload: dict[str, object] | None
) -> dict[str, object]:
    question = str(case["question"])
    expected_route = bool(case["comparison_route"])
    failures: list[str] = []
    actual_route = is_repellency_comparison_question(question)
    if actual_route != expected_route:
        failures.append(f"route expected {expected_route} but got {actual_route}")

    if expected_route:
        if not isinstance(payload, dict):
            failures.append("comparison route returned no payload")
        else:
            if (
                payload.get("contract_version")
                != REPELLENCY_COMPARISON_CONTRACT_VERSION
            ):
                failures.append("answer contract version is missing or incorrect")
            for field in (
                "answer",
                "claim",
                "comparison",
                "coverage",
                "evidence",
                "source_gap",
            ):
                if field not in payload:
                    failures.append(f"answer contract is missing {field}")
            claim = payload.get("claim")
            if not isinstance(claim, dict):
                failures.append("claim must be an object")
            else:
                expected_claim_type = case.get("claim_type")
                if expected_claim_type and claim.get("type") != expected_claim_type:
                    failures.append(
                        f"claim type expected {expected_claim_type} but got {claim.get('type')}"
                    )
                reasons = claim.get("reasons")
                reason_codes = {
                    str(reason.get("code"))
                    for reason in reasons or []
                    if isinstance(reason, dict) and reason.get("code")
                }
                required_reason_codes = {
                    str(code) for code in case.get("required_reason_codes") or []
                }
                missing_reasons = sorted(required_reason_codes - reason_codes)
                if missing_reasons:
                    failures.append(
                        "missing reason codes: " + ", ".join(missing_reasons)
                    )
                missing_target_fields = {
                    str(field) for field in claim.get("missing_target_fields") or []
                }
                required_target_fields = {
                    str(field)
                    for field in case.get("required_missing_target_fields") or []
                }
                absent_target_fields = sorted(
                    required_target_fields - missing_target_fields
                )
                if absent_target_fields:
                    failures.append(
                        "missing target-field diagnostics: "
                        + ", ".join(absent_target_fields)
                    )
            answer = str(payload.get("answer") or "").lower()
            for phrase in case.get("forbidden_phrases") or []:
                if str(phrase).lower() in answer:
                    failures.append(f"answer contains forbidden phrase: {phrase}")

    return {
        "id": case.get("id"),
        "question": question,
        "ok": not failures,
        "failures": failures,
    }


def run_evaluation(
    *,
    answer_fn: Callable[[str], dict[str, object]],
    cases_path: Path = DEFAULT_CASES_PATH,
) -> dict[str, object]:
    results: list[dict[str, object]] = []
    for case in load_cases(cases_path):
        payload = answer_fn(str(case["question"])) if case["comparison_route"] else None
        results.append(evaluate_case(case, payload))
    return {
        "ok": all(result["ok"] for result in results),
        "contract_version": REPELLENCY_COMPARISON_CONTRACT_VERSION,
        "case_count": len(results),
        "passed_count": sum(1 for result in results if result["ok"]),
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the Ask Insects repellency comparison contract."
    )
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--hosted", action="store_true")
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH))
    args = parser.parse_args(argv)

    if args.hosted:
        config = load_config()

        def answer_fn(question: str) -> dict[str, object]:
            return hosted_request(
                config, "POST", "/ask", {"question": question, "limit": 100}
            )

    else:
        artifact_dir = Path(args.artifact_dir)

        def answer_fn(question: str) -> dict[str, object]:
            return answer_question(question, artifact_dir=artifact_dir, limit=100)

    result = run_evaluation(answer_fn=answer_fn, cases_path=Path(args.cases))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
