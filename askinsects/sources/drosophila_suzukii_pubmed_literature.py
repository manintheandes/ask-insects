from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import re
import time
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.literature import normalize_doi


DROSOPHILA_SUZUKII_PUBMED_LITERATURE_SOURCE_ID = "drosophila_suzukii_pubmed_literature"
SPECIES = "Drosophila suzukii"
COMMON_NAME = "spotted wing drosophila"
PUBMED_API_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PUBMED_QUERY = (
    '("Drosophila suzukii"[Title/Abstract] OR "spotted wing drosophila"[Title/Abstract] '
    'OR "spotted-wing drosophila"[Title/Abstract]) AND '
    '("2020/01/01"[Date - Publication] : "3000"[Date - Publication])'
)
PUBMED_LICENSE = "NCBI PubMed metadata; source terms apply"
USER_AGENT = "ask-insects/0.1 (+https://openinsects.org)"


@dataclass(frozen=True)
class DrosophilaSuzukiiPubMedLiteratureResult:
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
    pubmed_metadata_ingested_count: int


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_raw_json(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def fetch_json_url(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError(f"URL returned non-object JSON for {url}")
            return payload
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("unreachable")


def _eutils_url(endpoint: str, **params: object) -> str:
    values = {key: str(value) for key, value in params.items() if value is not None}
    values.setdefault("retmode", "json")
    values.setdefault("tool", "ask_insects")
    return f"{PUBMED_API_BASE}/{endpoint}.fcgi?{urlencode(values)}"


def _safe_id(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value or "")).strip("_") or "unknown"


def _as_string(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _int_value(value: object, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _title_key(title: str | None) -> str | None:
    if not title:
        return None
    key = re.sub(r"[^a-z0-9]+", " ", title.lower())
    key = re.sub(r"\b(the|a|an)\b", " ", key)
    key = re.sub(r"\s+", " ", key).strip()
    return key or None


def _doi_from_article(article: dict[str, object]) -> str | None:
    articleids = article.get("articleids")
    if isinstance(articleids, list):
        for item in articleids:
            if not isinstance(item, dict):
                continue
            if str(item.get("idtype", "")).lower() == "doi":
                doi = normalize_doi(_as_string(item.get("value")))
                if doi:
                    return doi
    return normalize_doi(_as_string(article.get("elocationid")))


def _pub_year(date_value: str) -> int | None:
    match = re.search(r"\b(20[2-9][0-9]|30[0-9][0-9])\b", date_value)
    return int(match.group(1)) if match else None


def _authors(article: dict[str, object], limit: int = 8) -> list[str]:
    authors = article.get("authors")
    if not isinstance(authors, list):
        return []
    names: list[str] = []
    for item in authors[:limit]:
        if isinstance(item, dict):
            name = _as_string(item.get("name"))
            if name:
                names.append(name)
    return names


def _candidate_ids(search_payload: dict[str, object]) -> tuple[list[str], int]:
    result = search_payload.get("esearchresult")
    if not isinstance(result, dict):
        return [], 0
    raw_ids = result.get("idlist")
    ids = [str(value) for value in raw_ids if value] if isinstance(raw_ids, list) else []
    return ids, _int_value(result.get("count"))


def _summary_articles(summary_payload: dict[str, object]) -> Iterable[tuple[str, dict[str, object]]]:
    result = summary_payload.get("result")
    if not isinstance(result, dict):
        return []
    uids = result.get("uids")
    ids = [str(uid) for uid in uids if uid] if isinstance(uids, list) else []
    return [(pmid, result[pmid]) for pmid in ids if isinstance(result.get(pmid), dict)]


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
    return "pubmed_metadata_ingested", [], []


def _record_for_article(
    *,
    pmid: str,
    article: dict[str, object],
    raw_path: Path,
    retrieved_at: str,
    by_doi: dict[str, list[dict[str, object]]],
    by_title: dict[str, list[dict[str, object]]],
) -> EvidenceRecord:
    title = _as_string(article.get("title")) or f"PubMed PMID {pmid}"
    doi = _doi_from_article(article)
    journal = _as_string(article.get("fulljournalname")) or _as_string(article.get("source")) or None
    publication_date = _as_string(article.get("pubdate")) or _as_string(article.get("epubdate"))
    publication_year = _pub_year(publication_date)
    authors = _authors(article)
    status, matched_record_ids, matched_sources = _coverage_status(doi=doi, title=title, by_doi=by_doi, by_title=by_title)
    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    payload = {
        "atom_type": "pubmed_literature_audit",
        "pmid": pmid,
        "doi": doi,
        "title": title,
        "authors": authors,
        "journal": journal,
        "publication_date": publication_date or None,
        "publication_year": publication_year,
        "coverage_status": status,
        "matched_record_ids": matched_record_ids,
        "matched_sources": matched_sources,
        "candidate_source": "pubmed_esearch_esummary",
        "query": PUBMED_QUERY,
        "scope": f"{SPECIES} literature from 2020 onward",
        "primary_taxon": SPECIES,
        "common_name": COMMON_NAME,
    }
    text_parts = [
        title,
        f"{SPECIES} ({COMMON_NAME}) PubMed literature audit candidate since 2020.",
        f"coverage_status={status}",
        f"pmid={pmid}",
    ]
    if doi:
        text_parts.append(f"doi={doi}")
    if journal:
        text_parts.append(f"journal={journal}")
    if publication_date:
        text_parts.append(f"publication_date={publication_date}")
    if authors:
        text_parts.append("authors=" + "; ".join(authors))
    if matched_record_ids:
        text_parts.append("matched_record_ids=" + "; ".join(matched_record_ids[:10]))
    return EvidenceRecord(
        record_id=f"swd_pubmed_literature:pubmed:{_safe_id(pmid)}",
        lane="literature",
        source=DROSOPHILA_SUZUKII_PUBMED_LITERATURE_SOURCE_ID,
        title=title,
        text=" ".join(part for part in text_parts if part),
        species=SPECIES,
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_PUBMED_LITERATURE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#result/{pmid}",
            retrieved_at=retrieved_at,
            license=PUBMED_LICENSE,
            source_url=url,
        ),
        payload=payload,
    )


def fetch_drosophila_suzukii_pubmed_literature_records(
    *,
    raw_dir: Path,
    existing_literature_rows: list[dict[str, object]] | None = None,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
    max_results: int = 1000,
    page_size: int = 100,
    delay_seconds: float = 0.34,
) -> DrosophilaSuzukiiPubMedLiteratureResult:
    retrieved = retrieved_at or utc_now()
    fetch = fetch_json or fetch_json_url
    requested_urls: list[str] = []
    raw_artifacts: list[str] = []
    gaps: list[dict[str, object]] = []
    candidate_ids: list[str] = []
    reported_total_count = 0
    bounded_page_size = max(1, min(page_size, 100))
    result_limit = max(1, max_results)
    for page_index, retstart in enumerate(range(0, result_limit, bounded_page_size), start=1):
        url = _eutils_url(
            "esearch",
            db="pubmed",
            term=PUBMED_QUERY,
            retstart=retstart,
            retmax=bounded_page_size,
            sort="pub+date",
        )
        requested_urls.append(url)
        try:
            payload = fetch(url)
        except Exception as exc:
            gaps.append(
                {
                    "source": DROSOPHILA_SUZUKII_PUBMED_LITERATURE_SOURCE_ID,
                    "lane": "literature",
                    "reason": "swd_pubmed_search_failed",
                    "locator": url,
                    "retrieved_at": retrieved,
                    "error": str(exc),
                }
            )
            break
        raw_path = write_raw_json(raw_dir, f"pubmed_esearch_{page_index:04d}.json", payload)
        raw_artifacts.append(raw_path.as_posix())
        ids, count = _candidate_ids(payload)
        reported_total_count = max(reported_total_count, count)
        candidate_ids.extend(uid for uid in ids if uid not in candidate_ids)
        if len(candidate_ids) >= min(reported_total_count, result_limit) or not ids:
            break
        if delay_seconds:
            time.sleep(delay_seconds)
    if reported_total_count > len(candidate_ids):
        gaps.append(
            {
                "source": DROSOPHILA_SUZUKII_PUBMED_LITERATURE_SOURCE_ID,
                "lane": "literature",
                "reason": "swd_pubmed_result_limit_applied",
                "locator": f"pubmed query; max_results={result_limit}",
                "retrieved_at": retrieved,
                "reported_total_count": reported_total_count,
                "fetched_candidate_count": len(candidate_ids),
            }
        )

    by_doi, by_title = _existing_index(existing_literature_rows or [])
    records: list[EvidenceRecord] = []
    for chunk_index, start in enumerate(range(0, len(candidate_ids), 100), start=1):
        ids = candidate_ids[start : start + 100]
        url = _eutils_url("esummary", db="pubmed", id=",".join(ids))
        requested_urls.append(url)
        try:
            payload = fetch(url)
        except Exception as exc:
            gaps.append(
                {
                    "source": DROSOPHILA_SUZUKII_PUBMED_LITERATURE_SOURCE_ID,
                    "lane": "literature",
                    "reason": "swd_pubmed_summary_failed",
                    "locator": url,
                    "retrieved_at": retrieved,
                    "error": str(exc),
                    "pmids": ids,
                }
            )
            continue
        raw_path = write_raw_json(raw_dir, f"pubmed_esummary_{chunk_index:04d}.json", payload)
        raw_artifacts.append(raw_path.as_posix())
        for pmid, article in _summary_articles(payload):
            records.append(
                _record_for_article(
                    pmid=pmid,
                    article=article,
                    raw_path=raw_path,
                    retrieved_at=retrieved,
                    by_doi=by_doi,
                    by_title=by_title,
                )
            )
        if delay_seconds and start + 100 < len(candidate_ids):
            time.sleep(delay_seconds)

    canonical_count = len(existing_literature_rows or [])
    if canonical_count == 0:
        gaps.append(
            {
                "source": DROSOPHILA_SUZUKII_PUBMED_LITERATURE_SOURCE_ID,
                "lane": "literature",
                "reason": "swd_pubmed_no_canonical_literature_rows",
                "locator": "records where source='drosophila_suzukii_core' and lane='literature'",
                "retrieved_at": retrieved,
            }
        )
    already_indexed_count = sum(1 for record in records if (record.payload or {}).get("coverage_status") == "already_indexed")
    return DrosophilaSuzukiiPubMedLiteratureResult(
        source_id=DROSOPHILA_SUZUKII_PUBMED_LITERATURE_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        query=PUBMED_QUERY,
        reported_total_count=reported_total_count,
        candidate_count=len(records),
        canonical_literature_row_count=canonical_count,
        already_indexed_count=already_indexed_count,
        pubmed_metadata_ingested_count=len(records) - already_indexed_count,
    )
