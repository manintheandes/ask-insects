from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import re
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.literature import normalize_doi


AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID = "aedes_crossref_literature_audit"
CROSSREF_API_BASE = "https://api.crossref.org/works"
CROSSREF_QUERY = "Aedes aegypti"
CROSSREF_LICENSE = "Crossref public metadata; source terms apply"
MATERIAL_AEDES_PATTERN = re.compile(r"\b(?:aedes|ae\.?|a\.)\s*aegypti\b", re.I)


@dataclass(frozen=True)
class AedesCrossrefLiteratureAuditResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    query: str
    reported_total_count: int
    candidate_count: int
    canonical_literature_row_count: int
    already_indexed_count: int
    crossref_metadata_ingested_count: int


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_raw_json(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def fetch_json_url(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": "ask-insects/0.1 (mailto:source-plane@example.invalid)"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError(f"URL returned non-object JSON for {url}")
            return payload
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("unreachable")


def _crossref_url(*, cursor: str, rows: int) -> str:
    params = {
        "query.bibliographic": CROSSREF_QUERY,
        "filter": "from-pub-date:2020-01-01,type:journal-article",
        "rows": str(max(1, min(rows, 100))),
        "cursor": cursor,
        "select": ",".join(
            [
                "DOI",
                "title",
                "abstract",
                "publisher",
                "container-title",
                "issued",
                "published-print",
                "published-online",
                "type",
                "subject",
                "URL",
                "member",
                "is-referenced-by-count",
                "license",
            ]
        ),
    }
    return f"{CROSSREF_API_BASE}?{urlencode(params)}"


def _as_string(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _first_text(value: object) -> str:
    if isinstance(value, list):
        for item in value:
            text = _as_string(item)
            if text:
                return text
        return ""
    return _as_string(value)


def _text_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [_as_string(item) for item in value if _as_string(item)]
    text = _as_string(value)
    return [text] if text else []


def _issued_date(item: dict[str, object]) -> str | None:
    for key in ("issued", "published-online", "published-print"):
        payload = item.get(key)
        if not isinstance(payload, dict):
            continue
        parts = payload.get("date-parts")
        if not isinstance(parts, list) or not parts:
            continue
        first = parts[0]
        if not isinstance(first, list) or not first:
            continue
        values = [str(int(part)) for part in first if isinstance(part, int) or str(part).isdigit()]
        if not values:
            continue
        if len(values) == 1:
            return values[0]
        if len(values) == 2:
            return f"{values[0]}-{int(values[1]):02d}"
        return f"{values[0]}-{int(values[1]):02d}-{int(values[2]):02d}"
    return None


def _title_key(title: str | None) -> str | None:
    if not title:
        return None
    key = re.sub(r"[^a-z0-9]+", " ", title.lower())
    key = re.sub(r"\b(the|a|an)\b", " ", key)
    key = re.sub(r"\s+", " ", key).strip()
    return key or None


def _safe_doi_id(doi: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", doi).strip("_")


def _has_material_aedes_scope(item: dict[str, object]) -> bool:
    values: list[object] = [
        item.get("abstract"),
        item.get("publisher"),
        item.get("type"),
    ]
    values.extend(_text_list(item.get("title")))
    values.extend(_text_list(item.get("subject")))
    values.extend(_text_list(item.get("container-title")))
    return any(MATERIAL_AEDES_PATTERN.search(_as_string(value)) for value in values)


def _items(payload: dict[str, object]) -> list[dict[str, object]]:
    message = payload.get("message")
    if not isinstance(message, dict):
        return []
    items = message.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _reported_total(payload: dict[str, object]) -> int:
    message = payload.get("message")
    if not isinstance(message, dict):
        return 0
    try:
        return int(str(message.get("total-results") or 0))
    except ValueError:
        return 0


def _next_cursor(payload: dict[str, object]) -> str | None:
    message = payload.get("message")
    if not isinstance(message, dict):
        return None
    cursor = _as_string(message.get("next-cursor"))
    return cursor or None


def _existing_index(existing_literature_rows: list[dict[str, object]]) -> tuple[dict[str, list[dict[str, object]]], dict[str, list[dict[str, object]]]]:
    by_doi: dict[str, list[dict[str, object]]] = {}
    by_title: dict[str, list[dict[str, object]]] = {}
    for row in existing_literature_rows:
        payload = row.get("payload")
        payload_text = json.dumps(payload, sort_keys=True) if isinstance(payload, dict) else _as_string(row.get("payload_json"))
        text = " ".join(_as_string(row.get(key)) for key in ("record_id", "title", "url"))
        for doi in {normalize_doi(text), normalize_doi(payload_text)}:
            if doi:
                by_doi.setdefault(doi, []).append(row)
        key = _title_key(_as_string(row.get("title")))
        if key:
            by_title.setdefault(key, []).append(row)
    return by_doi, by_title


def _canonical_literature_row_count(existing_literature_rows: list[dict[str, object]]) -> int:
    return sum(1 for row in existing_literature_rows if row.get("source") == "aedes_literature_openalex")


def _coverage_status(
    *,
    doi: str | None,
    title: str,
    by_doi: dict[str, list[dict[str, object]]],
    by_title: dict[str, list[dict[str, object]]],
) -> tuple[str, list[str], list[str]]:
    matches: list[dict[str, object]] = []
    if doi and doi in by_doi:
        matches.extend(by_doi[doi])
    key = _title_key(title)
    if key and key in by_title:
        matches.extend(row for row in by_title[key] if row not in matches)
    if matches:
        return (
            "already_indexed",
            sorted({_as_string(row.get("record_id")) for row in matches if row.get("record_id")}),
            sorted({_as_string(row.get("source")) for row in matches if row.get("source")}),
        )
    return "crossref_metadata_ingested", [], []


def _license_links(item: dict[str, object]) -> list[str]:
    payload = item.get("license")
    if not isinstance(payload, list):
        return []
    links: list[str] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        url = _as_string(entry.get("URL"))
        if url:
            links.append(url)
    return links


def _record_for_item(
    *,
    item: dict[str, object],
    raw_path: Path,
    item_index: int,
    retrieved_at: str,
    by_doi: dict[str, list[dict[str, object]]],
    by_title: dict[str, list[dict[str, object]]],
) -> EvidenceRecord:
    doi = normalize_doi(_as_string(item.get("DOI")))
    title = _first_text(item.get("title")) or (f"Crossref work {doi}" if doi else "Crossref Aedes aegypti work")
    publisher = _as_string(item.get("publisher")) or None
    container_titles = _text_list(item.get("container-title"))
    issued_date = _issued_date(item)
    subjects = _text_list(item.get("subject"))
    url = _as_string(item.get("URL")) or (f"https://doi.org/{doi}" if doi else None)
    work_type = _as_string(item.get("type")) or None
    member = _as_string(item.get("member")) or None
    reference_count = item.get("reference-count", item.get("is-referenced-by-count"))
    license_links = _license_links(item)
    status, matched_record_ids, matched_sources = _coverage_status(doi=doi, title=title, by_doi=by_doi, by_title=by_title)
    payload = {
        "doi": doi,
        "title": title,
        "publisher": publisher,
        "container_title": container_titles,
        "issued_date": issued_date,
        "type": work_type,
        "subjects": subjects,
        "url": url,
        "crossref_member": member,
        "reference_count": reference_count,
        "license_links": license_links,
        "coverage_status": status,
        "matched_record_ids": matched_record_ids,
        "matched_sources": matched_sources,
        "candidate_source": "crossref_works",
        "query": CROSSREF_QUERY,
        "scope": "Aedes aegypti Crossref publisher metadata audit from 2020 onward",
    }
    text_parts = [
        title,
        "Aedes aegypti Crossref literature audit candidate since 2020.",
        f"coverage_status={status}",
    ]
    if doi:
        text_parts.append(f"doi={doi}")
    if publisher:
        text_parts.append(f"publisher={publisher}")
    if container_titles:
        text_parts.append("container=" + "; ".join(container_titles[:3]))
    if issued_date:
        text_parts.append(f"issued_date={issued_date}")
    if subjects:
        text_parts.append("subjects=" + "; ".join(subjects[:8]))
    if matched_record_ids:
        text_parts.append("matched_record_ids=" + "; ".join(matched_record_ids[:10]))
    record_suffix = f"doi:{_safe_doi_id(doi)}" if doi else f"item:{raw_path.stem}:{item_index}"
    return EvidenceRecord(
        record_id=f"{AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID}:{record_suffix}",
        lane="literature",
        source=AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID,
        title=title,
        text=" ".join(part for part in text_parts if part),
        species="Aedes aegypti",
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#items/{item_index}",
            retrieved_at=retrieved_at,
            license=CROSSREF_LICENSE,
            source_url=url,
        ),
        payload=payload,
    )


def _candidate_key(item: dict[str, object]) -> str:
    doi = normalize_doi(_as_string(item.get("DOI")))
    if doi:
        return f"doi:{doi}"
    title = _title_key(_first_text(item.get("title")))
    return f"title:{title}" if title else "unknown"


def _result(
    *,
    records: list[EvidenceRecord],
    gaps: list[dict[str, object]],
    raw_artifacts: list[str],
    requested_urls: list[str],
    reported_total_count: int,
    existing_literature_rows: list[dict[str, object]],
) -> AedesCrossrefLiteratureAuditResult:
    already = sum(1 for record in records if record.payload and record.payload.get("coverage_status") == "already_indexed")
    missing = sum(1 for record in records if record.payload and record.payload.get("coverage_status") == "crossref_metadata_ingested")
    return AedesCrossrefLiteratureAuditResult(
        source_id=AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        query=CROSSREF_QUERY,
        reported_total_count=reported_total_count,
        candidate_count=len(records),
        canonical_literature_row_count=_canonical_literature_row_count(existing_literature_rows),
        already_indexed_count=already,
        crossref_metadata_ingested_count=missing,
    )


def fetch_aedes_crossref_literature_audit_records(
    *,
    raw_dir: Path,
    existing_literature_rows: list[dict[str, object]] | None = None,
    fetch_json=None,
    retrieved_at: str | None = None,
    max_results: int = 500,
    page_size: int = 100,
) -> AedesCrossrefLiteratureAuditResult:
    retrieved = retrieved_at or utc_now()
    existing_rows = existing_literature_rows or []
    by_doi, by_title = _existing_index(existing_rows)
    fetch = fetch_json or fetch_json_url
    max_results = max(1, max_results)
    page_size = max(1, min(page_size, 100))
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []
    seen_candidates: set[str] = set()
    cursor = "*"
    reported_total_count = 0
    page_index = 0

    try:
        while len(records) < max_results:
            url = _crossref_url(cursor=cursor, rows=min(page_size, max_results - len(records)))
            requested_urls.append(url)
            payload = fetch(url)
            if not isinstance(payload, dict):
                raise ValueError("Crossref response was not a JSON object")
            reported_total_count = max(reported_total_count, _reported_total(payload))
            raw_path = write_raw_json(raw_dir, f"crossref_works_{page_index + 1:04d}.json", payload)
            raw_artifacts.append(raw_path.as_posix())
            page_items = _items(payload)
            for item_index, item in enumerate(page_items):
                if len(records) >= max_results:
                    break
                if not _has_material_aedes_scope(item):
                    continue
                candidate_key = _candidate_key(item)
                if candidate_key in seen_candidates:
                    continue
                seen_candidates.add(candidate_key)
                records.append(
                    _record_for_item(
                        item=item,
                        raw_path=raw_path,
                        item_index=item_index,
                        retrieved_at=retrieved,
                        by_doi=by_doi,
                        by_title=by_title,
                    )
                )
            next_cursor = _next_cursor(payload)
            page_index += 1
            if not next_cursor or next_cursor == cursor or not page_items:
                break
            cursor = next_cursor
    except Exception as exc:
        gaps.append(
            {
                "source": AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID,
                "reason": "aedes_crossref_fetch_failed",
                "message": str(exc),
                "retrieved_at": retrieved,
                "requested_urls": requested_urls,
            }
        )
        return _result(
            records=[],
            gaps=gaps,
            raw_artifacts=raw_artifacts,
            requested_urls=requested_urls,
            reported_total_count=reported_total_count,
            existing_literature_rows=existing_rows,
        )

    if reported_total_count > len(records) or len(records) >= max_results:
        gaps.append(
            {
                "source": AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID,
                "reason": "aedes_crossref_result_limit_applied",
                "reported_total_count": reported_total_count,
                "candidate_count": len(records),
                "max_results": max_results,
                "retrieved_at": retrieved,
            }
        )
    if not records:
        gaps.append(
            {
                "source": AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID,
                "reason": "aedes_crossref_no_material_aedes_records",
                "retrieved_at": retrieved,
                "requested_urls": requested_urls,
            }
        )
    if _canonical_literature_row_count(existing_rows) == 0:
        gaps.append(
            {
                "source": AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID,
                "reason": "aedes_crossref_no_canonical_literature_rows",
                "retrieved_at": retrieved,
            }
        )

    return _result(
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        reported_total_count=reported_total_count,
        existing_literature_rows=existing_rows,
    )
