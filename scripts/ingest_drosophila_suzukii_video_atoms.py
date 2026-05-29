#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.replace_source_records(DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID, result.records)
    gaps = _replace_source_gaps(artifact_dir / "gaps.json", result.gaps)
    summary = index.summary()
    counts = source_counts(index)
    atoms = _atom_counts(index)
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
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
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
        "lanes": summary["lanes"],
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
