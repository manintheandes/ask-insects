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
from askinsects.sources.plutella_xylostella_literature import (
    PLUTELLA_XYLOSTELLA_LITERATURE_SOURCE_ID,
    PLUTELLA_XYLOSTELLA_OPENALEX_WORK_IDS,
    fetch_plutella_xylostella_literature_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _update_metadata(
    artifact_dir: Path,
    *,
    retrieved_at: str,
    outcome: dict[str, object],
    result,
) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = {
        row["source"]: int(row["n"])
        for row in index.sql(
            "select source, count(*) as n from records group by source order by source",
            limit=4000,
        )
    }
    source_payload = {
        "source": PLUTELLA_XYLOSTELLA_LITERATURE_SOURCE_ID,
        "record_count": source_counts.get(PLUTELLA_XYLOSTELLA_LITERATURE_SOURCE_ID, 0),
        "required_work_count": len(PLUTELLA_XYLOSTELLA_OPENALEX_WORK_IDS),
        "requested_urls": result.requested_urls,
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
        "retrieved_at": retrieved_at,
        "refresh_failed": bool(outcome["refresh_failed"]),
        "preserved_existing": bool(outcome["preserved_existing"]),
        "method": "exact OpenAlex work IDs with direct Plutella xylostella confirmation",
    }
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[PLUTELLA_XYLOSTELLA_LITERATURE_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if PLUTELLA_XYLOSTELLA_LITERATURE_SOURCE_ID not in sources:
                sources.append(PLUTELLA_XYLOSTELLA_LITERATURE_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload[PLUTELLA_XYLOSTELLA_LITERATURE_SOURCE_ID] = source_payload
        write_json(path, payload)


def ingest_plutella_xylostella_literature(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    fetch_json=None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    result = fetch_plutella_xylostella_literature_records(
        raw_dir=artifact_dir / "raw" / "plutella_xylostella_literature",
        fetch_json=fetch_json,
        retrieved_at=retrieved,
    )
    complete = (
        not result.gaps
        and len(result.records) == len(PLUTELLA_XYLOSTELLA_OPENALEX_WORK_IDS)
    )
    outcome = run_source_ingest(
        index=index,
        artifact_dir=artifact_dir,
        source_id=PLUTELLA_XYLOSTELLA_LITERATURE_SOURCE_ID,
        records=result.records if complete else [],
        gaps=result.gaps,
        retrieved_at=retrieved,
        raw_artifacts=result.raw_artifacts,
        persist_gap_records=True,
    )
    _update_metadata(
        artifact_dir,
        retrieved_at=retrieved,
        outcome=outcome,
        result=result,
    )
    return {
        **outcome,
        "complete": complete,
        "required_work_count": len(PLUTELLA_XYLOSTELLA_OPENALEX_WORK_IDS),
        "fetched_work_count": len(result.records),
        "requested_urls": result.requested_urls,
        "artifact_dir": artifact_dir.as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest exact reviewed Plutella xylostella literature records."
    )
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_plutella_xylostella_literature(
        artifact_dir=Path(args.artifact_dir),
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") and result.get("complete") else 2


if __name__ == "__main__":
    raise SystemExit(main())
