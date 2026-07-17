from __future__ import annotations

import json
from pathlib import Path

from .builder import write_json


def _read_object(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def update_source_metadata_incrementally(
    artifact_dir: Path,
    *,
    source_id: str,
    default_lane: str,
    installed_record_count: int,
    installed_lane_counts: dict[str, int],
    source_payload: dict[str, object],
) -> None:
    """Update one source without scanning the complete hosted index."""

    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_object(path)

        prior_source_payload = payload.get(source_id)
        raw_counts = payload.get("source_counts")
        source_counts = {
            str(source): count
            for source, raw_count in (
                raw_counts.items() if isinstance(raw_counts, dict) else ()
            )
            if (count := _nonnegative_int(raw_count)) is not None
        }
        previous_source_count = source_counts.get(source_id)
        if previous_source_count is None:
            previous_source_count = (
                _nonnegative_int(prior_source_payload.get("record_count"))
                if isinstance(prior_source_payload, dict)
                else 0
            )
        previous_source_count = previous_source_count or 0
        source_counts[source_id] = installed_record_count

        previous_total = _nonnegative_int(payload.get("record_count"))
        if previous_total is None:
            record_count = sum(source_counts.values())
        else:
            record_count = max(
                0,
                previous_total - previous_source_count + installed_record_count,
            )

        raw_lanes = payload.get("lanes")
        lanes = {
            str(name): count
            for name, raw_count in (
                raw_lanes.items() if isinstance(raw_lanes, dict) else ()
            )
            if (count := _nonnegative_int(raw_count)) is not None
        }
        prior_source_lanes_raw = (
            prior_source_payload.get("lane_counts")
            if isinstance(prior_source_payload, dict)
            else None
        )
        prior_source_lanes = {
            str(name): count
            for name, raw_count in (
                prior_source_lanes_raw.items()
                if isinstance(prior_source_lanes_raw, dict)
                else ()
            )
            if (count := _nonnegative_int(raw_count)) is not None
        }
        if not prior_source_lanes and previous_source_count:
            prior_source_lanes = {default_lane: previous_source_count}
        for lane in set(prior_source_lanes) | set(installed_lane_counts):
            lanes[lane] = max(
                0,
                lanes.get(lane, 0)
                - prior_source_lanes.get(lane, 0)
                + installed_lane_counts.get(lane, 0),
            )

        species_count = _nonnegative_int(payload.get("species_count"))
        if species_count is None:
            species_count = 1 if installed_record_count else 0

        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[source_id] = source_payload
        else:
            source_list = list(sources) if isinstance(sources, list) else []
            if source_id not in source_list:
                source_list.append(source_id)
            sources = source_list

        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = record_count
        payload["species_count"] = species_count
        payload["lanes"] = lanes
        payload[source_id] = source_payload
        write_json(path, payload)
