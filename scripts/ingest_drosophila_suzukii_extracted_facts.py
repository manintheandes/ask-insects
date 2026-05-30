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
from askinsects.gaps import persist_source_gaps
from askinsects.index import SourceIndex
from askinsects.sources.drosophila_suzukii_extracted_facts import (
    DROSOPHILA_SUZUKII_EXTRACTED_FACTS_PROFILE,
    DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID,
)
from askinsects.sources.extracted_facts import (
    DEFAULT_MAX_SUPPLEMENT_BYTES,
    MAX_CANDIDATE_TEXT_CHARS,
    build_extracted_fact_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _gap_receipt_key(gap: dict[str, object]) -> tuple[str, str, str, str, str]:
    return (
        str(gap.get("source")),
        str(gap.get("lane")),
        str(gap.get("reason")),
        str(gap.get("record_id")),
        str(gap.get("locator")),
    )


def _dedup_gap_rows(gaps: list[object]) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for gap in gaps:
        if not isinstance(gap, dict):
            continue
        key = _gap_receipt_key(gap)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(gap)
    return deduped


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]], *, replace_source_gaps: bool = True) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    if replace_source_gaps:
        combined = [
            gap
            for gap in existing
            if not (isinstance(gap, dict) and gap.get("source") == DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID)
        ]
    else:
        combined = _dedup_gap_rows(existing)
        seen = {_gap_receipt_key(gap) for gap in combined}
        gaps = [gap for gap in gaps if _gap_receipt_key(gap) not in seen]
    combined.extend(gaps)
    combined = _dedup_gap_rows(combined)
    write_json(gaps_path, combined)
    return len(combined)


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=2000)
    }


def _scalar(index: SourceIndex, sql: str) -> int:
    rows = index.sql(sql, limit=1)
    return int(rows[0]["n"]) if rows else 0


def _global_metrics(index: SourceIndex) -> dict[str, object]:
    source_id = DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID
    fact_rows = index.sql(
        """
        select json_extract(payload_json, '$.fact_type') as fact_type, count(*) as n
        from record_payloads
        where source='drosophila_suzukii_extracted_facts'
          and json_extract(payload_json, '$.fact_type') is not null
        group by fact_type
        order by fact_type
        """,
        limit=1000,
    )
    fact_counts = {
        str(row["fact_type"]): int(row["n"])
        for row in fact_rows
        if str(row["fact_type"]) not in {"supplement_manifest", "supplement_audit"}
    }
    route_rows = index.sql(
        """
        select coalesce(json_extract(payload_json, '$.supplement.source'), 'unknown') as route, count(*) as n
        from record_payloads
        where source='drosophila_suzukii_extracted_facts'
          and json_extract(payload_json, '$.fact_type')='supplement_manifest'
        group by route
        order by route
        """,
        limit=1000,
    )
    return {
        "source_record_count": _scalar(
            index,
            """
            select count(*) as n
            from records
            where source='drosophila_suzukii_core'
              and lane='literature'
              and lower(coalesce(species, ''))='drosophila suzukii'
            """,
        ),
        "supplement_manifest_count": int(next((row["n"] for row in fact_rows if row["fact_type"] == "supplement_manifest"), 0)),
        "supplement_audit_record_count": int(next((row["n"] for row in fact_rows if row["fact_type"] == "supplement_audit"), 0)),
        "papers_with_supplement_manifest_count": _scalar(
            index,
            """
            select count(distinct json_extract(payload_json, '$.source_record_id')) as n
            from record_payloads
            where source='drosophila_suzukii_extracted_facts'
              and json_extract(payload_json, '$.fact_type')='supplement_manifest'
            """,
        ),
        "papers_with_parsed_supplement_rows_count": _scalar(
            index,
            """
            select count(distinct json_extract(payload_json, '$.source_record_id')) as n
            from record_payloads
            where source='drosophila_suzukii_extracted_facts'
              and json_extract(payload_json, '$.confidence')='parsed'
            """,
        ),
        "papers_with_promoted_supplement_rows_count": _scalar(
            index,
            """
            select count(distinct json_extract(payload_json, '$.source_record_id')) as n
            from record_payloads
            where source='drosophila_suzukii_extracted_facts'
              and json_extract(payload_json, '$.confidence')='parsed'
              and json_extract(payload_json, '$.fact_type') not in ('supplement_manifest', 'supplement_audit')
            """,
        ),
        "fact_counts": fact_counts,
        "supplement_discovery_route_counts": {str(row["route"]): int(row["n"]) for row in route_rows},
    }


def _delete_records_for_source_records(index: SourceIndex, source_record_ids: list[str], *, delete_fts: bool = True) -> int:
    if not source_record_ids:
        return 0
    deleted = 0
    with index.connect() as conn:
        for record_id in source_record_ids:
            rows = conn.execute(
                """
                SELECT r.record_id
                FROM records r
                LEFT JOIN record_payloads p ON p.record_id = r.record_id
                WHERE r.source=?
                  AND json_extract(p.payload_json, '$.source_record_id')=?
                """,
                (DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID, record_id),
            ).fetchall()
            record_ids = [str(row["record_id"]) for row in rows]
            if not record_ids:
                continue
            deleted += len(record_ids)
            for start in range(0, len(record_ids), 500):
                chunk = record_ids[start : start + 500]
                placeholders = ",".join("?" for _ in chunk)
                if delete_fts:
                    conn.execute(f"DELETE FROM records_fts WHERE record_id IN ({placeholders})", chunk)
                conn.execute(f"DELETE FROM record_payloads WHERE record_id IN ({placeholders})", chunk)
                conn.execute(f"DELETE FROM records WHERE record_id IN ({placeholders})", chunk)
    return deleted


def _update_metadata(
    artifact_dir: Path,
    result,
    *,
    merge_existing: bool = False,
    source_record_ids: list[str] | None = None,
    ok: bool = True,
) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    installed_record_count = int(source_counts.get(DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID, len(result.records)))
    global_metrics = _global_metrics(index)
    source_payload = {
        "source": DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID,
        "record_count": installed_record_count,
        "last_build_record_count": len(result.records),
        "merge_existing": merge_existing,
        "source_record_ids": source_record_ids or None,
        "candidate_count": result.candidate_count,
        "source_record_count": global_metrics["source_record_count"],
        "fulltext_unit_count": result.fulltext_unit_count,
        "max_fulltext_units": result.max_fulltext_units,
        "max_candidate_text_chars": MAX_CANDIDATE_TEXT_CHARS,
        "selected_fulltext_unit_count": result.selected_fulltext_unit_count,
        "truncated_fulltext_unit_count": result.truncated_fulltext_unit_count,
        "selected_record_text_count": result.selected_record_text_count,
        "supplement_manifest_count": global_metrics["supplement_manifest_count"],
        "supplement_audit_record_count": global_metrics["supplement_audit_record_count"],
        "papers_with_supplement_manifest_count": global_metrics["papers_with_supplement_manifest_count"],
        "papers_with_parsed_supplement_rows_count": global_metrics["papers_with_parsed_supplement_rows_count"],
        "papers_with_promoted_supplement_rows_count": global_metrics["papers_with_promoted_supplement_rows_count"],
        "supplement_discovery_record_count": result.supplement_discovery_record_count,
        "max_repository_supplement_discovery_records": result.max_repository_supplement_discovery_records,
        "discovered_supplement_count": result.discovered_supplement_count,
        "downloaded_supplement_file_count": result.downloaded_supplement_file_count,
        "parsed_supplement_file_count": result.parsed_supplement_file_count,
        "parsed_supplement_row_count": result.parsed_supplement_row_count,
        "max_pdf_supplement_files": result.max_pdf_supplement_files,
        "parsed_pdf_supplement_file_count": result.parsed_pdf_supplement_file_count,
        "skipped_pdf_supplement_file_count": result.skipped_pdf_supplement_file_count,
        "fact_counts": global_metrics["fact_counts"],
        "supplement_discovery_route_counts": global_metrics["supplement_discovery_route_counts"],
        "gap_count": len(result.gaps),
        "method": "deterministic supplement manifest discovery, supported supplement table parsing, and cross-lane Drosophila suzukii fact extraction from literature records and bounded legal full-text units",
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps, replace_source_gaps=not merge_existing)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID not in sources:
                sources.append(DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload[DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "source": DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID,
        "record_count": installed_record_count,
        "last_build_record_count": len(result.records),
        "merge_existing": merge_existing,
        "source_record_ids": source_record_ids or None,
        "candidate_count": result.candidate_count,
        "source_record_count": global_metrics["source_record_count"],
        "supplement_manifest_count": global_metrics["supplement_manifest_count"],
        "supplement_audit_record_count": global_metrics["supplement_audit_record_count"],
        "papers_with_supplement_manifest_count": global_metrics["papers_with_supplement_manifest_count"],
        "papers_with_parsed_supplement_rows_count": global_metrics["papers_with_parsed_supplement_rows_count"],
        "papers_with_promoted_supplement_rows_count": global_metrics["papers_with_promoted_supplement_rows_count"],
        "supplement_discovery_route_counts": global_metrics["supplement_discovery_route_counts"],
        "gap_count": len(result.gaps),
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_drosophila_suzukii_extracted_facts(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    retrieved_at: str | None = None,
    max_fulltext_units: int | None = 5000,
    discover_supplements: bool = False,
    download_supplements: bool = False,
    fetch_supplement_metadata_fn=None,
    fetch_supplement_file_fn=None,
    max_supplement_discovery_records: int | None = 500,
    max_repository_supplement_discovery_records: int | None = 100,
    max_supplement_files: int = 100,
    max_supplement_bytes: int = DEFAULT_MAX_SUPPLEMENT_BYTES,
    max_pdf_supplement_files: int = 10,
    source_record_ids: list[str] | None = None,
    merge_existing: bool = False,
    update_fts: bool = True,
    update_metadata: bool = True,
) -> dict[str, object]:
    result = build_extracted_fact_records(
        artifact_dir,
        retrieved_at=retrieved_at,
        max_fulltext_units=max_fulltext_units,
        discover_supplements=discover_supplements,
        download_supplements=download_supplements,
        fetch_supplement_metadata_fn=fetch_supplement_metadata_fn,
        fetch_supplement_file_fn=fetch_supplement_file_fn,
        max_supplement_discovery_records=max_supplement_discovery_records,
        max_repository_supplement_discovery_records=max_repository_supplement_discovery_records,
        max_supplement_files=max_supplement_files,
        max_supplement_bytes=max_supplement_bytes,
        max_pdf_supplement_files=max_pdf_supplement_files,
        source_record_ids=source_record_ids,
        profile=DROSOPHILA_SUZUKII_EXTRACTED_FACTS_PROFILE,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    deleted_existing_record_count = 0
    refresh_failed = not merge_existing and not result.records and bool(result.gaps)
    if merge_existing:
        if not source_record_ids:
            raise ValueError("merge_existing requires at least one source_record_id")
        deleted_existing_record_count = _delete_records_for_source_records(index, source_record_ids, delete_fts=update_fts)
        index.upsert_records(result.records, update_fts=update_fts)
    elif not refresh_failed:
        index.replace_source_records(
            DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID,
            result.records,
            update_fts=update_fts,
            delete_existing_fts=update_fts,
        )
    persist_source_gaps(index, DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID, result.gaps, retrieved_at=retrieved_at)
    if update_metadata:
        payload = _update_metadata(
            artifact_dir,
            result,
            merge_existing=merge_existing,
            source_record_ids=source_record_ids,
            ok=not refresh_failed,
        )
    else:
        payload = {
            "ok": not refresh_failed,
            "source": DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID,
            "record_count": len(result.records),
            "last_build_record_count": len(result.records),
            "merge_existing": merge_existing,
            "source_record_ids": source_record_ids or None,
            "metadata_update_skipped": True,
        }
    payload["deleted_existing_record_count"] = deleted_existing_record_count
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract spotted wing drosophila facts and supplement audits from indexed literature.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    parser.add_argument("--max-fulltext-units", type=int, default=5000)
    parser.add_argument("--discover-supplements", action="store_true")
    parser.add_argument("--download-supplements", action="store_true")
    parser.add_argument("--max-supplement-discovery-records", type=int, default=500)
    parser.add_argument("--max-repository-supplement-discovery-records", type=int, default=100)
    parser.add_argument("--max-supplement-files", type=int, default=100)
    parser.add_argument("--max-supplement-bytes", type=int, default=DEFAULT_MAX_SUPPLEMENT_BYTES)
    parser.add_argument("--max-pdf-supplement-files", type=int, default=10)
    parser.add_argument("--source-record-id", action="append", default=[])
    parser.add_argument("--merge-existing", action="store_true")
    parser.add_argument("--skip-fts-update", action="store_true")
    parser.add_argument("--skip-metadata-update", action="store_true")
    args = parser.parse_args(argv)
    result = ingest_drosophila_suzukii_extracted_facts(
        artifact_dir=Path(args.artifact_dir),
        retrieved_at=args.retrieved_at,
        max_fulltext_units=args.max_fulltext_units,
        discover_supplements=args.discover_supplements,
        download_supplements=args.download_supplements,
        max_supplement_discovery_records=args.max_supplement_discovery_records,
        max_repository_supplement_discovery_records=args.max_repository_supplement_discovery_records,
        max_supplement_files=args.max_supplement_files,
        max_supplement_bytes=args.max_supplement_bytes,
        max_pdf_supplement_files=args.max_pdf_supplement_files,
        source_record_ids=args.source_record_id or None,
        merge_existing=args.merge_existing,
        update_fts=not args.skip_fts_update,
        update_metadata=not args.skip_metadata_update,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
