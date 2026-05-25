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
from askinsects.sources.aedes_deep_sources import AEDES_DEEP_SOURCE_IDS, fetch_aedes_deep_source_records


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    source_ids = set(AEDES_DEEP_SOURCE_IDS)
    combined = [gap for gap in existing if not (isinstance(gap, dict) and gap.get("source") in source_ids)]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=3000)
    }


def _update_metadata(artifact_dir: Path, result, retrieved_at: str) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    source_payload = {
        "sources": list(result.source_ids),
        "requested_urls": result.requested_urls,
        "record_count": len(result.records),
        "source_record_counts": result.source_record_counts,
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
        "retrieved_at": retrieved_at,
        "method": "bounded five-lane Aedes ingest for taxonomy authorities, WorldClim climate source metadata, global occurrence compendium rows, NCBI population-genomics BioProjects, and WHO Aedes insecticide-resistance guidance",
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            for source_id in result.source_ids:
                sources[source_id] = {**source_payload, "source": source_id, "record_count": result.source_record_counts.get(source_id, 0)}
        else:
            if not isinstance(sources, list):
                sources = []
            for source_id in result.source_ids:
                if source_id not in sources:
                    sources.append(source_id)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload["aedes_deep_sources"] = source_payload
        for source_id in result.source_ids:
            payload[source_id] = {**source_payload, "source": source_id, "record_count": result.source_record_counts.get(source_id, 0)}
        write_json(path, payload)
    return {
        "ok": True,
        "sources": list(result.source_ids),
        "record_count": len(result.records),
        "source_record_counts": result.source_record_counts,
        "gap_count": len(result.gaps),
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_aedes_deep_sources(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    retrieved_at: str | None = None,
    compendium_row_limit: int = 5000,
    bioproject_limit: int = 20,
    fetch_records=fetch_aedes_deep_source_records,
    fetch_text=None,
    fetch_json=None,
    fetch_bytes=None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    result = fetch_records(
        raw_dir=artifact_dir / "raw" / "aedes_deep_sources",
        fetch_text=fetch_text,
        fetch_json=fetch_json,
        fetch_bytes=fetch_bytes,
        retrieved_at=retrieved,
        compendium_row_limit=compendium_row_limit,
        bioproject_limit=bioproject_limit,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    for source_id in result.source_ids:
        records = [record for record in result.records if record.source == source_id]
        index.replace_source_records(source_id, records)
    return _update_metadata(artifact_dir, result, retrieved)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest five deep Aedes aegypti source expansions into Ask Insects.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    parser.add_argument("--compendium-row-limit", type=int, default=5000)
    parser.add_argument("--bioproject-limit", type=int, default=20)
    args = parser.parse_args(argv)
    result = ingest_aedes_deep_sources(
        artifact_dir=Path(args.artifact_dir),
        retrieved_at=args.retrieved_at,
        compendium_row_limit=args.compendium_row_limit,
        bioproject_limit=args.bioproject_limit,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
