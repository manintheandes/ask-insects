#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR
from askinsects.index import SourceIndex
from askinsects.server import read_json, source_counts, write_json
from askinsects.sources.drosophila_suzukii_deep_sources import (
    DROSOPHILA_SUZUKII_DEEP_SOURCE_ID,
    fetch_drosophila_suzukii_deep_records,
)


def _gap_key(gap: dict[str, object]) -> tuple[object, ...]:
    return (
        gap.get("source"),
        gap.get("lane"),
        gap.get("reason"),
        gap.get("record_id"),
        gap.get("locator"),
    )


def _dedupe_gaps(gaps: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for gap in gaps:
        key = _gap_key(gap)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(gap)
    return deduped


def _replace_source_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> list[dict[str, object]]:
    old_gaps = read_json(gaps_path, [])
    if not isinstance(old_gaps, list):
        old_gaps = []
    kept = [gap for gap in old_gaps if not (isinstance(gap, dict) and gap.get("source") == DROSOPHILA_SUZUKII_DEEP_SOURCE_ID)]
    kept.extend(_dedupe_gaps(gaps))
    return _dedupe_gaps([gap for gap in kept if isinstance(gap, dict)])


def ingest_drosophila_suzukii_deep_sources(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    ncbi_limit: int = 50,
    protein_limit: int = 100,
    proteome_limit: int = 10,
    repository_limit: int = 50,
    retrieved_at: str | None = None,
    fetch_records_fn: Callable[..., object] = fetch_drosophila_suzukii_deep_records,
) -> dict[str, object]:
    result = fetch_records_fn(
        raw_dir=artifact_dir / "raw" / "drosophila_suzukii_deep_sources",
        retrieved_at=retrieved_at,
        ncbi_limit=ncbi_limit,
        protein_limit=protein_limit,
        proteome_limit=proteome_limit,
        repository_limit=repository_limit,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    refresh_failed = not result.records and bool(result.gaps)
    if not refresh_failed:
        index.replace_source_records(DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, result.records)

    gaps = _replace_source_gaps(artifact_dir / "gaps.json", result.gaps)
    summary = index.summary()
    counts = source_counts(index)
    sources = [source for source in counts if counts[source] > 0]
    source_payload = {
        "source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID,
        "record_count": len(result.records),
        "gap_count": len(result.gaps),
        "raw_artifacts": result.raw_artifacts,
        "requested_urls": result.requested_urls,
        "lane_counts": result.source_counts,
        "boundary": "Drosophila suzukii deep source expansion",
    }

    status = read_json(artifact_dir / "source_status.json", {})
    if not isinstance(status, dict):
        status = {}
    status.update(
        {
            "ok": not refresh_failed,
            "source_id": sources[0] if sources else DROSOPHILA_SUZUKII_DEEP_SOURCE_ID,
            "sources": sources,
            "source_counts": counts,
            "boundary": "mosquitoes first, with Drosophila suzukii expansion boundary",
            "fully_parsed": True,
            "record_count": summary["record_count"],
            "species_count": summary["species_count"],
            "lanes": summary["lanes"],
            "gap_count": len(gaps),
            DROSOPHILA_SUZUKII_DEEP_SOURCE_ID: source_payload,
        }
    )

    receipt = read_json(artifact_dir / "source_receipt.json", {})
    if not isinstance(receipt, dict):
        receipt = {}
    receipt_sources = receipt.get("sources")
    if not isinstance(receipt_sources, dict):
        receipt_sources = {}
    receipt_sources[DROSOPHILA_SUZUKII_DEEP_SOURCE_ID] = source_payload
    receipt.update(
        {
            "source_id": sources[0] if sources else DROSOPHILA_SUZUKII_DEEP_SOURCE_ID,
            "sources": receipt_sources,
            "source_counts": counts,
            "artifact_dir": artifact_dir.as_posix(),
            "sqlite_index": (artifact_dir / "source_index.sqlite").as_posix(),
            "record_count": summary["record_count"],
            "lanes": summary["lanes"],
            DROSOPHILA_SUZUKII_DEEP_SOURCE_ID: source_payload,
        }
    )

    write_json(artifact_dir / "gaps.json", gaps)
    write_json(artifact_dir / "source_status.json", status)
    write_json(artifact_dir / "source_receipt.json", receipt)
    return {
        "ok": not refresh_failed,
        "source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID,
        "artifact_dir": artifact_dir.as_posix(),
        "record_count": len(result.records),
        "gap_count": len(result.gaps),
        "lane_counts": result.source_counts,
        "source_counts": counts,
        "lanes": summary["lanes"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest deep Drosophila suzukii public source records into Ask Insects.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--ncbi-limit", type=int, default=50)
    parser.add_argument("--protein-limit", type=int, default=100)
    parser.add_argument("--proteome-limit", type=int, default=10)
    parser.add_argument("--repository-limit", type=int, default=50)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_drosophila_suzukii_deep_sources(
        artifact_dir=Path(args.artifact_dir),
        ncbi_limit=args.ncbi_limit,
        protein_limit=args.protein_limit,
        proteome_limit=args.proteome_limit,
        repository_limit=args.repository_limit,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
