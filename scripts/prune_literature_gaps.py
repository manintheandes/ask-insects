#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


DEFAULT_REASONS = ("pubmed_skipped",)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prune_gaps(artifact_dir: Path, reasons: set[str]) -> dict[str, object]:
    artifact_dir = artifact_dir.expanduser().absolute()
    gaps_path = artifact_dir / "gaps.json"
    gaps = read_json(gaps_path, [])
    if not isinstance(gaps, list):
        raise ValueError(f"{gaps_path} must contain a JSON list")

    kept = [gap for gap in gaps if not (isinstance(gap, dict) and str(gap.get("reason")) in reasons)]
    removed = len(gaps) - len(kept)
    write_json(gaps_path, kept)

    generated_at = utc_now()
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = read_json(path, {})
        if not isinstance(payload, dict):
            continue
        payload["gap_count"] = len(kept)
        payload["generated_at"] = generated_at
        literature = payload.get("literature")
        if isinstance(literature, dict):
            literature["gap_count"] = len([gap for gap in kept if isinstance(gap, dict) and gap.get("source") == "aedes_literature_openalex"])
            literature["gaps_path"] = gaps_path.as_posix()
        write_json(path, payload)

    return {
        "ok": True,
        "artifact_dir": artifact_dir.as_posix(),
        "gap_count_before": len(gaps),
        "gap_count_after": len(kept),
        "removed": removed,
        "removed_reasons": sorted(reasons),
    }


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Remove stale, non-current literature gap rows from an Ask Insects artifact.")
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--reason", action="append", default=list(DEFAULT_REASONS))
    return parser


def main() -> int:
    args = create_parser().parse_args()
    result = prune_gaps(args.artifact_dir, {str(reason) for reason in args.reason})
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
