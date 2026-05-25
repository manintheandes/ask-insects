#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import sqlite3
from pathlib import Path


VECTORBASE_SOURCE_ID = "vectorbase_aedes_genomics"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    return payload


def refresh_receipts(artifact_dir: Path, *, include_vectorbase_sequence_refresh: bool = False) -> dict[str, object]:
    summary = sqlite_summary(artifact_dir)
    retrieved_at = utc_now()
    vectorbase_refresh = (
        vectorbase_sequence_refresh(artifact_dir, retrieved_at) if include_vectorbase_sequence_refresh else None
    )
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = update_receipt_payload(
            read_json(path),
            summary=summary,
            vectorbase_refresh=vectorbase_refresh,
        )
        write_json(path, payload)
    return {"ok": True, "artifact_dir": artifact_dir.as_posix(), **summary, "vectorbase_sequence_atom_refresh": vectorbase_refresh}


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
