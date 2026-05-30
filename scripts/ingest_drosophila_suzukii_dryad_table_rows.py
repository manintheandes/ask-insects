#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR
from askinsects.gaps import persist_source_gaps
from askinsects.index import SourceIndex
from askinsects.server import read_json, source_counts, write_json
from askinsects.sources.drosophila_suzukii_dryad_table_rows import (
    DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID,
    build_drosophila_suzukii_dryad_table_row_records,
)


def _dedupe_gaps(gaps: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for gap in gaps:
        key = (
            str(gap.get("source")),
            str(gap.get("lane")),
            str(gap.get("reason")),
            str(gap.get("record_id")),
            str(gap.get("locator")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(gap)
    return deduped


def _replace_source_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> list[dict[str, object]]:
    old_gaps = read_json(gaps_path, [])
    if not isinstance(old_gaps, list):
        old_gaps = []
    kept = [gap for gap in old_gaps if not (isinstance(gap, dict) and gap.get("source") == DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID)]
    kept.extend(gaps)
    return _dedupe_gaps([gap for gap in kept if isinstance(gap, dict)])


def _atom_counts(index: SourceIndex) -> dict[str, int]:
    rows = index.sql(
        """
        select json_extract(payload_json, '$.atom_type') as atom_type, count(*) as n
        from record_payloads
        where source='drosophila_suzukii_dryad_table_rows'
        group by atom_type
        """,
        limit=100,
    )
    return {str(row["atom_type"]): int(row["n"]) for row in rows if row["atom_type"]}


def ingest_drosophila_suzukii_dryad_table_rows(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    retrieved_at: str | None = None,
    max_table_files: int = 50,
    max_table_rows_per_file: int = 500,
    fetch_preview_text_fn: Callable[[str], str] | None = None,
) -> dict[str, object]:
    result = build_drosophila_suzukii_dryad_table_row_records(
        artifact_dir,
        retrieved_at=retrieved_at,
        max_table_files=max_table_files,
        max_table_rows_per_file=max_table_rows_per_file,
        fetch_preview_text_fn=fetch_preview_text_fn,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    refresh_failed = not result.records and bool(result.gaps)
    if not refresh_failed:
        index.replace_source_records(DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID, result.records)
    gap_retrieved_at = retrieved_at or (
        result.records[0].provenance.retrieved_at if result.records else None
    )
    persist_source_gaps(
        index,
        DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID,
        result.gaps,
        retrieved_at=gap_retrieved_at,
    )
    gaps = _replace_source_gaps(artifact_dir / "gaps.json", result.gaps)
    summary = index.summary()
    counts = source_counts(index)
    atoms = _atom_counts(index)
    source_payload = {
        "source": DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID,
        "record_count": counts.get(DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID, 0),
        "candidate_count": result.candidate_count,
        "parsed_table_file_count": result.parsed_table_file_count,
        "table_sheet_count": atoms.get("dryad_table_sheet", 0),
        "table_row_count": atoms.get("dryad_table_row", 0),
        "gap_count": atoms.get("dryad_table_gap", 0),
        "method": "parsed Drosophila suzukii Dryad public preview tables from indexed file manifests",
    }

    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        if filename == "source_receipt.json":
            sources = payload.get("sources")
            if not isinstance(sources, dict):
                sources = {}
            sources[DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID] = source_payload
        else:
            sources = payload.get("sources")
            if not isinstance(sources, list):
                sources = []
            if DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID not in sources:
                sources.append(DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = len(gaps)
        payload[DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID] = source_payload
        write_json(path, payload)
    write_json(artifact_dir / "gaps.json", gaps)
    return {
        "ok": not refresh_failed,
        "source": DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID,
        "artifact_dir": artifact_dir.as_posix(),
        **source_payload,
        "source_counts": counts,
        "lanes": summary["lanes"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Drosophila suzukii Dryad preview table rows from indexed Ask Insects manifests.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    parser.add_argument("--max-table-files", type=int, default=50)
    parser.add_argument("--max-table-rows-per-file", type=int, default=500)
    args = parser.parse_args(argv)
    result = ingest_drosophila_suzukii_dryad_table_rows(
        artifact_dir=Path(args.artifact_dir),
        retrieved_at=args.retrieved_at,
        max_table_files=args.max_table_files,
        max_table_rows_per_file=args.max_table_rows_per_file,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
