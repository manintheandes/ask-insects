from __future__ import annotations

from pathlib import Path

from .gaps import persist_source_gaps
from .index import SourceIndex
from .records import EvidenceRecord


def _is_gap_record(record: EvidenceRecord) -> bool:
    payload = record.payload or {}
    atom = str(payload.get("atom_type") or "")
    # ":gap:" in record_id covers adapters that don't set payload atom_type.
    return atom.endswith("gap") or ":gap:" in record.record_id


def _source_count(index: SourceIndex, source_id: str) -> int:
    with index.connect() as conn:
        row = conn.execute(
            "select count(*) as n from records where source=?", (source_id,)
        ).fetchone()
    return int(row["n"]) if row else 0


def run_source_ingest(
    *,
    index: SourceIndex,
    artifact_dir: Path,
    source_id: str,
    records: list[EvidenceRecord],
    gaps: list[dict],
    retrieved_at: str,
    raw_artifacts: list[str] | None = None,
    extra_status: dict | None = None,
    update_status_files: bool = True,
    persist_gap_records: bool = True,
    preserve_existing_fts: bool = False,
) -> dict:
    """Single safe persistence path for every ingest script.

    If no non-gap records are produced, existing rows are preserved (never wiped
    to empty); gaps are still persisted when persist_gap_records is True.
    Otherwise the source's rows are replaced with the fresh records.

    extra_status and update_status_files are reserved for a future status-file
    unification pass (currently unused, kept to avoid re-touching all call sites
    later).
    """
    non_gap = [r for r in records if not _is_gap_record(r)]
    refresh_failed = not non_gap
    if not refresh_failed:
        if preserve_existing_fts:
            index.replace_source_records_preserving_existing_fts(
                source_id, records
            )
        else:
            index.replace_source_records(source_id, records)
    if persist_gap_records:
        persist_source_gaps(
            index,
            source_id,
            gaps,
            retrieved_at=retrieved_at,
            preserve_existing_fts=preserve_existing_fts,
        )
    installed = _source_count(index, source_id)
    preserved_existing = refresh_failed and installed > 0
    return {
        "ok": not refresh_failed,
        "source": source_id,
        "refresh_failed": refresh_failed,
        "preserved_existing": preserved_existing,
        "record_count": installed,
        "refresh_record_count": len(records),
        "source_gap_count": len(gaps),
        "retrieved_at": retrieved_at,
        "raw_artifacts": raw_artifacts or [],
    }
