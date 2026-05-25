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


AEDES_OLFACTION_LITERATURE_SOURCE_ID = "aedes_olfaction_literature"
PUBMED_API_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PUBMED_QUERY = (
    '("Aedes aegypti"[Title/Abstract] OR "Ae. aegypti"[Title/Abstract]) AND '
    "(olfaction[Title/Abstract] OR olfactory[Title/Abstract] OR odor[Title/Abstract] OR "
    "odour[Title/Abstract] OR odorant[Title/Abstract] OR chemosensory[Title/Abstract] OR "
    "antenna[Title/Abstract] OR antennal[Title/Abstract] OR Orco[Title/Abstract] OR "
    '"odorant receptor"[Title/Abstract] OR "ionotropic receptor"[Title/Abstract]) AND '
    '("2020/01/01"[Date - Publication] : "3000"[Date - Publication])'
)
PUBMED_LICENSE = "NCBI PubMed metadata; source terms apply"


@dataclass(frozen=True)
class AedesOlfactionLiteratureResult:
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
    request = Request(url, headers={"User-Agent": "ask-insects/0.1"})
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
    elocationid = _as_string(article.get("elocationid"))
    return normalize_doi(elocationid)


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


def _pub_year(date_value: str) -> int | None:
    match = re.search(r"\b(20[2-9][0-9]|30[0-9][0-9])\b", date_value)
    return int(match.group(1)) if match else None


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
        "scope": "Aedes aegypti olfaction, odor, odorant, chemosensory, antenna, Orco, and receptor papers from 2020 onward",
    }
    text_parts = [
        title,
        "Aedes aegypti olfaction literature audit candidate from PubMed since 2020.",
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
        record_id=f"aedes_olfaction_literature:pubmed:{pmid}",
        lane="literature",
        source=AEDES_OLFACTION_LITERATURE_SOURCE_ID,
        title=title,
        text=" ".join(part for part in text_parts if part),
        species="Aedes aegypti",
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=AEDES_OLFACTION_LITERATURE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#result/{pmid}",
            retrieved_at=retrieved_at,
            license=PUBMED_LICENSE,
            source_url=url,
        ),
        payload=payload,
    )


def fetch_aedes_olfaction_literature_records(
    *,
    raw_dir: Path,
    existing_literature_rows: list[dict[str, object]] | None = None,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
    max_results: int = 500,
    page_size: int = 100,
) -> AedesOlfactionLiteratureResult:
    retrieved = retrieved_at or utc_now()
    fetch = fetch_json or fetch_json_url
    existing_rows = existing_literature_rows or []
    by_doi, by_title = _existing_index(existing_rows)
    canonical_literature_row_count = _canonical_literature_row_count(existing_rows)
    requested_urls: list[str] = []
    raw_artifacts: list[str] = []
    gaps: list[dict[str, object]] = []
    all_ids: list[str] = []
    reported_total_count = 0
    page = 0

    bounded_page_size = max(1, min(page_size, 200))
    bounded_max_results = max(1, max_results)
    for retstart in range(0, bounded_max_results, bounded_page_size):
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
            search_payload = fetch(url)
        except Exception as exc:
            gaps.append(
                {
                    "source": AEDES_OLFACTION_LITERATURE_SOURCE_ID,
                    "lane": "literature",
                    "reason": "aedes_olfaction_pubmed_search_failed",
                    "locator": url,
                    "retrieved_at": retrieved,
                    "error": str(exc),
                }
            )
            break
        raw_path = write_raw_json(raw_dir, f"pubmed_esearch_{page + 1:04d}.json", search_payload)
        raw_artifacts.append(raw_path.as_posix())
        ids, reported_count = _candidate_ids(search_payload)
        reported_total_count = max(reported_total_count, reported_count)
        all_ids.extend(uid for uid in ids if uid not in all_ids)
        page += 1
        if len(all_ids) >= min(reported_total_count, bounded_max_results) or not ids:
            break

    if reported_total_count > len(all_ids):
        gaps.append(
            {
                "source": AEDES_OLFACTION_LITERATURE_SOURCE_ID,
                "lane": "literature",
                "reason": "aedes_olfaction_result_limit_applied",
                "locator": f"pubmed query; max_results={bounded_max_results}",
                "retrieved_at": retrieved,
                "reported_total_count": reported_total_count,
                "fetched_candidate_count": len(all_ids),
            }
        )
    if canonical_literature_row_count == 0:
        gaps.append(
            {
                "source": AEDES_OLFACTION_LITERATURE_SOURCE_ID,
                "lane": "literature",
                "reason": "aedes_olfaction_no_canonical_literature_rows",
                "locator": "records where lane='literature' and source='aedes_literature_openalex'",
                "retrieved_at": retrieved,
                "detail": "Coverage comparison could not check the canonical OpenAlex literature lane in this artifact.",
            }
        )

    records: list[EvidenceRecord] = []
    for chunk_index, start in enumerate(range(0, len(all_ids), 100), start=1):
        ids = all_ids[start : start + 100]
        url = _eutils_url("esummary", db="pubmed", id=",".join(ids))
        requested_urls.append(url)
        try:
            summary_payload = fetch(url)
        except Exception as exc:
            gaps.append(
                {
                    "source": AEDES_OLFACTION_LITERATURE_SOURCE_ID,
                    "lane": "literature",
                    "reason": "aedes_olfaction_pubmed_summary_failed",
                    "locator": url,
                    "retrieved_at": retrieved,
                    "error": str(exc),
                    "pmids": ids,
                }
            )
            continue
        raw_path = write_raw_json(raw_dir, f"pubmed_esummary_{chunk_index:04d}.json", summary_payload)
        raw_artifacts.append(raw_path.as_posix())
        for pmid, article in _summary_articles(summary_payload):
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

    if not all_ids and not any(gap.get("reason") == "aedes_olfaction_pubmed_search_failed" for gap in gaps):
        gaps.append(
            {
                "source": AEDES_OLFACTION_LITERATURE_SOURCE_ID,
                "lane": "literature",
                "reason": "aedes_olfaction_no_pubmed_results",
                "locator": "pubmed query",
                "retrieved_at": retrieved,
                "query": PUBMED_QUERY,
            }
        )

    already_indexed_count = sum(1 for record in records if record.payload and record.payload.get("coverage_status") == "already_indexed")
    pubmed_metadata_ingested_count = sum(
        1 for record in records if record.payload and record.payload.get("coverage_status") == "pubmed_metadata_ingested"
    )
    audit_payload = {
        "source": AEDES_OLFACTION_LITERATURE_SOURCE_ID,
        "query": PUBMED_QUERY,
        "reported_total_count": reported_total_count,
        "candidate_count": len(all_ids),
        "canonical_literature_row_count": canonical_literature_row_count,
        "record_count": len(records),
        "already_indexed_count": already_indexed_count,
        "pubmed_metadata_ingested_count": pubmed_metadata_ingested_count,
        "gap_count": len(gaps),
        "retrieved_at": retrieved,
    }
    raw_artifacts.append(write_raw_json(raw_dir, "coverage_audit.json", audit_payload).as_posix())
    return AedesOlfactionLiteratureResult(
        source_id=AEDES_OLFACTION_LITERATURE_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        query=PUBMED_QUERY,
        reported_total_count=reported_total_count,
        candidate_count=len(all_ids),
        canonical_literature_row_count=canonical_literature_row_count,
        already_indexed_count=already_indexed_count,
        pubmed_metadata_ingested_count=pubmed_metadata_ingested_count,
    )
