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
from askinsects.sources.drosophila_suzukii_dryad_landscape_monitoring import (
    DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID,
    fetch_drosophila_suzukii_dryad_landscape_monitoring_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=5000)
    }


def _replace_source_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    old_gaps = _read_json(gaps_path, [])
    if not isinstance(old_gaps, list):
        old_gaps = []
    kept = [
        gap
        for gap in old_gaps
        if not (isinstance(gap, dict) and gap.get("source") == DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID)
    ]
    kept.extend(gaps)
    write_json(gaps_path, kept)
    return len(kept)


def _atom_counts(index: SourceIndex) -> dict[str, int]:
    rows = index.sql(
        """
        select json_extract(payload_json, '$.atom_type') as atom_type, count(*) as n
        from record_payloads
        where source='drosophila_suzukii_dryad_landscape_monitoring'
        group by atom_type
        """,
        limit=100,
    )
    return {str(row["atom_type"]): int(row["n"]) for row in rows if row["atom_type"]}


def ingest_drosophila_suzukii_dryad_landscape_monitoring(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    fetch_json=None,
    fetch_text=None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    result = fetch_drosophila_suzukii_dryad_landscape_monitoring_records(
        raw_dir=artifact_dir / "raw" / DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID,
        fetch_json=fetch_json,
        fetch_text=fetch_text,
        retrieved_at=retrieved,
    )
    # Persist whenever the fetch produced any records (dataset/file manifests or
    # honest gap records), so a blocked preview is still queryable in the index.
    # Only a total fetch failure (no records at all) preserves prior data instead.
    # Mirrors the jki/umn sibling lanes; row_count alone dropped gap records.
    refresh_failed = not result.records and bool(result.gaps)
    if not refresh_failed:
        index.replace_source_records(DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID, result.records)
    with index.connect() as conn:
        preserved_existing = bool(
            conn.execute(
                "select 1 from records where source=? limit 1",
                (DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID,),
            ).fetchone()
        )
    summary = index.summary()
    counts = _source_counts(index)
    atoms = _atom_counts(index)
    gap_count = _replace_source_gaps(artifact_dir / "gaps.json", result.gaps)
    installed_record_count = int(counts.get(DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID, 0))
    source_payload = {
        "source": DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID,
        "record_count": installed_record_count,
        "refresh_record_count": len(result.records),
        "row_count": atoms.get("dryad_landscape_monitoring_row", 0),
        "file_count": atoms.get("dryad_landscape_file_manifest", 0),
        "dataset_manifest_count": atoms.get("dryad_landscape_dataset_manifest", 0),
        "source_gap_count": atoms.get("source_gap", 0),
        "raw_artifacts": result.raw_artifacts,
        "retrieved_at": retrieved,
        "refresh_failed": refresh_failed,
        "preserved_existing": refresh_failed and preserved_existing,
        "method": "parsed Dryad public preview table for southeast U.S. blueberry SWD landscape monitoring rows",
    }
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID not in sources:
                sources.append(DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload[DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {
        "ok": not refresh_failed,
        "artifact_dir": artifact_dir.as_posix(),
        **source_payload,
        "source_counts": counts,
        "lanes": summary["lanes"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest Dryad southeast U.S. blueberry SWD landscape monitoring rows.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_drosophila_suzukii_dryad_landscape_monitoring(
        artifact_dir=Path(args.artifact_dir),
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
