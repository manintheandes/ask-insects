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
from askinsects.gaps import persist_source_gaps
from askinsects.index import SourceIndex
from askinsects.sources.vectornet_surveillance import (
    DEFAULT_VECTORNET_SPECIES,
    VECTORNET_SOURCE_ID,
    fetch_vectornet_surveillance_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [gap for gap in existing if not (isinstance(gap, dict) and gap.get("source") == VECTORNET_SOURCE_ID)]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_count(index: SourceIndex) -> int:
    with index.connect() as conn:
        return int(
            conn.execute(
                "select count(*) as n from records where source=?",
                (VECTORNET_SOURCE_ID,),
            ).fetchone()["n"]
        )


def _update_metadata(artifact_dir: Path, result, retrieved_at: str, *, ok: bool = True, preserved_existing: bool = False) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=1000)
    }
    installed_record_count = _source_count(index)
    source_payload = {
        "source": VECTORNET_SOURCE_ID,
        "dataset_key": result.dataset_key,
        "dataset_title": result.dataset_title,
        "species": result.species,
        "archive_url": result.archive_url,
        "resource_url": result.resource_url,
        "license": result.license,
        "pub_date": result.pub_date,
        "row_count": result.row_count,
        "matched_row_count": result.matched_row_count,
        "observation_record_count": result.observation_record_count,
        "ecology_record_count": result.ecology_record_count,
        "record_count": installed_record_count,
        "refresh_record_count": len(result.records),
        "raw_artifacts": result.raw_artifacts,
        "filtered_rows_path": result.filtered_rows_path,
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
            sources[VECTORNET_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if VECTORNET_SOURCE_ID not in sources:
                sources.append(VECTORNET_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload["vectornet_surveillance"] = source_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "source": VECTORNET_SOURCE_ID,
        "record_count": installed_record_count,
        "refresh_record_count": len(result.records),
        "matched_row_count": result.matched_row_count,
        "observation_record_count": result.observation_record_count,
        "ecology_record_count": result.ecology_record_count,
        "gap_count": len(result.gaps),
        "preserved_existing": preserved_existing,
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_vectornet_surveillance(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    species: str = DEFAULT_VECTORNET_SPECIES,
    archive_url: str | None = None,
    max_records: int | None = None,
    fetch_bytes=None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    kwargs: dict[str, object] = {
        "raw_dir": artifact_dir / "raw" / "vectornet_surveillance",
        "species": species,
        "max_records": max_records,
        "fetch_bytes": fetch_bytes,
        "retrieved_at": retrieved,
    }
    if archive_url:
        kwargs["archive_url"] = archive_url
    result = fetch_vectornet_surveillance_records(**kwargs)
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    refresh_failed = not result.records and bool(result.gaps)
    if not refresh_failed:
        index.replace_source_records(VECTORNET_SOURCE_ID, result.records)
    persist_source_gaps(index, VECTORNET_SOURCE_ID, result.gaps, retrieved_at=retrieved)
    return _update_metadata(
        artifact_dir,
        result,
        retrieved,
        ok=not refresh_failed,
        preserved_existing=refresh_failed and _source_count(index) > 0,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest VectorNet ECDC/EFSA Aedes aegypti surveillance rows into Ask Insects.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--species", default=DEFAULT_VECTORNET_SPECIES)
    parser.add_argument("--archive-url")
    parser.add_argument("--max-records", type=int)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_vectornet_surveillance(
        artifact_dir=Path(args.artifact_dir),
        species=args.species,
        archive_url=args.archive_url,
        max_records=args.max_records,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
