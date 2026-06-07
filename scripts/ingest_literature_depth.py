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
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR
from askinsects.index import SourceIndex
from askinsects.ingest_runner import run_source_ingest
from askinsects.sources.extracted_facts import DEFAULT_MAX_SUPPLEMENT_BYTES, build_extracted_fact_records
from askinsects.sources.literature_depth_profiles import LITERATURE_DEPTH_PROFILES


def ingest_profile(profile, *, artifact_dir, retrieved_at, max_fulltext_units,
                   discover_supplements, download_supplements,
                   max_supplement_discovery_records, max_repository_supplement_discovery_records,
                   max_supplement_files, max_supplement_bytes, max_pdf_supplement_files) -> dict:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    result = build_extracted_fact_records(
        artifact_dir,
        retrieved_at=retrieved_at,
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
        index=index, artifact_dir=artifact_dir, source_id=profile.source_id,
        records=result.records, gaps=result.gaps, retrieved_at=retrieved_at or "",
    )
    return {
        "source": profile.source_id,
        "input": profile.input_literature_source_id,
        "record_count": len(result.records),
        "candidate_count": result.candidate_count,
        "gap_count": len(result.gaps),
        "refresh_failed": outcome["refresh_failed"],
        "ok": not outcome["refresh_failed"],
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Mine paper-depth facts for any literature lane.")
    p.add_argument("--profile", help="output source id from LITERATURE_DEPTH_PROFILES; omit with --all")
    p.add_argument("--all", action="store_true", help="run every profile in the registry")
    p.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    p.add_argument("--retrieved-at")
    p.add_argument("--max-fulltext-units", type=int, default=2000)
    p.add_argument("--discover-supplements", action="store_true")
    p.add_argument("--download-supplements", action="store_true")
    p.add_argument("--max-supplement-discovery-records", type=int, default=2000)
    p.add_argument("--max-repository-supplement-discovery-records", type=int, default=100)
    p.add_argument("--max-supplement-files", type=int, default=50)
    p.add_argument("--max-supplement-bytes", type=int, default=DEFAULT_MAX_SUPPLEMENT_BYTES)
    p.add_argument("--max-pdf-supplement-files", type=int, default=10)
    args = p.parse_args(argv)

    if args.all:
        profiles = list(LITERATURE_DEPTH_PROFILES.values())
    elif args.profile:
        if args.profile not in LITERATURE_DEPTH_PROFILES:
            print(json.dumps({"ok": False, "error": f"unknown profile {args.profile}", "known": sorted(LITERATURE_DEPTH_PROFILES)}))
            return 2
        profiles = [LITERATURE_DEPTH_PROFILES[args.profile]]
    else:
        print(json.dumps({"ok": False, "error": "pass --profile <id> or --all", "known": sorted(LITERATURE_DEPTH_PROFILES)}))
        return 2

    results = []
    for profile in profiles:
        results.append(ingest_profile(
            profile,
            artifact_dir=Path(args.artifact_dir),
            retrieved_at=args.retrieved_at,
            max_fulltext_units=args.max_fulltext_units,
            discover_supplements=args.discover_supplements,
            download_supplements=args.download_supplements,
            max_supplement_discovery_records=args.max_supplement_discovery_records,
            max_repository_supplement_discovery_records=args.max_repository_supplement_discovery_records,
            max_supplement_files=args.max_supplement_files,
            max_supplement_bytes=args.max_supplement_bytes,
            max_pdf_supplement_files=args.max_pdf_supplement_files,
        ))
    print(json.dumps({"ok": all(r["ok"] for r in results), "results": results}, sort_keys=True))
    return 0 if all(r["ok"] for r in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
