#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR, write_json
from askinsects.index import SourceIndex
from askinsects.ingest_runner import run_source_ingest
from askinsects.sources.image_atoms import IMAGE_ATOMS_SOURCE_ID, build_image_atom_records


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [gap for gap in existing if not (isinstance(gap, dict) and gap.get("source") == IMAGE_ATOMS_SOURCE_ID)]
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
                (IMAGE_ATOMS_SOURCE_ID,),
            ).fetchone()["n"]
        )


def _update_metadata(artifact_dir: Path, result, *, ok: bool = True, preserved_existing: bool = False) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    source_payload = {
        "source": IMAGE_ATOMS_SOURCE_ID,
        "record_count": len(result.records),
        "image_asset_count": result.image_asset_count,
        "image_label_count": result.image_label_count,
        "image_gap_count": result.image_gap_count,
        "mirrored_image_count": result.mirrored_image_count,
        "verified_image_count": result.verified_image_count,
        "gap_count": len(result.gaps),
        "method": "derived Aedes aegypti image atoms from indexed iNaturalist and Mosquito Alert still-image media payloads, with optional bounded image-byte mirrors and checksum/dimension verification",
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
            sources[IMAGE_ATOMS_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if IMAGE_ATOMS_SOURCE_ID not in sources:
                sources.append(IMAGE_ATOMS_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload[IMAGE_ATOMS_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "source": IMAGE_ATOMS_SOURCE_ID,
        "record_count": len(result.records),
        "preserved_existing": preserved_existing,
        "image_asset_count": result.image_asset_count,
        "image_label_count": result.image_label_count,
        "image_gap_count": result.image_gap_count,
        "mirrored_image_count": result.mirrored_image_count,
        "verified_image_count": result.verified_image_count,
        "gap_count": len(result.gaps),
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def _split_csv(value: str | None) -> tuple[str, ...] | None:
    if not value:
        return None
    return tuple(part.strip() for part in value.split(",") if part.strip())


def ingest_image_atoms(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    retrieved_at: str | None = None,
    mirror_images: bool = False,
    max_image_bytes: int = 5_000_000,
    max_image_mirrors: int = 250,
    allow_unclear_license: bool = False,
    allowed_licenses: tuple[str, ...] | None = None,
    fetch_image_bytes_fn: Callable[[str, int], tuple[bytes, str | None]] | None = None,
) -> dict[str, object]:
    result = build_image_atom_records(
        artifact_dir,
        retrieved_at=retrieved_at,
        mirror_images=mirror_images,
        max_image_bytes=max_image_bytes,
        max_image_mirrors=max_image_mirrors,
        allow_unclear_license=allow_unclear_license,
        allowed_licenses=allowed_licenses,
        fetch_image_bytes_fn=fetch_image_bytes_fn,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    outcome = run_source_ingest(
        index=index,
        artifact_dir=artifact_dir,
        source_id=IMAGE_ATOMS_SOURCE_ID,
        records=result.records,
        gaps=result.gaps,
        retrieved_at=retrieved_at or "",
        raw_artifacts=getattr(result, "raw_artifacts", None),
        persist_gap_records=False,  # adapter builds gap EvidenceRecords (image_gap) into result.records
    )
    refresh_failed = outcome["refresh_failed"]
    preserved_existing = outcome["preserved_existing"]
    return _update_metadata(
        artifact_dir,
        result,
        ok=not refresh_failed,
        preserved_existing=preserved_existing,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build queryable Aedes aegypti image atoms from indexed still-image sources.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    parser.add_argument("--mirror-images", action="store_true")
    parser.add_argument("--max-image-bytes", type=int, default=5_000_000)
    parser.add_argument("--max-image-mirrors", type=int, default=250)
    parser.add_argument("--allow-unclear-license", action="store_true")
    parser.add_argument("--allowed-licenses")
    args = parser.parse_args(argv)
    result = ingest_image_atoms(
        artifact_dir=Path(args.artifact_dir),
        retrieved_at=args.retrieved_at,
        mirror_images=args.mirror_images,
        max_image_bytes=args.max_image_bytes,
        max_image_mirrors=args.max_image_mirrors,
        allow_unclear_license=args.allow_unclear_license,
        allowed_licenses=_split_csv(args.allowed_licenses),
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
