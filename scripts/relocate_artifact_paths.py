#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3


SQLITE_TEXT_COLUMNS = {
    "records": ("provenance_json",),
    "record_payloads": ("payload_json", "provenance_json"),
    "literature_fulltext_units": ("provenance_json",),
}


def _sqlite_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("select name from sqlite_master where type='table'").fetchall()
    return {str(row[0]) for row in rows}


def relocate_sqlite_paths(db_path: Path, old_path: str, new_path: str) -> int:
    if not db_path.exists():
        return 0

    changes_before: int
    with sqlite3.connect(db_path) as conn:
        changes_before = conn.total_changes
        tables = _sqlite_tables(conn)
        for table, columns in SQLITE_TEXT_COLUMNS.items():
            if table not in tables:
                continue
            for column in columns:
                conn.execute(
                    f"update {table} set {column}=replace({column}, ?, ?) where instr({column}, ?) > 0",
                    (old_path, new_path, old_path),
                )
        return conn.total_changes - changes_before


def relocate_json_paths(artifact_dir: Path, old_path: str, new_path: str) -> tuple[int, list[str]]:
    replacements = 0
    updated: list[str] = []
    for path in sorted(artifact_dir.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        if old_path not in text:
            continue
        replacements += text.count(old_path)
        path.write_text(text.replace(old_path, new_path), encoding="utf-8")
        updated.append(path.name)
    return replacements, updated


def relocate_artifact_paths(artifact_dir: Path, old_path: str, new_path: str) -> dict[str, object]:
    artifact_dir = artifact_dir.expanduser().absolute()
    if not artifact_dir.exists():
        raise FileNotFoundError(f"missing artifact dir: {artifact_dir}")
    if old_path == new_path:
        return {
            "ok": True,
            "artifact_dir": artifact_dir.as_posix(),
            "old_path": old_path,
            "new_path": new_path,
            "sqlite_changes": 0,
            "json_replacements": 0,
            "json_files_updated": [],
        }

    sqlite_changes = relocate_sqlite_paths(artifact_dir / "source_index.sqlite", old_path, new_path)
    json_replacements, json_files_updated = relocate_json_paths(artifact_dir, old_path, new_path)
    return {
        "ok": True,
        "artifact_dir": artifact_dir.as_posix(),
        "old_path": old_path,
        "new_path": new_path,
        "sqlite_changes": sqlite_changes,
        "json_replacements": json_replacements,
        "json_files_updated": json_files_updated,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rewrite stale absolute paths inside an Ask Insects artifact.")
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--old-path", required=True)
    parser.add_argument("--new-path", required=True)
    args = parser.parse_args()

    result = relocate_artifact_paths(args.artifact_dir, args.old_path, args.new_path)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
