from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import median
from typing import Any


PUBLIC_MANIFEST_VERSION = "ask-insects-reality-public.v1"
HOLDOUT_BUNDLE_VERSION = "ask-insects-reality-holdouts.v1"
HOLDOUT_RECEIPT_VERSION = "ask-insects-reality-holdout-receipt.v1"
CONTRACT_VERSION = "realityeval.v1"
RESULTS_VERSION = "realityeval-results.v1"
TARGET = "ask-insects"
PUBLIC_QUESTION_COUNT = 40
HOLDOUT_QUESTION_COUNT = 10
QUESTION_COUNT = 50
MAXIMUM_SECONDS = 60.0
MINIMUM_CATEGORY_COUNT = 6
QUESTION_KINDS = {"domain", "boundary", "adversarial"}

_EVALUATION_MODE = "evaluation"
_INTERFACE = "codex-app"
_CASE_STRING_FIELDS = (
    "id",
    "question",
    "category",
    "origin",
    "why_realistic",
    "expected_behavior",
    "truth_source",
)
_TRUTH_SOURCE_FIELDS = ("source_id", "locator", "public_url", "supports")
_REQUIRED_RULES = (
    "exact_question_required",
    "first_attempt_only",
    "full_answer_required",
    "fresh_task_per_question",
    "sibling_answer_routes_forbidden",
)
_PASS_FIELDS = (
    "route_verdict",
    "content_verdict",
    "source_verdict",
    "privacy_verdict",
    "usefulness_verdict",
)
_META_MARKERS = (
    "coverage status",
    "program status",
    "what sources does ask",
)
_PRODUCT_META_PATTERN = re.compile(
    r"\b(?:what does ask \S+ cover|is ask \S+ complete|what is ask \S+ missing)\b"
)
_HOLDOUT_RECEIPT_FIELDS = frozenset(
    {
        "receipt_version",
        "target",
        "bundle_version",
        "created_at",
        "question_count",
        "bundle_sha256",
    }
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class RealityEvalError(ValueError):
    pass


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_json_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RealityEvalError(f"could not read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RealityEvalError(f"{path} must contain a JSON object")
    return payload


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RealityEvalError(f"{name} must be an object")
    return value


def _nonempty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RealityEvalError(f"{name} must be a nonempty string")
    return value


def _iso_timestamp(value: object, name: str) -> str:
    timestamp = _nonempty_string(value, name)
    if "T" not in timestamp:
        raise RealityEvalError(f"{name} must be an ISO-shaped timestamp")
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RealityEvalError(f"{name} must be an ISO-shaped timestamp") from exc
    return timestamp


def _string_list(
    value: object,
    name: str,
    *,
    require_nonempty: bool,
) -> list[str]:
    if not isinstance(value, list):
        raise RealityEvalError(f"{name} must be a list of nonempty strings")
    if require_nonempty and not value:
        raise RealityEvalError(f"{name} must be a nonempty list of nonempty strings")
    for index, item in enumerate(value):
        _nonempty_string(item, f"{name}[{index}]")
    return value


def _validate_truth_packet(value: object, name: str) -> dict[str, Any]:
    truth_packet = _object(value, name)
    _string_list(
        truth_packet.get("required_claims"),
        f"{name}.required_claims",
        require_nonempty=True,
    )
    _string_list(
        truth_packet.get("forbidden_claims"),
        f"{name}.forbidden_claims",
        require_nonempty=False,
    )
    _string_list(
        truth_packet.get("reasoning_boundaries"),
        f"{name}.reasoning_boundaries",
        require_nonempty=True,
    )

    sources = truth_packet.get("sources")
    if not isinstance(sources, list) or not sources:
        raise RealityEvalError(f"{name}.sources must be a nonempty list")
    for index, raw_source in enumerate(sources):
        source = _object(raw_source, f"{name}.sources[{index}]")
        for field in _TRUTH_SOURCE_FIELDS:
            _nonempty_string(source.get(field), f"{name}.sources[{index}].{field}")
    return truth_packet


def _normalized_question(question: str) -> str:
    return " ".join(question.casefold().split())


def _validate_case(
    value: object,
    name: str,
    *,
    expected_holdout: bool | None = None,
    expected_kind: str | None = None,
) -> dict[str, Any]:
    case = _object(value, name)
    strings = {
        field: _nonempty_string(case.get(field), f"{name}.{field}")
        for field in _CASE_STRING_FIELDS
    }

    kind = case.get("kind")
    if kind not in QUESTION_KINDS:
        raise RealityEvalError(f"{name}.kind must be one of {sorted(QUESTION_KINDS)}")
    if expected_kind is not None and kind != expected_kind:
        raise RealityEvalError(f"{name}.kind must be {expected_kind}")

    holdout = case.get("holdout")
    if not isinstance(holdout, bool):
        raise RealityEvalError(f"{name}.holdout must be a boolean")
    if expected_holdout is not None and holdout is not expected_holdout:
        expected = str(expected_holdout).lower()
        raise RealityEvalError(f"{name}.holdout must be {expected}")

    normalized = _normalized_question(strings["question"])
    if kind == "domain" and (
        any(marker in normalized for marker in _META_MARKERS)
        or _PRODUCT_META_PATTERN.search(normalized)
    ):
        raise RealityEvalError(
            f"question {strings['id']} is marked domain but asks about product coverage or status"
        )

    _validate_truth_packet(case.get("truth_packet"), f"{name}.truth_packet")
    return case


def _validate_cases(
    value: object,
    *,
    name: str,
    expected_count: int,
    expected_holdout: bool | None = None,
    expected_kind: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise RealityEvalError(f"{name} must be a list")
    if len(value) != expected_count:
        raise RealityEvalError(f"{name} must contain exactly {expected_count} questions")

    cases = [
        _validate_case(
            raw_case,
            f"{name}[{index}]",
            expected_holdout=expected_holdout,
            expected_kind=expected_kind,
        )
        for index, raw_case in enumerate(value)
    ]
    ids = [str(case["id"]) for case in cases]
    normalized_questions = [
        _normalized_question(str(case["question"])) for case in cases
    ]
    if len(ids) != len(set(ids)):
        raise RealityEvalError("question ids must be unique")
    if len(normalized_questions) != len(set(normalized_questions)):
        raise RealityEvalError("question wording must be unique")
    return cases


def _maximum_seconds(value: object, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) != MAXIMUM_SECONDS
    ):
        raise RealityEvalError(f"{name} must be {int(MAXIMUM_SECONDS)}")
    return float(value)


def validate_public_manifest(payload: object) -> dict[str, object]:
    manifest = _object(payload, "public manifest")
    if manifest.get("manifest_version") != PUBLIC_MANIFEST_VERSION:
        raise RealityEvalError(f"manifest_version must be {PUBLIC_MANIFEST_VERSION}")
    if manifest.get("target") != TARGET:
        raise RealityEvalError(f"public manifest target must be {TARGET}")
    _maximum_seconds(manifest.get("maximum_seconds"), "public manifest.maximum_seconds")
    _validate_cases(
        manifest.get("questions"),
        name="public manifest.questions",
        expected_count=PUBLIC_QUESTION_COUNT,
        expected_holdout=False,
        expected_kind="domain",
    )
    return manifest


def validate_holdout_bundle(payload: object) -> dict[str, object]:
    bundle = _object(payload, "holdout bundle")
    if bundle.get("bundle_version") != HOLDOUT_BUNDLE_VERSION:
        raise RealityEvalError(f"bundle_version must be {HOLDOUT_BUNDLE_VERSION}")
    if bundle.get("target") != TARGET:
        raise RealityEvalError(f"holdout bundle target must be {TARGET}")
    _iso_timestamp(bundle.get("created_at"), "holdout bundle.created_at")
    _validate_cases(
        bundle.get("questions"),
        name="holdout bundle.questions",
        expected_count=HOLDOUT_QUESTION_COUNT,
        expected_holdout=True,
    )
    return bundle


def _json_object_from_bytes(payload: bytes, name: str) -> dict[str, object]:
    if not isinstance(payload, bytes):
        raise RealityEvalError(f"{name} must be bytes")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RealityEvalError(f"could not parse {name}: {exc}") from exc
    if not isinstance(value, dict):
        raise RealityEvalError(f"{name} must contain a JSON object")
    return value


def build_holdout_receipt(bundle_bytes: bytes) -> dict[str, object]:
    bundle = validate_holdout_bundle(
        _json_object_from_bytes(bundle_bytes, "holdout bundle bytes")
    )
    return {
        "receipt_version": HOLDOUT_RECEIPT_VERSION,
        "target": TARGET,
        "bundle_version": HOLDOUT_BUNDLE_VERSION,
        "created_at": bundle["created_at"],
        "question_count": HOLDOUT_QUESTION_COUNT,
        "bundle_sha256": sha256_bytes(bundle_bytes),
    }


def validate_holdout_receipt(
    payload: object,
    *,
    bundle_bytes: bytes | None = None,
) -> dict[str, object]:
    receipt = _object(payload, "holdout receipt")
    if set(receipt) != _HOLDOUT_RECEIPT_FIELDS:
        raise RealityEvalError(
            f"holdout receipt keys must be exactly {sorted(_HOLDOUT_RECEIPT_FIELDS)}"
        )
    if receipt.get("receipt_version") != HOLDOUT_RECEIPT_VERSION:
        raise RealityEvalError(f"receipt_version must be {HOLDOUT_RECEIPT_VERSION}")
    if receipt.get("target") != TARGET:
        raise RealityEvalError(f"holdout receipt target must be {TARGET}")
    if receipt.get("bundle_version") != HOLDOUT_BUNDLE_VERSION:
        raise RealityEvalError(f"bundle_version must be {HOLDOUT_BUNDLE_VERSION}")
    created_at = _iso_timestamp(receipt.get("created_at"), "holdout receipt.created_at")
    question_count = receipt.get("question_count")
    if type(question_count) is not int or question_count != HOLDOUT_QUESTION_COUNT:
        raise RealityEvalError(
            f"holdout receipt.question_count must be {HOLDOUT_QUESTION_COUNT}"
        )
    bundle_sha256 = receipt.get("bundle_sha256")
    if not isinstance(bundle_sha256, str) or not _SHA256_PATTERN.fullmatch(bundle_sha256):
        raise RealityEvalError(
            "holdout receipt.bundle_sha256 must be a lowercase 64-hex SHA-256"
        )

    if bundle_bytes is not None:
        if not isinstance(bundle_bytes, bytes):
            raise RealityEvalError("holdout bundle bytes must be bytes")
        if sha256_bytes(bundle_bytes) != bundle_sha256:
            raise RealityEvalError(
                "holdout receipt bundle_sha256 does not match the exact bundle bytes"
            )
        bundle = validate_holdout_bundle(
            _json_object_from_bytes(bundle_bytes, "holdout bundle bytes")
        )
        if bundle["created_at"] != created_at:
            raise RealityEvalError(
                "holdout receipt.created_at does not match the holdout bundle"
            )
    return receipt


def assemble_contract(
    public_manifest: object,
    holdout_bundle: object,
) -> dict[str, object]:
    public = validate_public_manifest(public_manifest)
    holdouts = validate_holdout_bundle(holdout_bundle)
    contract = {
        "contract_version": CONTRACT_VERSION,
        "target": TARGET,
        "mode": _EVALUATION_MODE,
        "interface": _INTERFACE,
        "maximum_seconds": int(MAXIMUM_SECONDS),
        "rules": {name: True for name in _REQUIRED_RULES},
        "questions": deepcopy(public["questions"]) + deepcopy(holdouts["questions"]),
    }
    return validate_contract(contract)


def validate_contract(payload: object) -> dict[str, object]:
    contract = _object(payload, "contract")
    if contract.get("contract_version") != CONTRACT_VERSION:
        raise RealityEvalError(f"contract_version must be {CONTRACT_VERSION}")
    if contract.get("target") != TARGET:
        raise RealityEvalError(f"contract target must be {TARGET}")
    if contract.get("mode") != _EVALUATION_MODE:
        raise RealityEvalError(f"contract mode must be {_EVALUATION_MODE}")
    if contract.get("interface") != _INTERFACE:
        raise RealityEvalError(f"contract interface must be {_INTERFACE}")
    _maximum_seconds(contract.get("maximum_seconds"), "contract.maximum_seconds")

    rules = _object(contract.get("rules"), "contract.rules")
    for name in _REQUIRED_RULES:
        if rules.get(name) is not True:
            raise RealityEvalError(f"contract.rules.{name} must be true")

    cases = _validate_cases(
        contract.get("questions"),
        name="contract.questions",
        expected_count=QUESTION_COUNT,
    )
    holdout_count = sum(case["holdout"] is True for case in cases)
    if holdout_count != HOLDOUT_QUESTION_COUNT:
        raise RealityEvalError(
            f"contract must contain exactly {HOLDOUT_QUESTION_COUNT} holdouts"
        )
    domain_count = sum(case["kind"] == "domain" for case in cases)
    if domain_count < PUBLIC_QUESTION_COUNT:
        raise RealityEvalError(
            f"contract must contain at least {PUBLIC_QUESTION_COUNT} domain questions"
        )
    category_count = len({str(case["category"]) for case in cases})
    if category_count < MINIMUM_CATEGORY_COUNT:
        raise RealityEvalError(
            f"contract must contain at least {MINIMUM_CATEGORY_COUNT} categories"
        )
    if any(case["holdout"] is True for case in cases[:PUBLIC_QUESTION_COUNT]):
        raise RealityEvalError("contract public questions must precede holdouts")
    if any(case["holdout"] is False for case in cases[PUBLIC_QUESTION_COUNT:]):
        raise RealityEvalError("contract holdouts must follow public questions")
    return contract


def validate_results(
    payload: object,
    *,
    contract: dict[str, object],
    contract_sha256: str,
) -> dict[str, object]:
    validated_contract = validate_contract(contract)
    result_doc = _object(payload, "results document")
    if result_doc.get("results_version") != RESULTS_VERSION:
        raise RealityEvalError(f"results_version must be {RESULTS_VERSION}")
    if result_doc.get("contract_sha256") != contract_sha256:
        raise RealityEvalError("contract_sha256 does not match the exact contract bytes")
    if result_doc.get("target") != validated_contract["target"]:
        raise RealityEvalError("results target does not match contract target")
    if result_doc.get("mode") != validated_contract["mode"]:
        raise RealityEvalError("results mode does not match contract mode")
    _nonempty_string(result_doc.get("environment"), "results.environment")
    _nonempty_string(result_doc.get("revision"), "results.revision")

    recording = _object(result_doc.get("recording"), "results.recording")
    _nonempty_string(
        recording.get("recording_path"),
        "results.recording.recording_path",
    )
    if recording.get("question_count") != QUESTION_COUNT:
        raise RealityEvalError(
            f"results.recording.question_count must be {QUESTION_COUNT}"
        )
    if recording.get("complete_answers_visible") is not True:
        raise RealityEvalError("results.recording.complete_answers_visible must be true")
    if recording.get("privacy_review") != "pass":
        raise RealityEvalError("results.recording.privacy_review must be pass")
    if recording.get("shared_with_josh") is not True:
        raise RealityEvalError("results.recording.shared_with_josh must be true")

    raw_results = result_doc.get("results")
    if not isinstance(raw_results, list):
        raise RealityEvalError("results must be a list")
    cases = {
        str(case["id"]): case
        for case in validated_contract["questions"]
        if isinstance(case, dict)
    }
    if len(raw_results) != QUESTION_COUNT:
        raise RealityEvalError("results must contain exactly 50 unique results")

    maximum_seconds = float(validated_contract["maximum_seconds"])
    seen_ids: set[str] = set()
    for index, raw_result in enumerate(raw_results):
        result = _object(raw_result, f"results[{index}]")
        case_id = _nonempty_string(result.get("id"), f"results[{index}].id")
        if case_id not in cases:
            raise RealityEvalError(f"results[{index}] has unknown id {case_id}")
        if case_id in seen_ids:
            raise RealityEvalError(f"results contains duplicate id {case_id}")
        seen_ids.add(case_id)
        if result.get("question") != cases[case_id]["question"]:
            raise RealityEvalError(f"result {case_id} changed the exact frozen question")
        _nonempty_string(result.get("answer"), f"result {case_id}.answer")

        elapsed = result.get("elapsed_seconds")
        if (
            isinstance(elapsed, bool)
            or not isinstance(elapsed, (int, float))
            or not math.isfinite(float(elapsed))
            or float(elapsed) < 0
        ):
            raise RealityEvalError(
                f"result {case_id}.elapsed_seconds must be a nonnegative number"
            )
        if float(elapsed) >= maximum_seconds:
            raise RealityEvalError(f"result {case_id} exceeded the strict time limit")
        if type(result.get("attempt")) is not int or result.get("attempt") != 1:
            raise RealityEvalError(f"result {case_id} must preserve attempt 1")
        if result.get("interface_observed") != _INTERFACE:
            raise RealityEvalError(f"result {case_id} must use the codex-app interface")
        if result.get("answer_systems") != [TARGET]:
            raise RealityEvalError(
                f"result {case_id} used a sibling or alternate answer system"
            )
        if result.get("fresh_task") is not True:
            raise RealityEvalError(f"result {case_id} did not use a fresh task")
        if result.get("complete_answer_visible") is not True:
            raise RealityEvalError(f"result {case_id} did not preserve the complete answer")
        for field in _PASS_FIELDS:
            if result.get(field) != "pass":
                raise RealityEvalError(f"result {case_id}.{field} must be pass")
        _nonempty_string(result.get("judge_evidence"), f"result {case_id}.judge_evidence")

        provenance = result.get("provenance")
        if not isinstance(provenance, list) or not provenance:
            raise RealityEvalError(f"result {case_id}.provenance must be a nonempty list")
        for provenance_index, raw_item in enumerate(provenance):
            item = _object(
                raw_item,
                f"result {case_id}.provenance[{provenance_index}]",
            )
            _nonempty_string(
                item.get("source_id"),
                f"result {case_id}.provenance[{provenance_index}].source_id",
            )
            _nonempty_string(
                item.get("locator"),
                f"result {case_id}.provenance[{provenance_index}].locator",
            )

    missing = set(cases) - seen_ids
    if missing:
        raise RealityEvalError(f"results omitted ids: {', '.join(sorted(missing))}")
    return result_doc


def summarize_results(results: dict[str, object]) -> dict[str, object]:
    raw_results = results["results"]
    assert isinstance(raw_results, list)
    elapsed_values = sorted(float(result["elapsed_seconds"]) for result in raw_results)
    passed_count = sum(
        all(result.get(field) == "pass" for field in _PASS_FIELDS)
        for result in raw_results
    )
    question_count = len(raw_results)
    failed_count = question_count - passed_count
    p95_index = math.ceil(0.95 * question_count) - 1
    return {
        "question_count": question_count,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "p50_seconds": median(elapsed_values),
        "p95_seconds": elapsed_values[p95_index],
        "maximum_seconds": elapsed_values[-1],
        "reality_eval_passed": question_count == QUESTION_COUNT and failed_count == 0,
    }
