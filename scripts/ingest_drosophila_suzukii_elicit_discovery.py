#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.index import SourceIndex
from askinsects.sources.elicit_discovery import (
    SPECIES_CONFIG,
    default_existing_doi_lookup,
    default_fetch_json,
    fetch_elicit_discovery_records,
    utc_now,
)

SPECIES = "drosophila_suzukii"
SOURCE_ID = str(SPECIES_CONFIG[SPECIES]["source_id"])
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "mosquito-v1"


def _read_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def ingest(*, artifact_dir: Path = DEFAULT_ARTIFACT_DIR, fetch_json=None,
           existing_doi_lookup=None, retrieved_at: str | None = None,
           max_results: int = 50, min_year: int = 2020) -> dict:
    retrieved = retrieved_at or utc_now()
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    result = fetch_elicit_discovery_records(
        species=SPECIES,
        raw_dir=artifact_dir / "raw" / SOURCE_ID,
        retrieved_at=retrieved,
        max_results=max_results, min_year=min_year,
        fetch_json=fetch_json or default_fetch_json,
        existing_doi_lookup=existing_doi_lookup or default_existing_doi_lookup,
    )
    refresh_failed = (not result.records) and bool(result.gaps)
    if not refresh_failed:
        index.replace_source_records(SOURCE_ID, result.records)
    source_payload = {
        "source": SOURCE_ID,
        "boundary": f"Elicit semantic-search discovery of {SPECIES_CONFIG[SPECIES]['species']} candidate papers not already in the hosted corpus.",
        "requested_queries": result.requested_queries,
        "returned_count": result.returned_count,
        "new_count": result.new_count,
        "dedup_dropped": result.dedup_dropped,
        "gap_reasons": sorted({str(g.get("reason")) for g in result.gaps if g.get("reason")}),
        "gap_count": len(result.gaps),
        "raw_artifacts": result.raw_artifacts,
        "retrieved_at": retrieved,
        "refresh_failed": refresh_failed,
    }
    gaps_path = artifact_dir / "gaps.json"
    existing_gaps = [g for g in _read_json(gaps_path, []) if not (isinstance(g, dict) and g.get("source") == SOURCE_ID)]
    existing_gaps.extend(result.gaps)
    _write_json(gaps_path, existing_gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        payload[SOURCE_ID] = source_payload
        _write_json(path, payload)
    return {"ok": not refresh_failed, "source": SOURCE_ID, "new_count": result.new_count,
            "returned_count": result.returned_count, "dedup_dropped": result.dedup_dropped,
            "gap_count": len(result.gaps), "refresh_failed": refresh_failed,
            "artifact_dir": artifact_dir.as_posix()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=f"Ingest {SOURCE_ID} into Ask Insects.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--max-results", type=int, default=50)
    parser.add_argument("--min-year", type=int, default=2020)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest(artifact_dir=Path(args.artifact_dir), max_results=args.max_results,
                    min_year=args.min_year, retrieved_at=args.retrieved_at)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
