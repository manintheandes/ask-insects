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
from askinsects.gaps import persist_source_gaps
from askinsects.index import SourceIndex
from askinsects.sources.dryad_behavior_videos import (
    DEFAULT_DRYAD_DATASETS,
    DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
    DryadDatasetSpec,
    fetch_dryad_behavior_video_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [gap for gap in existing if not (isinstance(gap, dict) and gap.get("source") == DRYAD_BEHAVIOR_VIDEO_SOURCE_ID)]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=1000)
    }


def _source_count(index: SourceIndex) -> int:
    with index.connect() as conn:
        return int(
            conn.execute(
                "select count(*) as n from records where source=?",
                (DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,),
            ).fetchone()["n"]
        )


def _update_metadata(artifact_dir: Path, result, retrieved_at: str, *, ok: bool = True, preserved_existing: bool = False) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    source_payload = {
        "source": DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
        "requested_dois": result.requested_dois,
        "dataset_count": result.dataset_count,
        "file_count": result.file_count,
        "media_file_count": result.media_file_count,
        "table_file_count": result.table_file_count,
        "parsed_table_file_count": result.parsed_table_file_count,
        "skipped_table_file_count": result.skipped_table_file_count,
        "table_sheet_count": result.table_sheet_count,
        "table_row_count": result.table_row_count,
        "landing_page_count": result.landing_page_count,
        "assay_method_count": result.assay_method_count,
        "record_count": len(result.records),
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
        "retrieved_at": retrieved_at,
        "refresh_failed": not ok,
        "preserved_existing": preserved_existing,
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[DRYAD_BEHAVIOR_VIDEO_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if DRYAD_BEHAVIOR_VIDEO_SOURCE_ID not in sources:
                sources.append(DRYAD_BEHAVIOR_VIDEO_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload["dryad_behavior_videos"] = source_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "source": DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
        "record_count": len(result.records),
        "preserved_existing": preserved_existing,
        "dataset_count": result.dataset_count,
        "file_count": result.file_count,
        "media_file_count": result.media_file_count,
        "table_file_count": result.table_file_count,
        "parsed_table_file_count": result.parsed_table_file_count,
        "skipped_table_file_count": result.skipped_table_file_count,
        "table_sheet_count": result.table_sheet_count,
        "table_row_count": result.table_row_count,
        "landing_page_count": result.landing_page_count,
        "assay_method_count": result.assay_method_count,
        "gap_count": len(result.gaps),
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def _dataset_specs_from_dois(dois: list[str] | None) -> list[DryadDatasetSpec]:
    if not dois:
        return list(DEFAULT_DRYAD_DATASETS)
    known = {spec.doi: spec for spec in DEFAULT_DRYAD_DATASETS}
    return [known.get(doi, DryadDatasetSpec(doi=doi, behavior_labels=("behavior", "video"))) for doi in dois]


def ingest_dryad_behavior_videos(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    dois: list[str] | None = None,
    fetch_json=None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    result = fetch_dryad_behavior_video_records(
        _dataset_specs_from_dois(dois),
        raw_dir=artifact_dir / "raw" / "dryad_behavior_videos",
        fetch_json=fetch_json,
        retrieved_at=retrieved,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    refresh_failed = not result.records and bool(result.gaps)
    if not refresh_failed:
        index.replace_source_records(DRYAD_BEHAVIOR_VIDEO_SOURCE_ID, result.records)
    persist_source_gaps(index, DRYAD_BEHAVIOR_VIDEO_SOURCE_ID, result.gaps, retrieved_at=retrieved)
    return _update_metadata(
        artifact_dir,
        result,
        retrieved,
        ok=not refresh_failed,
        preserved_existing=refresh_failed and _source_count(index) > 0,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest Dryad Aedes aegypti behavior/video dataset manifests into Ask Insects.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--doi", action="append", default=[])
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_dryad_behavior_videos(
        artifact_dir=Path(args.artifact_dir),
        dois=args.doi or None,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
