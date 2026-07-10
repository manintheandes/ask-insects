#!/usr/bin/env python3
"""Generic paper-depth miner for any literature lane (insectsource mandatory-mining rule).

Runs the extracted-facts engine over one or all profiles in
LITERATURE_DEPTH_PROFILES so every paper in those lanes gets a depth outcome.
Reuses the generic engine and the standard safe persistence path; no per-source
clones, no engine changes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR, utc_now  # noqa: E402
from askinsects.index import SourceIndex  # noqa: E402
from askinsects.ingest_runner import run_source_ingest  # noqa: E402
from askinsects.sources.extracted_facts import (  # noqa: E402
    DEFAULT_MAX_SUPPLEMENT_BYTES,
    build_extracted_fact_records,
)
from askinsects.sources.literature_depth_profiles import LITERATURE_DEPTH_PROFILES  # noqa: E402


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _update_source_metadata(
    *,
    artifact_dir: Path,
    profile,
    result,
    outcome: dict[str, object],
    retrieved_at: str,
) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = {
        str(row["source"]): int(row["n"])
        for row in index.sql(
            "select source, count(*) as n from records group by source order by source",
            limit=10_000,
        )
    }
    source_payload = {
        "source": profile.source_id,
        "input_source": profile.input_literature_source_id,
        "record_count": int(outcome["record_count"]),
        "refresh_record_count": len(result.records),
        "candidate_count": result.candidate_count,
        "source_record_count": result.source_record_count,
        "fulltext_unit_count": result.fulltext_unit_count,
        "supplement_audit_record_count": result.supplement_audit_record_count,
        "fact_counts": result.fact_counts,
        "gap_count": len(result.gaps),
        "retrieved_at": retrieved_at,
        "refresh_failed": bool(outcome["refresh_failed"]),
        "preserved_existing": bool(outcome["preserved_existing"]),
    }
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path)
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[profile.source_id] = source_payload
        else:
            source_list = (
                [str(source) for source in sources] if isinstance(sources, list) else []
            )
            if profile.source_id not in source_list:
                source_list.append(profile.source_id)
            payload["sources"] = source_list
        payload[profile.source_id] = source_payload
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        _write_json_atomic(path, payload)
    return source_payload


def ingest_profile(
    profile,
    *,
    artifact_dir,
    retrieved_at,
    max_fulltext_units,
    discover_supplements,
    download_supplements,
    max_supplement_discovery_records,
    max_repository_supplement_discovery_records,
    max_supplement_files,
    max_supplement_bytes,
    max_pdf_supplement_files,
) -> dict:
    effective_retrieved_at = retrieved_at or utc_now()
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    result = build_extracted_fact_records(
        artifact_dir,
        retrieved_at=effective_retrieved_at,
        max_fulltext_units=max_fulltext_units,
        discover_supplements=discover_supplements,
        download_supplements=download_supplements,
        max_supplement_discovery_records=max_supplement_discovery_records,
        max_repository_supplement_discovery_records=max_repository_supplement_discovery_records,
        max_supplement_files=max_supplement_files,
        max_supplement_bytes=max_supplement_bytes,
        max_pdf_supplement_files=max_pdf_supplement_files,
        profile=profile,
    )
    outcome = run_source_ingest(
        index=index,
        artifact_dir=artifact_dir,
        source_id=profile.source_id,
        records=result.records,
        gaps=result.gaps,
        retrieved_at=effective_retrieved_at,
    )
    _update_source_metadata(
        artifact_dir=artifact_dir,
        profile=profile,
        result=result,
        outcome=outcome,
        retrieved_at=effective_retrieved_at,
    )
    return {
        "source": profile.source_id,
        "input": profile.input_literature_source_id,
        "record_count": outcome["record_count"],
        "refresh_record_count": len(result.records),
        "candidate_count": result.candidate_count,
        "gap_count": len(result.gaps),
        "refresh_failed": outcome["refresh_failed"],
        "preserved_existing": outcome["preserved_existing"],
        "retrieved_at": effective_retrieved_at,
        "ok": not outcome["refresh_failed"],
    }


def ingest_literature_depth(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    profile: str | None = None,
    all_profiles: bool = False,
    retrieved_at: str | None = None,
    max_fulltext_units: int = 2000,
    discover_supplements: bool = False,
    download_supplements: bool = False,
    max_supplement_discovery_records: int = 2000,
    max_repository_supplement_discovery_records: int = 100,
    max_supplement_files: int = 50,
    max_supplement_bytes: int = DEFAULT_MAX_SUPPLEMENT_BYTES,
    max_pdf_supplement_files: int = 10,
) -> dict[str, object]:
    if all_profiles == bool(profile):
        return {
            "ok": False,
            "error": "pass exactly one of profile or all_profiles",
            "known": sorted(LITERATURE_DEPTH_PROFILES),
        }
    if profile and profile not in LITERATURE_DEPTH_PROFILES:
        return {
            "ok": False,
            "error": f"unknown profile {profile}",
            "known": sorted(LITERATURE_DEPTH_PROFILES),
        }
    profiles = (
        list(LITERATURE_DEPTH_PROFILES.values())
        if all_profiles
        else [LITERATURE_DEPTH_PROFILES[str(profile)]]
    )
    results = [
        ingest_profile(
            selected_profile,
            artifact_dir=artifact_dir,
            retrieved_at=retrieved_at,
            max_fulltext_units=max_fulltext_units,
            discover_supplements=discover_supplements,
            download_supplements=download_supplements,
            max_supplement_discovery_records=max_supplement_discovery_records,
            max_repository_supplement_discovery_records=max_repository_supplement_discovery_records,
            max_supplement_files=max_supplement_files,
            max_supplement_bytes=max_supplement_bytes,
            max_pdf_supplement_files=max_pdf_supplement_files,
        )
        for selected_profile in profiles
    ]
    return {"ok": all(result["ok"] for result in results), "results": results}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Mine paper-depth facts for any literature lane."
    )
    p.add_argument(
        "--profile",
        help="output source id from LITERATURE_DEPTH_PROFILES; omit with --all",
    )
    p.add_argument(
        "--all", action="store_true", help="run every profile in the registry"
    )
    p.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    p.add_argument("--retrieved-at")
    p.add_argument("--max-fulltext-units", type=int, default=2000)
    p.add_argument("--discover-supplements", action="store_true")
    p.add_argument("--download-supplements", action="store_true")
    p.add_argument("--max-supplement-discovery-records", type=int, default=2000)
    p.add_argument(
        "--max-repository-supplement-discovery-records", type=int, default=100
    )
    p.add_argument("--max-supplement-files", type=int, default=50)
    p.add_argument(
        "--max-supplement-bytes", type=int, default=DEFAULT_MAX_SUPPLEMENT_BYTES
    )
    p.add_argument("--max-pdf-supplement-files", type=int, default=10)
    args = p.parse_args(argv)

    result = ingest_literature_depth(
        artifact_dir=Path(args.artifact_dir),
        profile=args.profile,
        all_profiles=args.all,
        retrieved_at=args.retrieved_at,
        max_fulltext_units=args.max_fulltext_units,
        discover_supplements=args.discover_supplements,
        download_supplements=args.download_supplements,
        max_supplement_discovery_records=args.max_supplement_discovery_records,
        max_repository_supplement_discovery_records=args.max_repository_supplement_discovery_records,
        max_supplement_files=args.max_supplement_files,
        max_supplement_bytes=args.max_supplement_bytes,
        max_pdf_supplement_files=args.max_pdf_supplement_files,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
