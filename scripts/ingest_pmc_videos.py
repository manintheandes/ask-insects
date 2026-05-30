#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import utc_now, write_json
from askinsects.index import SourceIndex
from askinsects.ingest_runner import run_source_ingest
from askinsects.sources.pmc_videos import DEFAULT_PMC_VIDEO_ARTICLES, PMC_VIDEO_SOURCE_ID, fetch_pmc_video_records


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [gap for gap in existing if not (isinstance(gap, dict) and gap.get("source") == PMC_VIDEO_SOURCE_ID)]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _update_metadata(artifact_dir: Path, result) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=1000)
    }
    pmc_payload = {
        "source": PMC_VIDEO_SOURCE_ID,
        "article_count": result.article_count,
        "video_count": result.video_count,
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if not isinstance(sources, list):
            sources = []
        if PMC_VIDEO_SOURCE_ID not in sources:
            sources.append(PMC_VIDEO_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload["pmc_videos"] = pmc_payload
        write_json(path, payload)
    return {
        "ok": True,
        "source": PMC_VIDEO_SOURCE_ID,
        "record_count": len(result.records),
        "article_count": result.article_count,
        "video_count": result.video_count,
        "gap_count": len(result.gaps),
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def _existing_source_record_count(index: SourceIndex) -> int:
    rows = index.sql(
        f"select count(*) as n from records where source = '{PMC_VIDEO_SOURCE_ID}'",
        limit=1,
    )
    return int(rows[0]["n"]) if rows else 0


def _preserve_existing_metadata(artifact_dir: Path, result, existing_count: int) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=1000)
    }
    pmc_payload = {
        "source": PMC_VIDEO_SOURCE_ID,
        "article_count": result.article_count,
        "video_count": existing_count,
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
        "refresh_skipped": True,
        "refresh_skip_reason": "pmc_refresh_returned_zero_records_preserved_existing_source_rows",
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if not isinstance(sources, list):
            sources = []
        if PMC_VIDEO_SOURCE_ID not in sources:
            sources.append(PMC_VIDEO_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload["pmc_videos"] = pmc_payload
        write_json(path, payload)
    return {
        "ok": True,
        "source": PMC_VIDEO_SOURCE_ID,
        "record_count": existing_count,
        "refreshed_record_count": 0,
        "article_count": result.article_count,
        "video_count": existing_count,
        "gap_count": len(result.gaps),
        "refresh_skipped": True,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_pmc_videos(
    *,
    artifact_dir: Path,
    article_urls: list[str] | None = None,
    fetch_text=None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    result = fetch_pmc_video_records(
        article_urls or list(DEFAULT_PMC_VIDEO_ARTICLES),
        raw_dir=artifact_dir / "raw" / "pmc_videos",
        fetch_text=fetch_text,
        retrieved_at=retrieved,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    existing_count = _existing_source_record_count(index)
    if not result.records and existing_count:
        return _preserve_existing_metadata(artifact_dir, result, existing_count)
    outcome = run_source_ingest(
        index=index,
        artifact_dir=artifact_dir,
        source_id=PMC_VIDEO_SOURCE_ID,
        records=result.records,
        gaps=result.gaps,
        retrieved_at=retrieved,
        raw_artifacts=getattr(result, "raw_artifacts", None),
        persist_gap_records=True,  # adapter produces only plain gap dicts (no gap EvidenceRecords)
    )
    # Note: preserved_existing is the real guard; refresh_record_count reflects the live fetch.
    return _update_metadata(artifact_dir, result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest public PMC Aedes aegypti supplementary videos into an Ask Insects artifact.")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--article-url", action="append", help="PMC article URL to scan. Can be passed multiple times.")
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_pmc_videos(
        artifact_dir=Path(args.artifact_dir),
        article_urls=args.article_url,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
