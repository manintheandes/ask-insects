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
from askinsects.sources.mosquito_alert import MOSQUITO_ALERT_SOURCE_ID, fetch_mosquito_alert_records


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [gap for gap in existing if not (isinstance(gap, dict) and gap.get("source") == MOSQUITO_ALERT_SOURCE_ID)]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _update_metadata(artifact_dir: Path, result, retrieved_at: str) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=1000)
    }
    source_payload = {
        "source": MOSQUITO_ALERT_SOURCE_ID,
        "dataset_key": result.dataset_key,
        "dataset_doi": result.dataset_doi,
        "taxon_key": result.taxon_key,
        "occurrence_limit": result.occurrence_limit,
        "occurrence_page_size": result.occurrence_page_size,
        "total_results": result.total_results,
        "page_count": result.page_count,
        "record_count": len(result.records),
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
        "retrieved_at": retrieved_at,
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[MOSQUITO_ALERT_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if MOSQUITO_ALERT_SOURCE_ID not in sources:
                sources.append(MOSQUITO_ALERT_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload["mosquito_alert"] = source_payload
        write_json(path, payload)
    return {
        "ok": True,
        "source": MOSQUITO_ALERT_SOURCE_ID,
        "record_count": len(result.records),
        "total_results": result.total_results,
        "gap_count": len(result.gaps),
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_mosquito_alert_observations(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    occurrence_limit: int = 1000,
    occurrence_page_size: int = 300,
    fetch_json=None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    result = fetch_mosquito_alert_records(
        raw_dir=artifact_dir / "raw" / "mosquito_alert",
        occurrence_limit=occurrence_limit,
        occurrence_page_size=occurrence_page_size,
        fetch_json=fetch_json,
        retrieved_at=retrieved,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.replace_source_records(MOSQUITO_ALERT_SOURCE_ID, result.records)
    return _update_metadata(artifact_dir, result, retrieved)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest Mosquito Alert Aedes aegypti observations and images into Ask Insects.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--occurrence-limit", type=int, default=1000)
    parser.add_argument("--occurrence-page-size", type=int, default=300)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_mosquito_alert_observations(
        artifact_dir=Path(args.artifact_dir),
        occurrence_limit=args.occurrence_limit,
        occurrence_page_size=args.occurrence_page_size,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
