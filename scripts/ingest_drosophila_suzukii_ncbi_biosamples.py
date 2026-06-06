#!/usr/bin/env python3
"""Deepen SWD biosamples coverage.

Reuses the tested, species-parameterized NCBI BioSample fetcher and re-tags the
records to a DEDICATED Drosophila suzukii source id so it is additive and never
clobbers the shared Aedes ``ncbi_biosamples`` rows (different accessions ->
different record_ids; only the source tag changes).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR, utc_now, write_json
from askinsects.index import SourceIndex
from askinsects.ingest_runner import run_source_ingest
from askinsects.sources.ncbi_biosample import fetch_ncbi_biosample_records

DROSOPHILA_SUZUKII_NCBI_BIOSAMPLES_SOURCE_ID = "drosophila_suzukii_ncbi_biosamples"
SPECIES = "Drosophila suzukii"


def _retag_records(records):
    out = []
    for r in records:
        out.append(replace(
            r,
            source=DROSOPHILA_SUZUKII_NCBI_BIOSAMPLES_SOURCE_ID,
            provenance=replace(r.provenance, source_id=DROSOPHILA_SUZUKII_NCBI_BIOSAMPLES_SOURCE_ID),
        ))
    return out


def _retag_gaps(gaps):
    out = []
    for g in gaps:
        if isinstance(g, dict):
            g = {**g, "source": DROSOPHILA_SUZUKII_NCBI_BIOSAMPLES_SOURCE_ID}
        out.append(g)
    return out


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [
        gap for gap in existing
        if not (isinstance(gap, dict) and gap.get("source") == DROSOPHILA_SUZUKII_NCBI_BIOSAMPLES_SOURCE_ID)
    ]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_record_count(index: SourceIndex) -> int:
    with index.connect() as conn:
        return int(conn.execute(
            "select count(*) as n from records where source=?",
            (DROSOPHILA_SUZUKII_NCBI_BIOSAMPLES_SOURCE_ID,),
        ).fetchone()["n"])


def _update_metadata(artifact_dir: Path, result, retrieved_at: str, *, ok: bool, preserved_existing: bool) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    installed = _source_record_count(index)
    source_counts = {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=2000)
    }
    gaps = _retag_gaps(list(result.gaps))
    source_payload = {
        "source": DROSOPHILA_SUZUKII_NCBI_BIOSAMPLES_SOURCE_ID,
        "species": SPECIES,
        "record_count": installed,
        "refresh_record_count": len(result.records),
        "total_count": result.total_count,
        "fetched_count": result.fetched_count,
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(gaps),
        "retrieved_at": retrieved_at,
        "refresh_failed": not ok,
        "preserved_existing": preserved_existing,
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[DROSOPHILA_SUZUKII_NCBI_BIOSAMPLES_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if DROSOPHILA_SUZUKII_NCBI_BIOSAMPLES_SOURCE_ID not in sources:
                sources.append(DROSOPHILA_SUZUKII_NCBI_BIOSAMPLES_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload[DROSOPHILA_SUZUKII_NCBI_BIOSAMPLES_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "source": DROSOPHILA_SUZUKII_NCBI_BIOSAMPLES_SOURCE_ID,
        "record_count": installed,
        "refresh_record_count": len(result.records),
        "total_count": result.total_count,
        "fetched_count": result.fetched_count,
        "gap_count": len(gaps),
        "preserved_existing": preserved_existing,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_drosophila_suzukii_ncbi_biosamples(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    fetch_json=None,
    retrieved_at: str | None = None,
    limit: int = 1300,
    page_size: int = 200,
    delay_seconds: float = 0.34,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    result = fetch_ncbi_biosample_records(
        species=SPECIES,
        raw_dir=artifact_dir / "raw" / "drosophila_suzukii_ncbi_biosamples",
        limit=limit,
        page_size=page_size,
        delay_seconds=delay_seconds,
        fetch_json=fetch_json,
        retrieved_at=retrieved,
    )
    records = _retag_records(result.records)
    gaps = _retag_gaps(list(result.gaps))
    outcome = run_source_ingest(
        index=index,
        artifact_dir=artifact_dir,
        source_id=DROSOPHILA_SUZUKII_NCBI_BIOSAMPLES_SOURCE_ID,
        records=records,
        gaps=gaps,
        retrieved_at=retrieved,
        raw_artifacts=getattr(result, "raw_artifacts", None),
        persist_gap_records=True,
    )
    # Biosamples are real records; a fetch failure (no records) is a real failure.
    return _update_metadata(
        artifact_dir, result, retrieved,
        ok=not outcome["refresh_failed"],
        preserved_existing=outcome["preserved_existing"],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deepen Drosophila suzukii NCBI BioSample coverage.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--limit", type=int, default=1300)
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--retrieved-at")
    parser.add_argument("--delay-seconds", type=float, default=0.34)
    args = parser.parse_args(argv)
    result = ingest_drosophila_suzukii_ncbi_biosamples(
        artifact_dir=Path(args.artifact_dir),
        limit=args.limit,
        page_size=args.page_size,
        retrieved_at=args.retrieved_at,
        delay_seconds=args.delay_seconds,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
