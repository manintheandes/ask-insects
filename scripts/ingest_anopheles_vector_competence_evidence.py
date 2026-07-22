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
from askinsects.sources.anopheles_vector_competence_evidence import (
    ANOPHELES_VECTOR_COMPETENCE_SOURCE_ID,
    build_anopheles_vector_competence_records,
)


def ingest_anopheles_vector_competence_evidence(
    *, artifact_dir: Path = DEFAULT_ARTIFACT_DIR, retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    result = build_anopheles_vector_competence_records(artifact_dir, retrieved_at=retrieved)
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    outcome = run_source_ingest(
        index=index,
        artifact_dir=artifact_dir,
        source_id=ANOPHELES_VECTOR_COMPETENCE_SOURCE_ID,
        records=result.records,
        gaps=result.gaps,
        retrieved_at=retrieved,
        raw_artifacts=[],
        persist_gap_records=True,
    )
    class_counts: dict[str, int] = {}
    for record in result.records:
        evidence_class = str((record.payload or {}).get("evidence_class") or "unknown")
        class_counts[evidence_class] = class_counts.get(evidence_class, 0) + 1
    source_payload = {
        "source": ANOPHELES_VECTOR_COMPETENCE_SOURCE_ID,
        "lanes": ["vector_competence"],
        "record_count": int(outcome["record_count"]),
        "refresh_record_count": int(outcome["refresh_record_count"]),
        "source_record_count": result.source_record_count,
        "candidate_sentence_count": result.candidate_sentence_count,
        "excluded_model_sentence_count": result.excluded_model_sentence_count,
        "evidence_class_counts": class_counts,
        "gap_count": len(result.gaps),
        "retrieved_at": retrieved,
        "method": "Conservative extraction of numeric Anopheles endpoint results from exact OpenAlex abstract sentences",
    }
    update_source_metadata_incrementally(
        artifact_dir,
        source_id=ANOPHELES_VECTOR_COMPETENCE_SOURCE_ID,
        default_lane="vector_competence",
        installed_record_count=int(outcome["record_count"]),
        installed_lane_counts={"vector_competence": int(outcome["record_count"])},
        source_payload=source_payload,
    )
    return {
        **outcome,
        "source_record_count": result.source_record_count,
        "candidate_sentence_count": result.candidate_sentence_count,
        "excluded_model_sentence_count": result.excluded_model_sentence_count,
        "evidence_class_counts": class_counts,
        "artifact_dir": artifact_dir.as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest abstract-level Anopheles vector-competence evidence.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_anopheles_vector_competence_evidence(
        artifact_dir=Path(args.artifact_dir), retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
