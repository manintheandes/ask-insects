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
from askinsects.gaps import persist_source_gaps
from askinsects.index import SourceIndex
from askinsects.sources.ncvbdc_dengue_surveillance import (
    DEFAULT_NCVBDC_DENGUE_PAGE,
    NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID,
    fetch_ncvbdc_dengue_surveillance_records,
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
        if not (isinstance(gap, dict) and gap.get("source") == NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID)
    ]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=2000)
    }


def _update_metadata(artifact_dir: Path, result, retrieved_at: str, *, ok: bool = True, preserved_existing: bool = False) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    source_payload = {
        "source": NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID,
        "refresh_failed": not ok,
        "preserved_existing": preserved_existing,
        "requested_urls": result.requested_urls,
        "record_count": len(result.records),
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
        "page_count": result.page_count,
        "table_row_count": result.table_row_count,
        "state_year_record_count": result.state_year_record_count,
        "national_year_record_count": result.national_year_record_count,
        "recent_summary_count": result.recent_summary_count,
        "retrieved_at": retrieved_at,
        "method": "official India NCVBDC dengue situation HTML table parsed into state/UT-year, country-year, and two-latest-complete-year summary public-health records for Aedes aegypti intelligence",
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID not in sources:
                sources.append(NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload["fully_parsed"] = gap_count == 0
        payload["parsed_scope"] = "India NCVBDC dengue cases/deaths table at state/UT-year, country-year, and recent complete-year summary grain"
        payload[NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "preserved_existing": preserved_existing,
        "source": NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID,
        "record_count": len(result.records),
        "gap_count": len(result.gaps),
        "page_count": result.page_count,
        "table_row_count": result.table_row_count,
        "state_year_record_count": result.state_year_record_count,
        "national_year_record_count": result.national_year_record_count,
        "recent_summary_count": result.recent_summary_count,
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_ncvbdc_dengue_surveillance(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    source_urls: list[str] | None = None,
    fetch_text=None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    sources = [DEFAULT_NCVBDC_DENGUE_PAGE]
    if source_urls:
        sources = [
            {
                "organization": "NCVBDC",
                "url": url,
                "page_kind": f"custom_{index + 1}",
                "topic": "custom India NCVBDC dengue surveillance page",
            }
            for index, url in enumerate(source_urls)
        ]
    result = fetch_ncvbdc_dengue_surveillance_records(
        sources,
        raw_dir=artifact_dir / "raw" / "ncvbdc_dengue_surveillance",
        fetch_text=fetch_text,
        retrieved_at=retrieved,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    refresh_failed = not result.records and bool(result.gaps)
    if not refresh_failed:
        index.replace_source_records(NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID, result.records)
    persist_source_gaps(index, NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID, result.gaps, retrieved_at=retrieved)
    preserved_existing = refresh_failed and _source_counts(index).get(NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID, 0) > 0
    return _update_metadata(artifact_dir, result, retrieved, ok=not refresh_failed, preserved_existing=preserved_existing)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest official India NCVBDC dengue cases/deaths table for Aedes aegypti public-health intelligence.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--source-url", action="append", help="Override default India NCVBDC dengue situation URL. Can be passed multiple times.")
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_ncvbdc_dengue_surveillance(
        artifact_dir=Path(args.artifact_dir),
        source_urls=args.source_url,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
