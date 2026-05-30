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
from askinsects.gaps import persist_source_gaps
from askinsects.index import SourceIndex
from askinsects.server import read_json, source_counts, write_json
from askinsects.sources.drosophila_suzukii_genome_files import (
    DEFAULT_ASSEMBLY_ACCESSION,
    DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID,
    fetch_drosophila_suzukii_genome_file_records,
)


def _replace_source_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> list[dict[str, object]]:
    old_gaps = read_json(gaps_path, [])
    if not isinstance(old_gaps, list):
        old_gaps = []
    kept = [gap for gap in old_gaps if not (isinstance(gap, dict) and gap.get("source") == DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID)]
    kept.extend(gaps)
    return kept


def ingest_drosophila_suzukii_genome_files(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    assembly_accession: str = DEFAULT_ASSEMBLY_ACCESSION,
    retrieved_at: str | None = None,
    max_download_bytes: int = 100_000_000,
    fetch_records_fn: Callable[..., object] = fetch_drosophila_suzukii_genome_file_records,
) -> dict[str, object]:
    result = fetch_records_fn(
        artifact_dir,
        assembly_accession=assembly_accession,
        retrieved_at=retrieved_at,
        max_download_bytes=max_download_bytes,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    refresh_failed = not result.records and bool(result.gaps)
    if not refresh_failed:
        index.replace_source_records(DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID, result.records)
    persist_source_gaps(index, DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID, result.gaps, retrieved_at=retrieved_at)
    gaps = _replace_source_gaps(artifact_dir / "gaps.json", result.gaps)
    summary = index.summary()
    counts = source_counts(index)
    source_payload = {
        "source": DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID,
        "record_count": counts.get(DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID, 0),
        "gap_count": len(result.gaps),
        "assembly_accession": result.assembly_accession,
        "raw_artifacts": result.raw_artifacts,
        "requested_urls": result.requested_urls,
        "lane_counts": result.lane_counts,
        "boundary": "Drosophila suzukii NCBI genome file parsing",
    }
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        if filename == "source_receipt.json":
            sources = payload.get("sources")
            if not isinstance(sources, dict):
                sources = {}
            sources[DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID] = source_payload
        else:
            sources = payload.get("sources")
            if not isinstance(sources, list):
                sources = []
            if DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID not in sources:
                sources.append(DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = len(gaps)
        payload[DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID] = source_payload
        write_json(path, payload)
    write_json(artifact_dir / "gaps.json", gaps)
    return {
        "ok": not refresh_failed,
        "source": DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID,
        "artifact_dir": artifact_dir.as_posix(),
        **source_payload,
        "source_counts": counts,
        "lanes": summary["lanes"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest Drosophila suzukii NCBI genome GFF/protein files into Ask Insects.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--assembly-accession", default=DEFAULT_ASSEMBLY_ACCESSION)
    parser.add_argument("--retrieved-at")
    parser.add_argument("--max-download-bytes", type=int, default=100_000_000)
    args = parser.parse_args(argv)
    result = ingest_drosophila_suzukii_genome_files(
        artifact_dir=Path(args.artifact_dir),
        assembly_accession=args.assembly_accession,
        retrieved_at=args.retrieved_at,
        max_download_bytes=args.max_download_bytes,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
