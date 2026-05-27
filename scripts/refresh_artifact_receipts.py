#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import sqlite3
from pathlib import Path


VECTORBASE_SOURCE_ID = "vectorbase_aedes_genomics"
LITERATURE_SOURCE_ID = "aedes_literature_openalex"
VIDEO_ATOMS_SOURCE_ID = "aedes_video_atoms"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json_list(path: Path) -> list[object]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


def gap_key(gap: dict[str, object]) -> tuple[str, str, str, str, str]:
    return (
        str(gap.get("source")),
        str(gap.get("lane")),
        str(gap.get("reason")),
        str(gap.get("record_id")),
        str(gap.get("locator")),
    )


def dedupe_gaps(artifact_dir: Path) -> dict[str, int]:
    gaps_path = artifact_dir / "gaps.json"
    gaps = read_json_list(gaps_path)
    deduped: list[object] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for gap in gaps:
        if not isinstance(gap, dict):
            deduped.append(gap)
            continue
        key = gap_key(gap)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(gap)
    if deduped != gaps:
        gaps_path.write_text(json.dumps(deduped, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"gap_count_before": len(gaps), "gap_count_after": len(deduped), "deduped_gap_count": len(gaps) - len(deduped)}


def sqlite_tables(conn: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in conn.execute("select name from sqlite_master where type='table'")}


def direct_fulltext_target(payload: dict[str, object]) -> str | None:
    unpaywall = payload.get("unpaywall")
    if isinstance(unpaywall, dict) and unpaywall.get("is_oa"):
        location = unpaywall.get("best_oa_location")
        if isinstance(location, dict):
            url = location.get("url_for_pdf") or location.get("url_for_xml")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                return url
    work = payload.get("raw_openalex_work")
    if isinstance(work, dict):
        location = work.get("best_oa_location")
        if isinstance(location, dict):
            url = location.get("pdf_url")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                return url
    return None


def backfill_literature_fulltext_gaps(artifact_dir: Path, retrieved_at: str) -> dict[str, int]:
    db_path = artifact_dir / "source_index.sqlite"
    gaps_path = artifact_dir / "gaps.json"
    gaps = read_json_list(gaps_path)
    existing_gap_ids = {
        str(gap.get("record_id"))
        for gap in gaps
        if isinstance(gap, dict)
        and gap.get("source") == LITERATURE_SOURCE_ID
        and gap.get("reason") in {"fulltext_fetch_failed", "fulltext_parse_failed"}
    }
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        tables = sqlite_tables(conn)
        if "record_payloads" not in tables or "literature_fulltext_units" not in tables:
            return {"literature_fulltext_gap_backfill_count": 0}
        fulltext_ids = {
            str(row["record_id"])
            for row in conn.execute("select distinct record_id from literature_fulltext_units")
        }
        rows = conn.execute(
            """
            select p.record_id, p.payload_json, r.species
            from record_payloads p
            left join records r on r.record_id = p.record_id
            where p.source = ?
            """,
            (LITERATURE_SOURCE_ID,),
        ).fetchall()
    backfilled = 0
    for row in rows:
        record_id = str(row["record_id"])
        if record_id in fulltext_ids or record_id in existing_gap_ids:
            continue
        try:
            payload = json.loads(str(row["payload_json"]))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        target = direct_fulltext_target(payload)
        if not target:
            continue
        gaps.append(
            {
                "source": LITERATURE_SOURCE_ID,
                "lane": "literature",
                "species": str(row["species"] or "Aedes aegypti"),
                "reason": "fulltext_fetch_failed",
                "record_id": record_id,
                "locator": target,
                "external_id": target,
                "detail": "Direct full-text candidate is not extracted in this merged artifact, so it is preserved as an explicit source gap.",
                "retrieved_at": retrieved_at,
            }
        )
        existing_gap_ids.add(record_id)
        backfilled += 1
    if backfilled:
        gaps_path.write_text(json.dumps(gaps, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"literature_fulltext_gap_backfill_count": backfilled}


def _chunks(values: list[str], size: int = 500) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def dedupe_video_gap_records(artifact_dir: Path) -> dict[str, int]:
    db_path = artifact_dir / "source_index.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        tables = sqlite_tables(conn)
        if "records" not in tables or "record_payloads" not in tables:
            return {"video_gap_record_dedupe_count": 0}
        rows = conn.execute(
            """
            select record_id, payload_json
            from record_payloads
            where source = ?
              and json_extract(payload_json, '$.atom_type') = 'video_gap'
            order by record_id
            """,
            (VIDEO_ATOMS_SOURCE_ID,),
        ).fetchall()
        seen: set[tuple[str, str, str, str, str]] = set()
        duplicate_ids: list[str] = []
        for row in rows:
            try:
                payload = json.loads(str(row["payload_json"]))
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            key = gap_key(payload)
            if key in seen:
                duplicate_ids.append(str(row["record_id"]))
                continue
            seen.add(key)
        if duplicate_ids:
            for chunk in _chunks(duplicate_ids):
                placeholders = ",".join("?" for _ in chunk)
                if "records_fts" in tables:
                    conn.execute(f"delete from records_fts where record_id in ({placeholders})", chunk)
                conn.execute(f"delete from record_payloads where record_id in ({placeholders})", chunk)
                conn.execute(f"delete from records where record_id in ({placeholders})", chunk)
            conn.commit()
    return {"video_gap_record_dedupe_count": len(duplicate_ids)}


def sqlite_summary(artifact_dir: Path) -> dict[str, object]:
    db_path = artifact_dir / "source_index.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return {
            "record_count": int(conn.execute("select count(1) from records").fetchone()[0]),
            "species_count": int(
                conn.execute("select count(distinct species) from records where species is not null").fetchone()[0]
            ),
            "lanes": {
                str(row["lane"]): int(row["n"])
                for row in conn.execute("select lane, count(1) as n from records group by lane")
            },
            "source_counts": {
                str(row["source"]): int(row["n"])
                for row in conn.execute("select source, count(1) as n from records group by source order by source")
            },
        }


def video_atom_counts(artifact_dir: Path) -> dict[str, int]:
    db_path = artifact_dir / "source_index.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        tables = sqlite_tables(conn)
        if "record_payloads" not in tables:
            return {}
        return {
            str(row["atom_type"]): int(row["n"])
            for row in conn.execute(
                """
                select json_extract(payload_json, '$.atom_type') as atom_type, count(*) as n
                from record_payloads
                where source = ?
                group by atom_type
                """,
                (VIDEO_ATOMS_SOURCE_ID,),
            )
            if row["atom_type"]
        }


def vectorbase_sequence_refresh(artifact_dir: Path, retrieved_at: str) -> dict[str, object]:
    db_path = artifact_dir / "source_index.sqlite"
    with sqlite3.connect(db_path) as conn:
        cds_count = int(
            conn.execute(
                "select count(1) from records where source=? and record_id like 'vectorbase:cds:%'",
                (VECTORBASE_SOURCE_ID,),
            ).fetchone()[0]
        )
        transcript_sequence_count = int(
            conn.execute(
                "select count(1) from records where source=? and record_id like 'vectorbase:transcript_sequence:%'",
                (VECTORBASE_SOURCE_ID,),
            ).fetchone()[0]
        )
        vectorbase_count = int(
            conn.execute("select count(1) from records where source=?", (VECTORBASE_SOURCE_ID,)).fetchone()[0]
        )
    raw_dir = artifact_dir / "raw" / "vectorbase_genomics"
    raw_artifacts = sorted(path.as_posix() for path in raw_dir.iterdir()) if raw_dir.exists() else []
    return {
        "source": VECTORBASE_SOURCE_ID,
        "retrieved_at": retrieved_at,
        "method": "receipt refresh from installed SQLite VectorBase sequence atoms",
        "record_count": vectorbase_count,
        "cds_live_count": cds_count,
        "transcript_sequence_live_count": transcript_sequence_count,
        "raw_artifacts": raw_artifacts,
        "gap_count": 0,
    }


def update_receipt_payload(
    payload: dict[str, object],
    *,
    summary: dict[str, object],
    video_counts: dict[str, int],
    vectorbase_refresh: dict[str, object] | None,
) -> dict[str, object]:
    payload["record_count"] = summary["record_count"]
    payload["species_count"] = summary["species_count"]
    payload["lanes"] = summary["lanes"]
    payload["source_counts"] = summary["source_counts"]
    source_counts = summary["source_counts"]
    if isinstance(source_counts, dict):
        for source, count in source_counts.items():
            direct_payload = payload.get(source)
            if isinstance(direct_payload, dict) and "record_count" in direct_payload:
                direct_payload["record_count"] = count
            sources = payload.get("sources")
            if isinstance(sources, dict):
                nested_payload = sources.get(source)
                if isinstance(nested_payload, dict) and "record_count" in nested_payload:
                    nested_payload["record_count"] = count
    if vectorbase_refresh:
        payload["vectorbase_sequence_atom_refresh"] = vectorbase_refresh
        vectorbase_payload = payload.get("vectorbase_genomics")
        if not isinstance(vectorbase_payload, dict):
            vectorbase_payload = {}
        vectorbase_payload.update(
            {
                "source": VECTORBASE_SOURCE_ID,
                "record_count": vectorbase_refresh["record_count"],
                "sequence_atom_refresh": vectorbase_refresh,
                "gap_count": int(vectorbase_payload.get("gap_count") or 0),
            }
        )
        payload["vectorbase_genomics"] = vectorbase_payload
        sources = payload.get("sources")
        if isinstance(sources, dict):
            nested = sources.get(VECTORBASE_SOURCE_ID)
            if not isinstance(nested, dict):
                nested = {}
            nested.update(vectorbase_payload)
            sources[VECTORBASE_SOURCE_ID] = nested
            payload["sources"] = sources
        elif isinstance(sources, list):
            if VECTORBASE_SOURCE_ID not in sources:
                sources.append(VECTORBASE_SOURCE_ID)
            payload["sources"] = sources
    video_payload = payload.get(VIDEO_ATOMS_SOURCE_ID)
    if not isinstance(video_payload, dict):
        video_payload = {}
    if video_counts and VIDEO_ATOMS_SOURCE_ID in summary["source_counts"]:
        video_payload["record_count"] = summary["source_counts"].get(VIDEO_ATOMS_SOURCE_ID, video_payload.get("record_count"))
        video_payload["video_asset_count"] = video_counts.get("video_asset", video_payload.get("video_asset_count", 0))
        video_payload["motion_row_count"] = video_counts.get("video_motion_row", video_payload.get("motion_row_count", 0))
        video_payload["gap_count"] = video_counts.get("video_gap", 0)
        artifact_count = sum(
            video_counts.get(atom_type, 0)
            for atom_type in ("video_thumbnail", "video_keyframe", "video_preview_clip", "video_frame_manifest")
        )
        video_payload["artifact_count"] = artifact_count
        payload[VIDEO_ATOMS_SOURCE_ID] = video_payload
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[VIDEO_ATOMS_SOURCE_ID] = video_payload
            payload["sources"] = sources
    return payload


def refresh_receipts(artifact_dir: Path, *, include_vectorbase_sequence_refresh: bool = False) -> dict[str, object]:
    retrieved_at = utc_now()
    fulltext_gap_summary = backfill_literature_fulltext_gaps(artifact_dir, retrieved_at)
    gap_summary = dedupe_gaps(artifact_dir)
    video_gap_record_summary = dedupe_video_gap_records(artifact_dir)
    summary = sqlite_summary(artifact_dir)
    video_counts = video_atom_counts(artifact_dir)
    vectorbase_refresh = (
        vectorbase_sequence_refresh(artifact_dir, retrieved_at) if include_vectorbase_sequence_refresh else None
    )
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = update_receipt_payload(
            read_json(path),
            summary=summary,
            video_counts=video_counts,
            vectorbase_refresh=vectorbase_refresh,
        )
        payload["gap_count"] = gap_summary["gap_count_after"]
        write_json(path, payload)
    return {
        "ok": True,
        "artifact_dir": artifact_dir.as_posix(),
        **summary,
        **gap_summary,
        **fulltext_gap_summary,
        **video_gap_record_summary,
        "vectorbase_sequence_atom_refresh": vectorbase_refresh,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh Ask Insects artifact receipts from installed SQLite counts.")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--vectorbase-sequence-refresh", action="store_true")
    args = parser.parse_args(argv)
    result = refresh_receipts(
        Path(args.artifact_dir),
        include_vectorbase_sequence_refresh=args.vectorbase_sequence_refresh,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
