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
from askinsects.sources.aedes_crossref_literature_audit import (
    AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID,
    fetch_aedes_crossref_literature_audit_records,
)


FATAL_REFRESH_GAP_REASONS = {
    "aedes_crossref_fetch_failed",
}


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
        if not (isinstance(gap, dict) and gap.get("source") == AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID)
    ]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_record_count(index: SourceIndex) -> int:
    with index.connect() as conn:
        return int(
            conn.execute(
                "select count(*) as n from records where source=?",
                (AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID,),
            ).fetchone()["n"]
        )


def _existing_literature_rows(index: SourceIndex) -> list[dict[str, object]]:
    with index.connect() as conn:
        rows = conn.execute(
            """
            select
              r.record_id,
              r.source,
              r.title,
              r.url,
              p.payload_json
            from records r
            left join record_payloads p on p.record_id = r.record_id
            where r.lane = 'literature'
              and r.source != ?
            """,
            (AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID,),
        ).fetchall()
    parsed: list[dict[str, object]] = []
    for row in rows:
        payload_json = row["payload_json"]
        payload: dict[str, object] | None = None
        if isinstance(payload_json, str) and payload_json:
            try:
                loaded = json.loads(payload_json)
                if isinstance(loaded, dict):
                    payload = loaded
            except json.JSONDecodeError:
                payload = None
        parsed.append(
            {
                "record_id": row["record_id"],
                "source": row["source"],
                "title": row["title"],
                "url": row["url"],
                "payload": payload,
                "payload_json": payload_json,
            }
        )
    return parsed


def _update_metadata(artifact_dir: Path, result, retrieved_at: str, *, ok: bool = True, preserved_existing: bool = False) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    installed_record_count = _source_record_count(index)
    source_counts = {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=4000)
    }
    source_payload = {
        "source": AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID,
        "query": result.query,
        "requested_urls": result.requested_urls,
        "record_count": installed_record_count,
        "refresh_record_count": len(result.records),
        "reported_total_count": result.reported_total_count,
        "candidate_count": result.candidate_count,
        "canonical_literature_row_count": result.canonical_literature_row_count,
        "already_indexed_count": result.already_indexed_count,
        "crossref_metadata_ingested_count": result.crossref_metadata_ingested_count,
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
            sources[AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID not in sources:
                sources.append(AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload[AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "source": AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID,
        "record_count": installed_record_count,
        "refresh_record_count": len(result.records),
        "reported_total_count": result.reported_total_count,
        "candidate_count": result.candidate_count,
        "canonical_literature_row_count": result.canonical_literature_row_count,
        "already_indexed_count": result.already_indexed_count,
        "crossref_metadata_ingested_count": result.crossref_metadata_ingested_count,
        "gap_count": len(result.gaps),
        "preserved_existing": preserved_existing,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_aedes_crossref_literature_audit(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    fetch_json=None,
    retrieved_at: str | None = None,
    max_results: int = 500,
    page_size: int = 100,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    existing_rows = _existing_literature_rows(index)
    result = fetch_aedes_crossref_literature_audit_records(
        raw_dir=artifact_dir / "raw" / "aedes_crossref_literature_audit",
        existing_literature_rows=existing_rows,
        fetch_json=fetch_json,
        retrieved_at=retrieved,
        max_results=max_results,
        page_size=page_size,
    )
    fatal_gap = any(isinstance(gap, dict) and gap.get("reason") in FATAL_REFRESH_GAP_REASONS for gap in result.gaps)
    refresh_failed = fatal_gap or (not result.records and bool(result.gaps))
    if not refresh_failed:
        index.replace_source_records(AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID, result.records)
    return _update_metadata(
        artifact_dir,
        result,
        retrieved,
        ok=not refresh_failed,
        preserved_existing=refresh_failed and _source_record_count(index) > 0,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest a Crossref-backed Aedes aegypti literature audit lane.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--max-results", type=int, default=500)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_aedes_crossref_literature_audit(
        artifact_dir=Path(args.artifact_dir),
        max_results=args.max_results,
        page_size=args.page_size,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
