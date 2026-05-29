from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Callable
from urllib.parse import quote
from urllib.request import Request, urlopen

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance


DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID = "drosophila_suzukii_dryad_table_rows"
DEEP_SOURCE_ID = "drosophila_suzukii_deep_sources"
SPECIES = "Drosophila suzukii"
COMMON_NAME = "spotted wing drosophila"
DRYAD_BASE = "https://datadryad.org"
TABLE_EXTENSIONS = (".csv", ".tsv", ".xlsx")
DEFAULT_MAX_TABLE_FILES = 50
DEFAULT_MAX_TABLE_ROWS_PER_FILE = 500


@dataclass(frozen=True)
class DryadTableCandidate:
    source_record_id: str
    title: str
    url: str | None
    locator: str
    retrieved_at: str
    license_text: str | None
    dataset_doi: str | None
    file_path: str
    mime_type: str | None
    byte_size: int | None
    digest: str | None
    digest_type: str | None
    download_url: str | None
    raw_payload: dict[str, object]


@dataclass(frozen=True)
class PreviewTable:
    rows: list[list[str]]


@dataclass(frozen=True)
class DrosophilaSuzukiiDryadTableRowsResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    candidate_count: int
    parsed_table_file_count: int
    table_sheet_count: int
    table_row_count: int
    gap_count: int


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_id(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value or "")).strip("_") or "dryad"


def _safe_json(raw: object) -> dict[str, object]:
    if not raw:
        return {}
    try:
        payload = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _coerce_int(value: object) -> int | None:
    try:
        if value is not None:
            return int(value)
    except (TypeError, ValueError):
        return None
    return None


def _is_table_file(file_path: str, mime_type: str | None) -> bool:
    lower = file_path.lower()
    mime = str(mime_type or "").lower()
    if any(lower.endswith(ext) for ext in TABLE_EXTENSIONS):
        return True
    return "csv" in mime or "spreadsheetml" in mime or "tab-separated-values" in mime


def _file_id(candidate: DryadTableCandidate) -> str | None:
    for value in (candidate.download_url, candidate.raw_payload.get("download_url")):
        match = re.search(r"/files/([0-9]+)/download\b", str(value or ""))
        if match:
            return match.group(1)
    raw_file = candidate.raw_payload.get("raw_file")
    if isinstance(raw_file, dict):
        link = raw_file.get("_links")
        if isinstance(link, dict):
            self_link = link.get("self")
            href = self_link.get("href") if isinstance(self_link, dict) else None
            match = re.search(r"/files/([0-9]+)\b", str(href or ""))
            if match:
                return match.group(1)
    return None


def _preview_url(file_id: str) -> str:
    return f"{DRYAD_BASE}/data_file/preview/{quote(file_id, safe='')}.js"


def _default_fetch_preview_text(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "AskInsects/0.1 source-plane",
            "Accept": "text/javascript, application/javascript, */*;q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": DRYAD_BASE,
        },
    )
    with urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


class _PreviewTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._cell_tag: str | None = None
        self._cell_parts: list[str] = []
        self._current_row: list[str] | None = None
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._current_row = []
        if tag in {"th", "td"}:
            self._cell_tag = tag
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._cell_tag:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._cell_tag:
            if self._current_row is not None:
                self._current_row.append(_clean(" ".join(self._cell_parts)))
            self._cell_tag = None
            self._cell_parts = []
        if tag == "tr" and self._current_row:
            self.rows.append(self._current_row)
            self._current_row = None


def _parse_preview_table(preview_js: str) -> PreviewTable | None:
    parser = _PreviewTableParser()
    parser.feed(preview_js)
    parser.close()
    rows = [row for row in parser.rows if any(cell for cell in row)]
    return PreviewTable(rows=rows) if rows else None


def _table_layout(rows: list[list[str]]) -> tuple[list[str], list[tuple[int, list[str]]]]:
    for index, row in enumerate(rows):
        if any(cell for cell in row):
            headers = [cell or f"column_{i + 1}" for i, cell in enumerate(row)]
            data_rows = [(row_index + 1, values) for row_index, values in enumerate(rows[index + 1 :], start=index + 1) if any(values)]
            return headers, data_rows
    return [], []


def _row_values(headers: list[str], row: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for index, header in enumerate(headers):
        value = row[index] if index < len(row) else ""
        if value:
            values[header] = value
    return values


def _source_candidates(index: SourceIndex) -> list[DryadTableCandidate]:
    with index.connect() as conn:
        rows = conn.execute(
            """
            select r.record_id, r.title, r.url, r.provenance_json, p.payload_json
            from records r
            join record_payloads p on p.record_id=r.record_id
            where r.source=? and p.source=? and json_extract(p.payload_json, '$.record_type')='dryad_file_manifest'
            order by r.record_id
            """,
            (DEEP_SOURCE_ID, DEEP_SOURCE_ID),
        ).fetchall()
    candidates: list[DryadTableCandidate] = []
    for row in rows:
        payload = _safe_json(row["payload_json"])
        file_path = _clean(payload.get("file_path"))
        mime_type = _clean(payload.get("mime_type")) or None
        if not file_path or not _is_table_file(file_path, mime_type):
            continue
        provenance = _safe_json(row["provenance_json"])
        candidates.append(
            DryadTableCandidate(
                source_record_id=str(row["record_id"]),
                title=str(row["title"]),
                url=str(row["url"]) if row["url"] else None,
                locator=str(provenance.get("locator") or f"records#{row['record_id']}"),
                retrieved_at=str(provenance.get("retrieved_at") or utc_now()),
                license_text=str(provenance.get("license") or payload.get("license") or "").strip() or None,
                dataset_doi=str(payload.get("dataset_doi") or "") or None,
                file_path=file_path,
                mime_type=mime_type,
                byte_size=_coerce_int(payload.get("byte_size")),
                digest=str(payload.get("digest") or "") or None,
                digest_type=str(payload.get("digest_type") or "") or None,
                download_url=str(payload.get("download_url") or "") or None,
                raw_payload=payload,
            )
        )
    return candidates


def _gap_record(
    candidate: DryadTableCandidate | None,
    *,
    reason: str,
    retrieved_at: str,
    ordinal: int,
    preview_url: str | None = None,
    error: str | None = None,
) -> EvidenceRecord:
    source_record_id = candidate.source_record_id if candidate else "swd_dryad_table_rows"
    file_path = candidate.file_path if candidate else None
    payload = {
        "atom_type": "dryad_table_gap",
        "reason": reason,
        "source_file_record_id": source_record_id,
        "file_path": file_path,
        "dataset_doi": candidate.dataset_doi if candidate else None,
        "byte_size": candidate.byte_size if candidate else None,
        "digest": candidate.digest if candidate else None,
        "digest_type": candidate.digest_type if candidate else None,
        "download_url": candidate.download_url if candidate else None,
        "preview_url": preview_url,
        "error": error,
    }
    return EvidenceRecord(
        record_id=f"swd:dryad_table:gap:{_safe_id(source_record_id)}:{_safe_id(reason)}:{ordinal}",
        lane="behavior",
        source=DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID,
        title=f"Drosophila suzukii Dryad table gap: {reason}",
        text=(
            f"Ask Insects Dryad table gap for {COMMON_NAME}: {reason}. "
            f"Source file: {file_path or 'not supplied'}. Preview URL: {preview_url or 'not supplied'}."
        ),
        species=SPECIES,
        url=candidate.url if candidate else None,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID,
            locator=f"{candidate.locator if candidate else 'drosophila_suzukii_dryad_table_rows'}#gap/{reason}",
            retrieved_at=retrieved_at,
            license=candidate.license_text if candidate else "Ask Insects source gap",
            source_url=preview_url or (candidate.download_url if candidate else None),
        ),
        payload=payload,
    )


def _sheet_record(
    candidate: DryadTableCandidate,
    *,
    preview_path: str,
    preview_url: str,
    headers: list[str],
    row_count: int,
    retrieved_at: str,
) -> EvidenceRecord:
    payload = {
        "atom_type": "dryad_table_sheet",
        "source_file_record_id": candidate.source_record_id,
        "dataset_doi": candidate.dataset_doi,
        "file_path": candidate.file_path,
        "headers": headers,
        "row_count": row_count,
        "preview_path": preview_path,
        "preview_url": preview_url,
        "download_url": candidate.download_url,
        "byte_size": candidate.byte_size,
        "digest": candidate.digest,
        "digest_type": candidate.digest_type,
        "table_source": "dryad_preview",
    }
    return EvidenceRecord(
        record_id=f"swd:dryad_table:sheet:{_safe_id(candidate.source_record_id)}",
        lane="behavior",
        source=DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID,
        title=f"Drosophila suzukii Dryad parsed table sheet {candidate.file_path}",
        text=(
            f"Parsed Dryad preview table for {COMMON_NAME}: {candidate.file_path}. "
            f"Rows indexed: {row_count}. Headers: {', '.join(headers[:12])}."
        ),
        species=SPECIES,
        url=candidate.url,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID,
            locator=f"{preview_path}#sheet/1",
            retrieved_at=retrieved_at,
            license=candidate.license_text,
            source_url=preview_url,
        ),
        payload=payload,
    )


def _row_record(
    candidate: DryadTableCandidate,
    *,
    preview_path: str,
    preview_url: str,
    row_number: int,
    row_values: dict[str, str],
    retrieved_at: str,
) -> EvidenceRecord:
    formatted_values = "; ".join(f"{key}={value}" for key, value in list(row_values.items())[:20])
    payload = {
        "atom_type": "dryad_table_row",
        "source_file_record_id": candidate.source_record_id,
        "dataset_doi": candidate.dataset_doi,
        "file_path": candidate.file_path,
        "row_number": row_number,
        "row_values": row_values,
        "preview_path": preview_path,
        "preview_url": preview_url,
        "download_url": candidate.download_url,
        "table_source": "dryad_preview",
    }
    return EvidenceRecord(
        record_id=f"swd:dryad_table:row:{_safe_id(candidate.source_record_id)}:{row_number}",
        lane="behavior",
        source=DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID,
        title=f"Drosophila suzukii Dryad table row {candidate.file_path} row {row_number}",
        text=f"Parsed {COMMON_NAME} Dryad preview table row from {candidate.file_path}: {formatted_values}.",
        species=SPECIES,
        url=candidate.url,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID,
            locator=f"{preview_path}#sheet/1/row/{row_number}",
            retrieved_at=retrieved_at,
            license=candidate.license_text,
            source_url=preview_url,
        ),
        payload=payload,
    )


def _gap_payload(record: EvidenceRecord) -> dict[str, object]:
    return {
        "source": DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID,
        "lane": record.lane,
        "reason": str(record.payload.get("reason") if record.payload else "unknown"),
        "record_id": record.record_id,
        "locator": record.provenance.locator,
        "retrieved_at": record.provenance.retrieved_at,
    }


def build_drosophila_suzukii_dryad_table_row_records(
    artifact_dir: Path,
    *,
    retrieved_at: str | None = None,
    max_table_files: int = DEFAULT_MAX_TABLE_FILES,
    max_table_rows_per_file: int = DEFAULT_MAX_TABLE_ROWS_PER_FILE,
    fetch_preview_text_fn: Callable[[str], str] | None = None,
) -> DrosophilaSuzukiiDryadTableRowsResult:
    artifact_dir = Path(artifact_dir)
    retrieved_at = retrieved_at or utc_now()
    if max_table_files < 1:
        raise ValueError("max_table_files must be positive")
    if max_table_rows_per_file < 1:
        raise ValueError("max_table_rows_per_file must be positive")
    candidates = _source_candidates(SourceIndex(artifact_dir / "source_index.sqlite"))
    fetch_preview = fetch_preview_text_fn or _default_fetch_preview_text
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    parsed_table_file_count = 0
    table_sheet_count = 0
    table_row_count = 0
    preview_dir = artifact_dir / "raw" / "drosophila_suzukii_dryad_table_rows" / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    if not candidates:
        gap = _gap_record(None, reason="swd_dryad_table_candidates_not_found", retrieved_at=retrieved_at, ordinal=1)
        records.append(gap)
        gaps.append(_gap_payload(gap))
    for ordinal, candidate in enumerate(candidates[:max_table_files], start=1):
        file_id = _file_id(candidate)
        if not file_id:
            gap = _gap_record(candidate, reason="dryad_table_preview_id_missing", retrieved_at=retrieved_at, ordinal=ordinal)
            records.append(gap)
            gaps.append(_gap_payload(gap))
            continue
        preview_url = _preview_url(file_id)
        preview_path = preview_dir / f"{_safe_id(candidate.source_record_id)}_{file_id}.js"
        try:
            preview_text = fetch_preview(preview_url)
            preview_path.write_text(preview_text, encoding="utf-8")
            preview = _parse_preview_table(preview_text)
        except Exception as exc:
            gap = _gap_record(candidate, reason="dryad_table_preview_fetch_or_parse_failed", retrieved_at=retrieved_at, ordinal=ordinal, preview_url=preview_url, error=str(exc))
            records.append(gap)
            gaps.append(_gap_payload(gap))
            continue
        if preview is None:
            gap = _gap_record(candidate, reason="dryad_table_preview_empty_or_not_tabular", retrieved_at=retrieved_at, ordinal=ordinal, preview_url=preview_url)
            records.append(gap)
            gaps.append(_gap_payload(gap))
            continue
        headers, data_rows = _table_layout(preview.rows)
        if not headers or not data_rows:
            gap = _gap_record(candidate, reason="dryad_table_preview_no_data_rows", retrieved_at=retrieved_at, ordinal=ordinal, preview_url=preview_url)
            records.append(gap)
            gaps.append(_gap_payload(gap))
            continue
        bounded_rows = data_rows[:max_table_rows_per_file]
        parsed_table_file_count += 1
        table_sheet_count += 1
        table_row_count += len(bounded_rows)
        rel_preview_path = preview_path.relative_to(artifact_dir).as_posix()
        records.append(_sheet_record(candidate, preview_path=rel_preview_path, preview_url=preview_url, headers=headers, row_count=len(bounded_rows), retrieved_at=retrieved_at))
        for row_number, row in bounded_rows:
            values = _row_values(headers, row)
            if values:
                records.append(_row_record(candidate, preview_path=rel_preview_path, preview_url=preview_url, row_number=row_number, row_values=values, retrieved_at=retrieved_at))
        gap = _gap_record(candidate, reason="dryad_table_file_download_blocked_preview_used", retrieved_at=retrieved_at, ordinal=ordinal, preview_url=preview_url)
        records.append(gap)
        gaps.append(_gap_payload(gap))
    if len(candidates) > max_table_files:
        gap = _gap_record(
            None,
            reason="swd_dryad_table_file_limit_applied",
            retrieved_at=retrieved_at,
            ordinal=len(records) + 1,
            error=f"{len(candidates)} candidates found, {max_table_files} processed",
        )
        records.append(gap)
        gaps.append(_gap_payload(gap))
    return DrosophilaSuzukiiDryadTableRowsResult(
        source_id=DROSOPHILA_SUZUKII_DRYAD_TABLE_ROWS_SOURCE_ID,
        records=records,
        gaps=gaps,
        candidate_count=len(candidates),
        parsed_table_file_count=parsed_table_file_count,
        table_sheet_count=table_sheet_count,
        table_row_count=table_row_count,
        gap_count=len(gaps),
    )
