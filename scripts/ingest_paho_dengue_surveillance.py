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
from askinsects.sources.paho_surveillance import (
    DEFAULT_PAHO_CORE_INDICATOR_PAGES,
    DEFAULT_PAHO_DENGUE_DASHBOARD_PAGES,
    DEFAULT_PAHO_DENGUE_REPORTS,
    PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
    fetch_paho_dengue_surveillance_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [gap for gap in existing if not (isinstance(gap, dict) and gap.get("source") == PAHO_DENGUE_SURVEILLANCE_SOURCE_ID)]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=2000)
    }


def _source_count(index: SourceIndex) -> int:
    with index.connect() as conn:
        return int(
            conn.execute(
                "select count(*) as n from records where source=?",
                (PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,),
            ).fetchone()["n"]
        )


def _update_metadata(artifact_dir: Path, result, retrieved_at: str, *, ok: bool = True, preserved_existing: bool = False) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    source_payload = {
        "source": PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
        "requested_urls": result.requested_urls,
        "record_count": len(result.records),
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
        "report_count": result.report_count,
        "dashboard_page_count": result.dashboard_page_count,
        "core_indicator_page_count": result.core_indicator_page_count,
        "core_indicator_download_count": result.core_indicator_download_count,
        "core_indicator_row_count": result.core_indicator_row_count,
        "retrieved_at": retrieved_at,
        "refresh_failed": not ok,
        "preserved_existing": preserved_existing,
        "method": "official PAHO dengue situation report HTML plus PAHO/EIH Open Data Core Indicators ZIP/CSV dengue rows parsed into Aedes aegypti-relevant public-health surveillance records; weekly dashboard cells remain a source gap until stable weekly CSV or JSON access is proven",
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[PAHO_DENGUE_SURVEILLANCE_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if PAHO_DENGUE_SURVEILLANCE_SOURCE_ID not in sources:
                sources.append(PAHO_DENGUE_SURVEILLANCE_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload["fully_parsed"] = gap_count == 0
        payload["parsed_scope"] = "PAHO dengue report/page grain plus annual Core Indicators ZIP/CSV rows; weekly dashboard row-level data is complete only when no source gaps are present"
        payload["aedes_paho_dengue_surveillance"] = source_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "source": PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
        "record_count": len(result.records),
        "preserved_existing": preserved_existing,
        "gap_count": len(result.gaps),
        "report_count": result.report_count,
        "dashboard_page_count": result.dashboard_page_count,
        "core_indicator_page_count": result.core_indicator_page_count,
        "core_indicator_download_count": result.core_indicator_download_count,
        "core_indicator_row_count": result.core_indicator_row_count,
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_paho_dengue_surveillance(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    report_urls: list[str] | None = None,
    dashboard_pages: list[str] | None = None,
    core_indicator_pages: list[str] | None = None,
    fetch_text=None,
    fetch_bytes=None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    reports = list(DEFAULT_PAHO_DENGUE_REPORTS)
    if report_urls:
        reports = [{"url": url, "landing_url": url, "organization": "PAHO/WHO", "topic": "custom PAHO dengue surveillance report"} for url in report_urls]
    dashboard_urls = list(DEFAULT_PAHO_DENGUE_DASHBOARD_PAGES) if dashboard_pages is None else dashboard_pages
    core_pages = list(DEFAULT_PAHO_CORE_INDICATOR_PAGES) if core_indicator_pages is None else core_indicator_pages
    result = fetch_paho_dengue_surveillance_records(
        reports,
        raw_dir=artifact_dir / "raw" / "paho_dengue_surveillance",
        fetch_text=fetch_text,
        fetch_bytes=fetch_bytes,
        retrieved_at=retrieved,
        dashboard_pages=dashboard_urls,
        core_indicator_pages=core_pages,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    refresh_failed = not result.records and bool(result.gaps)
    if not refresh_failed:
        index.replace_source_records(PAHO_DENGUE_SURVEILLANCE_SOURCE_ID, result.records)
    persist_source_gaps(index, PAHO_DENGUE_SURVEILLANCE_SOURCE_ID, result.gaps, retrieved_at=retrieved)
    return _update_metadata(
        artifact_dir,
        result,
        retrieved,
        ok=not refresh_failed,
        preserved_existing=refresh_failed and _source_count(index) > 0,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest official PAHO dengue surveillance evidence for Aedes aegypti public-health intelligence.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--report-url", action="append", help="Override default PAHO dengue situation report URL. Can be passed multiple times.")
    parser.add_argument("--dashboard-page", action="append", help="Override default PAHO dengue dashboard landing page URLs. Can be passed multiple times.")
    parser.add_argument("--core-indicator-page", action="append", help="Override default PAHO Core Indicators download page URL. Can be passed multiple times.")
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_paho_dengue_surveillance(
        artifact_dir=Path(args.artifact_dir),
        report_urls=args.report_url,
        dashboard_pages=args.dashboard_page,
        core_indicator_pages=args.core_indicator_page,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
