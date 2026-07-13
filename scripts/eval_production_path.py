#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import tomllib
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_VERSION = "ask-insects-production-path.v1"
DEFAULT_CASES_PATH = REPO_ROOT / "evals" / "ask_insects_production_path_v1.json"
DEFAULT_RESULTS_DIR = REPO_ROOT / "artifacts" / "production-path-evals"
BLOCKED_COMMAND_TERMS = (
    ".codex/memories",
    "ask-monarch",
    "verify_complete.py",
    "setup-agent",
    " ingest-",
    " refresh",
)


@dataclass
class ExecutionResult:
    elapsed_seconds: float
    exit_code: int | None
    timed_out: bool
    turn_completed: bool
    visible_answer: str
    agent_messages: list[str]
    commands: list[str]
    event_types: list[str]
    stdout_jsonl: str
    stderr: str


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _string_list(value: object, label: str, *, required: bool = False) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{label} must be a list of non-empty strings")
    if required and not value:
        raise ValueError(f"{label} must not be empty")
    return [item.strip() for item in value]


def validate_contract(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("production-path evaluation contract must be an object")
    if payload.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("production-path evaluation contract version mismatch")
    minimum_case_count = payload.get("minimum_case_count")
    if not isinstance(minimum_case_count, int) or minimum_case_count < 200:
        raise ValueError("production-path evaluation minimum_case_count must be at least 200")
    maximum_seconds = payload.get("maximum_seconds")
    if not isinstance(maximum_seconds, (int, float)) or maximum_seconds <= 0 or maximum_seconds > 30:
        raise ValueError("production-path evaluation maximum_seconds must be at most 30")
    required_categories = payload.get("required_categories")
    if not isinstance(required_categories, dict) or not required_categories:
        raise ValueError("production-path evaluation required_categories must be a non-empty object")
    for category, minimum in required_categories.items():
        if not isinstance(category, str) or not category.strip() or not isinstance(minimum, int) or minimum <= 0:
            raise ValueError("production-path category minimums must use non-empty names and positive integers")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not all(isinstance(case, dict) for case in cases):
        raise ValueError("production-path evaluation cases must be a list of objects")
    if len(cases) < minimum_case_count:
        raise ValueError(
            f"production-path evaluation requires at least {minimum_case_count} cases; found {len(cases)}"
        )

    ids: list[str] = []
    questions: list[str] = []
    category_counts: Counter[str] = Counter()
    for index, case in enumerate(cases):
        case_id = case.get("id")
        question = case.get("question")
        category = case.get("category")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"case {index} must have a non-empty id")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"case {case_id} must have a non-empty question")
        if not isinstance(category, str) or category not in required_categories:
            raise ValueError(f"case {case_id} has an unknown category: {category}")
        expect = case.get("expect")
        if not isinstance(expect, dict):
            raise ValueError(f"case {case_id} expect must be an object")
        if expect.get("behavior") not in {"bounded_answer", "source_gap", "boundary"}:
            raise ValueError(f"case {case_id} has an invalid expected behavior")
        _string_list(expect.get("required_terms"), f"case {case_id} required_terms", required=True)
        _string_list(expect.get("forbidden_terms"), f"case {case_id} forbidden_terms")
        _string_list(expect.get("source_ids"), f"case {case_id} source_ids", required=True)
        _string_list(expect.get("locator_patterns"), f"case {case_id} locator_patterns", required=True)
        ids.append(case_id)
        questions.append(question)
        category_counts[category] += 1

    if len(ids) != len(set(ids)):
        raise ValueError("production-path evaluation case ids must be unique")
    if len(questions) != len(set(questions)):
        raise ValueError("production-path evaluation questions must be unique")
    for category, minimum in required_categories.items():
        actual = category_counts[str(category)]
        if actual < int(minimum):
            raise ValueError(f"category {category} requires {minimum} cases; found {actual}")
    return payload


def load_contract(path: Path = DEFAULT_CASES_PATH) -> dict[str, object]:
    return validate_contract(json.loads(path.read_text(encoding="utf-8")))


def parse_codex_events(stdout_jsonl: str) -> tuple[list[str], list[str], list[str], bool]:
    agent_messages: list[str] = []
    commands: list[str] = []
    event_types: list[str] = []
    turn_completed = False
    for line in stdout_jsonl.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "")
        if event_type:
            event_types.append(event_type)
        if event_type == "turn.completed":
            turn_completed = True
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "agent_message" and isinstance(item.get("text"), str):
            agent_messages.append(str(item["text"]))
        if item_type == "command_execution" and isinstance(item.get("command"), str):
            command = str(item["command"])
            if command not in commands:
                commands.append(command)
        if item_type == "web_search":
            event_types.append("web_search")
    return agent_messages, commands, event_types, turn_completed


def execute_codex_case(
    case: dict[str, object],
    *,
    maximum_seconds: float,
    codex_binary: str = "codex",
) -> ExecutionResult:
    question = str(case["question"])
    command = [
        codex_binary,
        "-a",
        "never",
        "-s",
        "danger-full-access",
        "-C",
        str(REPO_ROOT),
        "exec",
        "--ephemeral",
        "--json",
        question,
    ]
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        env={**os.environ, "NO_COLOR": "1"},
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=maximum_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
    elapsed_seconds = time.monotonic() - started
    agent_messages, commands, event_types, turn_completed = parse_codex_events(stdout)
    return ExecutionResult(
        elapsed_seconds=round(elapsed_seconds, 3),
        exit_code=process.returncode,
        timed_out=timed_out,
        turn_completed=turn_completed,
        visible_answer=agent_messages[-1] if agent_messages else "",
        agent_messages=agent_messages,
        commands=commands,
        event_types=event_types,
        stdout_jsonl=stdout,
        stderr=stderr,
    )


def _matched_locator(answer: str, pattern: str) -> str | None:
    if pattern.startswith("re:"):
        match = re.search(pattern[3:], answer, flags=re.IGNORECASE)
        return match.group(0) if match else None
    start = answer.casefold().find(pattern.casefold())
    return answer[start : start + len(pattern)] if start >= 0 else None


def evaluate_case(
    case: dict[str, object],
    execution: ExecutionResult,
    *,
    maximum_seconds: float,
) -> dict[str, object]:
    failures: list[str] = []
    question = str(case["question"])
    expect = case["expect"]
    assert isinstance(expect, dict)
    answer = execution.visible_answer
    answer_lower = answer.casefold()

    if execution.timed_out or execution.elapsed_seconds >= maximum_seconds:
        failures.append(
            f"time limit failed: {execution.elapsed_seconds:.3f}s; required under {maximum_seconds:g}s"
        )
    if execution.exit_code != 0:
        failures.append(f"Codex process exited with {execution.exit_code}")
    if not execution.turn_completed:
        failures.append("Codex turn did not complete")
    if not answer.strip():
        failures.append("Codex returned no final visible answer")

    ask_commands = [
        command
        for command in execution.commands
        if re.search(r"\bask-insects\s+ask\s", command, flags=re.IGNORECASE)
    ]
    if not ask_commands:
        failures.append("normal Codex route did not call ask-insects ask")
    elif question.casefold() not in ask_commands[0].casefold():
        failures.append("first ask-insects call did not preserve the user's exact question")
    if len(ask_commands) > 1:
        failures.append(f"normal answer used {len(ask_commands)} ask-insects calls; expected exactly one")

    for command in execution.commands:
        command_lower = command.casefold()
        for blocked in BLOCKED_COMMAND_TERMS:
            if blocked in command_lower:
                failures.append(f"blocked fallback or maintenance command used: {blocked.strip()}")
        if "ask-insects" in command_lower and "--local" in command_lower:
            failures.append("Ask Insects used the local index instead of hosted production")
        if re.search(r"\bask-insects\s+(search|sql)\s", command, flags=re.IGNORECASE):
            failures.append("normal answer expanded into search or SQL instead of using the complete first answer")
    if any("web_search" in event_type.casefold() for event_type in execution.event_types):
        failures.append("web search was used instead of the hosted Ask Insects source plane")

    for term in _string_list(expect.get("required_terms"), "required_terms"):
        if term.casefold() not in answer_lower:
            failures.append(f"final answer missing required term: {term}")
    for term in _string_list(expect.get("forbidden_terms"), "forbidden_terms"):
        if term.casefold() in answer_lower:
            failures.append(f"final answer contains forbidden term: {term}")

    behavior = expect.get("behavior")
    if behavior == "source_gap" and not any(
        phrase in answer_lower
        for phrase in ("source gap", "missing evidence", "insufficient evidence", "cannot support", "not yet")
    ):
        failures.append("expected source-gap behavior was not visible")
    if behavior == "boundary" and not (
        "public" in answer_lower and ("private" in answer_lower or "cannot" in answer_lower)
    ):
        failures.append("public/private boundary was not visible")

    matched_source_ids: list[str] = []
    for source_id in _string_list(expect.get("source_ids"), "source_ids"):
        if source_id.casefold() not in answer_lower:
            failures.append(f"final answer missing source id: {source_id}")
        else:
            matched_source_ids.append(source_id)
    matched_locators: list[str] = []
    for locator_pattern in _string_list(expect.get("locator_patterns"), "locator_patterns"):
        matched = _matched_locator(answer, locator_pattern)
        if matched is None:
            failures.append(f"final answer missing locator: {locator_pattern}")
        else:
            matched_locators.append(matched)

    return {
        "id": case["id"],
        "category": case["category"],
        "question": question,
        "expected": expect,
        "ok": not failures,
        "failures": failures,
        "elapsed_seconds": execution.elapsed_seconds,
        "visible_answer": answer,
        "agent_messages": execution.agent_messages,
        "commands": execution.commands,
        "event_types": execution.event_types,
        "provenance": {
            "source_ids": matched_source_ids,
            "locators": matched_locators,
        },
        "timed_out": execution.timed_out,
        "turn_completed": execution.turn_completed,
        "exit_code": execution.exit_code,
        "stdout_jsonl": execution.stdout_jsonl,
        "stderr": execution.stderr,
    }


def run_evaluation(
    contract: dict[str, object],
    *,
    execute: Callable[[dict[str, object]], ExecutionResult],
    selected_case_ids: set[str] | None = None,
    route_overrides: bool = False,
    jobs: int = 1,
) -> dict[str, object]:
    cases = list(contract["cases"])
    if selected_case_ids is not None:
        cases = [case for case in cases if str(case["id"]) in selected_case_ids]
    if jobs < 1:
        raise ValueError("jobs must be at least 1")
    started_at = utc_now()
    if jobs == 1:
        executions = [execute(case) for case in cases]
    else:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            executions = list(pool.map(execute, cases))
    maximum_seconds = float(contract["maximum_seconds"])
    results = [
        evaluate_case(case, execution, maximum_seconds=maximum_seconds)
        for case, execution in zip(cases, executions, strict=True)
    ]
    all_case_ids = {str(case["id"]) for case in contract["cases"]}
    selected_ids = {str(case["id"]) for case in cases}
    gate_eligible = (
        len(cases) >= int(contract["minimum_case_count"])
        and selected_ids == all_case_ids
        and not route_overrides
    )
    all_cases_passed = bool(results) and all(bool(result["ok"]) for result in results)
    return {
        "contract_version": CONTRACT_VERSION,
        "started_at": started_at,
        "finished_at": utc_now(),
        "normal_codex_route": not route_overrides,
        "maximum_seconds": maximum_seconds,
        "minimum_case_count": int(contract["minimum_case_count"]),
        "corpus_case_count": len(contract["cases"]),
        "selected_case_count": len(cases),
        "passed_count": sum(1 for result in results if result["ok"]),
        "failed_count": sum(1 for result in results if not result["ok"]),
        "all_cases_passed": all_cases_passed,
        "gate_eligible": gate_eligible,
        "production_gate_passed": gate_eligible and all_cases_passed,
        "results": results,
    }


def _codex_version() -> str:
    try:
        return subprocess.run(
            ["codex", "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def _normal_codex_settings() -> dict[str, object]:
    path = Path.home() / ".codex" / "config.toml"
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"config_path": str(path), "readable": False}
    return {
        "config_path": str(path),
        "readable": True,
        "model": payload.get("model"),
        "model_reasoning_effort": payload.get("model_reasoning_effort"),
        "personality": payload.get("personality"),
    }


def _default_output_path() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return DEFAULT_RESULTS_DIR / stamp / "results.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the Ask Insects black-box evaluation through Josh's normal Codex route."
    )
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--smoke", action="store_true", help="Permit a non-gating subset run")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    if args.case_id and not args.smoke:
        parser.error("--case-id requires --smoke; subset runs can never pass the production gate")

    contract = load_contract(Path(args.cases))
    selected = set(args.case_id) if args.case_id else None
    known_ids = {str(case["id"]) for case in contract["cases"]}
    unknown_ids = sorted((selected or set()) - known_ids)
    if unknown_ids:
        parser.error("unknown case ids: " + ", ".join(unknown_ids))
    maximum_seconds = float(contract["maximum_seconds"])
    result = run_evaluation(
        contract,
        execute=lambda case: execute_codex_case(case, maximum_seconds=maximum_seconds),
        selected_case_ids=selected,
        jobs=args.jobs,
    )
    result["codex_version"] = _codex_version()
    result["codex_settings"] = _normal_codex_settings()
    result["repository"] = str(REPO_ROOT)
    output_path = Path(args.output) if args.output else _default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    summary = {
        key: result[key]
        for key in (
            "contract_version",
            "codex_version",
            "selected_case_count",
            "passed_count",
            "failed_count",
            "gate_eligible",
            "production_gate_passed",
        )
    }
    summary["results_path"] = str(output_path)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.smoke:
        return 0 if result["all_cases_passed"] else 2
    return 0 if result["production_gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
