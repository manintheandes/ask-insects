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
from askinsects.sources.anopheles_who_malaria_resistance import (
    ANOPHELES_WHO_MALARIA_RESISTANCE_SOURCE_ID,
    fetch_anopheles_who_malaria_resistance,
)


def ingest_anopheles_who_malaria_resistance(
    *, artifact_dir: Path = DEFAULT_ARTIFACT_DIR, page_size: int = 1000, max_rows: int = 10000,
    delay_seconds: float = 0.2, fetch_json=None, retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    result = fetch_anopheles_who_malaria_resistance(
        raw_dir=artifact_dir / "raw" / "anopheles_who_malaria_resistance",
        page_size=page_size, max_rows=max_rows, delay_seconds=delay_seconds,
        fetch_json=fetch_json, retrieved_at=retrieved,
    )
    outcome = run_source_ingest(
        index=index, artifact_dir=artifact_dir, source_id=ANOPHELES_WHO_MALARIA_RESISTANCE_SOURCE_ID,
        records=result.records, gaps=result.gaps, retrieved_at=retrieved,
        raw_artifacts=result.raw_artifacts, persist_gap_records=True, preserve_existing_fts=True,
    )
    with index.connect() as connection:
        lane_counts = {
            str(row["lane"]): int(row["n"])
            for row in connection.execute("select lane, count(*) as n from records where source=? group by lane", (ANOPHELES_WHO_MALARIA_RESISTANCE_SOURCE_ID,)).fetchall()
        }
    update_source_metadata_incrementally(
        artifact_dir, source_id=ANOPHELES_WHO_MALARIA_RESISTANCE_SOURCE_ID,
        default_lane="resistance", installed_record_count=int(outcome["record_count"]),
        installed_lane_counts=lane_counts,
        source_payload={
            "source": ANOPHELES_WHO_MALARIA_RESISTANCE_SOURCE_ID, "record_count": int(outcome["record_count"]),
            "refresh_record_count": int(outcome["refresh_record_count"]), "source_gap_count": int(outcome["source_gap_count"]),
            "fetched_row_count": result.fetched_row_count, "unique_record_count": len(result.records),
            "species_labels": result.species_labels, "page_size": result.page_size, "max_rows": result.max_rows,
            "requested_urls": result.requested_urls, "raw_artifacts": result.raw_artifacts,
            "retrieved_at": retrieved, "refresh_failed": bool(outcome["refresh_failed"]),
            "preserved_existing": bool(outcome["preserved_existing"]),
            "method": "paged WHO MAL_THREATS FACT_PREVENTION_VIEW Anopheles filter to atomic resistance assay rows",
        },
    )
    return {**outcome, "fetched_row_count": result.fetched_row_count, "unique_record_count": len(result.records), "species_labels": result.species_labels, "page_size": result.page_size, "max_rows": result.max_rows, "artifact_dir": artifact_dir.as_posix()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest WHO malaria-vector Anopheles insecticide-resistance rows.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--max-rows", type=int, default=10000)
    parser.add_argument("--delay-seconds", type=float, default=0.2)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_anopheles_who_malaria_resistance(
        artifact_dir=Path(args.artifact_dir), page_size=args.page_size, max_rows=args.max_rows,
        delay_seconds=args.delay_seconds, retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
