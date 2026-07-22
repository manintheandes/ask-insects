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
from askinsects.sources.anopheles_gbif import (
    ANOPHELES_GBIF_SOURCE_ID,
    ANOPHELES_GBIF_TARGET_TAXA,
    fetch_anopheles_gbif_records,
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
                (ANOPHELES_GBIF_SOURCE_ID,),
            ).fetchall()
        }
    installed_record_count = int(outcome["record_count"])
    source_payload = {
        "source": ANOPHELES_GBIF_SOURCE_ID,
        "lanes": ["taxonomy", "observations"],
        "lane_counts": installed_lane_counts,
        "record_count": installed_record_count,
        "refresh_record_count": int(outcome["refresh_record_count"]),
        "target_taxa": list(result.requested_species),
        "taxon_keys": result.taxon_keys,
        "total_results": result.total_results,
        "occurrence_limit": result.occurrence_limit,
        "occurrence_page_size": result.occurrence_page_size,
        "occurrence_workers": result.occurrence_workers,
        "page_count": result.page_count,
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
        "retrieved_at": retrieved_at,
        "refresh_failed": bool(outcome["refresh_failed"]),
        "preserved_existing": bool(outcome["preserved_existing"]),
        "method": "bounded GBIF species-match and occurrence search for priority Anopheles malaria-vector taxa",
    }
    update_source_metadata_incrementally(
        artifact_dir,
        source_id=ANOPHELES_GBIF_SOURCE_ID,
        default_lane="observations",
        installed_record_count=installed_record_count,
        installed_lane_counts=installed_lane_counts,
        source_payload=source_payload,
    )


def ingest_anopheles_gbif(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    species_names: list[str] | tuple[str, ...] = ANOPHELES_GBIF_TARGET_TAXA,
    occurrence_limit: int = 25,
    occurrence_page_size: int = 100,
    occurrence_workers: int = 1,
    delay_seconds: float = 0.0,
    fetch_json=None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    result = fetch_anopheles_gbif_records(
        raw_dir=artifact_dir / "raw" / "anopheles_gbif",
        species_names=species_names,
        occurrence_limit=occurrence_limit,
        occurrence_page_size=occurrence_page_size,
        occurrence_workers=occurrence_workers,
        delay_seconds=delay_seconds,
        fetch_json=fetch_json,
        retrieved_at=retrieved,
    )
    outcome = run_source_ingest(
        index=index,
        artifact_dir=artifact_dir,
        source_id=ANOPHELES_GBIF_SOURCE_ID,
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
        "target_taxa": list(result.requested_species),
        "taxon_keys": result.taxon_keys,
        "total_results": result.total_results,
        "occurrence_limit": occurrence_limit,
        "occurrence_page_size": occurrence_page_size,
        "occurrence_workers": occurrence_workers,
        "page_count": result.page_count,
        "artifact_dir": artifact_dir.as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest bounded Anopheles GBIF taxonomy and occurrence records.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--species", action="append", default=[])
    parser.add_argument("--occurrence-limit", type=int, default=25)
    parser.add_argument("--occurrence-page-size", type=int, default=100)
    parser.add_argument("--occurrence-workers", type=int, default=1)
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_anopheles_gbif(
        artifact_dir=Path(args.artifact_dir),
        species_names=args.species or ANOPHELES_GBIF_TARGET_TAXA,
        occurrence_limit=args.occurrence_limit,
        occurrence_page_size=args.occurrence_page_size,
        occurrence_workers=args.occurrence_workers,
        delay_seconds=args.delay_seconds,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
