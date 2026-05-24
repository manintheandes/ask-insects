#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COVERAGE_PATH = REPO_ROOT / "config/mosquito-intelligence-coverage.json"

REQUIRED_GATES = {
    "mapped",
    "accessible",
    "atomically_queryable",
    "receipted",
    "ask_surface_wired",
}
REQUIRED_DOMAINS = {
    "literature",
    "genomics",
    "behavior",
    "observations",
    "images",
    "video",
    "neurobiology",
    "vector_competence",
    "resistance",
    "ecology",
    "public_health",
}
ALLOWED_STATUS = {
    "source_grade",
    "partial_source_grade",
    "thin",
    "planned",
    "source_gap",
}
ALLOWED_GATE_STATE = {
    "yes",
    "partial",
    "no",
    "future_gap",
}


def fail(message: str) -> int:
    print(f"coverage verification failed: {message}", file=sys.stderr)
    return 1


def load_coverage(path: Path = COVERAGE_PATH) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("coverage ledger must be a JSON object")
    return payload


def _require_nonempty_list(domain_id: str, domain: dict[str, object], key: str) -> None:
    value = domain.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"domain {domain_id} must declare nonempty string list {key}")


def verify_coverage(payload: dict[str, object]) -> None:
    scope = payload.get("scope")
    if not isinstance(scope, dict):
        raise ValueError("coverage ledger missing scope object")
    if scope.get("primary_taxon") != "Aedes aegypti":
        raise ValueError("coverage ledger must declare Aedes aegypti as primary_taxon")
    strategy = scope.get("strategy")
    if not isinstance(strategy, str) or "most comprehensive Aedes aegypti intelligence system in the world" not in strategy:
        raise ValueError("coverage ledger strategy must state the world-comprehensive Aedes goal")

    gates = payload.get("source_contract_gates")
    if not isinstance(gates, list) or set(gates) != REQUIRED_GATES:
        raise ValueError("coverage ledger must declare exactly the required source-contract gates")

    domains = payload.get("domains")
    if not isinstance(domains, list):
        raise ValueError("coverage ledger missing domains list")
    by_id: dict[str, dict[str, object]] = {}
    priorities: set[int] = set()
    for domain in domains:
        if not isinstance(domain, dict):
            raise ValueError("each domain must be an object")
        domain_id = domain.get("id")
        if not isinstance(domain_id, str) or not domain_id:
            raise ValueError("each domain must have a string id")
        if domain_id in by_id:
            raise ValueError(f"duplicate domain id: {domain_id}")
        by_id[domain_id] = domain

        priority = domain.get("priority")
        if not isinstance(priority, int) or priority < 1:
            raise ValueError(f"domain {domain_id} must declare a positive integer priority")
        if priority in priorities:
            raise ValueError(f"duplicate domain priority: {priority}")
        priorities.add(priority)

        status = domain.get("status")
        if status not in ALLOWED_STATUS:
            raise ValueError(f"domain {domain_id} has invalid status: {status}")
        for key in ("target_state",):
            if not isinstance(domain.get(key), str) or not str(domain.get(key)).strip():
                raise ValueError(f"domain {domain_id} missing {key}")

        gate_states = domain.get("current_gates")
        if not isinstance(gate_states, dict) or set(gate_states) != REQUIRED_GATES:
            raise ValueError(f"domain {domain_id} must declare every source-contract gate")
        invalid_gate_states = {
            key: value for key, value in gate_states.items() if value not in ALLOWED_GATE_STATE
        }
        if invalid_gate_states:
            raise ValueError(f"domain {domain_id} has invalid gate states: {invalid_gate_states}")

        _require_nonempty_list(domain_id, domain, "current_evidence")
        _require_nonempty_list(domain_id, domain, "completion_evidence")
        if status != "source_grade":
            _require_nonempty_list(domain_id, domain, "required_next_sources")

    missing = REQUIRED_DOMAINS - set(by_id)
    if missing:
        raise ValueError(f"coverage ledger missing required domain(s): {', '.join(sorted(missing))}")


def main() -> int:
    try:
        verify_coverage(load_coverage())
    except Exception as exc:
        return fail(str(exc))
    print("coverage verification ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
