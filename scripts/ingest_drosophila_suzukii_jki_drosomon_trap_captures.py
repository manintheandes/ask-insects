#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR, utc_now, write_json
from askinsects.index import SourceIndex
from askinsects.sources.drosophila_suzukii_jki_drosomon_trap_captures import (
    DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID,
    fetch_drosophila_suzukii_jki_drosomon_trap_capture_records,
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
        if not (isinstance(gap, dict) and gap.get("source") == DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID)
    ]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_count(index: SourceIndex) -> int:
    with index.connect() as conn:
        return int(
            conn.execute(
                "select count(*) as n from records where source=?",
                (DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID,),
            ).fetchone()["n"]
        )


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=3000)
    }


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _source_count_from_payload(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    source_counts = payload.get("source_counts")
    if isinstance(source_counts, dict):
        count = _int_or_none(source_counts.get(DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID))
        if count is not None:
            return count
    source_payload = payload.get(DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID)
    if isinstance(source_payload, dict):
        count = _int_or_none(source_payload.get("record_count"))
        if count is not None:
            return count
    return 0


def _metadata_counts(artifact_dir: Path, installed_record_count: int) -> tuple[dict[str, int], dict[str, int], int, int]:
    status_payload = _read_json(artifact_dir / "source_status.json", {})
    if not isinstance(status_payload, dict):
        status_payload = {}
    previous_source_count = _source_count_from_payload(status_payload)
    existing_source_counts = status_payload.get("source_counts")
    existing_lanes = status_payload.get("lanes")
    previous_record_count = _int_or_none(status_payload.get("record_count"))
    previous_species_count = _int_or_none(status_payload.get("species_count"))
    if not isinstance(existing_source_counts, dict) or previous_record_count is None or previous_species_count is None:
        index = SourceIndex(artifact_dir / "source_index.sqlite")
        summary = index.summary()
        source_counts = _source_counts(index)
        return source_counts, summary["lanes"], summary["record_count"], summary["species_count"]

    source_counts = {str(source): int(count) for source, count in existing_source_counts.items()}
    source_counts[DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID] = installed_record_count

    lanes: dict[str, int]
    if isinstance(existing_lanes, dict):
        lanes = {str(lane): int(count) for lane, count in existing_lanes.items()}
        lanes["ecology"] = max(0, int(lanes.get("ecology", 0)) - previous_source_count + installed_record_count)
    else:
        lanes = SourceIndex(artifact_dir / "source_index.sqlite").summary()["lanes"]

    record_count = max(0, previous_record_count - previous_source_count + installed_record_count)
    return source_counts, lanes, record_count, previous_species_count


def _update_metadata(artifact_dir: Path, result, retrieved_at: str, *, ok: bool = True, preserved_existing: bool = False) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    installed_record_count = _source_count(index)
    source_counts, lanes, record_count, species_count = _metadata_counts(artifact_dir, installed_record_count)
    source_payload = {
        "source": DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID,
        "record_count": installed_record_count,
        "refresh_record_count": len(result.records),
        "file_count": result.file_count,
        "parsed_trap_row_count": result.parsed_trap_row_count,
        "parsed_trap_location_count": result.parsed_trap_location_count,
        "requested_urls": result.requested_urls,
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
        "retrieved_at": retrieved_at,
        "refresh_failed": not ok,
        "preserved_existing": preserved_existing,
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID not in sources:
                sources.append(DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = record_count
        payload["species_count"] = species_count
        payload["lanes"] = lanes
        payload["gap_count"] = gap_count
        payload[DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "source": DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID,
        "record_count": installed_record_count,
        "refresh_record_count": len(result.records),
        "file_count": result.file_count,
        "parsed_trap_row_count": result.parsed_trap_row_count,
        "parsed_trap_location_count": result.parsed_trap_location_count,
        "gap_count": len(result.gaps),
        "preserved_existing": preserved_existing,
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": lanes,
    }


def ingest_drosophila_suzukii_jki_drosomon_trap_captures(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    fetch_json=None,
    fetch_body=None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    result = fetch_drosophila_suzukii_jki_drosomon_trap_capture_records(
        raw_dir=artifact_dir / "raw" / DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID,
        fetch_json=fetch_json,
        fetch_body=fetch_body,
        retrieved_at=retrieved,
    )
    refresh_failed = not result.records and bool(result.gaps)
    if not refresh_failed:
        index.replace_source_records(DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID, result.records)
    return _update_metadata(
        artifact_dir,
        result,
        retrieved,
        ok=not refresh_failed,
        preserved_existing=refresh_failed and _source_count(index) > 0,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest JKI DrosoMon Drosophila suzukii trap-capture manifests and source gaps.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_drosophila_suzukii_jki_drosomon_trap_captures(
        artifact_dir=Path(args.artifact_dir),
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
