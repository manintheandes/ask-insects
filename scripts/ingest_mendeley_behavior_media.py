#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR, utc_now, write_json
from askinsects.index import SourceIndex
from askinsects.sources.mendeley_behavior_media import (
    DEFAULT_MENDELEY_DATASETS,
    MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
    MendeleyDatasetSpec,
    fetch_mendeley_behavior_media_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [gap for gap in existing if not (isinstance(gap, dict) and gap.get("source") == MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID)]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=1000)
    }


def _update_metadata(artifact_dir: Path, result, retrieved_at: str) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    source_payload = {
        "source": MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
        "requested_datasets": result.requested_datasets,
        "dataset_count": result.dataset_count,
        "folder_count": result.folder_count,
        "file_count": result.file_count,
        "media_file_count": result.media_file_count,
        "record_count": len(result.records),
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
        "retrieved_at": retrieved_at,
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID not in sources:
                sources.append(MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload["mendeley_behavior_media"] = source_payload
        write_json(path, payload)
    return {
        "ok": True,
        "source": MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
        "record_count": len(result.records),
        "dataset_count": result.dataset_count,
        "folder_count": result.folder_count,
        "file_count": result.file_count,
        "media_file_count": result.media_file_count,
        "gap_count": len(result.gaps),
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def _dataset_specs_from_cli(values: list[str] | None) -> list[MendeleyDatasetSpec]:
    if not values:
        return list(DEFAULT_MENDELEY_DATASETS)
    specs = []
    known = {f"{spec.dataset_id}:{spec.version}": spec for spec in DEFAULT_MENDELEY_DATASETS}
    for value in values:
        dataset_id, _, version_text = value.partition(":")
        if not dataset_id or not version_text:
            raise ValueError("datasets must be formatted as DATASET_ID:VERSION")
        key = f"{dataset_id}:{int(version_text)}"
        specs.append(known.get(key, MendeleyDatasetSpec(dataset_id=dataset_id, version=int(version_text), behavior_labels=("behavior", "media"))))
    return specs


def ingest_mendeley_behavior_media(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    datasets: list[str] | None = None,
    fetch_json=None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    result = fetch_mendeley_behavior_media_records(
        _dataset_specs_from_cli(datasets),
        raw_dir=artifact_dir / "raw" / "mendeley_behavior_media",
        fetch_json=fetch_json,
        retrieved_at=retrieved,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.delete_source(MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID)
    index.upsert_records(result.records)
    return _update_metadata(artifact_dir, result, retrieved)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest Mendeley Aedes aegypti behavior/media dataset manifests into Ask Insects.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--dataset", action="append", default=[], help="Mendeley dataset spec formatted as DATASET_ID:VERSION")
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_mendeley_behavior_media(
        artifact_dir=Path(args.artifact_dir),
        datasets=args.dataset or None,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
