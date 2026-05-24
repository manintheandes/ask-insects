#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR, write_json
from askinsects.index import SourceIndex
from askinsects.sources.extracted_facts import (
    EXTRACTED_FACTS_SOURCE_ID,
    MAX_CANDIDATE_TEXT_CHARS,
    build_extracted_fact_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [gap for gap in existing if not (isinstance(gap, dict) and gap.get("source") == EXTRACTED_FACTS_SOURCE_ID)]
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
        "source": EXTRACTED_FACTS_SOURCE_ID,
        "record_count": len(result.records),
        "candidate_count": result.candidate_count,
        "source_record_count": result.source_record_count,
        "fulltext_unit_count": result.fulltext_unit_count,
        "max_fulltext_units": result.max_fulltext_units,
        "max_candidate_text_chars": MAX_CANDIDATE_TEXT_CHARS,
        "selected_fulltext_unit_count": result.selected_fulltext_unit_count,
        "truncated_fulltext_unit_count": result.truncated_fulltext_unit_count,
        "selected_record_text_count": result.selected_record_text_count,
        "supplement_manifest_count": result.supplement_manifest_count,
        "discovered_supplement_count": result.discovered_supplement_count,
        "downloaded_supplement_file_count": result.downloaded_supplement_file_count,
        "parsed_supplement_file_count": result.parsed_supplement_file_count,
        "parsed_supplement_row_count": result.parsed_supplement_row_count,
        "fact_counts": result.fact_counts,
        "gap_count": len(result.gaps),
        "method": "deterministic supplement manifest discovery, supported supplement table parsing, and cross-lane Aedes fact extraction from literature records and bounded legal full-text units",
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[EXTRACTED_FACTS_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if EXTRACTED_FACTS_SOURCE_ID not in sources:
                sources.append(EXTRACTED_FACTS_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload["aedes_extracted_facts"] = source_payload
        write_json(path, payload)
    return {
        "ok": True,
        "source": EXTRACTED_FACTS_SOURCE_ID,
        "record_count": len(result.records),
        "candidate_count": result.candidate_count,
        "source_record_count": result.source_record_count,
        "fulltext_unit_count": result.fulltext_unit_count,
        "max_fulltext_units": result.max_fulltext_units,
        "max_candidate_text_chars": MAX_CANDIDATE_TEXT_CHARS,
        "selected_fulltext_unit_count": result.selected_fulltext_unit_count,
        "truncated_fulltext_unit_count": result.truncated_fulltext_unit_count,
        "selected_record_text_count": result.selected_record_text_count,
        "supplement_manifest_count": result.supplement_manifest_count,
        "discovered_supplement_count": result.discovered_supplement_count,
        "downloaded_supplement_file_count": result.downloaded_supplement_file_count,
        "parsed_supplement_file_count": result.parsed_supplement_file_count,
        "parsed_supplement_row_count": result.parsed_supplement_row_count,
        "fact_counts": result.fact_counts,
        "gap_count": len(result.gaps),
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_extracted_facts(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    retrieved_at: str | None = None,
    max_fulltext_units: int | None = 5000,
    discover_supplements: bool = False,
    download_supplements: bool = False,
    fetch_supplement_metadata_fn=None,
    fetch_supplement_file_fn=None,
    max_supplement_files: int = 100,
    max_supplement_bytes: int = 2_000_000,
) -> dict[str, object]:
    result = build_extracted_fact_records(
        artifact_dir,
        retrieved_at=retrieved_at,
        max_fulltext_units=max_fulltext_units,
        discover_supplements=discover_supplements,
        download_supplements=download_supplements,
        fetch_supplement_metadata_fn=fetch_supplement_metadata_fn,
        fetch_supplement_file_fn=fetch_supplement_file_fn,
        max_supplement_files=max_supplement_files,
        max_supplement_bytes=max_supplement_bytes,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.delete_source(EXTRACTED_FACTS_SOURCE_ID)
    index.upsert_records(result.records)
    return _update_metadata(artifact_dir, result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract cross-lane Aedes facts and supplement manifests from indexed literature.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    parser.add_argument("--max-fulltext-units", type=int, default=5000)
    parser.add_argument("--discover-supplements", action="store_true")
    parser.add_argument("--download-supplements", action="store_true")
    parser.add_argument("--max-supplement-files", type=int, default=100)
    parser.add_argument("--max-supplement-bytes", type=int, default=2_000_000)
    args = parser.parse_args(argv)
    result = ingest_extracted_facts(
        artifact_dir=Path(args.artifact_dir),
        retrieved_at=args.retrieved_at,
        max_fulltext_units=args.max_fulltext_units,
        discover_supplements=args.discover_supplements,
        download_supplements=args.download_supplements,
        max_supplement_files=args.max_supplement_files,
        max_supplement_bytes=args.max_supplement_bytes,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
