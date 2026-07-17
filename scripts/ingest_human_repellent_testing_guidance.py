#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR, utc_now, write_json
from askinsects.index import SourceIndex
from askinsects.ingest_runner import run_source_ingest
from askinsects.sources.human_repellent_testing_guidance import (
    HUMAN_REPELLENT_TESTING_GUIDANCE_SOURCE_ID,
    build_human_repellent_testing_guidance_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def ingest_human_repellent_testing_guidance(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    records = build_human_repellent_testing_guidance_records(retrieved_at=retrieved)
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    outcome = run_source_ingest(
        index=index,
        artifact_dir=artifact_dir,
        source_id=HUMAN_REPELLENT_TESTING_GUIDANCE_SOURCE_ID,
        records=records,
        gaps=[],
        retrieved_at=retrieved,
        persist_gap_records=True,
    )
    summary = index.summary()
    source_counts = {
        row["source"]: int(row["n"])
        for row in index.sql(
            "select source, count(*) as n from records group by source order by source",
            limit=4000,
        )
    }
    source_payload = {
        "source": HUMAN_REPELLENT_TESTING_GUIDANCE_SOURCE_ID,
        "record_count": source_counts.get(HUMAN_REPELLENT_TESTING_GUIDANCE_SOURCE_ID, 0),
        "retrieved_at": retrieved,
        "refresh_failed": bool(outcome["refresh_failed"]),
        "method": "reviewed exact official guidance and peer-reviewed source URLs",
    }
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[HUMAN_REPELLENT_TESTING_GUIDANCE_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if HUMAN_REPELLENT_TESTING_GUIDANCE_SOURCE_ID not in sources:
                sources.append(HUMAN_REPELLENT_TESTING_GUIDANCE_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload[HUMAN_REPELLENT_TESTING_GUIDANCE_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {**outcome, "artifact_dir": artifact_dir.as_posix()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest exact human mosquito-repellent testing guidance."
    )
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_human_repellent_testing_guidance(
        artifact_dir=Path(args.artifact_dir),
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
