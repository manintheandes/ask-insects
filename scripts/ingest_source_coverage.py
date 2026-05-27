#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR, write_json
from askinsects.index import SourceIndex
from askinsects.sources.source_coverage import DEFAULT_COVERAGE_LEDGER, SOURCE_COVERAGE_SOURCE_ID, build_source_coverage_records


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=1000)
    }


def _update_metadata(artifact_dir: Path, records: list[object], coverage_path: Path) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    domain_count = sum(1 for record in records if record.payload and record.payload.get("atom_type") == "source_coverage_domain")
    gap_count = sum(1 for record in records if record.payload and record.payload.get("atom_type") == "source_coverage_gap")
    source_payload = {
        "source": SOURCE_COVERAGE_SOURCE_ID,
        "record_count": len(records),
        "domain_count": domain_count,
        "coverage_gap_count": gap_count,
        "coverage_ledger": coverage_path.as_posix(),
        "method": "derived queryable source-coverage and missing-coverage records from the Ask Insects coverage ledger",
    }
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[SOURCE_COVERAGE_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if SOURCE_COVERAGE_SOURCE_ID not in sources:
                sources.append(SOURCE_COVERAGE_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload[SOURCE_COVERAGE_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {
        "ok": True,
        "source": SOURCE_COVERAGE_SOURCE_ID,
        "record_count": len(records),
        "domain_count": domain_count,
        "coverage_gap_count": gap_count,
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_source_coverage(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    coverage_path: Path = DEFAULT_COVERAGE_LEDGER,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    records = build_source_coverage_records(coverage_path=coverage_path, retrieved_at=retrieved_at)
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.replace_source_records(SOURCE_COVERAGE_SOURCE_ID, records)
    return _update_metadata(artifact_dir, records, coverage_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build queryable Aedes source-coverage records from the coverage ledger.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--coverage-path", default=str(DEFAULT_COVERAGE_LEDGER))
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_source_coverage(
        artifact_dir=Path(args.artifact_dir),
        coverage_path=Path(args.coverage_path),
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
