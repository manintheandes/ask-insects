from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
import time
from collections.abc import Iterator
from typing import TYPE_CHECKING

from .records import EvidenceRecord, Provenance

if TYPE_CHECKING:
    from .sources.literature import FullTextUnit


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
CREATE INDEX IF NOT EXISTS idx_records_source ON records(source);
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
CREATE TABLE IF NOT EXISTS literature_fulltext_units (
  unit_id TEXT PRIMARY KEY,
  record_id TEXT NOT NULL,
  source TEXT NOT NULL,
  unit_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  url TEXT,
  license TEXT,
  provenance_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_literature_fulltext_units_record_id ON literature_fulltext_units(record_id);
CREATE VIRTUAL TABLE IF NOT EXISTS literature_fulltext_fts
USING fts5(unit_id UNINDEXED, record_id UNINDEXED, text);
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

SEARCH_TIMEOUT_SECONDS = 8.0
SEARCH_PROGRESS_STEPS = 1_000


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


def _chunks(values: list[str], size: int = 500) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _record_chunks(records: list[EvidenceRecord], size: int = 500) -> Iterator[list[EvidenceRecord]]:
    for index in range(0, len(records), size):
        yield records[index : index + size]


def _snippet(text: str, query: str, *, max_length: int = 520) -> str:
    terms = [term.lower() for term in re.findall(r"[A-Za-z0-9]+", query) if term]
    lower = text.lower()
    positions = [lower.find(term) for term in terms if lower.find(term) >= 0]
    if positions:
        start = max(0, min(positions) - 120)
    else:
        start = 0
    snippet = re.sub(r"\s+", " ", text[start : start + max_length]).strip()
    if start > 0:
        snippet = f"... {snippet}"
    if start + max_length < len(text):
        snippet = f"{snippet} ..."
    return snippet


def _fts_prefix_query(query: str) -> str | None:
    operators = {"AND", "OR", "NOT", "NEAR"}
    terms = [
        term
        for term in re.findall(r"[A-Za-z0-9]+", query)
        if term and term.upper() not in operators
    ]
    if not terms:
        return None
    return " AND ".join(f'"{term}"*' for term in terms)


class SourceIndex:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.last_search_timed_out = False

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        # WAL lets readers and a writer proceed concurrently instead of a writer
        # blocking all readers (the cause of intermittent "database is locked").
        # busy_timeout makes contending connections wait rather than fail fast.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def upsert_records(self, records: list[EvidenceRecord], *, update_fts: bool = True) -> None:
        if not records:
            return
        with self.connect() as conn:
            for chunk in _record_chunks(records):
                self._upsert_records(conn, chunk, update_fts=update_fts)

    def upsert_fulltext_units(self, units: list[FullTextUnit]) -> None:
        with self.connect() as conn:
            self._upsert_fulltext_units(conn, units)

    def upsert_records_and_fulltext_units(self, records: list[EvidenceRecord], units: list[FullTextUnit]) -> None:
        with self.connect() as conn:
            self._upsert_records(conn, records)
            self._upsert_fulltext_units(conn, units)

    def _upsert_records(self, conn: sqlite3.Connection, records: list[EvidenceRecord], *, update_fts: bool = True) -> None:
        if not records:
            return
        rows = [record.to_row() for record in records]
        existing_fts_record_ids: list[str] = []
        if update_fts:
            record_ids = [record.record_id for record in records]
            for chunk in _chunks(record_ids):
                placeholders = ",".join("?" for _ in chunk)
                existing_rows = conn.execute(
                    f"SELECT record_id FROM records WHERE record_id IN ({placeholders})",
                    chunk,
                ).fetchall()
                existing_fts_record_ids.extend(str(row["record_id"]) for row in existing_rows)
        conn.executemany(
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
                [
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
                    )
                    for row in rows
                ],
        )
        if update_fts:
            for chunk in _chunks(existing_fts_record_ids):
                placeholders = ",".join("?" for _ in chunk)
                conn.execute(f"DELETE FROM records_fts WHERE record_id IN ({placeholders})", chunk)
            conn.executemany(
                "INSERT INTO records_fts(record_id, lane, species, title, text) VALUES (?, ?, ?, ?, ?)",
                [(record.record_id, record.lane, record.species, record.title, record.text) for record in records],
            )

        empty_payload_record_ids = [record.record_id for record in records if record.payload is None]
        for chunk in _chunks(empty_payload_record_ids):
            placeholders = ",".join("?" for _ in chunk)
            conn.execute(f"DELETE FROM record_payloads WHERE record_id IN ({placeholders})", chunk)
        conn.executemany(
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
            [
                (
                    record.record_id,
                    record.source,
                    record.lane,
                    json.dumps(record.payload, sort_keys=True),
                    row["provenance_json"],
                )
                for record, row in zip(records, rows, strict=True)
                if record.payload is not None
            ],
        )

    def _upsert_fulltext_units(self, conn: sqlite3.Connection, units: list[FullTextUnit]) -> None:
        affected_record_ids = sorted({unit.record_id for unit in units})
        for record_id in affected_record_ids:
            conn.execute("DELETE FROM literature_fulltext_fts WHERE record_id=?", (record_id,))
            conn.execute("DELETE FROM literature_fulltext_units WHERE record_id=?", (record_id,))
        for unit in units:
            provenance_json = json.dumps(unit.provenance.to_dict(), sort_keys=True)
            conn.execute(
                """
                INSERT INTO literature_fulltext_units (
                  unit_id, record_id, source, unit_index, text, url, license, provenance_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(unit_id) DO UPDATE SET
                  record_id=excluded.record_id,
                  source=excluded.source,
                  unit_index=excluded.unit_index,
                  text=excluded.text,
                  url=excluded.url,
                  license=excluded.license,
                  provenance_json=excluded.provenance_json
                """,
                (
                    unit.unit_id,
                    unit.record_id,
                    unit.source,
                    unit.unit_index,
                    unit.text,
                    unit.url,
                    unit.license,
                    provenance_json,
                ),
            )
            conn.execute(
                "INSERT INTO literature_fulltext_fts(unit_id, record_id, text) VALUES (?, ?, ?)",
                (unit.unit_id, unit.record_id, unit.text),
            )

    def delete_source(self, source: str) -> None:
        with self.connect() as conn:
            self._delete_source_records(conn, source)

    def replace_source_records(
        self,
        source: str,
        records: list[EvidenceRecord],
        *,
        update_fts: bool = True,
        delete_existing_fts: bool = True,
    ) -> None:
        attempts = 4
        for attempt in range(attempts):
            try:
                with self.connect() as conn:
                    self._delete_source_records(conn, source, delete_fts=delete_existing_fts)
                    for chunk in _record_chunks(records):
                        self._upsert_records(conn, chunk, update_fts=update_fts)
                return
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt == attempts - 1:
                    raise
                time.sleep(1.5 * (attempt + 1))

    def _delete_source_records(self, conn: sqlite3.Connection, source: str, *, delete_fts: bool = True) -> None:
        record_ids: list[str] = []
        if delete_fts:
            rows = conn.execute("SELECT record_id FROM records WHERE source=?", (source,)).fetchall()
            record_ids = [row["record_id"] for row in rows]
            for chunk in _chunks(record_ids):
                placeholders = ",".join("?" for _ in chunk)
                conn.execute(f"DELETE FROM records_fts WHERE record_id IN ({placeholders})", chunk)

        fulltext_rows = conn.execute("SELECT record_id FROM literature_fulltext_units WHERE source=?", (source,)).fetchall()
        fulltext_record_ids = [row["record_id"] for row in fulltext_rows]
        for chunk in _chunks(fulltext_record_ids):
            placeholders = ",".join("?" for _ in chunk)
            conn.execute(f"DELETE FROM literature_fulltext_fts WHERE record_id IN ({placeholders})", chunk)
            conn.execute(f"DELETE FROM literature_fulltext_units WHERE record_id IN ({placeholders})", chunk)
        conn.execute("DELETE FROM record_payloads WHERE source=?", (source,))
        conn.execute("DELETE FROM records WHERE source=?", (source,))

    def search(self, query: str, lane: str | None = None, limit: int = 10) -> list[EvidenceRecord]:
        self.last_search_timed_out = False
        match = _fts_prefix_query(query)
        if not match:
            return []
        lowered_query = query.lower()
        preferred_source_order = ""
        if any(term in lowered_query for term in ("video", "videos", "movie", "motion", "keyframe", "preview")):
            if any(term in lowered_query for term in ("drosophila suzukii", "spotted wing", "suzukii")):
                preferred_source_order = "CASE WHEN r.source = 'drosophila_suzukii_video_atoms' THEN 0 ELSE 1 END,"
            elif any(term in lowered_query for term in ("aedes", "aegypti", "mosquito")):
                preferred_source_order = "CASE WHEN r.source = 'aedes_video_atoms' THEN 0 ELSE 1 END,"
        params: list[object] = [match]
        lane_filter = ""
        if lane:
            lane_filter = "AND r.lane = ?"
            params.append(lane)
        params.append(limit)
        with self.connect() as conn:
            deadline = time.monotonic() + SEARCH_TIMEOUT_SECONDS
            deadline_interrupted_search = False

            def deadline_expired() -> bool:
                nonlocal deadline_interrupted_search
                deadline_interrupted_search = time.monotonic() >= deadline
                return deadline_interrupted_search

            conn.set_progress_handler(deadline_expired, SEARCH_PROGRESS_STEPS)
            try:
                rows = conn.execute(
                    f"""
                    SELECT r.*
                    FROM records_fts f
                    JOIN records r ON r.record_id = f.record_id
                    WHERE records_fts MATCH ?
                    {lane_filter}
                    ORDER BY {preferred_source_order} bm25(records_fts)
                    LIMIT ?
                    """,
                    params,
                ).fetchall()
            except sqlite3.OperationalError:
                if not deadline_interrupted_search:
                    raise
                self.last_search_timed_out = True
                rows = []
            finally:
                conn.set_progress_handler(None, 0)
        return [EvidenceRecord.from_row(dict(row)) for row in rows]

    def search_literature_fulltext(self, query: str, limit: int = 10) -> list[EvidenceRecord]:
        match = _fts_prefix_query(query)
        if not match:
            return []
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                  u.unit_id,
                  u.record_id AS paper_record_id,
                  u.source,
                  u.unit_index,
                  u.text,
                  u.url AS fulltext_url,
                  u.license AS fulltext_license,
                  u.provenance_json AS fulltext_provenance_json,
                  r.title AS paper_title,
                  r.species AS paper_species,
                  r.url AS paper_url
                FROM literature_fulltext_fts f
                JOIN literature_fulltext_units u ON u.unit_id = f.unit_id
                LEFT JOIN records r ON r.record_id = u.record_id
                WHERE literature_fulltext_fts MATCH ?
                ORDER BY bm25(literature_fulltext_fts)
                LIMIT ?
                """,
                (match, limit),
            ).fetchall()
        records: list[EvidenceRecord] = []
        for row in rows:
            payload = dict(row)
            provenance_payload = json.loads(str(row["fulltext_provenance_json"]))
            source_url = row["fulltext_url"] or row["paper_url"] or provenance_payload.get("source_url")
            title = str(row["paper_title"] or row["paper_record_id"])
            text = _snippet(str(row["text"]), query)
            records.append(
                EvidenceRecord(
                    record_id=str(row["unit_id"]),
                    lane="literature_fulltext",
                    source=str(row["source"]),
                    title=f"Full text match: {title}",
                    text=text,
                    species=row["paper_species"],
                    url=source_url,
                    media_url=None,
                    provenance=Provenance(
                        source_id=str(row["source"]),
                        locator=f"{provenance_payload.get('locator', '')};literature_fulltext_units#{row['unit_id']}",
                        retrieved_at=str(provenance_payload.get("retrieved_at", "")),
                        license=row["fulltext_license"] or provenance_payload.get("license"),
                        source_url=source_url,
                    ),
                    payload=payload,
                )
            )
        return records

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
