#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR, write_json
from askinsects.index import SourceIndex
from askinsects.sources.reviewed_repellent_evidence import (
    REVIEWED_REPELLENT_SOURCE_ID,
    build_reviewed_repellent_records,
    default_reviewed_repellent_catalog,
)


def _can_preserve_existing_fts(
    index: SourceIndex,
    records: list[object],
) -> bool:
    with index.connect() as conn:
        existing_rows = conn.execute(
            """
            SELECT record_id, lane, species, title, text
            FROM records
            WHERE source=?
            """,
            (REVIEWED_REPELLENT_SOURCE_ID,),
        ).fetchall()
    incoming = {
        record.record_id: (
            record.lane,
            record.species,
            record.title,
            record.text,
        )
        for record in records
    }
    existing = {
        str(row["record_id"]): (
            str(row["lane"]),
            row["species"],
            str(row["title"]),
            str(row["text"]),
        )
        for row in existing_rows
    }
    return existing.keys() <= incoming.keys() and all(
        incoming[record_id] == searchable_fields
        for record_id, searchable_fields in existing.items()
    )


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def ingest_reviewed_repellent_evidence(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    catalog_path: Path | None = None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    path = catalog_path or default_reviewed_repellent_catalog()
    records = build_reviewed_repellent_records(
        catalog_path=path,
        retrieved_at=retrieved_at,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    preserved_existing_fts = _can_preserve_existing_fts(index, records)
    if preserved_existing_fts:
        index.replace_source_records_preserving_existing_fts(
            REVIEWED_REPELLENT_SOURCE_ID,
            records,
        )
    else:
        index.replace_source_records(
            REVIEWED_REPELLENT_SOURCE_ID,
            records,
            update_fts=True,
            delete_existing_fts=True,
        )
    summary = index.summary()
    source_payload = {
        "source": REVIEWED_REPELLENT_SOURCE_ID,
        "record_count": len(records),
        "catalog": Path(path).as_posix(),
        "method": (
            "human-reviewed material identities and claim-level public "
            "repellent evidence"
        ),
        "preserved_existing_fts": preserved_existing_fts,
    }
    generated_at = retrieved_at or (
        datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    for filename in ("source_status.json", "source_receipt.json"):
        target = artifact_dir / filename
        payload = _read_json(target)
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[REVIEWED_REPELLENT_SOURCE_ID] = source_payload
        else:
            source_ids = list(sources) if isinstance(sources, list) else []
            if REVIEWED_REPELLENT_SOURCE_ID not in source_ids:
                source_ids.append(REVIEWED_REPELLENT_SOURCE_ID)
            sources = source_ids
        payload["sources"] = sources
        payload["generated_at"] = generated_at
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload[REVIEWED_REPELLENT_SOURCE_ID] = source_payload
        write_json(target, payload)
    return {
        "ok": True,
        **source_payload,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest the reviewed public repellent evidence catalog."
    )
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--catalog-path")
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_reviewed_repellent_evidence(
        artifact_dir=Path(args.artifact_dir),
        catalog_path=Path(args.catalog_path) if args.catalog_path else None,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
