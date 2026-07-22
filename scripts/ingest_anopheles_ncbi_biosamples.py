#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR, utc_now
from askinsects.incremental_metadata import update_source_metadata_incrementally
from askinsects.index import SourceIndex
from askinsects.ingest_runner import run_source_ingest
from askinsects.sources.anopheles_ncbi_biosamples import (
    ANOPHELES_NCBI_BIOSAMPLES_SOURCE_ID,
    ANOPHELES_NCBI_BIOSAMPLES_TARGET_TAXA,
    fetch_anopheles_ncbi_biosample_records,
)


def _update_metadata(
    artifact_dir: Path,
    *,
    retrieved_at: str,
    outcome: dict[str, object],
    result,
) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    with index.connect() as connection:
        installed_lane_counts = {
            str(row["lane"]): int(row["n"])
            for row in connection.execute(
                "select lane, count(*) as n from records where source=? group by lane",
                (ANOPHELES_NCBI_BIOSAMPLES_SOURCE_ID,),
            ).fetchall()
        }
        installed_sample_count = int(
            connection.execute(
                "select count(*) as n from records where source=? and record_id like 'anopheles_ncbi:biosample:%'",
                (ANOPHELES_NCBI_BIOSAMPLES_SOURCE_ID,),
            ).fetchone()["n"]
        )
    source_payload = {
        "source": ANOPHELES_NCBI_BIOSAMPLES_SOURCE_ID,
        "lanes": ["biosamples"],
        "lane_counts": installed_lane_counts,
        "record_count": int(outcome["record_count"]),
        "sample_record_count": installed_sample_count,
        "source_gap_count": int(outcome["source_gap_count"]),
        "refresh_record_count": int(outcome["refresh_record_count"]),
        "target_taxa": list(result.target_taxa),
        "reported_total_counts": result.total_counts,
        "fetched_counts": result.fetched_counts,
        "page_counts": result.page_counts,
        "limit_per_taxon": result.requested_limit_per_taxon,
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
        "retrieved_at": retrieved_at,
        "refresh_failed": bool(outcome["refresh_failed"]),
        "preserved_existing": bool(outcome["preserved_existing"]),
        "method": "bounded NCBI BioSample ESearch and ESummary for priority Anopheles malaria-vector taxa",
    }
    update_source_metadata_incrementally(
        artifact_dir,
        source_id=ANOPHELES_NCBI_BIOSAMPLES_SOURCE_ID,
        default_lane="biosamples",
        installed_record_count=int(outcome["record_count"]),
        installed_lane_counts=installed_lane_counts,
        source_payload=source_payload,
    )


def ingest_anopheles_ncbi_biosamples(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    target_taxa: list[str] | tuple[str, ...] = ANOPHELES_NCBI_BIOSAMPLES_TARGET_TAXA,
    limit_per_taxon: int = 250,
    page_size: int = 200,
    delay_seconds: float = 0.34,
    fetch_json=None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    result = fetch_anopheles_ncbi_biosample_records(
        raw_dir=artifact_dir / "raw" / "anopheles_ncbi_biosamples",
        target_taxa=target_taxa,
        limit_per_taxon=limit_per_taxon,
        page_size=page_size,
        delay_seconds=delay_seconds,
        fetch_json=fetch_json,
        retrieved_at=retrieved,
    )
    outcome = run_source_ingest(
        index=index,
        artifact_dir=artifact_dir,
        source_id=ANOPHELES_NCBI_BIOSAMPLES_SOURCE_ID,
        records=result.records,
        gaps=result.gaps,
        retrieved_at=retrieved,
        raw_artifacts=result.raw_artifacts,
        persist_gap_records=True,
        preserve_existing_fts=True,
    )
    _update_metadata(artifact_dir, retrieved_at=retrieved, outcome=outcome, result=result)
    return {
        **outcome,
        "sample_record_count": len(result.records),
        "target_taxa": list(result.target_taxa),
        "reported_total_counts": result.total_counts,
        "fetched_counts": result.fetched_counts,
        "page_counts": result.page_counts,
        "limit_per_taxon": result.requested_limit_per_taxon,
        "artifact_dir": artifact_dir.as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest bounded Anopheles NCBI BioSample metadata.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--species", action="append", default=[])
    parser.add_argument("--limit-per-taxon", type=int, default=250)
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--delay-seconds", type=float, default=0.34)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_anopheles_ncbi_biosamples(
        artifact_dir=Path(args.artifact_dir),
        target_taxa=args.species or ANOPHELES_NCBI_BIOSAMPLES_TARGET_TAXA,
        limit_per_taxon=args.limit_per_taxon,
        page_size=args.page_size,
        delay_seconds=args.delay_seconds,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
