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
from askinsects.ingest_runner import run_source_ingest
from askinsects.sources.vector_competence_assays import (
    VECTOR_COMPETENCE_ASSAY_SOURCE_ID,
    build_vector_competence_assay_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [gap for gap in existing if not (isinstance(gap, dict) and gap.get("source") == VECTOR_COMPETENCE_ASSAY_SOURCE_ID)]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_count(index: SourceIndex) -> int:
    with index.connect() as conn:
        return int(
            conn.execute(
                "select count(*) as n from records where source=?",
                (VECTOR_COMPETENCE_ASSAY_SOURCE_ID,),
            ).fetchone()["n"]
        )


def _source_counts(index: SourceIndex) -> dict[str, int]:
    return {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=1000)
    }


def _update_metadata(artifact_dir: Path, result, *, ok: bool = True, preserved_existing: bool = False) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    source_counts = _source_counts(index)
    installed_record_count = _source_count(index)
    source_payload = {
        "source": VECTOR_COMPETENCE_ASSAY_SOURCE_ID,
        "record_count": installed_record_count,
        "refresh_record_count": len(result.records),
        "candidate_count": result.candidate_count,
        "parsed_table_row_count": result.parsed_table_row_count,
        "source_record_count": result.source_record_count,
        "fulltext_unit_count": result.fulltext_unit_count,
        "gap_count": len(result.gaps),
        "refresh_failed": not ok,
        "preserved_existing": preserved_existing,
        "method": "deterministic assay-candidate extraction from Aedes literature records, legal full-text units, and schema-validated parsed supplement table rows from aedes_extracted_facts",
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[VECTOR_COMPETENCE_ASSAY_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if VECTOR_COMPETENCE_ASSAY_SOURCE_ID not in sources:
                sources.append(VECTOR_COMPETENCE_ASSAY_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload["aedes_vector_competence_assays"] = source_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "source": VECTOR_COMPETENCE_ASSAY_SOURCE_ID,
        "record_count": installed_record_count,
        "refresh_record_count": len(result.records),
        "candidate_count": result.candidate_count,
        "parsed_table_row_count": result.parsed_table_row_count,
        "source_record_count": result.source_record_count,
        "fulltext_unit_count": result.fulltext_unit_count,
        "gap_count": len(result.gaps),
        "preserved_existing": preserved_existing,
        "source_counts": source_counts,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_vector_competence_assays(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    result = build_vector_competence_assay_records(artifact_dir, retrieved_at=retrieved)
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    outcome = run_source_ingest(
        index=index,
        artifact_dir=artifact_dir,
        source_id=VECTOR_COMPETENCE_ASSAY_SOURCE_ID,
        records=result.records,
        gaps=result.gaps,
        retrieved_at=retrieved,
        persist_gap_records=True,  # gaps are plain dicts; runner persists them unconditionally
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
    parser = argparse.ArgumentParser(description="Extract Aedes vector-competence assay candidates from indexed literature and full text.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_vector_competence_assays(
        artifact_dir=Path(args.artifact_dir),
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
