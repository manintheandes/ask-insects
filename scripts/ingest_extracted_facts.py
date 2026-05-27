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
from askinsects.sources.extracted_facts import (
    EXTRACTED_FACTS_SOURCE_ID,
    MAX_CANDIDATE_TEXT_CHARS,
    build_extracted_fact_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]], *, replace_source_gaps: bool = True) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    if replace_source_gaps:
        combined = [gap for gap in existing if not (isinstance(gap, dict) and gap.get("source") == EXTRACTED_FACTS_SOURCE_ID)]
    else:
        combined = list(existing)
        seen = {json.dumps(gap, sort_keys=True, default=str) for gap in combined if isinstance(gap, dict)}
        gaps = [gap for gap in gaps if json.dumps(gap, sort_keys=True, default=str) not in seen]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=1000)
    }


def _update_metadata(
    artifact_dir: Path,
    result,
    *,
    merge_existing: bool = False,
    source_record_ids: list[str] | None = None,
) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    installed_record_count = int(source_counts.get(EXTRACTED_FACTS_SOURCE_ID, len(result.records)))
    source_payload = {
        "source": EXTRACTED_FACTS_SOURCE_ID,
        "record_count": installed_record_count,
        "last_build_record_count": len(result.records),
        "merge_existing": merge_existing,
        "source_record_ids": source_record_ids or None,
        "candidate_count": result.candidate_count,
        "source_record_count": result.source_record_count,
        "fulltext_unit_count": result.fulltext_unit_count,
        "max_fulltext_units": result.max_fulltext_units,
        "max_candidate_text_chars": MAX_CANDIDATE_TEXT_CHARS,
        "selected_fulltext_unit_count": result.selected_fulltext_unit_count,
        "truncated_fulltext_unit_count": result.truncated_fulltext_unit_count,
        "selected_record_text_count": result.selected_record_text_count,
        "supplement_manifest_count": result.supplement_manifest_count,
        "supplement_audit_record_count": result.supplement_audit_record_count,
        "papers_with_supplement_manifest_count": result.papers_with_supplement_manifest_count,
        "papers_with_parsed_supplement_rows_count": result.papers_with_parsed_supplement_rows_count,
        "papers_with_promoted_supplement_rows_count": result.papers_with_promoted_supplement_rows_count,
        "supplement_discovery_record_count": result.supplement_discovery_record_count,
        "max_repository_supplement_discovery_records": result.max_repository_supplement_discovery_records,
        "discovered_supplement_count": result.discovered_supplement_count,
        "downloaded_supplement_file_count": result.downloaded_supplement_file_count,
        "parsed_supplement_file_count": result.parsed_supplement_file_count,
        "parsed_supplement_row_count": result.parsed_supplement_row_count,
        "max_pdf_supplement_files": result.max_pdf_supplement_files,
        "parsed_pdf_supplement_file_count": result.parsed_pdf_supplement_file_count,
        "skipped_pdf_supplement_file_count": result.skipped_pdf_supplement_file_count,
        "fact_counts": result.fact_counts,
        "gap_count": len(result.gaps),
        "method": "deterministic supplement manifest discovery, supported supplement table parsing, and cross-lane Aedes fact extraction from literature records and bounded legal full-text units",
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps, replace_source_gaps=not merge_existing)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[EXTRACTED_FACTS_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if EXTRACTED_FACTS_SOURCE_ID not in sources:
                sources.append(EXTRACTED_FACTS_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload["aedes_extracted_facts"] = source_payload
        write_json(path, payload)
    return {
        "ok": True,
        "source": EXTRACTED_FACTS_SOURCE_ID,
        "record_count": installed_record_count,
        "last_build_record_count": len(result.records),
        "merge_existing": merge_existing,
        "source_record_ids": source_record_ids or None,
        "candidate_count": result.candidate_count,
        "source_record_count": result.source_record_count,
        "fulltext_unit_count": result.fulltext_unit_count,
        "max_fulltext_units": result.max_fulltext_units,
        "max_candidate_text_chars": MAX_CANDIDATE_TEXT_CHARS,
        "selected_fulltext_unit_count": result.selected_fulltext_unit_count,
        "truncated_fulltext_unit_count": result.truncated_fulltext_unit_count,
        "selected_record_text_count": result.selected_record_text_count,
        "supplement_manifest_count": result.supplement_manifest_count,
        "supplement_audit_record_count": result.supplement_audit_record_count,
        "papers_with_supplement_manifest_count": result.papers_with_supplement_manifest_count,
        "papers_with_parsed_supplement_rows_count": result.papers_with_parsed_supplement_rows_count,
        "papers_with_promoted_supplement_rows_count": result.papers_with_promoted_supplement_rows_count,
        "supplement_discovery_record_count": result.supplement_discovery_record_count,
        "max_repository_supplement_discovery_records": result.max_repository_supplement_discovery_records,
        "discovered_supplement_count": result.discovered_supplement_count,
        "downloaded_supplement_file_count": result.downloaded_supplement_file_count,
        "parsed_supplement_file_count": result.parsed_supplement_file_count,
        "parsed_supplement_row_count": result.parsed_supplement_row_count,
        "max_pdf_supplement_files": result.max_pdf_supplement_files,
        "parsed_pdf_supplement_file_count": result.parsed_pdf_supplement_file_count,
        "skipped_pdf_supplement_file_count": result.skipped_pdf_supplement_file_count,
        "fact_counts": result.fact_counts,
        "gap_count": len(result.gaps),
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def _delete_extracted_fact_records_for_source_records(index: SourceIndex, source_record_ids: list[str]) -> int:
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
                (EXTRACTED_FACTS_SOURCE_ID, record_id),
            ).fetchall()
            record_ids = [str(row["record_id"]) for row in rows]
            if not record_ids:
                continue
            deleted += len(record_ids)
            for start in range(0, len(record_ids), 500):
                chunk = record_ids[start : start + 500]
                placeholders = ",".join("?" for _ in chunk)
                conn.execute(f"DELETE FROM records_fts WHERE record_id IN ({placeholders})", chunk)
                conn.execute(f"DELETE FROM record_payloads WHERE record_id IN ({placeholders})", chunk)
                conn.execute(f"DELETE FROM records WHERE record_id IN ({placeholders})", chunk)
    return deleted


def ingest_extracted_facts(
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
    max_supplement_bytes: int = 2_000_000,
    max_pdf_supplement_files: int = 10,
    source_record_ids: list[str] | None = None,
    merge_existing: bool = False,
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
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    deleted_existing_record_count = 0
    if merge_existing:
        if not source_record_ids:
            raise ValueError("merge_existing requires at least one source_record_id")
        deleted_existing_record_count = _delete_extracted_fact_records_for_source_records(index, source_record_ids)
        index.upsert_records(result.records)
    else:
        index.replace_source_records(EXTRACTED_FACTS_SOURCE_ID, result.records)
    payload = _update_metadata(
        artifact_dir,
        result,
        merge_existing=merge_existing,
        source_record_ids=source_record_ids,
    )
    payload["deleted_existing_record_count"] = deleted_existing_record_count
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract cross-lane Aedes facts and supplement manifests from indexed literature.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    parser.add_argument("--max-fulltext-units", type=int, default=5000)
    parser.add_argument("--discover-supplements", action="store_true")
    parser.add_argument("--download-supplements", action="store_true")
    parser.add_argument("--max-supplement-discovery-records", type=int, default=500)
    parser.add_argument("--max-repository-supplement-discovery-records", type=int, default=100)
    parser.add_argument("--max-supplement-files", type=int, default=100)
    parser.add_argument("--max-supplement-bytes", type=int, default=2_000_000)
    parser.add_argument("--max-pdf-supplement-files", type=int, default=10)
    parser.add_argument("--source-record-id", action="append", default=[])
    parser.add_argument("--merge-existing", action="store_true")
    args = parser.parse_args(argv)
    result = ingest_extracted_facts(
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
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
