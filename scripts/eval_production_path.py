#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import time
import tomllib
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_VERSION = "ask-insects-production-path.v1"
DEFAULT_CASES_PATH = REPO_ROOT / "evals" / "ask_insects_production_path_v1.json"
DEFAULT_RESULTS_DIR = REPO_ROOT / "artifacts" / "production-path-evals"
PUBLIC_ANSWER_LEAK_PATTERNS = (
    ("authorization credential", re.compile(r"authorization\s*:\s*bearer\b", re.IGNORECASE)),
    ("private experiment identifier", re.compile(r"\bexperiment:[A-Za-z0-9][^\s`]*", re.IGNORECASE)),
    ("local machine path", re.compile(r"(?:^|[\s`(])(?:/Users/|/home/)", re.IGNORECASE)),
    (
        "private network address",
        re.compile(
            r"https?://(?:localhost|127(?:\.\d{1,3}){3}|[A-Za-z0-9.-]+\.internal)(?:[/:]|$)",
            re.IGNORECASE,
        ),
    ),
    ("private key material", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----", re.IGNORECASE)),
    (
        "credential-shaped assignment",
        re.compile(r"\b(?:api[_-]?key|access[_-]?token|secret[_-]?token)\s*[:=]", re.IGNORECASE),
    ),
)


def _command_tokens(command: str, *, allow_shell_wrapper: bool = True) -> list[str] | None:
    try:
        lexer = shlex.shlex(
            command,
            posix=True,
            punctuation_chars=";&|<>()",
        )
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return None
    if not tokens or any(re.fullmatch(r"[;&|<>()]+", token) for token in tokens):
        return None
    executable = Path(tokens[0]).name.casefold()
    if executable in {"bash", "sh", "zsh"}:
        if not allow_shell_wrapper or len(tokens) != 3 or tokens[1] not in {"-c", "-lc"}:
            return None
        return _command_tokens(tokens[2], allow_shell_wrapper=False)
    return tokens


def _is_installed_skill_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    if not normalized.endswith("/.codex/skills/askinsects/SKILL.md"):
        return False
    return normalized.startswith(("/", "$HOME/", "~/"))


def _is_allowed_installed_skill_read(command: str) -> bool:
    tokens = _command_tokens(command)
    if not tokens:
        return False
    executable = Path(tokens[0]).name.casefold()
    if executable == "cat":
        return len(tokens) == 2 and _is_installed_skill_path(tokens[1])
    if executable == "sed":
        return (
            len(tokens) == 4
            and tokens[1] == "-n"
            and re.fullmatch(r"\d+(?:,\d+)?p", tokens[2]) is not None
            and _is_installed_skill_path(tokens[3])
        )
    return False


def _is_ask_command(tokens: list[str] | None) -> bool:
    return bool(
        tokens
        and len(tokens) >= 2
        and Path(tokens[0]).name.casefold() == "ask-insects"
        and tokens[1] == "ask"
    )


def _ask_command_failure(command: str, question: str) -> str | None:
    tokens = _command_tokens(command)
    if not _is_ask_command(tokens):
        return "normal Codex route did not use exactly one ask-insects ask command"
    assert tokens is not None
    arguments = tokens[2:]
    if "--local" in arguments:
        return "normal Ask Insects call was not a hosted call"
    allowed_flags = {"--answer-only", "--hosted"}
    legacy_flags = {"--compact", "--json"}
    positionals = [
        argument for argument in arguments if argument not in allowed_flags | legacy_flags
    ]
    if positionals != [question]:
        return "first ask-insects call did not preserve the user's exact question"
    if arguments.count("--answer-only") != 1:
        return "normal Ask Insects call did not use the answer-only production payload"
    if arguments.count("--hosted") > 1:
        return "normal Ask Insects call was not the exact hosted allowlisted command"
    if any(argument.startswith("-") and argument not in allowed_flags for argument in arguments):
        return "normal Ask Insects call was not the exact hosted allowlisted command"
    return None


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
    if not isinstance(maximum_seconds, (int, float)) or maximum_seconds <= 0 or maximum_seconds > 60:
        raise ValueError("production-path evaluation maximum_seconds must be at most 60")
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
    command_item_ids: set[str] = set()
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
        if isinstance(item_type, str) and "web" in item_type.casefold():
            event_types.append(item_type)
        if item_type == "agent_message" and isinstance(item.get("text"), str):
            agent_messages.append(str(item["text"]))
        if item_type == "command_execution" and isinstance(item.get("command"), str):
            item_id = item.get("id")
            if isinstance(item_id, str) and item_id:
                if item_id in command_item_ids:
                    continue
                command_item_ids.add(item_id)
            commands.append(str(item["command"]))
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


def _basic_term_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.casefold())).strip()


@lru_cache(maxsize=1)
def _term_alias_groups() -> tuple[tuple[str, ...], ...]:
    groups: list[tuple[str, ...]] = []

    def add_group(values: list[object]) -> None:
        normalized = tuple(
            dict.fromkeys(
                text
                for value in values
                if (text := _basic_term_text(str(value or "")))
            )
        )
        if len(normalized) > 1:
            groups.append(normalized)

    add_group(["source gap", "source gaps", "missing evidence", "insufficient evidence"])
    add_group(["cannot", "can not", "can't", "unable to"])
    try:
        ledger = json.loads(
            (REPO_ROOT / "config" / "insect-intelligence-programs.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        ledger = {}
    if isinstance(ledger, dict):
        for key, name_field in (
            ("knowledge_domains", "name"),
            ("readiness_dimensions", "name"),
            ("species", "scientific_name"),
            ("products", "name"),
        ):
            entries = ledger.get(key)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                values: list[object] = [entry.get(name_field)]
                if key == "species":
                    values.append(entry.get("common_name"))
                aliases = entry.get("aliases")
                if isinstance(aliases, list):
                    values.extend(aliases)
                add_group(values)
    return tuple(groups)


def _contains_required_term(answer: str, term: str) -> bool:
    normalized_answer = _basic_term_text(answer)
    normalized_term = _basic_term_text(term)
    padded_answer = f" {normalized_answer} "
    if normalized_term and f" {normalized_term} " in padded_answer:
        return True
    for group in _term_alias_groups():
        if normalized_term in group and any(f" {alias} " in padded_answer for alias in group):
            return True
    return False


def _contains_forbidden_claim(answer: str, term: str) -> bool:
    normalized_answer = _basic_term_text(answer)
    normalized_term = _basic_term_text(term)
    if not normalized_term:
        return False
    for match in re.finditer(re.escape(normalized_term), normalized_answer):
        before = normalized_answer[max(0, match.start() - 80) : match.start()]
        negated = re.search(
            r"\b(?:no|not|cannot|can not|cant|do not|does not|did not|is not|are not|without|unsupported)\b"
            r"(?:\s+[a-z0-9]+){0,8}\s*$",
            before,
        )
        if not negated:
            return True
    return False


def _is_retrieval_summary_only(answer: str) -> bool:
    body = re.split(r"\n+Sources:\s*", answer, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    patterns = (
        r"(?:For .+?,\s*)?Ask Insects found \d+ structured repellency assay fact(?:\(s\)|s)? "
        r"across \d+ deduplicated candidate paper(?:\(s\)|s)?\. "
        r"The indexed rows are ready for a bounded comparison on the reported dimensions\.",
        r"I found \d+ indexed Ask Insects evidence record(?:\(s\)|s)? matching the question\.",
        r"I found \d+ indexed Ask Insects media record(?:\(s\)|s)?\.",
        r"I found \d+ indexed Ask Insects record(?:\(s\)|s)?\.",
    )
    return any(re.fullmatch(pattern, body, flags=re.IGNORECASE) for pattern in patterns)


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
    if _is_retrieval_summary_only(answer):
        failures.append("final answer is only a retrieval summary")
    for label, pattern in PUBLIC_ANSWER_LEAK_PATTERNS:
        if pattern.search(answer):
            failures.append(f"public answer leak marker detected: {label}")

    parsed_commands = [_command_tokens(command) for command in execution.commands]
    ask_indexes = [
        index for index, tokens in enumerate(parsed_commands) if _is_ask_command(tokens)
    ]
    if len(ask_indexes) != 1:
        failures.append(
            f"normal answer used {len(ask_indexes)} ask-insects ask commands; expected exactly one"
        )
        ask_index = None
    else:
        ask_index = ask_indexes[0]
        ask_failure = _ask_command_failure(execution.commands[ask_index], question)
        if ask_failure:
            failures.append(ask_failure)

    route_commands_are_allowed = False
    if ask_index is not None and ask_index == len(execution.commands) - 1:
        prior_commands = execution.commands[:ask_index]
        route_commands_are_allowed = (
            not prior_commands
            or (len(prior_commands) == 1 and _is_allowed_installed_skill_read(prior_commands[0]))
        )
    if not route_commands_are_allowed:
        failures.append("normal answer used an unexpected command outside the hosted Ask Insects route")

    if any("web" in event_type.casefold() for event_type in execution.event_types):
        failures.append("a web event was used instead of the hosted Ask Insects source plane")

    for term in _string_list(expect.get("required_terms"), "required_terms"):
        if not _contains_required_term(answer, term):
            failures.append(f"final answer missing required term: {term}")
    for term in _string_list(expect.get("forbidden_terms"), "forbidden_terms"):
        if _contains_forbidden_claim(answer, term):
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


def _execution_from_saved_result(saved: dict[str, object]) -> ExecutionResult:
    list_fields: dict[str, list[str]] = {}
    for field in ("agent_messages", "commands", "event_types"):
        value = saved.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"saved production result has invalid {field}")
        list_fields[field] = list(value)
    elapsed_seconds = saved.get("elapsed_seconds")
    if not isinstance(elapsed_seconds, (int, float)):
        raise ValueError("saved production result has invalid elapsed_seconds")
    exit_code = saved.get("exit_code")
    if exit_code is not None and not isinstance(exit_code, int):
        raise ValueError("saved production result has invalid exit_code")
    for field in ("timed_out", "turn_completed"):
        if not isinstance(saved.get(field), bool):
            raise ValueError(f"saved production result has invalid {field}")
    for field in ("visible_answer", "stdout_jsonl", "stderr"):
        if not isinstance(saved.get(field), str):
            raise ValueError(f"saved production result has invalid {field}")
    stdout_jsonl = str(saved["stdout_jsonl"])
    parsed_messages, parsed_commands, parsed_event_types, parsed_turn_completed = parse_codex_events(
        stdout_jsonl
    )
    if parsed_event_types:
        list_fields["agent_messages"] = parsed_messages
        list_fields["commands"] = parsed_commands
        list_fields["event_types"] = parsed_event_types
        visible_answer = parsed_messages[-1] if parsed_messages else ""
        turn_completed = parsed_turn_completed
    else:
        visible_answer = str(saved["visible_answer"])
        turn_completed = bool(saved["turn_completed"])
    return ExecutionResult(
        elapsed_seconds=float(elapsed_seconds),
        exit_code=exit_code,
        timed_out=bool(saved["timed_out"]),
        turn_completed=turn_completed,
        visible_answer=visible_answer,
        agent_messages=list_fields["agent_messages"],
        commands=list_fields["commands"],
        event_types=list_fields["event_types"],
        stdout_jsonl=stdout_jsonl,
        stderr=str(saved["stderr"]),
    )


def regrade_evaluation(
    contract: dict[str, object],
    source: dict[str, object],
) -> dict[str, object]:
    cases = list(contract["cases"])
    if source.get("contract_version") != contract.get("contract_version"):
        raise ValueError("saved production result contract version mismatch")
    if source.get("normal_codex_route") is not True:
        raise ValueError("saved production result did not use the normal Codex route")
    if source.get("gate_eligible") is not True:
        raise ValueError("saved production result was not a full gate-eligible run")
    if source.get("corpus_case_count") != len(cases):
        raise ValueError("saved production result corpus count mismatch")
    if source.get("selected_case_count") != len(cases):
        raise ValueError("saved production result does not contain the full corpus")
    source_maximum = source.get("maximum_seconds")
    if not isinstance(source_maximum, (int, float)) or float(source_maximum) != float(
        contract["maximum_seconds"]
    ):
        raise ValueError("saved production result time limit mismatch")
    saved_results = source.get("results")
    if not isinstance(saved_results, list) or not all(isinstance(item, dict) for item in saved_results):
        raise ValueError("saved production result has invalid results")
    if len(saved_results) != len(cases):
        raise ValueError("saved production result count mismatch")
    saved_by_id = {str(item.get("id")): item for item in saved_results}
    if len(saved_by_id) != len(saved_results):
        raise ValueError("saved production result has duplicate case ids")
    case_ids = {str(case["id"]) for case in cases}
    if set(saved_by_id) != case_ids:
        raise ValueError("saved production result case ids do not match the contract")

    executions: dict[str, ExecutionResult] = {}
    for case in cases:
        case_id = str(case["id"])
        saved = saved_by_id[case_id]
        if saved.get("question") != case.get("question"):
            raise ValueError(f"saved production result question mismatch for {case_id}")
        if saved.get("category") != case.get("category"):
            raise ValueError(f"saved production result category mismatch for {case_id}")
        if saved.get("expected") != case.get("expect"):
            raise ValueError(f"saved production result expectations mismatch for {case_id}")
        executions[case_id] = _execution_from_saved_result(saved)

    regraded = run_evaluation(
        contract,
        execute=lambda case: executions[str(case["id"])],
    )
    regraded["started_at"] = source.get("started_at")
    regraded["finished_at"] = source.get("finished_at")
    regraded["regraded_at"] = utc_now()
    return regraded


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
    parser.add_argument(
        "--regrade-results",
        help="Reapply the current grader to an unchanged saved full-run artifact",
    )
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    if args.case_id and not args.smoke:
        parser.error("--case-id requires --smoke; subset runs can never pass the production gate")
    if args.regrade_results and (args.case_id or args.smoke or args.jobs != 1):
        parser.error("--regrade-results cannot be combined with subset, smoke, or parallel options")

    contract = load_contract(Path(args.cases))
    if args.regrade_results:
        source_path = Path(args.regrade_results).resolve()
        source_bytes = source_path.read_bytes()
        source = json.loads(source_bytes)
        if not isinstance(source, dict):
            parser.error("--regrade-results must point to a saved result object")
        result = regrade_evaluation(contract, source)
        result["codex_version"] = source.get("codex_version")
        result["codex_settings"] = source.get("codex_settings")
        result["repository"] = source.get("repository")
        result["regraded_from"] = str(source_path)
        result["regraded_source_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    else:
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
    if args.regrade_results and output_path.resolve() == source_path:
        parser.error("--regrade-results output must not overwrite the source artifact")
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
