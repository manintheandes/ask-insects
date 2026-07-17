from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
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
EVALUATOR_VERSION = "ask-insects-reality-evaluator.v1"
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
_TRUTH_SOURCE_FIELDS = ("title", "source_id", "locator", "public_url", "supports")
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
_PRODUCT_REFERENCE_PATTERN = re.compile(
    r"\bask (?:insects|just|" + "mon" + r"arch)\b"
)
_CATEGORY_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_UTC_SECOND_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z"
)
_UTC_SECOND_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_UTC_SECOND_LENGTH = 20
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
_GIT_COMMIT_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_RUN_MANIFEST_FIELDS = frozenset(
    {
        "repository_commit",
        "installed_skill_sha256",
        "hosted_revision",
        "public_corpus_sha256",
        "holdout_receipt_sha256",
        "evaluator_version",
        "unchanged_run_started_at",
        "unchanged_run_finished_at",
    }
)
_SCIENTIFIC_JUDGE = "independent-source-review"


class RealityEvalError(ValueError):
    pass


def sha256_bytes(payload: bytes) -> str:
    if not isinstance(payload, bytes):
        raise RealityEvalError("SHA-256 payload must be bytes")
    return hashlib.sha256(payload).hexdigest()


def _reject_duplicate_object_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise RealityEvalError(f"duplicate JSON object key: {key}")
        value[key] = item
    return value


def _strict_json_loads(payload: str | bytes, name: str) -> object:
    try:
        return json.loads(payload, object_pairs_hook=_reject_duplicate_object_keys)
    except RealityEvalError:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise RealityEvalError(f"could not parse {name}: {exc}") from exc


def load_json_object(path: Path) -> dict[str, object]:
    try:
        raw_payload = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RealityEvalError(f"could not read {path}: {exc}") from exc
    payload = _strict_json_loads(raw_payload, str(path))
    if not isinstance(payload, dict):
        raise RealityEvalError(f"{path} must contain a JSON object")
    return payload


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RealityEvalError(f"{name} must be an object")
    return value


def _same_json_value(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(
            _same_json_value(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _same_json_value(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return left == right


def _nonempty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RealityEvalError(f"{name} must be a nonempty string")
    return value


def _utc_second_datetime(value: object, name: str) -> datetime:
    if (
        not isinstance(value, str)
        or len(value) != _UTC_SECOND_LENGTH
        or not _UTC_SECOND_PATTERN.fullmatch(value)
    ):
        raise RealityEvalError(f"{name} must be a UTC second timestamp YYYY-MM-DDTHH:MM:SSZ")
    try:
        parsed = datetime.strptime(value, _UTC_SECOND_FORMAT)
    except ValueError as exc:
        raise RealityEvalError(
            f"{name} must be a valid UTC second timestamp YYYY-MM-DDTHH:MM:SSZ"
        ) from exc
    return parsed.replace(tzinfo=UTC)


def _utc_second_timestamp(value: object, name: str) -> str:
    _utc_second_datetime(value, name)
    assert isinstance(value, str)
    return value


def _strict_integer(value: object, name: str, *, expected: int) -> int:
    if type(value) is not int or value != expected:
        raise RealityEvalError(f"{name} must be the strict integer {expected}")
    return value


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RealityEvalError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise RealityEvalError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise RealityEvalError(f"{name} must be a finite number")
    return number


def _absolute_path(value: object, name: str) -> str:
    path_string = _nonempty_string(value, name)
    try:
        is_absolute = Path(path_string).is_absolute()
    except (OSError, ValueError) as exc:
        raise RealityEvalError(f"{name} must be an absolute filesystem path") from exc
    if not is_absolute:
        raise RealityEvalError(f"{name} must be an absolute filesystem path")
    return path_string


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
        source_id = str(source["source_id"])
        locator = str(source["locator"])
        public_url = str(source["public_url"])
        if (
            source_id == "insect_intelligence_programs"
            or "config/insect-intelligence-programs.json" in locator
            or "config/insect-intelligence-programs.json" in public_url
        ):
            raise RealityEvalError(
                f"{name}.sources[{index}] must cite an original scientific or official source; "
                "the internal program ledger cannot count as scientific provenance"
            )
        if not public_url.startswith(("https://", "http://")):
            raise RealityEvalError(
                f"{name}.sources[{index}].public_url must be an HTTP(S) original source URL"
            )
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
    if not _CATEGORY_PATTERN.fullmatch(strings["category"]):
        raise RealityEvalError(f"{name}.category must be a lowercase slug")

    kind = case.get("kind")
    if not isinstance(kind, str) or kind not in QUESTION_KINDS:
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
        or _PRODUCT_REFERENCE_PATTERN.search(normalized)
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
    maximum_seconds = _finite_number(value, name)
    if maximum_seconds != MAXIMUM_SECONDS:
        raise RealityEvalError(f"{name} must be {int(MAXIMUM_SECONDS)}")
    return maximum_seconds


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
    _utc_second_timestamp(bundle.get("created_at"), "holdout bundle.created_at")
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
    value = _strict_json_loads(payload, name)
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
    created_at = _utc_second_timestamp(
        receipt.get("created_at"),
        "holdout receipt.created_at",
    )
    _strict_integer(
        receipt.get("question_count"),
        "holdout receipt.question_count",
        expected=HOLDOUT_QUESTION_COUNT,
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


def _lowercase_sha256(value: object, name: str) -> str:
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
        raise RealityEvalError(f"{name} must be a lowercase 64-hex SHA-256")
    return value


def _json_sha256(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise RealityEvalError(f"could not fingerprint JSON value: {exc}") from exc
    return sha256_bytes(payload)


def _validate_run_manifest(
    value: object,
    *,
    revision: str,
) -> tuple[datetime, datetime]:
    manifest = _object(value, "results.run_manifest")
    if set(manifest) != _RUN_MANIFEST_FIELDS:
        raise RealityEvalError(
            f"results.run_manifest keys must be exactly {sorted(_RUN_MANIFEST_FIELDS)}"
        )

    repository_commit = manifest.get("repository_commit")
    if (
        not isinstance(repository_commit, str)
        or not _GIT_COMMIT_PATTERN.fullmatch(repository_commit)
    ):
        raise RealityEvalError(
            "results.run_manifest.repository_commit must be a lowercase 40- or 64-hex Git commit"
        )
    _lowercase_sha256(
        manifest.get("installed_skill_sha256"),
        "results.run_manifest.installed_skill_sha256",
    )
    hosted_revision = _nonempty_string(
        manifest.get("hosted_revision"),
        "results.run_manifest.hosted_revision",
    )
    _lowercase_sha256(
        manifest.get("public_corpus_sha256"),
        "results.run_manifest.public_corpus_sha256",
    )
    _lowercase_sha256(
        manifest.get("holdout_receipt_sha256"),
        "results.run_manifest.holdout_receipt_sha256",
    )
    if manifest.get("evaluator_version") != EVALUATOR_VERSION:
        raise RealityEvalError(
            f"results.run_manifest.evaluator_version must be {EVALUATOR_VERSION}"
        )
    started_at = _utc_second_datetime(
        manifest.get("unchanged_run_started_at"),
        "results.run_manifest.unchanged_run_started_at",
    )
    finished_at = _utc_second_datetime(
        manifest.get("unchanged_run_finished_at"),
        "results.run_manifest.unchanged_run_finished_at",
    )
    if finished_at < started_at:
        raise RealityEvalError(
            "results.run_manifest unchanged run finished earlier than it started"
        )
    if revision != hosted_revision:
        raise RealityEvalError(
            "results.revision must match results.run_manifest.hosted_revision"
        )
    return started_at, finished_at


def _truth_packet_claims(truth_packet: dict[str, Any]) -> list[str]:
    claims: list[str] = []
    for field in (
        "required_claims",
        "forbidden_claims",
        "reasoning_boundaries",
    ):
        values = truth_packet[field]
        if not isinstance(values, list):
            raise RealityEvalError(f"validated truth_packet.{field} must be a list")
        claims.extend(str(value) for value in values)
    return claims


def _validate_scientific_grade(
    value: object,
    *,
    case_id: str,
    truth_packet: dict[str, Any],
) -> None:
    grade = _object(value, f"result {case_id}.scientific_grade")
    if grade.get("judge") != _SCIENTIFIC_JUDGE:
        raise RealityEvalError(
            f"result {case_id}.scientific_grade.judge must be {_SCIENTIFIC_JUDGE}"
        )
    truth_packet_sha256 = _lowercase_sha256(
        grade.get("truth_packet_sha256"),
        f"result {case_id}.scientific_grade.truth_packet_sha256",
    )
    if truth_packet_sha256 != _json_sha256(truth_packet):
        raise RealityEvalError(
            f"result {case_id}.scientific_grade.truth_packet_sha256 does not match the frozen truth packet"
        )

    raw_checks = grade.get("claim_checks")
    if not isinstance(raw_checks, list) or not raw_checks:
        raise RealityEvalError(
            f"result {case_id}.scientific_grade.claim_checks must be a nonempty list"
        )
    checked_claims: list[str] = []
    for index, raw_check in enumerate(raw_checks):
        check = _object(
            raw_check,
            f"result {case_id}.scientific_grade.claim_checks[{index}]",
        )
        checked_claims.append(
            _nonempty_string(
                check.get("claim"),
                f"result {case_id}.scientific_grade.claim_checks[{index}].claim",
            )
        )
        if check.get("verdict") != "pass":
            raise RealityEvalError(
                f"result {case_id}.scientific_grade.claim_checks[{index}].verdict must be pass"
            )
        _nonempty_string(
            check.get("evidence"),
            f"result {case_id}.scientific_grade.claim_checks[{index}].evidence",
        )

    expected_claims = _truth_packet_claims(truth_packet)
    if (
        len(checked_claims) != len(expected_claims)
        or len(checked_claims) != len(set(checked_claims))
        or set(checked_claims) != set(expected_claims)
    ):
        raise RealityEvalError(
            f"result {case_id}.scientific_grade.claim_checks do not cover the frozen truth packet exactly"
        )


def validate_results(
    payload: object,
    *,
    contract: dict[str, object],
    contract_bytes: bytes,
) -> dict[str, object]:
    contract_object = _object(contract, "contract")
    parsed_contract = _json_object_from_bytes(contract_bytes, "contract bytes")
    if not _same_json_value(contract_object, parsed_contract):
        raise RealityEvalError("contract object does not match the exact contract bytes")
    validated_contract = validate_contract(parsed_contract)

    result_doc = _object(payload, "results document")
    if result_doc.get("results_version") != RESULTS_VERSION:
        raise RealityEvalError(f"results_version must be {RESULTS_VERSION}")
    if result_doc.get("contract_sha256") != sha256_bytes(contract_bytes):
        raise RealityEvalError("contract_sha256 does not match the exact contract bytes")
    if result_doc.get("target") != validated_contract["target"]:
        raise RealityEvalError("results target does not match contract target")
    if result_doc.get("mode") != validated_contract["mode"]:
        raise RealityEvalError("results mode does not match contract mode")
    _nonempty_string(result_doc.get("environment"), "results.environment")
    revision = _nonempty_string(result_doc.get("revision"), "results.revision")
    run_started_at, run_finished_at = _validate_run_manifest(
        result_doc.get("run_manifest"),
        revision=revision,
    )

    recording = _object(result_doc.get("recording"), "results.recording")
    _absolute_path(
        recording.get("recording_path"),
        "results.recording.recording_path",
    )
    _strict_integer(
        recording.get("question_count"),
        "results.recording.question_count",
        expected=QUESTION_COUNT,
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
    contract_questions = validated_contract["questions"]
    if not isinstance(contract_questions, list):
        raise RealityEvalError("validated contract questions must be a list")
    cases = {
        str(case["id"]): case
        for case in contract_questions
        if isinstance(case, dict)
    }
    if len(raw_results) != QUESTION_COUNT:
        raise RealityEvalError("results must contain exactly 50 unique results")

    maximum_seconds = _maximum_seconds(
        validated_contract["maximum_seconds"],
        "contract.maximum_seconds",
    )
    seen_ids: set[str] = set()
    seen_thread_ids: set[str] = set()
    for index, raw_result in enumerate(raw_results):
        result = _object(raw_result, f"results[{index}]")
        case_id = _nonempty_string(result.get("id"), f"results[{index}].id")
        if case_id not in cases:
            raise RealityEvalError(f"results[{index}] has unknown id {case_id}")
        if case_id in seen_ids:
            raise RealityEvalError(f"results contains duplicate id {case_id}")
        seen_ids.add(case_id)
        case = cases[case_id]
        if result.get("question") != case["question"]:
            raise RealityEvalError(f"result {case_id} changed the exact frozen question")
        answer = _nonempty_string(result.get("answer"), f"result {case_id}.answer")
        truth_packet = _object(
            case.get("truth_packet"),
            f"contract case {case_id}.truth_packet",
        )

        elapsed = _finite_number(
            result.get("elapsed_seconds"),
            f"result {case_id}.elapsed_seconds",
        )
        if elapsed < 0:
            raise RealityEvalError(
                f"result {case_id}.elapsed_seconds must be a nonnegative finite number"
            )
        if elapsed >= maximum_seconds:
            raise RealityEvalError(f"result {case_id} exceeded the strict time limit")
        _strict_integer(
            result.get("attempt"),
            f"result {case_id}.attempt",
            expected=1,
        )
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

        route_trace = _object(
            result.get("route_trace"),
            f"result {case_id}.route_trace",
        )
        thread_id = _nonempty_string(
            route_trace.get("thread_id"),
            f"result {case_id}.route_trace.thread_id",
        )
        if thread_id in seen_thread_ids:
            raise RealityEvalError(
                f"result {case_id}.route_trace.thread_id must be unique across results"
            )
        seen_thread_ids.add(thread_id)
        submitted_at = _utc_second_datetime(
            route_trace.get("submitted_at"),
            f"result {case_id}.route_trace.submitted_at",
        )
        completed_at = _utc_second_datetime(
            route_trace.get("completed_at"),
            f"result {case_id}.route_trace.completed_at",
        )
        if completed_at < submitted_at:
            raise RealityEvalError(
                f"result {case_id}.route_trace.completed_at cannot be earlier than submitted_at"
            )
        if submitted_at < run_started_at:
            raise RealityEvalError(
                f"result {case_id}.route_trace.submitted_at is before the unchanged run"
            )
        if completed_at > run_finished_at:
            raise RealityEvalError(
                f"result {case_id}.route_trace.completed_at is after the unchanged run"
            )
        _strict_integer(
            route_trace.get("answer_command_count"),
            f"result {case_id}.route_trace.answer_command_count",
            expected=1,
        )
        if route_trace.get("hosted_route") is not True:
            raise RealityEvalError(
                f"result {case_id}.route_trace.hosted_route must be true"
            )
        _absolute_path(
            route_trace.get("raw_trace_path"),
            f"result {case_id}.route_trace.raw_trace_path",
        )

        for field in _PASS_FIELDS:
            if result.get(field) != "pass":
                raise RealityEvalError(f"result {case_id}.{field} must be pass")
        _nonempty_string(result.get("judge_evidence"), f"result {case_id}.judge_evidence")
        _validate_scientific_grade(
            result.get("scientific_grade"),
            case_id=case_id,
            truth_packet=truth_packet,
        )

        provenance = result.get("provenance")
        if not isinstance(provenance, list) or not provenance:
            raise RealityEvalError(f"result {case_id}.provenance must be a nonempty list")
        actual_provenance: list[tuple[str, str, str, str]] = []
        for provenance_index, raw_item in enumerate(provenance):
            item = _object(
                raw_item,
                f"result {case_id}.provenance[{provenance_index}]",
            )
            title = _nonempty_string(
                item.get("title"),
                f"result {case_id}.provenance[{provenance_index}].title",
            )
            source_id = _nonempty_string(
                item.get("source_id"),
                f"result {case_id}.provenance[{provenance_index}].source_id",
            )
            locator = _nonempty_string(
                item.get("locator"),
                f"result {case_id}.provenance[{provenance_index}].locator",
            )
            public_url = _nonempty_string(
                item.get("public_url"),
                f"result {case_id}.provenance[{provenance_index}].public_url",
            )
            if not public_url.startswith(("https://", "http://")):
                raise RealityEvalError(
                    f"result {case_id}.provenance[{provenance_index}].public_url "
                    "must be an HTTP(S) original source URL"
                )
            actual_provenance.append((title, source_id, locator, public_url))

        truth_sources = truth_packet.get("sources")
        if not isinstance(truth_sources, list):
            raise RealityEvalError(
                f"contract case {case_id}.truth_packet.sources must be a list"
            )
        expected_provenance = {
            (
                str(source["title"]),
                str(source["source_id"]),
                str(source["locator"]),
                str(source["public_url"]),
            )
            for source in truth_sources
            if isinstance(source, dict)
        }
        if (
            len(actual_provenance) != len(set(actual_provenance))
            or set(actual_provenance) != expected_provenance
        ):
            raise RealityEvalError(
                f"result {case_id}.provenance must match the frozen truth packet sources exactly"
            )
        for title, source_id, locator, public_url in actual_provenance:
            for field_name, value in (
                ("title", title),
                ("source_id", source_id),
                ("locator", locator),
                ("public_url", public_url),
            ):
                if value not in answer:
                    raise RealityEvalError(
                        f"result {case_id} must show provenance {field_name} "
                        "in the complete visible answer"
                    )

    missing = set(cases) - seen_ids
    if missing:
        raise RealityEvalError(f"results omitted ids: {', '.join(sorted(missing))}")
    return result_doc


def summarize_results(
    payload: object,
    *,
    contract: dict[str, object],
    contract_bytes: bytes,
) -> dict[str, object]:
    results = validate_results(
        payload,
        contract=contract,
        contract_bytes=contract_bytes,
    )
    raw_results = results["results"]
    if not isinstance(raw_results, list):
        raise RealityEvalError("validated results must be a list")

    elapsed_values: list[float] = []
    passed_count = 0
    for index, raw_result in enumerate(raw_results):
        result = _object(raw_result, f"validated results[{index}]")
        elapsed_values.append(
            _finite_number(
                result.get("elapsed_seconds"),
                f"validated results[{index}].elapsed_seconds",
            )
        )
        passed_count += int(all(result.get(field) == "pass" for field in _PASS_FIELDS))
    elapsed_values.sort()
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
