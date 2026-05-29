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
from askinsects.sources.drosophila_suzukii_geo_expression_matrices import (
    DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID,
    fetch_drosophila_suzukii_geo_expression_matrices_records,
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
        if not (isinstance(gap, dict) and gap.get("source") == DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID)
    ]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_record_count(index: SourceIndex) -> int:
    with index.connect() as conn:
        return int(
            conn.execute(
                "select count(*) as n from records where source=?",
                (DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID,),
            ).fetchone()["n"]
        )


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=3000)
    }


def _update_metadata(artifact_dir: Path, result, retrieved_at: str, *, ok: bool = True, preserved_existing: bool = False) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    installed_record_count = _source_record_count(index)
    source_counts = _source_counts(index)
    source_payload = {
        "source": DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID,
        "accessions": result.accessions,
        "requested_urls": result.requested_urls,
        "record_count": installed_record_count,
        "refresh_record_count": len(result.records),
        "file_count": result.file_count,
        "parsed_row_count": result.parsed_row_count,
        "significant_row_count": result.significant_row_count,
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
            sources[DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID not in sources:
                sources.append(DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload[DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "source": DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID,
        "record_count": installed_record_count,
        "refresh_record_count": len(result.records),
        "file_count": result.file_count,
        "parsed_row_count": result.parsed_row_count,
        "significant_row_count": result.significant_row_count,
        "gap_count": len(result.gaps),
        "preserved_existing": preserved_existing,
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_drosophila_suzukii_geo_expression_matrices(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    fetch_bytes=None,
    retrieved_at: str | None = None,
    max_download_bytes: int = 10_000_000,
    max_rows_per_file: int | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    result = fetch_drosophila_suzukii_geo_expression_matrices_records(
        artifact_dir=artifact_dir,
        fetch_bytes=fetch_bytes,
        retrieved_at=retrieved,
        max_download_bytes=max_download_bytes,
        max_rows_per_file=max_rows_per_file,
    )
    refresh_failed = not result.records and bool(result.gaps)
    if not refresh_failed:
        index.replace_source_records(DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID, result.records)
    return _update_metadata(
        artifact_dir,
        result,
        retrieved,
        ok=not refresh_failed,
        preserved_existing=refresh_failed and _source_record_count(index) > 0,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest GEO differential-expression matrix rows for Drosophila suzukii.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--max-download-bytes", type=int, default=10_000_000)
    parser.add_argument("--max-rows-per-file", type=int)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_drosophila_suzukii_geo_expression_matrices(
        artifact_dir=Path(args.artifact_dir),
        max_download_bytes=args.max_download_bytes,
        max_rows_per_file=args.max_rows_per_file,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
