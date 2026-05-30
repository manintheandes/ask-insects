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
from askinsects.ingest_runner import run_source_ingest
from askinsects.sources.video_atoms import (
    DISCOVERY_REPOSITORIES,
    DiscoverySweepResult,
    VIDEO_ATOMS_SOURCE_ID,
    build_video_atom_records,
)


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


def _dedupe_records(records):
    deduped = {}
    gap_keys = set()
    for record in records:
        payload = record.payload if isinstance(record.payload, dict) else {}
        if payload.get("atom_type") == "video_gap":
            gap_key = _video_gap_identity_key(payload)
            if gap_key in gap_keys:
                continue
            gap_keys.add(gap_key)
        deduped[record.record_id] = record
    return list(deduped.values())


def _chunks(values: list[str], size: int = 500):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _payload_repository(payload: dict[str, object]) -> str | None:
    repository = payload.get("repository") or payload.get("discovery_repository")
    return str(repository) if repository else None


def _repository_from_video_gap_payload(payload: dict[str, object]) -> str | None:
    repository = _payload_repository(payload)
    if repository:
        return repository
    locator = " ".join(
        str(payload.get(key) or "")
        for key in ("path", "locator", "source_table", "source_url", "raw_path")
    )
    path_repositories = (
        ("raw/pmc_videos/", "pmc_oa"),
        ("raw/dryad_behavior_videos/", "dryad"),
        ("raw/mendeley_behavior_media/", "mendeley"),
        ("raw/osf_flighttrackai_videos/", "osf"),
        ("raw/zenodo_aedes_videos/", "zenodo"),
        ("raw/figshare_aedes_videos/", "figshare"),
    )
    for marker, repository_name in path_repositories:
        if marker in locator:
            return repository_name
    return None


def _video_gap_identity_key(payload: dict[str, object]) -> tuple[str, str, str, str, str]:
    return (
        str(payload.get("source") or VIDEO_ATOMS_SOURCE_ID),
        str(payload.get("lane") or "media"),
        str(payload.get("reason") or ""),
        str(payload.get("record_id") or ""),
        str(payload.get("locator") or ""),
    )


def _delete_duplicate_video_gap_records(index: SourceIndex) -> int:
    with index.connect() as conn:
        rows = conn.execute(
            "SELECT record_id, payload_json FROM record_payloads WHERE source=?",
            (VIDEO_ATOMS_SOURCE_ID,),
        ).fetchall()
        seen: set[tuple[str, str, str, str, str]] = set()
        delete_ids: list[str] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            if not isinstance(payload, dict) or payload.get("atom_type") != "video_gap":
                continue
            key = _video_gap_identity_key(payload)
            if key in seen:
                delete_ids.append(str(row["record_id"]))
            else:
                seen.add(key)
        for chunk in _chunks(delete_ids):
            placeholders = ",".join("?" for _ in chunk)
            conn.execute(f"DELETE FROM records_fts WHERE record_id IN ({placeholders})", chunk)
            conn.execute(f"DELETE FROM record_payloads WHERE record_id IN ({placeholders})", chunk)
            conn.execute(f"DELETE FROM records WHERE record_id IN ({placeholders})", chunk)
    return len(delete_ids)


def _delete_video_atom_repository_records(index: SourceIndex, repositories: Iterable[str]) -> int:
    repository_scope = {str(repository) for repository in repositories}
    if not repository_scope:
        return 0
    with index.connect() as conn:
        rows = conn.execute(
            "SELECT record_id, payload_json FROM record_payloads WHERE source=?",
            (VIDEO_ATOMS_SOURCE_ID,),
        ).fetchall()
        record_payloads: dict[str, dict[str, object]] = {}
        delete_ids: set[str] = set()
        for row in rows:
            payload = json.loads(row["payload_json"])
            if not isinstance(payload, dict):
                continue
            record_id = str(row["record_id"])
            record_payloads[record_id] = payload
            if payload.get("atom_type") == "video_sweep":
                continue
            if _repository_from_video_gap_payload(payload) in repository_scope:
                delete_ids.add(record_id)
        if delete_ids:
            for record_id, payload in record_payloads.items():
                source_asset_id = payload.get("source_video_asset_id")
                if isinstance(source_asset_id, str) and source_asset_id in delete_ids:
                    delete_ids.add(record_id)
        for chunk in _chunks(sorted(delete_ids)):
            placeholders = ",".join("?" for _ in chunk)
            conn.execute(f"DELETE FROM records_fts WHERE record_id IN ({placeholders})", chunk)
            conn.execute(f"DELETE FROM record_payloads WHERE record_id IN ({placeholders})", chunk)
            conn.execute(f"DELETE FROM records WHERE record_id IN ({placeholders})", chunk)
    return len(delete_ids)


def _existing_sweep_receipts(artifact_dir: Path) -> list[dict[str, object]]:
    payload = _read_json(artifact_dir / "source_status.json", {})
    if not isinstance(payload, dict):
        return []
    source_payload = payload.get("aedes_video_atoms")
    if not isinstance(source_payload, dict):
        return []
    receipts = source_payload.get("discovery_sweep_receipts")
    if isinstance(receipts, list):
        return [receipt for receipt in receipts if isinstance(receipt, dict)]
    return []


def _merge_sweep_receipts(artifact_dir: Path, new_receipts: list[dict[str, object]]) -> list[dict[str, object]]:
    by_repository = {
        str(receipt.get("repository")): receipt
        for receipt in _existing_sweep_receipts(artifact_dir)
        if receipt.get("repository")
    }
    for receipt in new_receipts:
        if receipt.get("repository"):
            by_repository[str(receipt["repository"])] = receipt
    return [by_repository[repository] for repository in DISCOVERY_REPOSITORIES if repository in by_repository]


def _validate_discovery_repositories(values: Iterable[str] | None) -> tuple[str, ...] | None:
    if values is None:
        return None
    requested = tuple(dict.fromkeys(str(value) for value in values))
    invalid = [value for value in requested if value not in DISCOVERY_REPOSITORIES]
    if invalid:
        raise ValueError(
            "unknown video discovery repository: "
            + ", ".join(invalid)
            + "; expected one of "
            + ", ".join(DISCOVERY_REPOSITORIES)
        )
    return requested or None


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=1000)
    }


def _video_atom_counts(index: SourceIndex) -> dict[str, int]:
    rows = index.sql(
        """
        select json_extract(payload_json, '$.atom_type') as atom_type, count(*) as n
        from record_payloads
        where source='aedes_video_atoms'
        group by atom_type
        """,
        limit=100,
    )
    return {str(row["atom_type"]): int(row["n"]) for row in rows if row["atom_type"]}


def _count_verified_video_assets(index: SourceIndex) -> int:
    rows = index.sql(
        """
        select count(*) as n
        from record_payloads
        where source='aedes_video_atoms'
          and json_extract(payload_json, '$.atom_type')='video_asset'
          and json_extract(payload_json, '$.verification_status')='verified'
        """,
        limit=1,
    )
    return int(rows[0]["n"]) if rows else 0


def _count_mirrored_video_assets(index: SourceIndex) -> int:
    rows = index.sql(
        """
        select count(*) as n
        from record_payloads
        where source='aedes_video_atoms'
          and json_extract(payload_json, '$.atom_type')='video_asset'
          and coalesce(
            json_extract(payload_json, '$.mirror_path'),
            json_extract(payload_json, '$.raw_asset_path'),
            json_extract(payload_json, '$.mirrored_path'),
            json_extract(payload_json, '$.local_mirror_path')
          ) is not null
        """,
        limit=1,
    )
    return int(rows[0]["n"]) if rows else 0


def _installed_video_gaps(index: SourceIndex) -> list[dict[str, object]]:
    rows = index.sql(
        """
        select payload_json
        from record_payloads
        where source='aedes_video_atoms'
          and json_extract(payload_json, '$.atom_type')='video_gap'
        order by record_id
        """,
        limit=100000,
    )
    gaps: list[dict[str, object]] = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        if isinstance(payload, dict):
            payload.pop("atom_type", None)
            gaps.append(payload)
    return gaps


def _update_metadata(artifact_dir: Path, result, *, merge_existing: bool = False, ok: bool = True, preserved_existing: bool = False) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    atom_counts = _video_atom_counts(index)
    source_record_count = source_counts.get(VIDEO_ATOMS_SOURCE_ID, 0)
    artifact_count = sum(
        atom_counts.get(atom_type, 0)
        for atom_type in ("video_thumbnail", "video_keyframe", "video_preview_clip", "video_frame_manifest")
    )
    installed_gaps = _installed_video_gaps(index)
    discovery_sweep_receipts = (
        _merge_sweep_receipts(artifact_dir, result.discovery_sweep_receipts)
        if merge_existing
        else result.discovery_sweep_receipts
    )
    source_payload = {
        "source": VIDEO_ATOMS_SOURCE_ID,
        "record_count": source_record_count,
        "video_asset_count": atom_counts.get("video_asset", 0),
        "mirrored_video_count": _count_mirrored_video_assets(index),
        "verified_video_count": _count_verified_video_assets(index),
        "artifact_count": artifact_count,
        "motion_row_count": atom_counts.get("video_motion_row", 0),
        "discovery_candidate_count": result.discovery_candidate_count,
        "discovery_sweep_receipts": discovery_sweep_receipts,
        "gap_count": atom_counts.get("video_gap", 0),
        "refresh_record_count": len(result.records),
        "refresh_failed": not ok,
        "preserved_existing": preserved_existing,
        "method": "derived Aedes aegypti video atoms from indexed video manifests, bounded mirrors, ffprobe metadata, inspectable artifacts, motion tables, and repository discovery gaps",
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", installed_gaps)
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
        "ok": ok,
        "source": VIDEO_ATOMS_SOURCE_ID,
        "preserved_existing": preserved_existing,
        "refresh_record_count": len(result.records),
        "record_count": source_payload["record_count"],
        "video_asset_count": source_payload["video_asset_count"],
        "mirrored_video_count": source_payload["mirrored_video_count"],
        "verified_video_count": source_payload["verified_video_count"],
        "artifact_count": source_payload["artifact_count"],
        "motion_row_count": source_payload["motion_row_count"],
        "discovery_candidate_count": result.discovery_candidate_count,
        "discovery_sweep_receipts": discovery_sweep_receipts,
        "gap_count": source_payload["gap_count"],
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
    discovery_clients: dict[str, Callable[[], list[dict[str, object]] | DiscoverySweepResult]] | None = None,
    discovery_repositories: Iterable[str] | None = None,
    max_discovery_results: int = 1000,
    motion_table_paths: Iterable[Path] | None = None,
    merge_existing: bool = False,
    parse_motion_rows: bool = True,
) -> dict[str, object]:
    discovery_repositories = _validate_discovery_repositories(discovery_repositories)
    if discovery_repositories and not merge_existing:
        raise ValueError("discovery_repositories requires merge_existing so scoped video refreshes cannot shrink aedes_video_atoms")
    resolved_motion_table_paths = (
        [path if path.is_absolute() else artifact_dir / path for path in motion_table_paths]
        if motion_table_paths
        else None
    )
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
        discovery_repositories=discovery_repositories,
        max_discovery_results=max_discovery_results,
        motion_table_paths=resolved_motion_table_paths,
        parse_motion_rows=parse_motion_rows,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    records = _dedupe_records(result.records)
    refresh_failed = False
    preserved_existing = False
    if merge_existing:
        if discovery_repositories:
            _delete_video_atom_repository_records(index, discovery_repositories)
        index.upsert_records(records)
    else:
        outcome = run_source_ingest(
            index=index,
            artifact_dir=artifact_dir,
            source_id=VIDEO_ATOMS_SOURCE_ID,
            records=records,
            gaps=result.gaps,
            retrieved_at=retrieved_at or "",
            raw_artifacts=getattr(result, "raw_artifacts", None),
            persist_gap_records=False,  # adapter builds gap EvidenceRecords (video_gap) into result.records
        )
        refresh_failed = outcome["refresh_failed"]
        preserved_existing = outcome["preserved_existing"]
    _delete_duplicate_video_gap_records(index)
    payload = _update_metadata(
        artifact_dir,
        result,
        merge_existing=merge_existing,
        ok=not refresh_failed,
        preserved_existing=preserved_existing,
    )
    payload["merge_existing"] = merge_existing
    if discovery_repositories:
        payload["discovery_repositories"] = list(discovery_repositories)
    payload["parse_motion_rows"] = parse_motion_rows
    return payload


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
    parser.add_argument("--discovery-repository", action="append", choices=DISCOVERY_REPOSITORIES, default=[])
    parser.add_argument("--merge-existing", action="store_true")
    parser.add_argument("--skip-motion-rows", action="store_true")
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
        motion_table_paths=[Path(path) for path in args.motion_table] or None,
        discovery_repositories=args.discovery_repository or None,
        max_discovery_results=args.max_discovery_results,
        merge_existing=args.merge_existing,
        parse_motion_rows=not args.skip_motion_rows,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
