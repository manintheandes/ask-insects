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
from askinsects.sources.drosophila_suzukii_osu_trap_reports import (
    DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID,
    fetch_drosophila_suzukii_osu_trap_report_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=5000)
    }


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [
        gap
        for gap in existing
        if not (isinstance(gap, dict) and gap.get("source") == DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID)
    ]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _update_metadata(artifact_dir: Path, result, retrieved_at: str, *, ok: bool = True, preserved_existing: bool = False) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    installed_record_count = int(source_counts.get(DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID, 0))
    source_payload = {
        "source": DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID,
        "record_count": installed_record_count,
        "refresh_record_count": len(result.records),
        "file_count": result.file_count,
        "parsed_trap_site_count": result.parsed_trap_site_count,
        "parsed_trap_observation_count": result.parsed_trap_observation_count,
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
            sources[DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID not in sources:
                sources.append(DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload[DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "source": DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID,
        "record_count": installed_record_count,
        "refresh_record_count": len(result.records),
        "file_count": result.file_count,
        "parsed_trap_site_count": result.parsed_trap_site_count,
        "parsed_trap_observation_count": result.parsed_trap_observation_count,
        "gap_count": len(result.gaps),
        "preserved_existing": preserved_existing,
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_drosophila_suzukii_osu_trap_reports(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    fetch_body=None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    result = fetch_drosophila_suzukii_osu_trap_report_records(
        raw_dir=artifact_dir / "raw" / DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID,
        fetch_body=fetch_body,
        retrieved_at=retrieved,
    )
    refresh_failed = not any(record.payload and record.payload.get("atom_type") == "osu_swd_trap_observation" for record in result.records)
    if not refresh_failed:
        index.replace_source_records(DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID, result.records)
    with index.connect() as conn:
        preserved_existing = bool(
            conn.execute(
                "select 1 from records where source=? limit 1",
                (DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID,),
            ).fetchone()
        )
    return _update_metadata(
        artifact_dir,
        result,
        retrieved,
        ok=not refresh_failed,
        preserved_existing=refresh_failed and preserved_existing,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest Ohio State Drosophila suzukii trap report rows.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_drosophila_suzukii_osu_trap_reports(
        artifact_dir=Path(args.artifact_dir),
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
