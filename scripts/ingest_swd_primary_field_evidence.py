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
from askinsects.sources.swd_primary_field_evidence import (
    SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID,
    build_swd_primary_field_evidence_records,
)


def ingest_swd_primary_field_evidence(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    records = build_swd_primary_field_evidence_records(retrieved_at=retrieved)
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    outcome = run_source_ingest(
        index=index,
        artifact_dir=artifact_dir,
        source_id=SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID,
        records=records,
        gaps=[],
        retrieved_at=retrieved,
        persist_gap_records=True,
        preserve_existing_fts=True,
    )
    installed_record_count = int(outcome["record_count"])
    with index.connect() as connection:
        installed_lane_counts = {
            str(row["lane"]): int(row["n"])
            for row in connection.execute(
                "select lane, count(*) as n from records where source=? group by lane",
                (SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID,),
            ).fetchall()
        }
    source_payload = {
        "source": SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID,
        "lane": "literature",
        "lane_counts": installed_lane_counts,
        "record_count": installed_record_count,
        "retrieved_at": retrieved,
        "refresh_failed": bool(outcome["refresh_failed"]),
        "method": "human-reviewed exact SWD greenhouse-to-field primary study",
    }
    update_source_metadata_incrementally(
        artifact_dir,
        source_id=SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID,
        default_lane="literature",
        installed_record_count=installed_record_count,
        installed_lane_counts=installed_lane_counts,
        source_payload=source_payload,
    )
    return {**outcome, "artifact_dir": artifact_dir.as_posix()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest exact primary SWD greenhouse-to-field evidence."
    )
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_swd_primary_field_evidence(
        artifact_dir=Path(args.artifact_dir),
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
