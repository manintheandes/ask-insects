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
from askinsects.sources.anopheles_pathogen_taxonomy import (
    ANOPHELES_PATHOGEN_TAXONOMY_SOURCE_ID,
    fetch_anopheles_pathogen_taxonomy,
)


def ingest_anopheles_pathogen_taxonomy(
    *, artifact_dir: Path = DEFAULT_ARTIFACT_DIR, fetch_json=None, retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    result = fetch_anopheles_pathogen_taxonomy(
        raw_dir=artifact_dir / "raw" / "anopheles_pathogen_taxonomy",
        fetch_json=fetch_json,
        retrieved_at=retrieved,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    outcome = run_source_ingest(
        index=index,
        artifact_dir=artifact_dir,
        source_id=ANOPHELES_PATHOGEN_TAXONOMY_SOURCE_ID,
        records=result.records,
        gaps=result.gaps,
        retrieved_at=retrieved,
        raw_artifacts=result.raw_artifacts,
        persist_gap_records=True,
    )
    source_payload = {
        "source": ANOPHELES_PATHOGEN_TAXONOMY_SOURCE_ID,
        "lanes": ["vector_competence"],
        "record_count": int(outcome["record_count"]),
        "refresh_record_count": int(outcome["refresh_record_count"]),
        "pathogen_count": result.pathogen_count,
        "requested_taxids": result.requested_taxids,
        "query_url": result.query_url,
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
        "retrieved_at": retrieved,
        "method": "NCBI Taxonomy identity anchors for human and laboratory Plasmodium species used in Anopheles research",
    }
    update_source_metadata_incrementally(
        artifact_dir,
        source_id=ANOPHELES_PATHOGEN_TAXONOMY_SOURCE_ID,
        default_lane="vector_competence",
        installed_record_count=int(outcome["record_count"]),
        installed_lane_counts={"vector_competence": int(outcome["record_count"])},
        source_payload=source_payload,
    )
    return {**outcome, "pathogen_count": result.pathogen_count, "artifact_dir": artifact_dir.as_posix()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest NCBI Taxonomy Plasmodium identity anchors for Anopheles research.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_anopheles_pathogen_taxonomy(
        artifact_dir=Path(args.artifact_dir), retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
