from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import re
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.literature import normalize_doi


MOSQUITO_REPELLENT_LITERATURE_SOURCE_ID = "mosquito_repellent_literature"
PUBMED_API_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
CROSSREF_API_BASE = "https://api.crossref.org/works"
PUBMED_LICENSE = "NCBI PubMed metadata; source terms apply"
CROSSREF_LICENSE = "Crossref public metadata; source terms apply"
PUBMED_QUERY = (
    "(mosquito[Title/Abstract] OR mosquitoes[Title/Abstract] OR Aedes[Title/Abstract] OR "
    "Anopheles[Title/Abstract] OR Culex[Title/Abstract]) AND "
    "(repellent[Title/Abstract] OR repellents[Title/Abstract] OR repellency[Title/Abstract] OR "
    '"spatial repellent"[Title/Abstract] OR "topical repellent"[Title/Abstract] OR '
    '"personal protection"[Title/Abstract] OR DEET[Title/Abstract] OR picaridin[Title/Abstract] OR '
    "icaridin[Title/Abstract] OR IR3535[Title/Abstract] OR PMD[Title/Abstract] OR citronella[Title/Abstract] OR "
    '"oil of lemon eucalyptus"[Title/Abstract] OR "essential oil"[Title/Abstract] OR '
    '"plant extract"[Title/Abstract]) AND '
    '("2020/01/01"[Date - Publication] : "3000"[Date - Publication])'
)
CROSSREF_QUERIES = (
    "mosquito repellent",
    "mosquito repellents",
    "Aedes repellent",
    "Anopheles repellent",
    "Culex repellent",
    "mosquito DEET",
    "mosquito picaridin",
    "mosquito spatial repellent",
)
MOSQUITO_PATTERN = re.compile(r"\b(?:mosquito(?:es)?|aedes|anopheles|culex)\b", re.I)
REPELLENT_PATTERN = re.compile(
    r"\b(?:repellent|repellents|repellency|deet|picaridin|icaridin|ir3535|pmd|citronella|"
    r"spatial\s+repellent|topical\s+repellent|personal\s+protection|essential\s+oil|plant\s+extract)\b",
    re.I,
)


@dataclass(frozen=True)
class MosquitoRepellentLiteratureResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    pubmed_query: str
    crossref_queries: tuple[str, ...]
    pubmed_reported_total_count: int
    crossref_reported_total_count: int
    candidate_count: int
    canonical_literature_row_count: int
    already_indexed_count: int
    pubmed_metadata_ingested_count: int
    crossref_metadata_ingested_count: int


@dataclass
class ArticleCandidate:
    key: str
    title: str
    pmid: str | None = None
    doi: str | None = None
    journal: str | None = None
    publication_date: str | None = None
    publication_year: int | None = None
    authors: list[str] = field(default_factory=list)
    publisher: str | None = None
    container_titles: list[str] = field(default_factory=list)
    subjects: list[str] = field(default_factory=list)
    url: str | None = None
    candidate_sources: list[str] = field(default_factory=list)
    matched_mosquito_terms: list[str] = field(default_factory=list)
    matched_repellent_terms: list[str] = field(default_factory=list)
    raw_locators: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    crossref_queries: list[str] = field(default_factory=list)


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


def _eutils_url(endpoint: str, **params: object) -> str:
    values = {key: str(value) for key, value in params.items() if value is not None}
    values.setdefault("retmode", "json")
    values.setdefault("tool", "ask_insects")
    return f"{PUBMED_API_BASE}/{endpoint}.fcgi?{urlencode(values)}"


def _crossref_url(*, query: str, cursor: str, rows: int) -> str:
    params = {
        "query.bibliographic": query,
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


def _int_value(value: object, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _pub_year(date_value: str | None) -> int | None:
    if not date_value:
        return None
    match = re.search(r"\b(20[2-9][0-9]|30[0-9][0-9])\b", date_value)
    return int(match.group(1)) if match else None


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


def _candidate_key(*, doi: str | None, pmid: str | None, title: str) -> str:
    if doi:
        return f"doi:{doi}"
    if pmid:
        return f"pmid:{pmid}"
    title_key = _title_key(title)
    return f"title:{title_key}" if title_key else f"title:{abs(hash(title))}"


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", value).strip("_")


def _doi_from_article(article: dict[str, object]) -> str | None:
    articleids = article.get("articleids")
    if isinstance(articleids, list):
        for item in articleids:
            if isinstance(item, dict) and str(item.get("idtype", "")).lower() == "doi":
                doi = normalize_doi(_as_string(item.get("value")))
                if doi:
                    return doi
    return normalize_doi(_as_string(article.get("elocationid")))


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


def _summary_articles(summary_payload: dict[str, object]) -> list[tuple[str, dict[str, object]]]:
    result = summary_payload.get("result")
    if not isinstance(result, dict):
        return []
    uids = result.get("uids")
    ids = [str(uid) for uid in uids if uid] if isinstance(uids, list) else []
    return [(pmid, result[pmid]) for pmid in ids if isinstance(result.get(pmid), dict)]


def _crossref_items(payload: dict[str, object]) -> list[dict[str, object]]:
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
    return _int_value(message.get("total-results"))


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
    return "repellent_metadata_ingested", [], []


def _matched_terms(text: str, pattern: re.Pattern[str]) -> list[str]:
    return sorted({re.sub(r"\s+", " ", match.group(0).lower()) for match in pattern.finditer(text)})


def _is_material_repellent_item(item: dict[str, object]) -> bool:
    values: list[object] = [
        item.get("abstract"),
        item.get("publisher"),
        item.get("type"),
    ]
    values.extend(_text_list(item.get("title")))
    values.extend(_text_list(item.get("subject")))
    values.extend(_text_list(item.get("container-title")))
    text = " ".join(_as_string(value) for value in values)
    return bool(MOSQUITO_PATTERN.search(text) and REPELLENT_PATTERN.search(text))


def _merge_source(candidate: ArticleCandidate, source: str) -> None:
    if source not in candidate.candidate_sources:
        candidate.candidate_sources.append(source)


def _merge_terms(candidate: ArticleCandidate, text: str) -> None:
    for term in _matched_terms(text, MOSQUITO_PATTERN):
        if term not in candidate.matched_mosquito_terms:
            candidate.matched_mosquito_terms.append(term)
    for term in _matched_terms(text, REPELLENT_PATTERN):
        if term not in candidate.matched_repellent_terms:
            candidate.matched_repellent_terms.append(term)


def _add_pubmed_candidate(
    candidates: dict[str, ArticleCandidate],
    *,
    pmid: str,
    article: dict[str, object],
    raw_path: Path,
    raw_index: int,
) -> None:
    title = _as_string(article.get("title")) or f"PubMed PMID {pmid}"
    doi = _doi_from_article(article)
    publication_date = _as_string(article.get("pubdate")) or _as_string(article.get("epubdate")) or None
    key = _candidate_key(doi=doi, pmid=pmid, title=title)
    candidate = candidates.get(key)
    if candidate is None:
        candidate = ArticleCandidate(key=key, title=title, pmid=pmid, doi=doi)
        candidates[key] = candidate
    candidate.pmid = candidate.pmid or pmid
    candidate.doi = candidate.doi or doi
    candidate.journal = candidate.journal or _as_string(article.get("fulljournalname")) or _as_string(article.get("source")) or None
    candidate.publication_date = candidate.publication_date or publication_date
    candidate.publication_year = candidate.publication_year or _pub_year(publication_date)
    candidate.authors = candidate.authors or _authors(article)
    candidate.url = candidate.url or f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    locator = f"{raw_path.as_posix()}#result/{pmid}"
    if locator not in candidate.raw_locators:
        candidate.raw_locators.append(locator)
    if candidate.url and candidate.url not in candidate.source_urls:
        candidate.source_urls.append(candidate.url)
    _merge_source(candidate, "pubmed_esearch_esummary")
    _merge_terms(candidate, " ".join([title, candidate.journal or "", publication_date or ""]))


def _add_crossref_candidate(
    candidates: dict[str, ArticleCandidate],
    *,
    query: str,
    item: dict[str, object],
    raw_path: Path,
    item_index: int,
) -> None:
    doi = normalize_doi(_as_string(item.get("DOI")))
    title = _first_text(item.get("title")) or (f"Crossref work {doi}" if doi else "Crossref mosquito repellent work")
    title_key = _candidate_key(doi=doi, pmid=None, title=title)
    candidate = candidates.get(title_key)
    if candidate is None and doi is None:
        normalized_title = _title_key(title)
        for existing in candidates.values():
            if _title_key(existing.title) == normalized_title:
                candidate = existing
                break
    if candidate is None:
        candidate = ArticleCandidate(key=title_key, title=title, doi=doi)
        candidates[title_key] = candidate
    candidate.doi = candidate.doi or doi
    candidate.publisher = candidate.publisher or _as_string(item.get("publisher")) or None
    candidate.container_titles = candidate.container_titles or _text_list(item.get("container-title"))
    candidate.subjects = candidate.subjects or _text_list(item.get("subject"))
    issued_date = _issued_date(item)
    candidate.publication_date = candidate.publication_date or issued_date
    candidate.publication_year = candidate.publication_year or _pub_year(issued_date)
    url = _as_string(item.get("URL")) or (f"https://doi.org/{doi}" if doi else None)
    candidate.url = candidate.url or url
    locator = f"{raw_path.as_posix()}#items/{item_index}"
    if locator not in candidate.raw_locators:
        candidate.raw_locators.append(locator)
    if url and url not in candidate.source_urls:
        candidate.source_urls.append(url)
    if query not in candidate.crossref_queries:
        candidate.crossref_queries.append(query)
    _merge_source(candidate, "crossref_works")
    _merge_terms(
        candidate,
        " ".join(
            [
                title,
                _as_string(item.get("abstract")),
                candidate.publisher or "",
                " ".join(candidate.container_titles),
                " ".join(candidate.subjects),
            ]
        ),
    )


def _record_for_candidate(
    *,
    candidate: ArticleCandidate,
    retrieved_at: str,
    by_doi: dict[str, list[dict[str, object]]],
    by_title: dict[str, list[dict[str, object]]],
) -> EvidenceRecord:
    status, matched_record_ids, matched_sources = _coverage_status(
        doi=candidate.doi,
        title=candidate.title,
        by_doi=by_doi,
        by_title=by_title,
    )
    if candidate.pmid:
        suffix = f"pubmed:{candidate.pmid}"
    elif candidate.doi:
        suffix = f"doi:{_safe_id(candidate.doi)}"
    else:
        suffix = f"title:{_safe_id(_title_key(candidate.title) or candidate.key)}"
    payload = {
        "pmid": candidate.pmid,
        "doi": candidate.doi,
        "title": candidate.title,
        "authors": candidate.authors,
        "journal": candidate.journal,
        "publication_date": candidate.publication_date,
        "publication_year": candidate.publication_year,
        "publisher": candidate.publisher,
        "container_title": candidate.container_titles,
        "subjects": candidate.subjects,
        "url": candidate.url,
        "candidate_sources": candidate.candidate_sources,
        "crossref_queries": candidate.crossref_queries,
        "mosquito_terms": sorted(candidate.matched_mosquito_terms),
        "repellent_terms": sorted(candidate.matched_repellent_terms),
        "coverage_status": status,
        "matched_record_ids": matched_record_ids,
        "matched_sources": matched_sources,
        "query": PUBMED_QUERY,
        "scope": "Mosquito repellent, repellency, spatial repellent, topical repellent, DEET, picaridin, IR3535, PMD, citronella, essential oil, and plant-extract article metadata from 2020 onward",
        "raw_locators": candidate.raw_locators,
        "source_urls": candidate.source_urls,
    }
    text_parts = [
        candidate.title,
        "Mosquito repellent literature candidate since 2020.",
        f"coverage_status={status}",
        "candidate_sources=" + "; ".join(candidate.candidate_sources),
    ]
    if candidate.pmid:
        text_parts.append(f"pmid={candidate.pmid}")
    if candidate.doi:
        text_parts.append(f"doi={candidate.doi}")
    if candidate.journal:
        text_parts.append(f"journal={candidate.journal}")
    if candidate.publisher:
        text_parts.append(f"publisher={candidate.publisher}")
    if candidate.publication_date:
        text_parts.append(f"publication_date={candidate.publication_date}")
    if candidate.authors:
        text_parts.append("authors=" + "; ".join(candidate.authors))
    if candidate.matched_repellent_terms:
        text_parts.append("repellent_terms=" + "; ".join(sorted(candidate.matched_repellent_terms)))
    if candidate.matched_mosquito_terms:
        text_parts.append("mosquito_terms=" + "; ".join(sorted(candidate.matched_mosquito_terms)))
    if matched_record_ids:
        text_parts.append("matched_record_ids=" + "; ".join(matched_record_ids[:10]))
    license_values = {
        PUBMED_LICENSE if "pubmed_esearch_esummary" in candidate.candidate_sources else "",
        CROSSREF_LICENSE if "crossref_works" in candidate.candidate_sources else "",
    } - {""}
    return EvidenceRecord(
        record_id=f"{MOSQUITO_REPELLENT_LITERATURE_SOURCE_ID}:{suffix}",
        lane="literature",
        source=MOSQUITO_REPELLENT_LITERATURE_SOURCE_ID,
        title=candidate.title,
        text=" ".join(part for part in text_parts if part),
        species="Culicidae",
        url=candidate.url,
        media_url=None,
        provenance=Provenance(
            source_id=MOSQUITO_REPELLENT_LITERATURE_SOURCE_ID,
            locator=candidate.raw_locators[0] if candidate.raw_locators else "metadata candidate",
            retrieved_at=retrieved_at,
            license="; ".join(sorted(license_values)),
            source_url=candidate.url,
        ),
        payload=payload,
    )


def fetch_mosquito_repellent_literature_records(
    *,
    raw_dir: Path,
    existing_literature_rows: list[dict[str, object]] | None = None,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
    pubmed_max_results: int = 1000,
    crossref_max_results: int = 1000,
    page_size: int = 100,
) -> MosquitoRepellentLiteratureResult:
    retrieved = retrieved_at or utc_now()
    fetch = fetch_json or fetch_json_url
    existing_rows = existing_literature_rows or []
    by_doi, by_title = _existing_index(existing_rows)
    canonical_literature_row_count = _canonical_literature_row_count(existing_rows)
    bounded_page_size = max(1, min(page_size, 100))
    pubmed_limit = max(1, pubmed_max_results)
    crossref_limit = max(1, crossref_max_results)
    requested_urls: list[str] = []
    raw_artifacts: list[str] = []
    gaps: list[dict[str, object]] = []
    candidates: dict[str, ArticleCandidate] = {}
    pubmed_ids: list[str] = []
    pubmed_reported_total_count = 0

    for page_index, retstart in enumerate(range(0, pubmed_limit, bounded_page_size), start=1):
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
                    "source": MOSQUITO_REPELLENT_LITERATURE_SOURCE_ID,
                    "lane": "literature",
                    "reason": "mosquito_repellent_pubmed_search_failed",
                    "locator": url,
                    "retrieved_at": retrieved,
                    "error": str(exc),
                }
            )
            break
        raw_path = write_raw_json(raw_dir, f"pubmed_esearch_{page_index:04d}.json", payload)
        raw_artifacts.append(raw_path.as_posix())
        ids, reported_count = _candidate_ids(payload)
        pubmed_reported_total_count = max(pubmed_reported_total_count, reported_count)
        pubmed_ids.extend(uid for uid in ids if uid not in pubmed_ids)
        if len(pubmed_ids) >= min(pubmed_reported_total_count, pubmed_limit) or not ids:
            break

    if pubmed_reported_total_count > len(pubmed_ids):
        gaps.append(
            {
                "source": MOSQUITO_REPELLENT_LITERATURE_SOURCE_ID,
                "lane": "literature",
                "reason": "mosquito_repellent_pubmed_result_limit_applied",
                "locator": f"pubmed query; max_results={pubmed_limit}",
                "retrieved_at": retrieved,
                "reported_total_count": pubmed_reported_total_count,
                "fetched_candidate_count": len(pubmed_ids),
            }
        )

    for chunk_index, start in enumerate(range(0, len(pubmed_ids), 100), start=1):
        ids = pubmed_ids[start : start + 100]
        url = _eutils_url("esummary", db="pubmed", id=",".join(ids))
        requested_urls.append(url)
        try:
            payload = fetch(url)
        except Exception as exc:
            gaps.append(
                {
                    "source": MOSQUITO_REPELLENT_LITERATURE_SOURCE_ID,
                    "lane": "literature",
                    "reason": "mosquito_repellent_pubmed_summary_failed",
                    "locator": url,
                    "retrieved_at": retrieved,
                    "error": str(exc),
                    "pmids": ids,
                }
            )
            continue
        raw_path = write_raw_json(raw_dir, f"pubmed_esummary_{chunk_index:04d}.json", payload)
        raw_artifacts.append(raw_path.as_posix())
        for raw_index, (pmid, article) in enumerate(_summary_articles(payload)):
            _add_pubmed_candidate(candidates, pmid=pmid, article=article, raw_path=raw_path, raw_index=raw_index)

    crossref_reported_total_count = 0
    crossref_material_count = 0
    per_query_limit = max(1, crossref_limit // len(CROSSREF_QUERIES))
    for query in CROSSREF_QUERIES:
        cursor = "*"
        page_index = 0
        query_material_count = 0
        while query_material_count < per_query_limit and crossref_material_count < crossref_limit:
            url = _crossref_url(query=query, cursor=cursor, rows=min(bounded_page_size, per_query_limit - query_material_count))
            requested_urls.append(url)
            try:
                payload = fetch(url)
            except Exception as exc:
                gaps.append(
                    {
                        "source": MOSQUITO_REPELLENT_LITERATURE_SOURCE_ID,
                        "lane": "literature",
                        "reason": "mosquito_repellent_crossref_fetch_failed",
                        "locator": url,
                        "retrieved_at": retrieved,
                        "error": str(exc),
                        "query": query,
                    }
                )
                break
            crossref_reported_total_count += _reported_total(payload)
            raw_name = f"crossref_{_safe_id(query.lower())}_{page_index + 1:04d}.json"
            raw_path = write_raw_json(raw_dir, raw_name, payload)
            raw_artifacts.append(raw_path.as_posix())
            items = _crossref_items(payload)
            for item_index, item in enumerate(items):
                if query_material_count >= per_query_limit or crossref_material_count >= crossref_limit:
                    break
                if not _is_material_repellent_item(item):
                    continue
                before = len(candidates)
                _add_crossref_candidate(candidates, query=query, item=item, raw_path=raw_path, item_index=item_index)
                if len(candidates) > before:
                    crossref_material_count += 1
                    query_material_count += 1
            next_cursor = _next_cursor(payload)
            page_index += 1
            if not next_cursor or next_cursor == cursor or not items:
                break
            cursor = next_cursor

    if crossref_reported_total_count > crossref_material_count or crossref_material_count >= crossref_limit:
        gaps.append(
            {
                "source": MOSQUITO_REPELLENT_LITERATURE_SOURCE_ID,
                "lane": "literature",
                "reason": "mosquito_repellent_crossref_result_limit_applied",
                "locator": f"crossref queries; max_results={crossref_limit}",
                "retrieved_at": retrieved,
                "reported_total_count": crossref_reported_total_count,
                "material_candidate_count": crossref_material_count,
            }
        )
    if canonical_literature_row_count == 0:
        gaps.append(
            {
                "source": MOSQUITO_REPELLENT_LITERATURE_SOURCE_ID,
                "lane": "literature",
                "reason": "mosquito_repellent_no_canonical_literature_rows",
                "locator": "records where lane='literature' and source='aedes_literature_openalex'",
                "retrieved_at": retrieved,
                "detail": "Coverage comparison could not check the canonical OpenAlex literature lane in this artifact.",
            }
        )

    records = [
        _record_for_candidate(candidate=candidate, retrieved_at=retrieved, by_doi=by_doi, by_title=by_title)
        for candidate in sorted(candidates.values(), key=lambda item: (item.publication_year or 0, item.title.lower()), reverse=True)
    ]
    if not records and not any(str(gap.get("reason", "")).endswith("_failed") for gap in gaps):
        gaps.append(
            {
                "source": MOSQUITO_REPELLENT_LITERATURE_SOURCE_ID,
                "lane": "literature",
                "reason": "mosquito_repellent_no_candidates",
                "locator": "PubMed and Crossref repellent queries",
                "retrieved_at": retrieved,
                "pubmed_query": PUBMED_QUERY,
                "crossref_queries": list(CROSSREF_QUERIES),
            }
        )

    already_indexed_count = sum(1 for record in records if record.payload and record.payload.get("coverage_status") == "already_indexed")
    pubmed_metadata_ingested_count = sum(
        1
        for record in records
        if record.payload
        and record.payload.get("coverage_status") == "repellent_metadata_ingested"
        and "pubmed_esearch_esummary" in record.payload.get("candidate_sources", [])
    )
    crossref_metadata_ingested_count = sum(
        1
        for record in records
        if record.payload
        and record.payload.get("coverage_status") == "repellent_metadata_ingested"
        and "crossref_works" in record.payload.get("candidate_sources", [])
    )
    audit_payload = {
        "source": MOSQUITO_REPELLENT_LITERATURE_SOURCE_ID,
        "pubmed_query": PUBMED_QUERY,
        "crossref_queries": list(CROSSREF_QUERIES),
        "pubmed_reported_total_count": pubmed_reported_total_count,
        "crossref_reported_total_count": crossref_reported_total_count,
        "candidate_count": len(records),
        "canonical_literature_row_count": canonical_literature_row_count,
        "already_indexed_count": already_indexed_count,
        "pubmed_metadata_ingested_count": pubmed_metadata_ingested_count,
        "crossref_metadata_ingested_count": crossref_metadata_ingested_count,
        "gap_count": len(gaps),
        "retrieved_at": retrieved,
    }
    raw_artifacts.append(write_raw_json(raw_dir, "coverage_audit.json", audit_payload).as_posix())
    return MosquitoRepellentLiteratureResult(
        source_id=MOSQUITO_REPELLENT_LITERATURE_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        pubmed_query=PUBMED_QUERY,
        crossref_queries=CROSSREF_QUERIES,
        pubmed_reported_total_count=pubmed_reported_total_count,
        crossref_reported_total_count=crossref_reported_total_count,
        candidate_count=len(records),
        canonical_literature_row_count=canonical_literature_row_count,
        already_indexed_count=already_indexed_count,
        pubmed_metadata_ingested_count=pubmed_metadata_ingested_count,
        crossref_metadata_ingested_count=crossref_metadata_ingested_count,
    )
