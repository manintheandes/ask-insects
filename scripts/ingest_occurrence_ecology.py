#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR, write_json
from askinsects.index import SourceIndex
from askinsects.sources.occurrence_ecology import (
    OCCURRENCE_ECOLOGY_SOURCE_ID,
    build_occurrence_ecology_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [gap for gap in existing if not (isinstance(gap, dict) and gap.get("source") == OCCURRENCE_ECOLOGY_SOURCE_ID)]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=2000)
    }


def _update_metadata(artifact_dir: Path, result) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    source_payload = {
        "source": OCCURRENCE_ECOLOGY_SOURCE_ID,
        "record_count": len(result.records),
        "observation_count": result.observation_count,
        "country_count": result.country_count,
        "country_month_count": result.country_month_count,
        "habitat_count": result.habitat_count,
        "input_source_counts": result.input_source_counts,
        "gap_count": len(result.gaps),
        "method": "derived country, country-month, and habitat ecology summaries from indexed Aedes aegypti GBIF, iNaturalist, and Mosquito Alert observation payloads",
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[OCCURRENCE_ECOLOGY_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if OCCURRENCE_ECOLOGY_SOURCE_ID not in sources:
                sources.append(OCCURRENCE_ECOLOGY_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload["aedes_occurrence_ecology"] = source_payload
        write_json(path, payload)
    return {
        "ok": True,
        "source": OCCURRENCE_ECOLOGY_SOURCE_ID,
        "record_count": len(result.records),
        "observation_count": result.observation_count,
        "country_count": result.country_count,
        "country_month_count": result.country_month_count,
        "habitat_count": result.habitat_count,
        "input_source_counts": result.input_source_counts,
        "gap_count": len(result.gaps),
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_occurrence_ecology(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    result = build_occurrence_ecology_records(artifact_dir, retrieved_at=retrieved_at)
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.delete_source(OCCURRENCE_ECOLOGY_SOURCE_ID)
    index.upsert_records(result.records)
    return _update_metadata(artifact_dir, result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Derive Aedes aegypti occurrence ecology records from indexed observation payloads.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_occurrence_ecology(
        artifact_dir=Path(args.artifact_dir),
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
