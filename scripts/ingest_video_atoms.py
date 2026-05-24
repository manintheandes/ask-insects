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

from askinsects.builder import DEFAULT_ARTIFACT_DIR, write_json
from askinsects.index import SourceIndex
from askinsects.sources.video_atoms import VIDEO_ATOMS_SOURCE_ID, build_video_atom_records


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [gap for gap in existing if not (isinstance(gap, dict) and gap.get("source") == VIDEO_ATOMS_SOURCE_ID)]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=1000)
    }


def _update_metadata(artifact_dir: Path, result) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    source_payload = {
        "source": VIDEO_ATOMS_SOURCE_ID,
        "record_count": len(result.records),
        "video_asset_count": result.video_asset_count,
        "mirrored_video_count": result.mirrored_video_count,
        "verified_video_count": result.verified_video_count,
        "artifact_count": result.artifact_count,
        "motion_row_count": result.motion_row_count,
        "discovery_candidate_count": result.discovery_candidate_count,
        "gap_count": len(result.gaps),
        "method": "derived Aedes aegypti video atoms from indexed video manifests, bounded mirrors, ffprobe metadata, inspectable artifacts, motion tables, and repository discovery gaps",
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[VIDEO_ATOMS_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if VIDEO_ATOMS_SOURCE_ID not in sources:
                sources.append(VIDEO_ATOMS_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload["aedes_video_atoms"] = source_payload
        write_json(path, payload)
    return {
        "ok": True,
        "source": VIDEO_ATOMS_SOURCE_ID,
        "record_count": len(result.records),
        "video_asset_count": result.video_asset_count,
        "mirrored_video_count": result.mirrored_video_count,
        "verified_video_count": result.verified_video_count,
        "artifact_count": result.artifact_count,
        "motion_row_count": result.motion_row_count,
        "discovery_candidate_count": result.discovery_candidate_count,
        "gap_count": len(result.gaps),
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_video_atoms(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    retrieved_at: str | None = None,
    max_video_bytes: int = 750_000_000,
    mirror_videos: bool = False,
    generate_artifacts: bool = False,
    discover_sources: bool = False,
    allow_unclear_license: bool = False,
    allowed_licenses: Iterable[str] | None = None,
    fetch_video_bytes_fn: Callable[[str, int], bytes] | None = None,
    probe_video_file_fn: Callable[[Path], dict[str, object]] | None = None,
    artifact_generator_fn: Callable[[Path, Path, dict[str, object]], dict[str, object]] | None = None,
    discovery_clients: dict[str, Callable[[], list[dict[str, object]]]] | None = None,
    max_discovery_results: int = 1000,
    motion_table_paths: Iterable[Path] | None = None,
) -> dict[str, object]:
    result = build_video_atom_records(
        artifact_dir,
        retrieved_at=retrieved_at,
        max_video_bytes=max_video_bytes,
        mirror_videos=mirror_videos,
        generate_artifacts=generate_artifacts,
        discover_sources=discover_sources,
        allow_unclear_license=allow_unclear_license,
        allowed_licenses=allowed_licenses,
        fetch_video_bytes_fn=fetch_video_bytes_fn,
        probe_video_file_fn=probe_video_file_fn,
        artifact_generator_fn=artifact_generator_fn,
        discovery_clients=discovery_clients,
        max_discovery_results=max_discovery_results,
        motion_table_paths=motion_table_paths,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.delete_source(VIDEO_ATOMS_SOURCE_ID)
    index.upsert_records(result.records)
    return _update_metadata(artifact_dir, result)


def _split_csv(value: str | None) -> tuple[str, ...] | None:
    if not value:
        return None
    return tuple(part.strip() for part in value.split(",") if part.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build queryable Aedes aegypti video atoms from indexed video sources.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    parser.add_argument("--max-video-bytes", type=int, default=750_000_000)
    parser.add_argument("--mirror-videos", action="store_true")
    parser.add_argument("--generate-artifacts", action="store_true")
    parser.add_argument("--discover-sources", action="store_true")
    parser.add_argument("--allow-unclear-license", action="store_true")
    parser.add_argument("--allowed-licenses", help="Comma-separated license substrings allowed for mirroring.")
    parser.add_argument("--motion-table", action="append", default=[])
    parser.add_argument("--max-discovery-results", type=int, default=1000)
    args = parser.parse_args(argv)
    result = ingest_video_atoms(
        artifact_dir=Path(args.artifact_dir),
        retrieved_at=args.retrieved_at,
        max_video_bytes=args.max_video_bytes,
        mirror_videos=args.mirror_videos,
        generate_artifacts=args.generate_artifacts,
        discover_sources=args.discover_sources,
        allow_unclear_license=args.allow_unclear_license,
        allowed_licenses=_split_csv(args.allowed_licenses),
        motion_table_paths=[Path(path) for path in args.motion_table],
        max_discovery_results=args.max_discovery_results,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
