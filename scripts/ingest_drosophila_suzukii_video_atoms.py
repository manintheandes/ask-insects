#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from pathlib import Path
from typing import Callable, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR
from askinsects.index import SourceIndex
from askinsects.server import read_json, source_counts, write_json
from askinsects.sources.drosophila_suzukii_video_atoms import (
    DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID,
    build_drosophila_suzukii_video_atom_records,
)


def _replace_source_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> list[dict[str, object]]:
    old_gaps = read_json(gaps_path, [])
    if not isinstance(old_gaps, list):
        old_gaps = []
    kept = [gap for gap in old_gaps if not (isinstance(gap, dict) and gap.get("source") == DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID)]
    kept.extend(gaps)
    return kept


def _atom_counts(index: SourceIndex) -> dict[str, int]:
    rows = index.sql(
        """
        select json_extract(payload_json, '$.atom_type') as atom_type, count(*) as n
        from record_payloads
        where source='drosophila_suzukii_video_atoms'
        group by atom_type
        """,
        limit=100,
    )
    return {str(row["atom_type"]): int(row["n"]) for row in rows if row["atom_type"]}


def _source_stats(index: SourceIndex, source: str) -> tuple[int, dict[str, int]]:
    with index.connect() as conn:
        count = int(conn.execute("select count(*) from records where source=?", (source,)).fetchone()[0])
        rows = conn.execute(
            "select lane, count(*) as n from records where source=? group by lane",
            (source,),
        ).fetchall()
    return count, {str(row["lane"]): int(row["n"]) for row in rows}


def _fast_metadata_counts(
    artifact_dir: Path,
    index: SourceIndex,
    *,
    old_source_count: int,
    old_lane_counts: dict[str, int],
    records: list[object],
) -> tuple[dict[str, int], dict[str, int], int, int]:
    status = read_json(artifact_dir / "source_status.json", {})
    if not isinstance(status, dict):
        status = {}
    source_counts_payload = status.get("source_counts")
    lanes_payload = status.get("lanes")
    record_count = status.get("record_count")
    species_count = status.get("species_count")
    if (
        not isinstance(source_counts_payload, dict)
        or not isinstance(lanes_payload, dict)
        or not isinstance(record_count, int)
        or not isinstance(species_count, int)
    ):
        summary = index.summary()
        return source_counts(index), summary["lanes"], summary["record_count"], summary["species_count"]

    counts = {str(source): int(count) for source, count in source_counts_payload.items()}
    lane_counts = {str(lane): int(count) for lane, count in lanes_payload.items()}
    new_lane_counts = Counter(str(getattr(record, "lane")) for record in records)
    counts[DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID] = len(records)
    for lane, old_count in old_lane_counts.items():
        lane_counts[lane] = max(0, int(lane_counts.get(lane, 0)) - old_count)
    for lane, new_count in new_lane_counts.items():
        lane_counts[lane] = int(lane_counts.get(lane, 0)) + new_count
    lane_counts = {lane: count for lane, count in lane_counts.items() if count > 0}
    total = max(0, int(record_count) - old_source_count + len(records))
    return counts, lane_counts, total, int(species_count)


def ingest_drosophila_suzukii_video_atoms(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    retrieved_at: str | None = None,
    max_video_bytes: int = 750_000_000,
    mirror_videos: bool = False,
    generate_artifacts: bool = False,
    allow_unclear_license: bool = False,
    allowed_licenses: Iterable[str] | None = None,
    fetch_video_bytes_fn: Callable[[str, int], bytes] | None = None,
    probe_video_file_fn: Callable[[Path], dict[str, object]] | None = None,
    artifact_generator_fn: Callable[[Path, Path, dict[str, object]], dict[str, object]] | None = None,
    include_dryad_frame_archives: bool = True,
) -> dict[str, object]:
    result = build_drosophila_suzukii_video_atom_records(
        artifact_dir,
        retrieved_at=retrieved_at,
        max_video_bytes=max_video_bytes,
        mirror_videos=mirror_videos,
        generate_artifacts=generate_artifacts,
        allow_unclear_license=allow_unclear_license,
        allowed_licenses=allowed_licenses,
        fetch_video_bytes_fn=fetch_video_bytes_fn,
        probe_video_file_fn=probe_video_file_fn,
        artifact_generator_fn=artifact_generator_fn,
        include_dryad_frame_archives=include_dryad_frame_archives,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    old_source_count, old_lane_counts = _source_stats(index, DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID)
    index.replace_source_records(
        DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID,
        result.records,
        update_fts=False,
        delete_existing_fts=False,
    )
    gaps = _replace_source_gaps(artifact_dir / "gaps.json", result.gaps)
    atoms = _atom_counts(index)
    counts, lanes, record_count, species_count = _fast_metadata_counts(
        artifact_dir,
        index,
        old_source_count=old_source_count,
        old_lane_counts=old_lane_counts,
        records=result.records,
    )
    source_payload = {
        "source": DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID,
        "record_count": counts.get(DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID, 0),
        "video_asset_count": atoms.get("video_asset", 0),
        "mirrored_video_count": result.mirrored_video_count,
        "verified_video_count": result.verified_video_count,
        "artifact_count": sum(atoms.get(atom_type, 0) for atom_type in ("video_thumbnail", "video_keyframe", "video_preview_clip", "video_frame_manifest")),
        "motion_row_count": atoms.get("video_motion_row", 0),
        "gap_count": atoms.get("video_gap", 0),
        "method": "derived Drosophila suzukii video atoms from indexed repository media and supplement manifests",
    }

    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        if filename == "source_receipt.json":
            sources = payload.get("sources")
            if not isinstance(sources, dict):
                sources = {}
            sources[DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID] = source_payload
        else:
            sources = payload.get("sources")
            if not isinstance(sources, list):
                sources = []
            if DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID not in sources:
                sources.append(DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = counts
        payload["record_count"] = record_count
        payload["species_count"] = species_count
        payload["lanes"] = lanes
        payload["gap_count"] = len(gaps)
        payload[DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID] = source_payload
        write_json(path, payload)
    write_json(artifact_dir / "gaps.json", gaps)
    return {
        "ok": True,
        "source": DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID,
        "artifact_dir": artifact_dir.as_posix(),
        **source_payload,
        "source_counts": counts,
        "lanes": lanes,
    }


def _split_csv(value: str | None) -> tuple[str, ...] | None:
    if not value:
        return None
    return tuple(part.strip() for part in value.split(",") if part.strip()) or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build queryable Drosophila suzukii video atoms from indexed Ask Insects sources.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    parser.add_argument("--max-video-bytes", type=int, default=750_000_000)
    parser.add_argument("--mirror-videos", action="store_true")
    parser.add_argument("--generate-artifacts", action="store_true")
    parser.add_argument("--allow-unclear-license", action="store_true")
    parser.add_argument("--allowed-licenses")
    args = parser.parse_args(argv)
    result = ingest_drosophila_suzukii_video_atoms(
        artifact_dir=Path(args.artifact_dir),
        retrieved_at=args.retrieved_at,
        max_video_bytes=args.max_video_bytes,
        mirror_videos=args.mirror_videos,
        generate_artifacts=args.generate_artifacts,
        allow_unclear_license=args.allow_unclear_license,
        allowed_licenses=_split_csv(args.allowed_licenses),
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
