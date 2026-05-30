#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import utc_now, write_json
from askinsects.gaps import persist_source_gaps
from askinsects.index import SourceIndex
from askinsects.sources.bold_barcodes import BOLD_SOURCE_ID, DEFAULT_BOLD_SPECIES, fetch_bold_barcode_records


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [gap for gap in existing if not (isinstance(gap, dict) and gap.get("source") == BOLD_SOURCE_ID)]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _update_metadata(artifact_dir: Path, result, *, ok: bool = True) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=1000)
    }
    bold_payload = {
        "source": BOLD_SOURCE_ID,
        "species": result.species,
        "record_count": len(result.records),
        "requested_limit": result.requested_limit,
        "fetched_row_count": result.fetched_row_count,
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if not isinstance(sources, list):
            sources = []
        if BOLD_SOURCE_ID not in sources:
            sources.append(BOLD_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload["bold_barcodes"] = bold_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "source": BOLD_SOURCE_ID,
        "record_count": len(result.records),
        "fetched_row_count": result.fetched_row_count,
        "gap_count": len(result.gaps),
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_bold_barcodes(
    *,
    artifact_dir: Path,
    species: str = DEFAULT_BOLD_SPECIES,
    limit: int = 500,
    tsv_path: Path | None = None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    fetch_text = None
    if tsv_path:
        fetch_text = lambda url: tsv_path.read_text(encoding="utf-8")
    result = fetch_bold_barcode_records(
        species=species,
        raw_dir=artifact_dir / "raw" / "bold",
        limit=limit,
        fetch_text=fetch_text,
        retrieved_at=retrieved,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    refresh_failed = not result.records and bool(result.gaps)
    if not refresh_failed:
        index.replace_source_records(BOLD_SOURCE_ID, result.records)
    persist_source_gaps(index, BOLD_SOURCE_ID, result.gaps, retrieved_at=retrieved)
    return _update_metadata(artifact_dir, result, ok=not refresh_failed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest public BOLD barcode records into an existing Ask Insects artifact.")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--species", default=DEFAULT_BOLD_SPECIES)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--tsv-path", help="Use a saved BOLD combined TSV instead of fetching the public API.")
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_bold_barcodes(
        artifact_dir=Path(args.artifact_dir),
        species=args.species,
        limit=args.limit,
        tsv_path=Path(args.tsv_path) if args.tsv_path else None,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
