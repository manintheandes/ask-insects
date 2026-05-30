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
from askinsects.ingest_runner import run_source_ingest
from askinsects.server import read_json, source_counts, write_json
from askinsects.sources.inaturalist import DEFAULT_INATURALIST_SPECIES, INATURALIST_SOURCE_ID, fetch_inaturalist_records
from askinsects.sources.gbif import utc_now


def ingest_inaturalist_observations(
    *,
    artifact_dir: Path,
    species: list[str],
    place: str | None = None,
    observation_limit: int = 1000,
    page_size: int = 200,
    delay_seconds: float = 0.0,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    result = fetch_inaturalist_records(
        species or list(DEFAULT_INATURALIST_SPECIES),
        raw_dir=artifact_dir / "raw" / "inaturalist",
        place=place,
        observation_limit=observation_limit,
        page_size=page_size,
        delay_seconds=delay_seconds,
        retrieved_at=retrieved,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    outcome = run_source_ingest(
        index=index,
        artifact_dir=artifact_dir,
        source_id=INATURALIST_SOURCE_ID,
        records=result.records,
        gaps=result.gaps,
        retrieved_at=retrieved,
        raw_artifacts=getattr(result, "raw_artifacts", None),
        persist_gap_records=True,
    )
    refresh_failed = outcome["refresh_failed"]
    preserved_existing = outcome["preserved_existing"]

    old_gaps = read_json(artifact_dir / "gaps.json", [])
    if not isinstance(old_gaps, list):
        old_gaps = []
    gaps = [gap for gap in old_gaps if not (isinstance(gap, dict) and gap.get("source") == INATURALIST_SOURCE_ID)]
    gaps.extend(result.gaps)
    summary = index.summary()
    counts = source_counts(index)
    sources = [source for source in counts if source != INATURALIST_SOURCE_ID]
    if counts.get(INATURALIST_SOURCE_ID):
        sources.append(INATURALIST_SOURCE_ID)

    inaturalist_payload = {
        "requested_species": result.requested_species,
        "place": result.place,
        "observation_limit": result.observation_limit,
        "page_size": result.page_size,
        "delay_seconds": result.delay_seconds,
        "total_results": result.total_results,
        "raw_artifacts": result.raw_artifacts,
        "record_count": len(result.records),
        "gap_count": len(result.gaps),
        "retrieved_at": retrieved,
        "refresh_failed": refresh_failed,
        "preserved_existing": preserved_existing,
    }

    status = read_json(artifact_dir / "source_status.json", {})
    if not isinstance(status, dict):
        status = {}
    status.update(
        {
            "ok": not refresh_failed,
            "source_id": sources[0] if sources else INATURALIST_SOURCE_ID,
            "sources": sources,
            "source_counts": counts,
            "boundary": "mosquitoes first",
            "generated_at": retrieved,
            "fully_parsed": True,
            "record_count": summary["record_count"],
            "species_count": summary["species_count"],
            "lanes": summary["lanes"],
            "gap_count": len(gaps),
        }
    )
    receipt = read_json(artifact_dir / "source_receipt.json", {})
    if not isinstance(receipt, dict):
        receipt = {}
    receipt_sources = receipt.get("sources")
    if not isinstance(receipt_sources, dict):
        receipt_sources = {}
    receipt_sources[INATURALIST_SOURCE_ID] = inaturalist_payload
    receipt.update(
        {
            "source_id": sources[0] if sources else INATURALIST_SOURCE_ID,
            "sources": receipt_sources,
            "artifact_dir": artifact_dir.as_posix(),
            "sqlite_index": (artifact_dir / "source_index.sqlite").as_posix(),
            "generated_at": retrieved,
            "record_count": summary["record_count"],
            "lanes": summary["lanes"],
            "inaturalist": inaturalist_payload,
        }
    )

    write_json(artifact_dir / "gaps.json", gaps)
    write_json(artifact_dir / "source_status.json", status)
    write_json(artifact_dir / "source_receipt.json", receipt)
    return {"ok": not refresh_failed, "artifact_dir": artifact_dir.as_posix(), **status, "inaturalist": inaturalist_payload}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Incrementally ingest iNaturalist licensed observation/photo records.")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--species", action="append", default=[])
    parser.add_argument("--place")
    parser.add_argument("--observation-limit", type=int, default=1000)
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_inaturalist_observations(
        artifact_dir=Path(args.artifact_dir),
        species=args.species or list(DEFAULT_INATURALIST_SPECIES),
        place=args.place,
        observation_limit=args.observation_limit,
        page_size=args.page_size,
        delay_seconds=args.delay_seconds,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
