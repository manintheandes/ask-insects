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
from askinsects.ingest_runner import run_source_ingest
from askinsects.sources.cdc_dengue_surveillance import (
    CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
    DEFAULT_CDC_DENGUE_PAGES,
    fetch_cdc_dengue_surveillance_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [gap for gap in existing if not (isinstance(gap, dict) and gap.get("source") == CDC_DENGUE_SURVEILLANCE_SOURCE_ID)]
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
        "source": CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
        "requested_urls": result.requested_urls,
        "record_count": len(result.records),
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
        "page_count": result.page_count,
        "config_count": result.config_count,
        "dataset_count": result.dataset_count,
        "dataset_row_count": result.dataset_row_count,
        "limitation_count": result.limitation_count,
        "retrieved_at": retrieved_at,
        "refresh_failed": not ok,
        "preserved_existing": preserved_existing,
        "method": "official CDC dengue current/historic ArboNET HTML pages, CDC WCMS visualization JSON configs, and linked CDC CSV datasets parsed into Aedes aegypti-relevant public-health surveillance records",
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[CDC_DENGUE_SURVEILLANCE_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if CDC_DENGUE_SURVEILLANCE_SOURCE_ID not in sources:
                sources.append(CDC_DENGUE_SURVEILLANCE_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload["fully_parsed"] = gap_count == 0
        payload["parsed_scope"] = "CDC dengue current and historic pages, visualization configs, linked CSV datasets, and ArboNET limitations"
        payload[CDC_DENGUE_SURVEILLANCE_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "source": CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
        "record_count": len(result.records),
        "preserved_existing": preserved_existing,
        "gap_count": len(result.gaps),
        "page_count": result.page_count,
        "config_count": result.config_count,
        "dataset_count": result.dataset_count,
        "dataset_row_count": result.dataset_row_count,
        "limitation_count": result.limitation_count,
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_cdc_dengue_surveillance(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    source_urls: list[str] | None = None,
    fetch_text=None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    sources = list(DEFAULT_CDC_DENGUE_PAGES)
    if source_urls:
        sources = [
            {
                "organization": "CDC",
                "url": url,
                "page_kind": f"custom_{index + 1}",
                "topic": "custom CDC dengue surveillance page",
            }
            for index, url in enumerate(source_urls)
        ]
    result = fetch_cdc_dengue_surveillance_records(
        sources,
        raw_dir=artifact_dir / "raw" / "cdc_dengue_surveillance",
        fetch_text=fetch_text,
        retrieved_at=retrieved,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    outcome = run_source_ingest(
        index=index,
        artifact_dir=artifact_dir,
        source_id=CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
        records=result.records,
        gaps=result.gaps,
        retrieved_at=retrieved,
        raw_artifacts=getattr(result, "raw_artifacts", None),
        persist_gap_records=True,
    )
    refresh_failed = outcome["refresh_failed"]
    preserved_existing = outcome["preserved_existing"]
    return _update_metadata(artifact_dir, result, retrieved, ok=not refresh_failed, preserved_existing=preserved_existing)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest official CDC dengue ArboNET surveillance pages and CSV datasets for Aedes aegypti public-health intelligence.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--source-url", action="append", help="Override default CDC dengue surveillance page URL. Can be passed multiple times.")
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_cdc_dengue_surveillance(
        artifact_dir=Path(args.artifact_dir),
        source_urls=args.source_url,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
