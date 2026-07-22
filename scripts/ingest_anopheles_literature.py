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
from askinsects.sources.anopheles_literature import (
    ANOPHELES_LITERATURE_SEARCH_TERMS,
    ANOPHELES_LITERATURE_SOURCE_ID,
    ANOPHELES_TARGET_TAXA,
    fetch_anopheles_literature_records,
)


def _update_metadata(
    artifact_dir: Path,
    *,
    retrieved_at: str,
    outcome: dict[str, object],
    result,
    from_date: str,
    to_date: str,
    max_works: int,
) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    with index.connect() as connection:
        installed_lane_counts = {
            str(row["lane"]): int(row["n"])
            for row in connection.execute(
                "select lane, count(*) as n from records where source=? group by lane",
                (ANOPHELES_LITERATURE_SOURCE_ID,),
            ).fetchall()
        }
    installed_record_count = int(outcome["record_count"])
    source_payload = {
        "source": ANOPHELES_LITERATURE_SOURCE_ID,
        "lane": "literature",
        "lane_counts": installed_lane_counts,
        "record_count": installed_record_count,
        "refresh_record_count": int(outcome["refresh_record_count"]),
        "target_taxa": ANOPHELES_TARGET_TAXA,
        "from_date": from_date,
        "to_date": to_date,
        "max_works": max_works,
        "search_terms": [query.term for query in ANOPHELES_LITERATURE_SEARCH_TERMS],
        "search_modes": [query.mode for query in ANOPHELES_LITERATURE_SEARCH_TERMS],
        "topic_groups": [query.topic_group for query in ANOPHELES_LITERATURE_SEARCH_TERMS],
        "reported_total_count": result.reported_total_count,
        "page_count": result.page_count,
        "doi_count": result.doi_count,
        "inclusion_path_counts": result.inclusion_path_counts,
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
        "retrieved_at": retrieved_at,
        "refresh_failed": bool(outcome["refresh_failed"]),
        "preserved_existing": bool(outcome["preserved_existing"]),
        "method": "bounded OpenAlex works query for target Anopheles malaria-vector taxa and priority Anopheles R&D topics",
    }
    update_source_metadata_incrementally(
        artifact_dir,
        source_id=ANOPHELES_LITERATURE_SOURCE_ID,
        default_lane="literature",
        installed_record_count=installed_record_count,
        installed_lane_counts=installed_lane_counts,
        source_payload=source_payload,
    )


def ingest_anopheles_literature(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    from_date: str = "1900-01-01",
    to_date: str = "2026-12-31",
    max_works: int = 5000,
    page_size: int = 100,
    delay_seconds: float = 0.0,
    fetch_json=None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    result = fetch_anopheles_literature_records(
        raw_dir=artifact_dir / "raw" / "anopheles_literature",
        from_date=from_date,
        to_date=to_date,
        max_works=max_works,
        page_size=page_size,
        delay_seconds=delay_seconds,
        fetch_json=fetch_json,
        retrieved_at=retrieved,
    )
    outcome = run_source_ingest(
        index=index,
        artifact_dir=artifact_dir,
        source_id=ANOPHELES_LITERATURE_SOURCE_ID,
        records=result.records,
        gaps=result.gaps,
        retrieved_at=retrieved,
        raw_artifacts=result.raw_artifacts,
        persist_gap_records=True,
        preserve_existing_fts=True,
    )
    _update_metadata(
        artifact_dir,
        retrieved_at=retrieved,
        outcome=outcome,
        result=result,
        from_date=from_date,
        to_date=to_date,
        max_works=max_works,
    )
    return {
        **outcome,
        "target_taxa": ANOPHELES_TARGET_TAXA,
        "from_date": from_date,
        "to_date": to_date,
        "max_works": max_works,
        "fetched_work_count": len(result.records),
        "reported_total_count": result.reported_total_count,
        "page_count": result.page_count,
        "artifact_dir": artifact_dir.as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest bounded Anopheles OpenAlex literature records.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--from-date", default="1900-01-01")
    parser.add_argument("--to-date", default="2026-12-31")
    parser.add_argument("--max-works", type=int, default=5000)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_anopheles_literature(
        artifact_dir=Path(args.artifact_dir),
        from_date=args.from_date,
        to_date=args.to_date,
        max_works=args.max_works,
        page_size=args.page_size,
        delay_seconds=args.delay_seconds,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
