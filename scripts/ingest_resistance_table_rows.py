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
from askinsects.sources.resistance_table_rows import (
    RESISTANCE_TABLE_ROW_SOURCE_ID,
    build_resistance_table_row_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [gap for gap in existing if not (isinstance(gap, dict) and gap.get("source") == RESISTANCE_TABLE_ROW_SOURCE_ID)]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=1000)
    }


def _source_count(index: SourceIndex) -> int:
    with index.connect() as conn:
        return int(
            conn.execute(
                "select count(*) as n from records where source=?",
                (RESISTANCE_TABLE_ROW_SOURCE_ID,),
            ).fetchone()["n"]
        )


def _update_metadata(artifact_dir: Path, result, *, ok: bool = True, preserved_existing: bool = False) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    source_payload = {
        "source": RESISTANCE_TABLE_ROW_SOURCE_ID,
        "record_count": len(result.records),
        "parsed_table_row_count": result.parsed_table_row_count,
        "skipped_table_row_count": result.skipped_table_row_count,
        "extracted_fact_record_count": result.extracted_fact_record_count,
        "gap_count": len(result.gaps),
        "refresh_failed": not ok,
        "preserved_existing": preserved_existing,
        "method": "schema-validated resistance table-row promotion from parsed aedes_extracted_facts supplement rows",
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[RESISTANCE_TABLE_ROW_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if RESISTANCE_TABLE_ROW_SOURCE_ID not in sources:
                sources.append(RESISTANCE_TABLE_ROW_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload[RESISTANCE_TABLE_ROW_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "source": RESISTANCE_TABLE_ROW_SOURCE_ID,
        "record_count": len(result.records),
        "preserved_existing": preserved_existing,
        "parsed_table_row_count": result.parsed_table_row_count,
        "skipped_table_row_count": result.skipped_table_row_count,
        "extracted_fact_record_count": result.extracted_fact_record_count,
        "gap_count": len(result.gaps),
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_resistance_table_rows(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    result = build_resistance_table_row_records(artifact_dir, retrieved_at=retrieved_at)
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    refresh_failed = not result.records and bool(result.gaps)
    if not refresh_failed:
        index.replace_source_records(RESISTANCE_TABLE_ROW_SOURCE_ID, result.records)
    return _update_metadata(
        artifact_dir,
        result,
        ok=not refresh_failed,
        preserved_existing=refresh_failed and _source_count(index) > 0,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Promote parsed Aedes resistance supplement table rows into source-grade records.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_resistance_table_rows(
        artifact_dir=Path(args.artifact_dir),
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
