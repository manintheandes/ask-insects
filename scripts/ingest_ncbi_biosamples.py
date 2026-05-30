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
from askinsects.sources.ncbi_biosample import (
    DEFAULT_BIOSAMPLE_SPECIES,
    NCBI_BIOSAMPLE_SOURCE_ID,
    fetch_ncbi_biosample_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [gap for gap in existing if not (isinstance(gap, dict) and gap.get("source") == NCBI_BIOSAMPLE_SOURCE_ID)]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=1000)
    }


def _update_metadata(artifact_dir: Path, result, retrieved_at: str, *, ok: bool = True, preserved_existing: bool = False) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    source_payload = {
        "source": NCBI_BIOSAMPLE_SOURCE_ID,
        "refresh_failed": not ok,
        "preserved_existing": preserved_existing,
        "species": result.species,
        "reported_total_count": result.total_count,
        "requested_limit": result.requested_limit,
        "fetched_count": result.fetched_count,
        "record_count": len(result.records),
        "page_count": result.page_count,
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
            sources[NCBI_BIOSAMPLE_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if NCBI_BIOSAMPLE_SOURCE_ID not in sources:
                sources.append(NCBI_BIOSAMPLE_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload["ncbi_biosamples"] = source_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "preserved_existing": preserved_existing,
        "source": NCBI_BIOSAMPLE_SOURCE_ID,
        "species": result.species,
        "record_count": len(result.records),
        "reported_total_count": result.total_count,
        "requested_limit": result.requested_limit,
        "fetched_count": result.fetched_count,
        "gap_count": len(result.gaps),
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_ncbi_biosamples(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    species: str = DEFAULT_BIOSAMPLE_SPECIES,
    limit: int = 1000,
    page_size: int = 200,
    delay_seconds: float = 0.34,
    fetch_json=None,
    fetch_ncbi_biosample_records_fn=fetch_ncbi_biosample_records,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    result = fetch_ncbi_biosample_records_fn(
        species=species,
        raw_dir=artifact_dir / "raw" / "ncbi_biosamples",
        limit=limit,
        page_size=page_size,
        delay_seconds=delay_seconds,
        fetch_json=fetch_json,
        retrieved_at=retrieved,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    refresh_failed = not result.records and bool(result.gaps)
    if not refresh_failed:
        index.replace_source_records(NCBI_BIOSAMPLE_SOURCE_ID, result.records)
    persist_source_gaps(index, NCBI_BIOSAMPLE_SOURCE_ID, result.gaps, retrieved_at=retrieved)
    preserved_existing = refresh_failed and _source_counts(index).get(NCBI_BIOSAMPLE_SOURCE_ID, 0) > 0
    return _update_metadata(artifact_dir, result, retrieved, ok=not refresh_failed, preserved_existing=preserved_existing)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest NCBI BioSample metadata for Aedes aegypti source records.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--species", default=DEFAULT_BIOSAMPLE_SPECIES)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--delay-seconds", type=float, default=0.34)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_ncbi_biosamples(
        artifact_dir=Path(args.artifact_dir),
        species=args.species,
        limit=args.limit,
        page_size=args.page_size,
        delay_seconds=args.delay_seconds,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
