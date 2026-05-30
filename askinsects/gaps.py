"""Shared helper to make source gaps queryable.

Many adapters historically recorded gaps only as plain dicts written to
``gaps.json`` (a side file), never as rows in the queryable ``records`` table.
That violates the source contract ("a gap must be queryable"): ``ask``/``search``/
``sql`` could not see them. This helper converts those gap dicts into
``source_gap`` EvidenceRecords and upserts them into the index, so every honest
gap is reachable through the normal query surface.

Wire it into an ingest script right after the (guarded) record replace:

    from askinsects.gaps import persist_source_gaps
    ...
    if not refresh_failed:
        index.replace_source_records(SOURCE_ID, result.records)
    persist_source_gaps(index, SOURCE_ID, result.gaps, retrieved_at=retrieved)

It is safe to call unconditionally: gap records are keyed by reason so a refresh
overwrites stale gaps rather than duplicating them, and persisting gaps does not
disturb the non-gap records or the refresh guard.
"""

from __future__ import annotations

from typing import Iterable

from .records import EvidenceRecord, Provenance


def gap_records_from_dicts(
    source_id: str,
    gaps: Iterable[object],
    *,
    retrieved_at: str,
    default_lane: str = "source_coverage",
) -> list[EvidenceRecord]:
    """Build queryable ``source_gap`` EvidenceRecords from gap dicts."""
    records: list[EvidenceRecord] = []
    seen: set[str] = set()
    for index, gap in enumerate(gaps):
        if not isinstance(gap, dict):
            continue
        reason = str(gap.get("reason") or "unknown")
        lane = str(gap.get("lane") or default_lane)
        record_id = f"{source_id}:gap:{reason}"
        if record_id in seen:
            record_id = f"{source_id}:gap:{reason}:{index}"
        seen.add(record_id)
        url = gap.get("url") or gap.get("source_url")
        locator = str(gap.get("locator") or url or reason)
        payload = {"atom_type": "source_gap"}
        payload.update({key: value for key, value in gap.items()})
        records.append(
            EvidenceRecord(
                record_id=record_id,
                lane=lane,
                source=source_id,
                title=f"{source_id} source gap: {reason}",
                text=f"Source gap for {source_id}: {reason}.",
                species=gap.get("species"),
                url=url,
                media_url=None,
                provenance=Provenance(
                    source_id=source_id,
                    locator=locator,
                    retrieved_at=retrieved_at,
                    license=gap.get("license"),
                    source_url=gap.get("source_url") or url,
                ),
                payload=payload,
            )
        )
    return records


def persist_source_gaps(
    index,
    source_id: str,
    gaps: Iterable[object],
    *,
    retrieved_at: str,
    default_lane: str = "source_coverage",
) -> int:
    """Upsert ``source_gap`` records for ``source_id`` into the index.

    Returns the number of gap records written. No-op when there are no gaps.
    """
    records = gap_records_from_dicts(
        source_id, gaps, retrieved_at=retrieved_at, default_lane=default_lane
    )
    if records:
        index.upsert_records(records)
    return len(records)
