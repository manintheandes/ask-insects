#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR, utc_now, write_json
from askinsects.index import SourceIndex
from askinsects.sources.opendatasus_dengue_surveillance import (
    OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID,
    OpenDataSusDengueFileSpec,
    default_opendatasus_dengue_file_specs,
    fetch_opendatasus_dengue_surveillance_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [
        gap
        for gap in existing
        if not (isinstance(gap, dict) and gap.get("source") == OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID)
    ]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=5000)
    }


def _update_metadata(artifact_dir: Path, result, retrieved_at: str) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    source_payload = {
        "source": OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID,
        "requested_urls": result.requested_urls,
        "record_count": len(result.records),
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
        "file_count": result.file_count,
        "source_file_record_count": result.source_file_record_count,
        "country_year_record_count": result.country_year_record_count,
        "state_year_record_count": result.state_year_record_count,
        "country_week_record_count": result.country_week_record_count,
        "state_week_record_count": result.state_week_record_count,
        "input_csv_row_count": result.row_count,
        "years": result.years,
        "retrieved_at": retrieved_at,
        "method": "official Brazil OpenDataSUS SINAN dengue CSV ZIP files parsed into source-file, country-year, state-year, country-week, and residence-state-week public-health aggregate records for Aedes aegypti intelligence",
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID not in sources:
                sources.append(OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload["fully_parsed"] = gap_count == 0
        payload["parsed_scope"] = "Brazil OpenDataSUS current dengue CSV ZIPs aggregated by source file, country-year, state-year, country-week, and residence-state-week"
        payload[OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {
        "ok": True,
        "source": OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID,
        "record_count": len(result.records),
        "gap_count": len(result.gaps),
        "file_count": result.file_count,
        "source_file_record_count": result.source_file_record_count,
        "country_year_record_count": result.country_year_record_count,
        "state_year_record_count": result.state_year_record_count,
        "country_week_record_count": result.country_week_record_count,
        "state_week_record_count": result.state_week_record_count,
        "input_csv_row_count": result.row_count,
        "years": result.years,
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def _file_specs_from_args(years: list[int], file_urls: list[str]) -> list[OpenDataSusDengueFileSpec]:
    if file_urls:
        selected_years = years or list(range(1, len(file_urls) + 1))
        if len(selected_years) != len(file_urls):
            raise ValueError("--year count must match --file-url count when custom URLs are supplied")
        return [OpenDataSusDengueFileSpec(year=year, url=url) for year, url in zip(selected_years, file_urls, strict=True)]
    return default_opendatasus_dengue_file_specs(years or None)


def ingest_opendatasus_dengue_surveillance(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    years: list[int] | None = None,
    file_urls: list[str] | None = None,
    fetch_bytes=None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    specs = _file_specs_from_args(years or [], file_urls or [])
    result = fetch_opendatasus_dengue_surveillance_records(
        specs,
        raw_dir=artifact_dir / "raw" / "opendatasus_dengue_surveillance",
        fetch_bytes=fetch_bytes,
        retrieved_at=retrieved,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.replace_source_records(OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID, result.records)
    return _update_metadata(artifact_dir, result, retrieved)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest Brazil OpenDataSUS SINAN dengue CSV ZIP aggregates for Aedes aegypti public-health intelligence.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--year", type=int, action="append", default=[], help="OpenDataSUS annual file year. Defaults to current configured years.")
    parser.add_argument("--file-url", action="append", default=[], help="Custom OpenDataSUS dengue CSV ZIP URL. Can be passed multiple times.")
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_opendatasus_dengue_surveillance(
        artifact_dir=Path(args.artifact_dir),
        years=args.year,
        file_urls=args.file_url,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
