#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.reality_eval import (  # noqa: E402
    RealityEvalError,
    assemble_contract,
    build_holdout_receipt,
    load_json_object,
    summarize_results,
    validate_contract,
    validate_holdout_receipt,
    validate_public_manifest,
    validate_results,
)


DEFAULT_PUBLIC = REPO_ROOT / "evals" / "ask_insects_reality_eval_public_v1.json"
DEFAULT_RECEIPT = (
    REPO_ROOT / "evals" / "ask_insects_reality_eval_holdout_receipt_v1.json"
)
DEFAULT_HOLDOUTS = (
    Path.home()
    / ".local"
    / "share"
    / "ask-insects"
    / "realityeval"
    / "ask-insects-holdouts-v1.json"
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Freeze and validate the Ask Insects Reality Eval artifacts."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_public_parser = subparsers.add_parser("validate-public")
    validate_public_parser.add_argument(
        "--public",
        type=Path,
        default=DEFAULT_PUBLIC,
    )

    freeze_parser = subparsers.add_parser("freeze-holdouts")
    freeze_parser.add_argument(
        "--holdouts",
        type=Path,
        default=DEFAULT_HOLDOUTS,
    )
    freeze_parser.add_argument(
        "--receipt",
        type=Path,
        default=DEFAULT_RECEIPT,
    )

    assemble_parser = subparsers.add_parser("assemble")
    assemble_parser.add_argument(
        "--public",
        type=Path,
        default=DEFAULT_PUBLIC,
    )
    assemble_parser.add_argument(
        "--holdouts",
        type=Path,
        default=DEFAULT_HOLDOUTS,
    )
    assemble_parser.add_argument(
        "--receipt",
        type=Path,
        default=DEFAULT_RECEIPT,
    )
    assemble_parser.add_argument("--output", type=Path, required=True)

    validate_contract_parser = subparsers.add_parser("validate-contract")
    validate_contract_parser.add_argument("--contract", type=Path, required=True)

    validate_results_parser = subparsers.add_parser("validate-results")
    validate_results_parser.add_argument("--contract", type=Path, required=True)
    validate_results_parser.add_argument("--results", type=Path, required=True)

    summary_parser = subparsers.add_parser("summary")
    summary_parser.add_argument("--contract", type=Path, required=True)
    summary_parser.add_argument("--results", type=Path, required=True)
    return parser


def _validate_public(path: Path) -> dict[str, object]:
    manifest = validate_public_manifest(load_json_object(path))
    questions = manifest["questions"]
    assert isinstance(questions, list)
    return {
        "ok": True,
        "public": str(path),
        "question_count": len(questions),
    }


def _freeze_holdouts(holdouts_path: Path, receipt_path: Path) -> dict[str, object]:
    receipt = build_holdout_receipt(holdouts_path.read_bytes())
    _write_json(receipt_path, receipt)
    return receipt


def _assemble(
    public_path: Path,
    holdouts_path: Path,
    receipt_path: Path,
    output_path: Path,
) -> dict[str, object]:
    holdout_bytes = holdouts_path.read_bytes()
    validate_holdout_receipt(
        load_json_object(receipt_path),
        bundle_bytes=holdout_bytes,
    )
    contract = assemble_contract(
        load_json_object(public_path),
        load_json_object(holdouts_path),
    )
    _write_json(output_path, contract)
    questions = contract["questions"]
    assert isinstance(questions, list)
    return {
        "ok": True,
        "output": str(output_path),
        "question_count": len(questions),
        "holdout_count": sum(
            isinstance(case, dict) and case.get("holdout") is True
            for case in questions
        ),
    }


def _validate_contract(path: Path) -> dict[str, object]:
    contract = validate_contract(load_json_object(path))
    questions = contract["questions"]
    assert isinstance(questions, list)
    return {
        "ok": True,
        "contract": str(path),
        "question_count": len(questions),
    }


def _load_result_inputs(
    contract_path: Path,
    results_path: Path,
) -> tuple[dict[str, object], bytes, dict[str, object]]:
    contract_bytes = contract_path.read_bytes()
    contract = load_json_object(contract_path)
    results = load_json_object(results_path)
    return contract, contract_bytes, results


def _validate_results(
    contract_path: Path,
    results_path: Path,
) -> dict[str, object]:
    contract, contract_bytes, results = _load_result_inputs(
        contract_path,
        results_path,
    )
    validated = validate_results(
        results,
        contract=contract,
        contract_bytes=contract_bytes,
    )
    result_rows = validated["results"]
    assert isinstance(result_rows, list)
    return {
        "ok": True,
        "contract": str(contract_path),
        "results": str(results_path),
        "question_count": len(result_rows),
    }


def _summary(contract_path: Path, results_path: Path) -> dict[str, object]:
    contract, contract_bytes, results = _load_result_inputs(
        contract_path,
        results_path,
    )
    return summarize_results(
        results,
        contract=contract,
        contract_bytes=contract_bytes,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "validate-public":
            output = _validate_public(args.public)
        elif args.command == "freeze-holdouts":
            output = _freeze_holdouts(args.holdouts, args.receipt)
        elif args.command == "assemble":
            output = _assemble(
                args.public,
                args.holdouts,
                args.receipt,
                args.output,
            )
        elif args.command == "validate-contract":
            output = _validate_contract(args.contract)
        elif args.command == "validate-results":
            output = _validate_results(args.contract, args.results)
        elif args.command == "summary":
            output = _summary(args.contract, args.results)
        else:  # pragma: no cover
            raise AssertionError(f"unhandled command: {args.command}")
    except (OSError, RealityEvalError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    _print_json(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
