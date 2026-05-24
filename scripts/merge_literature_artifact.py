#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from askinsects.index import SCHEMA, SourceIndex


LITERATURE_SOURCE_ID = "aedes_literature_openalex"


def read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rewrite_paths(value: object, old_dir: Path, new_dir: Path) -> object:
    text = json.dumps(value, sort_keys=True)
    text = text.replace(old_dir.as_posix(), new_dir.as_posix()).replace(str(old_dir), str(new_dir))
    text = text.replace(f"artifacts/{old_dir.name}", new_dir.as_posix())
    return json.loads(text)


def source_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT source, COUNT(*) AS n FROM records GROUP BY source ORDER BY source").fetchall()
    return {str(source): int(count) for source, count in rows}


def ordered_sources(existing: object, counts: dict[str, int], source_id: str) -> list[str]:
    ordered: list[str] = []
    if isinstance(existing, list):
        ordered.extend(source for source in existing if isinstance(source, str) and source in counts)
    for source in counts:
        if source not in ordered and source != source_id:
            ordered.append(source)
    if counts.get(source_id) and source_id not in ordered:
        ordered.append(source_id)
    return ordered


def merge_gaps(target_artifact_dir: Path, literature_artifact_dir: Path, staging: Path, source_id: str) -> list[dict[str, object]]:
    old_gaps = read_json(staging / "gaps.json", [])
    if not isinstance(old_gaps, list):
        old_gaps = []
    preserved = [gap for gap in old_gaps if not (isinstance(gap, dict) and gap.get("source") == source_id)]

    incoming_gaps = read_json(literature_artifact_dir / "gaps.json", [])
    if not isinstance(incoming_gaps, list):
        incoming_gaps = []
    rewritten = rewrite_paths(incoming_gaps, literature_artifact_dir, target_artifact_dir)
    if not isinstance(rewritten, list):
        rewritten = []
    preserved.extend(gap for gap in rewritten if isinstance(gap, dict) and gap.get("source") == source_id)
    return preserved


def copy_raw_literature(literature_artifact_dir: Path, staging: Path) -> None:
    source_raw = literature_artifact_dir / "raw" / "literature"
    if source_raw.exists():
        shutil.copytree(source_raw, staging / "raw" / "literature", dirs_exist_ok=True)
    source_logs = literature_artifact_dir / "logs"
    if source_logs.exists():
        shutil.copytree(source_logs, staging / "logs" / "literature", dirs_exist_ok=True)


def merge_sqlite(staging: Path, literature_artifact_dir: Path, target_artifact_dir: Path, source_id: str) -> None:
    target_db = staging / "source_index.sqlite"
    incoming_db = literature_artifact_dir / "source_index.sqlite"
    if not incoming_db.exists():
        raise FileNotFoundError(f"missing literature SQLite index: {incoming_db}")

    index = SourceIndex(target_db)
    index.initialize()
    index.delete_source(source_id)

    with sqlite3.connect(target_db) as conn:
        conn.executescript(SCHEMA)
        conn.execute("ATTACH DATABASE ? AS incoming", (incoming_db.as_posix(),))
        old_dir = literature_artifact_dir.as_posix()
        old_relative_dir = f"artifacts/{literature_artifact_dir.name}"
        new_dir = target_artifact_dir.as_posix()
        conn.execute(
            """
            INSERT INTO records (
              record_id, lane, source, title, text, species, url, media_url, provenance_json
            )
            SELECT record_id, lane, source, title, text, species, url, media_url, replace(replace(provenance_json, ?, ?), ?, ?)
            FROM incoming.records
            WHERE source = ?
            ON CONFLICT(record_id) DO UPDATE SET
              lane=excluded.lane,
              source=excluded.source,
              title=excluded.title,
              text=excluded.text,
              species=excluded.species,
              url=excluded.url,
              media_url=excluded.media_url,
              provenance_json=excluded.provenance_json
            """,
            (old_dir, new_dir, old_relative_dir, new_dir, source_id),
        )
        conn.execute(
            """
            INSERT INTO record_payloads (
              record_id, source, lane, payload_json, provenance_json
            )
            SELECT record_id, source, lane, replace(replace(payload_json, ?, ?), ?, ?), replace(replace(provenance_json, ?, ?), ?, ?)
            FROM incoming.record_payloads
            WHERE source = ?
            ON CONFLICT(record_id) DO UPDATE SET
              source=excluded.source,
              lane=excluded.lane,
              payload_json=excluded.payload_json,
              provenance_json=excluded.provenance_json
            """,
            (old_dir, new_dir, old_relative_dir, new_dir, old_dir, new_dir, old_relative_dir, new_dir, source_id),
        )
        conn.execute(
            """
            INSERT INTO literature_fulltext_units (
              unit_id, record_id, source, unit_index, text, url, license, provenance_json
            )
            SELECT unit_id, record_id, source, unit_index, text, url, license, replace(replace(provenance_json, ?, ?), ?, ?)
            FROM incoming.literature_fulltext_units
            WHERE source = ?
            ON CONFLICT(unit_id) DO UPDATE SET
              record_id=excluded.record_id,
              source=excluded.source,
              unit_index=excluded.unit_index,
              text=excluded.text,
              url=excluded.url,
              license=excluded.license,
              provenance_json=excluded.provenance_json
            """,
            (old_dir, new_dir, old_relative_dir, new_dir, source_id),
        )
        conn.execute("DELETE FROM records_fts WHERE record_id IN (SELECT record_id FROM records WHERE source = ?)", (source_id,))
        conn.execute(
            """
            INSERT INTO records_fts(record_id, lane, species, title, text)
            SELECT record_id, lane, species, title, text
            FROM records
            WHERE source = ?
            """,
            (source_id,),
        )
        conn.execute(
            "DELETE FROM literature_fulltext_fts WHERE record_id IN (SELECT record_id FROM records WHERE source = ?)",
            (source_id,),
        )
        conn.execute(
            """
            INSERT INTO literature_fulltext_fts(unit_id, record_id, text)
            SELECT unit_id, record_id, text
            FROM literature_fulltext_units
            WHERE source = ?
            """,
            (source_id,),
        )
        conn.commit()
        conn.execute("DETACH DATABASE incoming")


def update_metadata(staging: Path, literature_artifact_dir: Path, target_artifact_dir: Path, source_id: str) -> dict[str, object]:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    index = SourceIndex(staging / "source_index.sqlite")
    summary = index.summary()
    with sqlite3.connect(staging / "source_index.sqlite") as conn:
        counts = source_counts(conn)

    old_status = read_json(staging / "source_status.json", {})
    if not isinstance(old_status, dict):
        old_status = {}
    incoming_status = read_json(literature_artifact_dir / "source_status.json", {})
    if not isinstance(incoming_status, dict):
        incoming_status = {}
    incoming_literature = rewrite_paths(incoming_status.get("literature", {}), literature_artifact_dir, target_artifact_dir)
    gaps = merge_gaps(target_artifact_dir, literature_artifact_dir, staging, source_id)
    sources = ordered_sources(old_status.get("sources"), counts, source_id)
    status = {
        **old_status,
        "ok": True,
        "source_id": old_status.get("source_id") or (sources[0] if sources else source_id),
        "sources": sources,
        "source_counts": counts,
        "boundary": old_status.get("boundary", "mosquitoes first"),
        "generated_at": now,
        "fully_parsed": True,
        "record_count": summary["record_count"],
        "species_count": summary["species_count"],
        "lanes": summary["lanes"],
        "gap_count": len(gaps),
        "literature": incoming_literature,
    }

    old_receipt = read_json(staging / "source_receipt.json", {})
    if not isinstance(old_receipt, dict):
        old_receipt = {}
    incoming_receipt = read_json(literature_artifact_dir / "source_receipt.json", {})
    if not isinstance(incoming_receipt, dict):
        incoming_receipt = {}
    receipt_sources = old_receipt.get("sources")
    if not isinstance(receipt_sources, dict):
        receipt_sources = {source: {} for source in sources}
    receipt_sources[source_id] = rewrite_paths(
        incoming_receipt.get("literature", incoming_receipt), literature_artifact_dir, target_artifact_dir
    )
    receipt = {
        **old_receipt,
        "source_id": status["source_id"],
        "sources": receipt_sources,
        "artifact_dir": target_artifact_dir.as_posix(),
        "sqlite_index": (target_artifact_dir / "source_index.sqlite").as_posix(),
        "generated_at": now,
        "record_count": summary["record_count"],
        "source_counts": counts,
        "lanes": summary["lanes"],
        "gap_count": len(gaps),
        "literature": receipt_sources[source_id],
    }

    enrichment = read_json(literature_artifact_dir / "literature_enrichment_receipt.json", {})
    if isinstance(enrichment, dict):
        enrichment = rewrite_paths(enrichment, literature_artifact_dir, target_artifact_dir)
        write_json(staging / "literature_enrichment_receipt.json", enrichment)

    write_json(staging / "gaps.json", gaps)
    write_json(staging / "source_status.json", status)
    write_json(staging / "source_receipt.json", receipt)
    return status


def merge_literature_artifact(target_artifact_dir: Path, literature_artifact_dir: Path, source_id: str = LITERATURE_SOURCE_ID) -> dict[str, object]:
    target_artifact_dir = target_artifact_dir.expanduser().absolute()
    literature_artifact_dir = literature_artifact_dir.expanduser().absolute()
    if not target_artifact_dir.exists():
        raise FileNotFoundError(f"missing target artifact dir: {target_artifact_dir}")
    if not literature_artifact_dir.exists():
        raise FileNotFoundError(f"missing literature artifact dir: {literature_artifact_dir}")

    staging = target_artifact_dir.parent / f".{target_artifact_dir.name}.literature-staging"
    backup = target_artifact_dir.parent / f".{target_artifact_dir.name}.before-literature"
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(target_artifact_dir, staging)
    try:
        copy_raw_literature(literature_artifact_dir, staging)
        merge_sqlite(staging, literature_artifact_dir, target_artifact_dir, source_id)
        status = update_metadata(staging, literature_artifact_dir, target_artifact_dir, source_id)
        if backup.exists():
            shutil.rmtree(backup)
        target_artifact_dir.replace(backup)
        staging.replace(target_artifact_dir)
        shutil.rmtree(backup, ignore_errors=True)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {"ok": True, "artifact_dir": target_artifact_dir.as_posix(), **status}


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge an enriched Aedes aegypti literature artifact into the active Ask Insects artifact.")
    parser.add_argument("--target-artifact-dir", required=True)
    parser.add_argument("--literature-artifact-dir", required=True)
    parser.add_argument("--source-id", default=LITERATURE_SOURCE_ID)
    return parser


def main() -> int:
    parser = create_parser()
    args = parser.parse_args()
    result = merge_literature_artifact(
        target_artifact_dir=Path(args.target_artifact_dir),
        literature_artifact_dir=Path(args.literature_artifact_dir),
        source_id=args.source_id,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
