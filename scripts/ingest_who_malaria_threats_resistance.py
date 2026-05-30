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
from askinsects.sources.who_malaria_threats_resistance import (
    DEFAULT_SPECIES,
    WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID,
    fetch_who_malaria_threats_resistance_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [
        gap
        for gap in existing
        if not (isinstance(gap, dict) and gap.get("source") == WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID)
    ]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_count(index: SourceIndex) -> int:
    with index.connect() as conn:
        return int(
            conn.execute(
                "select count(*) as n from records where source=?",
                (WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID,),
            ).fetchone()["n"]
        )


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=2000)
    }


def _update_metadata(artifact_dir: Path, result, retrieved_at: str, *, ok: bool = True, preserved_existing: bool = False) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    installed_record_count = _source_count(index)
    source_payload = {
        "source": WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID,
        "species": result.species,
        "record_count": installed_record_count,
        "refresh_record_count": len(result.records),
        "sample_row_count": result.sample_row_count,
        "aedes_row_count": result.aedes_row_count,
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
        "retrieved_at": retrieved_at,
        "refresh_failed": not ok,
        "preserved_existing": preserved_existing,
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID not in sources:
                sources.append(WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload[WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "source": WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID,
        "species": result.species,
        "record_count": installed_record_count,
        "refresh_record_count": len(result.records),
        "sample_row_count": result.sample_row_count,
        "aedes_row_count": result.aedes_row_count,
        "gap_count": len(result.gaps),
        "preserved_existing": preserved_existing,
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_who_malaria_threats_resistance(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    species: str = DEFAULT_SPECIES,
    sample_limit: int = 5,
    aedes_limit: int = 100,
    fetch_bytes=None,
    fetch_who_malaria_threats_resistance_records_fn=fetch_who_malaria_threats_resistance_records,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    result = fetch_who_malaria_threats_resistance_records_fn(
        raw_dir=artifact_dir / "raw" / "who_malaria_threats_resistance",
        species=species,
        sample_limit=sample_limit,
        aedes_limit=aedes_limit,
        fetch_bytes=fetch_bytes,
        retrieved_at=retrieved,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    refresh_failed = not result.records and bool(result.gaps)
    if not refresh_failed:
        index.replace_source_records(WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID, result.records)
    return _update_metadata(
        artifact_dir,
        result,
        retrieved,
        ok=not refresh_failed,
        preserved_existing=refresh_failed and _source_count(index) > 0,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest WHO Malaria Threats Map resistance availability audit records.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--species", default=DEFAULT_SPECIES)
    parser.add_argument("--sample-limit", type=int, default=5)
    parser.add_argument("--aedes-limit", type=int, default=100)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_who_malaria_threats_resistance(
        artifact_dir=Path(args.artifact_dir),
        species=args.species,
        sample_limit=args.sample_limit,
        aedes_limit=args.aedes_limit,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
