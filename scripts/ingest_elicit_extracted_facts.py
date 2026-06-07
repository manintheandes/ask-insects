#!/usr/bin/env python3
"""Paper-depth mining for the Elicit discovery lanes.

Runs the generic extracted-facts engine over each Elicit discovery source so
every discovered paper gets a depth outcome (extracted candidate facts from text,
plus supplement audit atoms). Reuses the existing per-species fact families and
the standard safe persistence path. One generic loop, no per-source clones.
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
from askinsects.sources.elicit_extracted_facts import ELICIT_EXTRACTED_FACTS_PROFILES


def ingest(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    retrieved_at: str | None = None,
    max_fulltext_units: int = 2000,
    discover_supplements: bool = False,
    download_supplements: bool = False,
    max_supplement_discovery_records: int = 500,
    max_repository_supplement_discovery_records: int = 100,
    max_supplement_files: int = 50,
    max_supplement_bytes: int = DEFAULT_MAX_SUPPLEMENT_BYTES,
    max_pdf_supplement_files: int = 10,
    profiles=ELICIT_EXTRACTED_FACTS_PROFILES,
) -> dict:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    results = []
    for profile in profiles:
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
            index=index,
            artifact_dir=artifact_dir,
            source_id=profile.source_id,
            records=result.records,
            gaps=result.gaps,
            retrieved_at=retrieved_at or "",
        )
        results.append({
            "source": profile.source_id,
            "input": profile.input_literature_source_id,
            "record_count": len(result.records),
            "candidate_count": result.candidate_count,
            "gap_count": len(result.gaps),
            "refresh_failed": outcome["refresh_failed"],
            "ok": not outcome["refresh_failed"],
        })
    return {"ok": all(r["ok"] for r in results), "results": results, "artifact_dir": artifact_dir.as_posix()}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Mine paper-depth facts for the Elicit discovery lanes.")
    p.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    p.add_argument("--retrieved-at")
    p.add_argument("--max-fulltext-units", type=int, default=2000)
    p.add_argument("--discover-supplements", action="store_true")
    p.add_argument("--download-supplements", action="store_true")
    p.add_argument("--max-supplement-discovery-records", type=int, default=500)
    p.add_argument("--max-repository-supplement-discovery-records", type=int, default=100)
    p.add_argument("--max-supplement-files", type=int, default=50)
    p.add_argument("--max-supplement-bytes", type=int, default=DEFAULT_MAX_SUPPLEMENT_BYTES)
    p.add_argument("--max-pdf-supplement-files", type=int, default=10)
    args = p.parse_args(argv)
    result = ingest(
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
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
