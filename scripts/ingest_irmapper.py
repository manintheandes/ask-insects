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
from askinsects.index import SourceIndex
from askinsects.sources.irmapper import DEFAULT_IRMAPPER_SPECIES, IRMAPPER_SOURCE_ID, fetch_irmapper_records


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [gap for gap in existing if not (isinstance(gap, dict) and gap.get("source") == IRMAPPER_SOURCE_ID)]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _update_metadata(artifact_dir: Path, result) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=1000)
    }
    payload = {
        "source": IRMAPPER_SOURCE_ID,
        "requested_species": result.requested_species,
        "fetched_row_count": result.fetched_row_count,
        "record_count": len(result.records),
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        doc = _read_json(path, {})
        if not isinstance(doc, dict):
            doc = {}
        sources = doc.get("sources")
        if not isinstance(sources, list):
            sources = []
        if IRMAPPER_SOURCE_ID not in sources:
            sources.append(IRMAPPER_SOURCE_ID)
        doc["sources"] = sources
        doc["source_counts"] = source_counts
        doc["record_count"] = summary["record_count"]
        doc["species_count"] = summary["species_count"]
        doc["lanes"] = summary["lanes"]
        doc["gap_count"] = gap_count
        doc["irmapper"] = payload
        write_json(path, doc)
    return {
        "ok": True,
        "source": IRMAPPER_SOURCE_ID,
        "species": result.requested_species,
        "record_count": len(result.records),
        "fetched_row_count": result.fetched_row_count,
        "gap_count": len(result.gaps),
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_irmapper(
    *,
    artifact_dir: Path,
    species: str = DEFAULT_IRMAPPER_SPECIES,
    fetch_json=None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    result = fetch_irmapper_records(
        raw_dir=artifact_dir / "raw" / "irmapper",
        species=species,
        fetch_json=fetch_json,
        retrieved_at=retrieved,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.replace_source_records(IRMAPPER_SOURCE_ID, result.records)
    return _update_metadata(artifact_dir, result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest IR Mapper Aedes aegypti resistance records into an Ask Insects artifact.")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--species", default=DEFAULT_IRMAPPER_SPECIES)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_irmapper(
        artifact_dir=Path(args.artifact_dir),
        species=args.species,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
