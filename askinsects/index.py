from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import sqlite3

from .records import EvidenceRecord


SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  record_id TEXT PRIMARY KEY,
  lane TEXT NOT NULL,
  source TEXT NOT NULL,
  title TEXT NOT NULL,
  text TEXT NOT NULL,
  species TEXT,
  url TEXT,
  media_url TEXT,
  provenance_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_records_lane ON records(lane);
CREATE INDEX IF NOT EXISTS idx_records_species ON records(species);
CREATE VIRTUAL TABLE IF NOT EXISTS records_fts
USING fts5(record_id UNINDEXED, lane UNINDEXED, species UNINDEXED, title, text);
CREATE TABLE IF NOT EXISTS record_payloads (
  record_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  lane TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  provenance_json TEXT NOT NULL,
  FOREIGN KEY(record_id) REFERENCES records(record_id)
);
CREATE INDEX IF NOT EXISTS idx_record_payloads_source ON record_payloads(source);
CREATE INDEX IF NOT EXISTS idx_record_payloads_lane ON record_payloads(lane);
"""


WRITE_SQL_KEYWORDS = {
    "alter",
    "attach",
    "create",
    "delete",
    "detach",
    "drop",
    "insert",
    "reindex",
    "replace",
    "update",
    "vacuum",
}


def _strip_sql_literals_and_comments(sql: str) -> str:
    return re.sub(
        r"(?is)'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|--[^\n]*(?:\n|$)|/\*.*?\*/",
        " ",
        sql,
    )


def ensure_read_only_sql(sql: str) -> str:
    statement = sql.strip()
    if not re.match(r"(?is)^(select|with)\b", statement):
        raise ValueError("sql is read-only; use SELECT or WITH")
    if ";" in statement.rstrip(";"):
        raise ValueError("sql accepts one read-only statement at a time")
    tokens = {token.lower() for token in re.findall(r"[A-Za-z_]+", _strip_sql_literals_and_comments(statement))}
    if tokens & WRITE_SQL_KEYWORDS:
        raise ValueError("sql is read-only; write statements are not allowed")
    if any(token == "pragma" or token.startswith("pragma_") for token in tokens):
        raise ValueError("sql is read-only; PRAGMA-style statements are not allowed")
    return statement


class SourceIndex:
    def __init__(self, path: Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def upsert_records(self, records: list[EvidenceRecord]) -> None:
        with self.connect() as conn:
            for record in records:
                row = record.to_row()
                conn.execute(
                    """
                    INSERT INTO records (
                      record_id, lane, source, title, text, species, url, media_url, provenance_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    (
                        row["record_id"],
                        row["lane"],
                        row["source"],
                        row["title"],
                        row["text"],
                        row["species"],
                        row["url"],
                        row["media_url"],
                        row["provenance_json"],
                    ),
                )
                conn.execute("DELETE FROM records_fts WHERE record_id=?", (record.record_id,))
                conn.execute(
                    "INSERT INTO records_fts(record_id, lane, species, title, text) VALUES (?, ?, ?, ?, ?)",
                    (record.record_id, record.lane, record.species, record.title, record.text),
                )
                if record.payload is None:
                    conn.execute("DELETE FROM record_payloads WHERE record_id=?", (record.record_id,))
                else:
                    conn.execute(
                        """
                        INSERT INTO record_payloads (
                          record_id, source, lane, payload_json, provenance_json
                        ) VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(record_id) DO UPDATE SET
                          source=excluded.source,
                          lane=excluded.lane,
                          payload_json=excluded.payload_json,
                          provenance_json=excluded.provenance_json
                        """,
                        (
                            record.record_id,
                            record.source,
                            record.lane,
                            json.dumps(record.payload, sort_keys=True),
                            row["provenance_json"],
                        ),
                    )

    def search(self, query: str, lane: str | None = None, limit: int = 10) -> list[EvidenceRecord]:
        terms = [term for term in re.findall(r"[A-Za-z0-9]+", query) if term]
        if not terms:
            return []
        match = " AND ".join(f"{term}*" for term in terms)
        params: list[object] = [match]
        lane_filter = ""
        if lane:
            lane_filter = "AND r.lane = ?"
            params.append(lane)
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT r.*
                FROM records_fts f
                JOIN records r ON r.record_id = f.record_id
                WHERE records_fts MATCH ?
                {lane_filter}
                ORDER BY bm25(records_fts)
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [EvidenceRecord.from_row(dict(row)) for row in rows]

    def sql(self, sql: str, limit: int = 100) -> list[dict[str, object]]:
        statement = ensure_read_only_sql(sql)
        with self.connect() as conn:
            cursor = conn.execute(statement)
            rows = []
            for row in cursor:
                rows.append(dict(row))
                if len(rows) >= limit:
                    break
        return rows

    def summary(self) -> dict[str, object]:
        with self.connect() as conn:
            rows = conn.execute("SELECT lane, COUNT(*) AS count FROM records GROUP BY lane").fetchall()
            record_count = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
            species_count = conn.execute("SELECT COUNT(DISTINCT species) FROM records WHERE species IS NOT NULL").fetchone()[0]
        return {
            "record_count": int(record_count),
            "species_count": int(species_count),
            "lanes": dict(Counter({row["lane"]: row["count"] for row in rows})),
        }
