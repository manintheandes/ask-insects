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
from askinsects.sources.who_dengue_surveillance import (
    DEFAULT_WHO_DENGUE_SURVEILLANCE_PAGES,
    WHO_DENGUE_SURVEILLANCE_SOURCE_ID,
    fetch_who_dengue_surveillance_records,
    who_dengue_source_spec,
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
        if not (isinstance(gap, dict) and gap.get("source") == WHO_DENGUE_SURVEILLANCE_SOURCE_ID)
    ]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=2000)
    }


def _update_metadata(artifact_dir: Path, result, retrieved_at: str) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    source_payload = {
        "source": WHO_DENGUE_SURVEILLANCE_SOURCE_ID,
        "requested_urls": result.requested_urls,
        "record_count": len(result.records),
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
        "page_count": result.page_count,
        "situation_report_count": result.situation_report_count,
        "archive_count": result.archive_count,
        "publication_count": result.publication_count,
        "dashboard_locator_count": result.dashboard_locator_count,
        "export_locator_count": result.export_locator_count,
        "retrieved_at": retrieved_at,
        "method": "official WHO dengue surveillance pages, WER global update page, WPRO situation-update links, and WPRO Health Data Platform dashboard locators parsed into Aedes aegypti-relevant public-health records; dashboard row extraction remains a structured source gap unless stable direct exports are exposed",
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[WHO_DENGUE_SURVEILLANCE_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if WHO_DENGUE_SURVEILLANCE_SOURCE_ID not in sources:
                sources.append(WHO_DENGUE_SURVEILLANCE_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload["fully_parsed"] = gap_count == 0
        payload["parsed_scope"] = "WHO page/report/dashboard-locator grain; dashboard row-level data is complete only when no WHO source gaps are present"
        payload[WHO_DENGUE_SURVEILLANCE_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {
        "ok": True,
        "source": WHO_DENGUE_SURVEILLANCE_SOURCE_ID,
        "record_count": len(result.records),
        "gap_count": len(result.gaps),
        "page_count": result.page_count,
        "situation_report_count": result.situation_report_count,
        "archive_count": result.archive_count,
        "publication_count": result.publication_count,
        "dashboard_locator_count": result.dashboard_locator_count,
        "export_locator_count": result.export_locator_count,
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_who_dengue_surveillance(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    source_urls: list[str] | None = None,
    fetch_text=None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    sources = list(DEFAULT_WHO_DENGUE_SURVEILLANCE_PAGES)
    if source_urls:
        sources = [who_dengue_source_spec(url, index=index + 1) for index, url in enumerate(source_urls)]
    result = fetch_who_dengue_surveillance_records(
        sources,
        raw_dir=artifact_dir / "raw" / "who_dengue_surveillance",
        fetch_text=fetch_text,
        retrieved_at=retrieved,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.replace_source_records(WHO_DENGUE_SURVEILLANCE_SOURCE_ID, result.records)
    return _update_metadata(artifact_dir, result, retrieved)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest official WHO dengue surveillance evidence for Aedes aegypti public-health intelligence.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--source-url", action="append", help="Override default WHO dengue surveillance URLs. Can be passed multiple times.")
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_who_dengue_surveillance(
        artifact_dir=Path(args.artifact_dir),
        source_urls=args.source_url,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
