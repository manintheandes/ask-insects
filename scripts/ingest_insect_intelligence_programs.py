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
from askinsects.sources.insect_intelligence_programs import (
    DEFAULT_PROGRAM_LEDGER,
    INSECT_INTELLIGENCE_SOURCE_ID,
    build_insect_intelligence_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=1000)
    }


def _update_metadata(artifact_dir: Path, records: list[object], program_path: Path) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    atom_counts: dict[str, int] = {}
    for record in records:
        atom_type = str(record.payload.get("atom_type") if record.payload else "unknown")
        atom_counts[atom_type] = atom_counts.get(atom_type, 0) + 1
    source_payload = {
        "source": INSECT_INTELLIGENCE_SOURCE_ID,
        "record_count": len(records),
        "species_count": atom_counts.get("species_profile", 0),
        "product_count": atom_counts.get("product_program", 0),
        "knowledge_domain_count": atom_counts.get("knowledge_domain", 0),
        "readiness_dimension_count": atom_counts.get("readiness_dimension", 0),
        "gap_count": atom_counts.get("knowledge_gap", 0) + atom_counts.get("readiness_gap", 0),
        "program_ledger": program_path.as_posix(),
        "method": "validated program ledger to queryable insect-intelligence records",
    }
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[INSECT_INTELLIGENCE_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if INSECT_INTELLIGENCE_SOURCE_ID not in sources:
                sources.append(INSECT_INTELLIGENCE_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload[INSECT_INTELLIGENCE_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {
        "ok": True,
        **source_payload,
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_insect_intelligence_programs(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    program_path: Path = DEFAULT_PROGRAM_LEDGER,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    records = build_insect_intelligence_records(program_path=program_path, retrieved_at=retrieved_at)
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.replace_source_records(INSECT_INTELLIGENCE_SOURCE_ID, records)
    return _update_metadata(artifact_dir, records, Path(program_path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build queryable insect and product intelligence records from the program ledger.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--program-path", default=str(DEFAULT_PROGRAM_LEDGER))
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_insect_intelligence_programs(
        artifact_dir=Path(args.artifact_dir),
        program_path=Path(args.program_path),
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
