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
from askinsects.sources.drosophila_suzukii import DROSOPHILA_SUZUKII_SOURCE_ID, _coverage_records
from askinsects.sources.drosophila_suzukii_biocontrol_outcome_rows import (
    DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID,
    build_drosophila_suzukii_biocontrol_outcome_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [
        gap
        for gap in existing
        if not (isinstance(gap, dict) and gap.get("source") == DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID)
    ]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=2000)
    }


def _existing_swd_upstream_sources(artifact_dir: Path) -> dict[str, dict[str, object]]:
    for filename in ("source_receipt.json", "source_status.json"):
        payload = _read_json(artifact_dir / filename, {})
        if not isinstance(payload, dict):
            continue
        source_payload = payload.get(DROSOPHILA_SUZUKII_SOURCE_ID)
        if isinstance(source_payload, dict) and isinstance(source_payload.get("upstream_sources"), dict):
            return {
                str(key): value
                for key, value in source_payload["upstream_sources"].items()
                if isinstance(value, dict)
            }
    return {}


def _refresh_swd_coverage_records(artifact_dir: Path, *, retrieved_at: str | None) -> None:
    records = _coverage_records(_existing_swd_upstream_sources(artifact_dir), retrieved_at=retrieved_at or "unknown")
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    with index.connect() as conn:
        rows = conn.execute(
            "SELECT record_id FROM records WHERE source = ? AND lane = 'source_coverage'",
            (DROSOPHILA_SUZUKII_SOURCE_ID,),
        ).fetchall()
        record_ids = [str(row["record_id"]) for row in rows]
        for record_id in record_ids:
            conn.execute("DELETE FROM records_fts WHERE record_id = ?", (record_id,))
        conn.execute(
            "DELETE FROM record_payloads WHERE source = ? AND lane = 'source_coverage'",
            (DROSOPHILA_SUZUKII_SOURCE_ID,),
        )
        conn.execute(
            "DELETE FROM records WHERE source = ? AND lane = 'source_coverage'",
            (DROSOPHILA_SUZUKII_SOURCE_ID,),
        )
    index.upsert_records(records)


def _update_metadata(artifact_dir: Path, result, *, ok: bool = True) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    source_payload = {
        "source": DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID,
        "record_count": len(result.records),
        "parsed_table_row_count": result.parsed_table_row_count,
        "candidate_fact_count": result.candidate_fact_count,
        "skipped_record_count": result.skipped_record_count,
        "extracted_fact_record_count": result.extracted_fact_record_count,
        "gap_count": len(result.gaps),
        "method": "schema-validated table-row and candidate biocontrol outcome evidence promotion from drosophila_suzukii_extracted_facts biocontrol records",
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID not in sources:
                sources.append(DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload[DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "source": DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID,
        "record_count": len(result.records),
        "parsed_table_row_count": result.parsed_table_row_count,
        "candidate_fact_count": result.candidate_fact_count,
        "skipped_record_count": result.skipped_record_count,
        "extracted_fact_record_count": result.extracted_fact_record_count,
        "gap_count": len(result.gaps),
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_drosophila_suzukii_biocontrol_outcome_rows(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    result = build_drosophila_suzukii_biocontrol_outcome_records(artifact_dir, retrieved_at=retrieved_at)
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    refresh_failed = not result.records and bool(result.gaps)
    if not refresh_failed:
        index.replace_source_records(DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID, result.records)
    coverage_retrieved_at = retrieved_at or (result.records[0].provenance.retrieved_at if result.records else None)
    _refresh_swd_coverage_records(artifact_dir, retrieved_at=coverage_retrieved_at)
    return _update_metadata(artifact_dir, result, ok=not refresh_failed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Promote Drosophila suzukii biocontrol outcome evidence rows into Ask Insects.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_drosophila_suzukii_biocontrol_outcome_rows(
        artifact_dir=Path(args.artifact_dir),
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
