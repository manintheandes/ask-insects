#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR
from askinsects.index import SourceIndex
from askinsects.server import read_json, source_counts, write_json
from askinsects.sources.drosophila_suzukii_occurrence_ecology import (
    DROSOPHILA_SUZUKII_OCCURRENCE_ECOLOGY_SOURCE_ID,
    build_drosophila_suzukii_occurrence_ecology_records,
)


def _replace_source_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> list[dict[str, object]]:
    old_gaps = read_json(gaps_path, [])
    if not isinstance(old_gaps, list):
        old_gaps = []
    kept = [
        gap
        for gap in old_gaps
        if not (isinstance(gap, dict) and gap.get("source") == DROSOPHILA_SUZUKII_OCCURRENCE_ECOLOGY_SOURCE_ID)
    ]
    kept.extend(gaps)
    return kept


def ingest_drosophila_suzukii_occurrence_ecology(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    result = build_drosophila_suzukii_occurrence_ecology_records(artifact_dir, retrieved_at=retrieved_at)
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.replace_source_records(DROSOPHILA_SUZUKII_OCCURRENCE_ECOLOGY_SOURCE_ID, result.records)

    gaps = _replace_source_gaps(artifact_dir / "gaps.json", result.gaps)
    summary = index.summary()
    counts = source_counts(index)
    source_payload = {
        "source": DROSOPHILA_SUZUKII_OCCURRENCE_ECOLOGY_SOURCE_ID,
        "record_count": len(result.records),
        "observation_count": result.observation_count,
        "country_count": result.country_count,
        "country_month_count": result.country_month_count,
        "habitat_count": result.habitat_count,
        "input_source_counts": result.input_source_counts,
        "gap_count": len(result.gaps),
        "method": "derived country, country-month, seasonality, coordinate, and habitat summaries from indexed Drosophila suzukii GBIF and iNaturalist observation payloads",
    }

    status = read_json(artifact_dir / "source_status.json", {})
    if not isinstance(status, dict):
        status = {}
    sources = status.get("sources")
    if not isinstance(sources, list):
        sources = [source for source in counts if counts[source] > 0]
    if DROSOPHILA_SUZUKII_OCCURRENCE_ECOLOGY_SOURCE_ID not in sources:
        sources.append(DROSOPHILA_SUZUKII_OCCURRENCE_ECOLOGY_SOURCE_ID)
    status.update(
        {
            "ok": True,
            "sources": sources,
            "source_counts": counts,
            "record_count": summary["record_count"],
            "species_count": summary["species_count"],
            "lanes": summary["lanes"],
            "gap_count": len(gaps),
            DROSOPHILA_SUZUKII_OCCURRENCE_ECOLOGY_SOURCE_ID: source_payload,
        }
    )

    receipt = read_json(artifact_dir / "source_receipt.json", {})
    if not isinstance(receipt, dict):
        receipt = {}
    receipt_sources = receipt.get("sources")
    if not isinstance(receipt_sources, dict):
        receipt_sources = {}
    receipt_sources[DROSOPHILA_SUZUKII_OCCURRENCE_ECOLOGY_SOURCE_ID] = source_payload
    receipt.update(
        {
            "sources": receipt_sources,
            "source_counts": counts,
            "artifact_dir": artifact_dir.as_posix(),
            "sqlite_index": (artifact_dir / "source_index.sqlite").as_posix(),
            "record_count": summary["record_count"],
            "lanes": summary["lanes"],
            DROSOPHILA_SUZUKII_OCCURRENCE_ECOLOGY_SOURCE_ID: source_payload,
        }
    )

    write_json(artifact_dir / "gaps.json", gaps)
    write_json(artifact_dir / "source_status.json", status)
    write_json(artifact_dir / "source_receipt.json", receipt)
    return {
        "ok": True,
        "source": DROSOPHILA_SUZUKII_OCCURRENCE_ECOLOGY_SOURCE_ID,
        "artifact_dir": artifact_dir.as_posix(),
        "record_count": len(result.records),
        "observation_count": result.observation_count,
        "country_count": result.country_count,
        "country_month_count": result.country_month_count,
        "habitat_count": result.habitat_count,
        "input_source_counts": result.input_source_counts,
        "gap_count": len(result.gaps),
        "source_counts": counts,
        "lanes": summary["lanes"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Derive Drosophila suzukii occurrence ecology records from indexed observation payloads.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_drosophila_suzukii_occurrence_ecology(
        artifact_dir=Path(args.artifact_dir),
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
