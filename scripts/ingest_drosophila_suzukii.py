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
from askinsects.ingest_runner import run_source_ingest
from askinsects.server import read_json, source_counts, write_json
from askinsects.sources.drosophila_suzukii import (
    DROSOPHILA_SUZUKII_SOURCE_ID,
    fetch_drosophila_suzukii_records,
)


def _replace_source_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> list[dict[str, object]]:
    old_gaps = read_json(gaps_path, [])
    if not isinstance(old_gaps, list):
        old_gaps = []
    kept = [gap for gap in old_gaps if not (isinstance(gap, dict) and gap.get("source") == DROSOPHILA_SUZUKII_SOURCE_ID)]
    kept.extend(gaps)
    return kept


def ingest_drosophila_suzukii(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    gbif_occurrence_limit: int = 100,
    inaturalist_observation_limit: int = 100,
    literature_max_works: int = 5000,
    bold_limit: int = 100,
    retrieved_at: str | None = None,
    fetch_records_fn: Callable[..., object] = fetch_drosophila_suzukii_records,
) -> dict[str, object]:
    result = fetch_records_fn(
        raw_dir=artifact_dir / "raw" / "drosophila_suzukii",
        retrieved_at=retrieved_at,
        gbif_occurrence_limit=gbif_occurrence_limit,
        inaturalist_observation_limit=inaturalist_observation_limit,
        literature_max_works=literature_max_works,
        bold_limit=bold_limit,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    outcome = run_source_ingest(
        index=index,
        artifact_dir=artifact_dir,
        source_id=DROSOPHILA_SUZUKII_SOURCE_ID,
        records=result.records,
        gaps=result.gaps,
        retrieved_at=retrieved_at or "",
        raw_artifacts=getattr(result, "raw_artifacts", None),
        persist_gap_records=True,  # gaps are plain dicts; runner persists them
    )
    refresh_failed = outcome["refresh_failed"]

    gaps = _replace_source_gaps(artifact_dir / "gaps.json", result.gaps)
    summary = index.summary()
    counts = source_counts(index)
    sources = [source for source in counts if counts[source] > 0]
    source_payload = {
        "source": DROSOPHILA_SUZUKII_SOURCE_ID,
        "record_count": len(result.records),
        "gap_count": len(result.gaps),
        "raw_artifacts": result.raw_artifacts,
        "upstream_sources": result.upstream_sources,
        "boundary": "Drosophila suzukii (spotted wing drosophila)",
    }

    status = read_json(artifact_dir / "source_status.json", {})
    if not isinstance(status, dict):
        status = {}
    status.update(
        {
            "ok": not refresh_failed,
            "source_id": sources[0] if sources else DROSOPHILA_SUZUKII_SOURCE_ID,
            "sources": sources,
            "source_counts": counts,
            "boundary": "mosquitoes first, with Drosophila suzukii expansion boundary",
            "fully_parsed": True,
            "record_count": summary["record_count"],
            "species_count": summary["species_count"],
            "lanes": summary["lanes"],
            "gap_count": len(gaps),
            DROSOPHILA_SUZUKII_SOURCE_ID: source_payload,
        }
    )

    receipt = read_json(artifact_dir / "source_receipt.json", {})
    if not isinstance(receipt, dict):
        receipt = {}
    receipt_sources = receipt.get("sources")
    if not isinstance(receipt_sources, dict):
        receipt_sources = {}
    receipt_sources[DROSOPHILA_SUZUKII_SOURCE_ID] = source_payload
    receipt.update(
        {
            "source_id": sources[0] if sources else DROSOPHILA_SUZUKII_SOURCE_ID,
            "sources": receipt_sources,
            "source_counts": counts,
            "artifact_dir": artifact_dir.as_posix(),
            "sqlite_index": (artifact_dir / "source_index.sqlite").as_posix(),
            "record_count": summary["record_count"],
            "lanes": summary["lanes"],
            DROSOPHILA_SUZUKII_SOURCE_ID: source_payload,
        }
    )

    write_json(artifact_dir / "gaps.json", gaps)
    write_json(artifact_dir / "source_status.json", status)
    write_json(artifact_dir / "source_receipt.json", receipt)
    return {
        "ok": not refresh_failed,
        "source": DROSOPHILA_SUZUKII_SOURCE_ID,
        "artifact_dir": artifact_dir.as_posix(),
        "record_count": len(result.records),
        "gap_count": len(result.gaps),
        "source_counts": counts,
        "lanes": summary["lanes"],
        "upstream_sources": result.upstream_sources,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest a bounded Drosophila suzukii source boundary into Ask Insects.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--gbif-occurrence-limit", type=int, default=100)
    parser.add_argument("--inaturalist-observation-limit", type=int, default=100)
    parser.add_argument("--literature-max-works", type=int, default=5000)
    parser.add_argument("--bold-limit", type=int, default=100)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_drosophila_suzukii(
        artifact_dir=Path(args.artifact_dir),
        gbif_occurrence_limit=args.gbif_occurrence_limit,
        inaturalist_observation_limit=args.inaturalist_observation_limit,
        literature_max_works=args.literature_max_works,
        bold_limit=args.bold_limit,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
