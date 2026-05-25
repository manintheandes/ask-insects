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
from askinsects.sources.mosquito_repellent_external_discovery import (
    MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID,
    fetch_mosquito_repellent_external_discovery_records,
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
        if not (isinstance(gap, dict) and gap.get("source") == MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID)
    ]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_record_count(index: SourceIndex) -> int:
    with index.connect() as conn:
        return int(
            conn.execute(
                "select count(*) as n from records where source=?",
                (MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID,),
            ).fetchone()["n"]
        )


def _update_metadata(artifact_dir: Path, result, retrieved_at: str, *, ok: bool = True, preserved_existing: bool = False) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    installed_record_count = _source_record_count(index)
    source_counts = {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=5000)
    }
    source_payload = {
        "source": MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID,
        "boundary": "Bounded external metadata discovery for mosquito repellent research since 2020 across OpenAlex, Europe PMC and AGRICOLA, Semantic Scholar, Crossref posted-content preprints, DataCite datasets, Zenodo, Figshare, and explicit patent/CABI/Google Scholar access gaps.",
        "requested_urls": result.requested_urls,
        "record_count": installed_record_count,
        "refresh_record_count": len(result.records),
        "candidate_count": result.candidate_count,
        "source_counts": result.source_counts,
        "lane_counts": result.lane_counts,
        "gap_reasons": sorted({str(gap.get("reason")) for gap in result.gaps if gap.get("reason")}),
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
            sources[MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID not in sources:
                sources.append(MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload[MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "source": MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID,
        "record_count": installed_record_count,
        "refresh_record_count": len(result.records),
        "candidate_count": result.candidate_count,
        "source_counts": result.source_counts,
        "lane_counts": result.lane_counts,
        "gap_count": len(result.gaps),
        "preserved_existing": preserved_existing,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_mosquito_repellent_external_discovery(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    fetch_json=None,
    retrieved_at: str | None = None,
    max_results_per_source: int = 50,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    result = fetch_mosquito_repellent_external_discovery_records(
        raw_dir=artifact_dir / "raw" / "mosquito_repellent_external_discovery",
        fetch_json=fetch_json,
        retrieved_at=retrieved,
        max_results_per_source=max_results_per_source,
    )
    real_records = [record for record in result.records if not (record.payload and record.payload.get("artifact_type") == "source_gap")]
    refresh_failed = (not real_records) and bool(result.gaps)
    if not refresh_failed:
        index.replace_source_records(MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID, result.records)
    return _update_metadata(
        artifact_dir,
        result,
        retrieved,
        ok=not refresh_failed,
        preserved_existing=refresh_failed and _source_record_count(index) > 0,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest external mosquito repellent discovery metadata into Ask Insects.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--max-results-per-source", type=int, default=50)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_mosquito_repellent_external_discovery(
        artifact_dir=Path(args.artifact_dir),
        max_results_per_source=args.max_results_per_source,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
