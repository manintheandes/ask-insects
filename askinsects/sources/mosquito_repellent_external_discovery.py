from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import re
import time
from pathlib import Path
from typing import Callable
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.literature import normalize_doi
from askinsects.sources.mosquito_repellent_literature import MOSQUITO_PATTERN, REPELLENT_PATTERN


MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID = "mosquito_repellent_external_discovery"
OPENALEX_API_BASE = "https://api.openalex.org/works"
EUROPEPMC_API_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
SEMANTIC_SCHOLAR_API_BASE = "https://api.semanticscholar.org/graph/v1/paper/search"
CROSSREF_API_BASE = "https://api.crossref.org/works"
DATACITE_API_BASE = "https://api.datacite.org/dois"
ZENODO_API_BASE = "https://zenodo.org/api/records"
FIGSHARE_API_BASE = "https://api.figshare.com/v2/articles/search"
EXTERNAL_QUERIES = (
    "mosquito repellent",
    "Aedes repellent",
    "mosquito repellency",
    "spatial repellent mosquito",
    "DEET mosquito",
    "picaridin mosquito",
)


@dataclass(frozen=True)
class MosquitoRepellentExternalDiscoveryResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    source_counts: dict[str, int]
    lane_counts: dict[str, int]
    candidate_count: int


@dataclass
class ExternalCandidate:
    key: str
    title: str
    source_family: str
    lane: str
    artifact_type: str
    doi: str | None = None
    external_id: str | None = None
    url: str | None = None
    publication_date: str | None = None
    publication_year: int | None = None
    authors: list[str] = field(default_factory=list)
    venue: str | None = None
    publisher: str | None = None
    repository: str | None = None
    abstract: str | None = None
    terms: list[str] = field(default_factory=list)
    raw_locators: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    raw_payload: dict[str, object] | list[object] | None = None


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_raw_json(raw_dir: Path, filename: str, payload: object) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def fetch_json_url(url: str, body_json: dict[str, object] | None = None) -> object:
    data = json.dumps(body_json).encode("utf-8") if body_json is not None else None
    headers = {
        "Accept": "application/json",
        "User-Agent": "ask-insects/0.1 (mailto:source-plane@example.invalid)",
    }
    if body_json is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers)
    for attempt in range(3):
        try:
            with urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("unreachable")


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


def _title_key(title: str | None) -> str | None:
    if not title:
        return None
    key = re.sub(r"[^a-z0-9]+", " ", title.lower())
    key = re.sub(r"\b(the|a|an)\b", " ", key)
    key = re.sub(r"\s+", " ", key).strip()
    return key or None


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", value).strip("_")


def _candidate_key(*, source_family: str, doi: str | None, external_id: str | None, title: str) -> str:
    if doi:
        return f"doi:{doi}"
    if external_id:
        return f"{source_family}:{external_id}"
    title_key = _title_key(title)
    return f"{source_family}:title:{title_key}" if title_key else f"{source_family}:title:{abs(hash(title))}"


def _material_text(*parts: object) -> str:
    values: list[str] = []
    for part in parts:
        if isinstance(part, list):
            values.extend(_as_string(item) for item in part)
        elif isinstance(part, dict):
            values.append(json.dumps(part, sort_keys=True))
        else:
            values.append(_as_string(part))
    return " ".join(value for value in values if value)


def _is_material(text: str) -> bool:
    return bool(MOSQUITO_PATTERN.search(text) and REPELLENT_PATTERN.search(text))


def _terms(text: str) -> list[str]:
    values = {
        re.sub(r"\s+", " ", match.group(0).lower())
        for pattern in (MOSQUITO_PATTERN, REPELLENT_PATTERN)
        for match in pattern.finditer(text)
    }
    return sorted(values)


def _merge_candidate(candidates: dict[str, ExternalCandidate], candidate: ExternalCandidate) -> None:
    existing = candidates.get(candidate.key)
    if existing is None:
        candidates[candidate.key] = candidate
        return
    existing.source_family = existing.source_family or candidate.source_family
    existing.lane = existing.lane or candidate.lane
    existing.artifact_type = existing.artifact_type or candidate.artifact_type
    existing.doi = existing.doi or candidate.doi
    existing.external_id = existing.external_id or candidate.external_id
    existing.url = existing.url or candidate.url
    existing.publication_date = existing.publication_date or candidate.publication_date
    existing.publication_year = existing.publication_year or candidate.publication_year
    existing.venue = existing.venue or candidate.venue
    existing.publisher = existing.publisher or candidate.publisher
    existing.repository = existing.repository or candidate.repository
    existing.abstract = existing.abstract or candidate.abstract
    for field_name in ("authors", "terms", "raw_locators", "source_urls"):
        target = getattr(existing, field_name)
        for item in getattr(candidate, field_name):
            if item and item not in target:
                target.append(item)


def _openalex_url(query: str, *, per_page: int) -> str:
    return f"{OPENALEX_API_BASE}?{urlencode({'search': query, 'filter': 'from_publication_date:2020-01-01', 'per-page': per_page})}"


def _europepmc_url(query: str, *, source: str | None, page_size: int) -> str:
    expression = f"({query}) AND FIRST_PDATE:[2020-01-01 TO 3000-12-31]"
    if source:
        expression = f"({query}) AND SRC:{source} AND FIRST_PDATE:[2020-01-01 TO 3000-12-31]"
    return f"{EUROPEPMC_API_BASE}?{urlencode({'query': expression, 'format': 'json', 'pageSize': page_size})}"


def _semantic_scholar_url(query: str, *, limit: int) -> str:
    fields = "title,abstract,year,venue,publicationDate,authors,url,externalIds,isOpenAccess,openAccessPdf,citationCount"
    return f"{SEMANTIC_SCHOLAR_API_BASE}?{urlencode({'query': query, 'year': '2020-', 'limit': limit, 'fields': fields})}"


def _crossref_preprint_url(query: str, *, rows: int) -> str:
    return f"{CROSSREF_API_BASE}?{urlencode({'query.bibliographic': query, 'filter': 'from-pub-date:2020-01-01,type:posted-content', 'rows': rows})}"


def _datacite_url(query: str, *, page_size: int) -> str:
    return f"{DATACITE_API_BASE}?{urlencode({'query': query, 'resource-type-id': 'dataset', 'page[size]': page_size})}"


def _zenodo_url(query: str, *, size: int) -> str:
    return f"{ZENODO_API_BASE}?{urlencode({'q': query, 'size': size})}"


def _add_openalex(candidates: dict[str, ExternalCandidate], payload: dict[str, object], raw_path: Path) -> None:
    results = payload.get("results")
    if not isinstance(results, list):
        return
    for index, item in enumerate(results):
        if not isinstance(item, dict):
            continue
        title = _as_string(item.get("title"))
        doi = normalize_doi(_as_string(item.get("doi")))
        location = item.get("primary_location") if isinstance(item.get("primary_location"), dict) else {}
        source = location.get("source") if isinstance(location.get("source"), dict) else {}
        abstract = _as_string(item.get("abstract"))
        text = _material_text(title, abstract, item.get("display_name"), source.get("display_name"), item.get("concepts"), item.get("keywords"))
        if not title or not _is_material(text):
            continue
        external_id = _as_string(item.get("id"))
        url = _as_string(item.get("landing_page_url")) or _as_string(item.get("doi")) or external_id
        candidate = ExternalCandidate(
            key=_candidate_key(source_family="openalex", doi=doi, external_id=external_id, title=title),
            title=title,
            source_family="openalex",
            lane="literature",
            artifact_type="article",
            doi=doi,
            external_id=external_id,
            url=url,
            publication_date=_as_string(item.get("publication_date")) or None,
            publication_year=_int_value(item.get("publication_year"), 0) or None,
            venue=_as_string(source.get("display_name")) or None,
            abstract=abstract or None,
            terms=_terms(text),
            raw_locators=[f"{raw_path.as_posix()}#results/{index}"],
            source_urls=[url] if url else [],
            raw_payload=item,
        )
        _merge_candidate(candidates, candidate)


def _add_europepmc(candidates: dict[str, ExternalCandidate], payload: dict[str, object], raw_path: Path, *, family: str, lane: str) -> None:
    result_list = payload.get("resultList") if isinstance(payload.get("resultList"), dict) else {}
    results = result_list.get("result")
    if not isinstance(results, list):
        return
    for index, item in enumerate(results):
        if not isinstance(item, dict):
            continue
        title = _as_string(item.get("title"))
        doi = normalize_doi(_as_string(item.get("doi")))
        text = _material_text(title, item.get("abstractText"), item.get("authorString"), item.get("journalTitle"), item.get("source"), item.get("pubType"))
        if not title or not _is_material(text):
            continue
        external_id = _as_string(item.get("id"))
        url = _as_string(item.get("fullTextUrlList")) or (f"https://europepmc.org/article/{_as_string(item.get('source'))}/{external_id}" if external_id else None)
        candidate = ExternalCandidate(
            key=_candidate_key(source_family=family, doi=doi, external_id=external_id, title=title),
            title=title,
            source_family=family,
            lane=lane,
            artifact_type="agricola_record" if family == "europepmc_agricola" else "article",
            doi=doi,
            external_id=external_id,
            url=url,
            publication_date=_as_string(item.get("firstPublicationDate")) or None,
            publication_year=_int_value(item.get("pubYear"), 0) or None,
            authors=[_as_string(item.get("authorString"))] if _as_string(item.get("authorString")) else [],
            venue=_as_string(item.get("journalTitle")) or None,
            abstract=_as_string(item.get("abstractText")) or None,
            terms=_terms(text),
            raw_locators=[f"{raw_path.as_posix()}#resultList/result/{index}"],
            source_urls=[url] if url else [],
            raw_payload=item,
        )
        _merge_candidate(candidates, candidate)


def _add_semantic_scholar(candidates: dict[str, ExternalCandidate], payload: dict[str, object], raw_path: Path) -> None:
    results = payload.get("data")
    if not isinstance(results, list):
        return
    for index, item in enumerate(results):
        if not isinstance(item, dict):
            continue
        title = _as_string(item.get("title"))
        ids = item.get("externalIds") if isinstance(item.get("externalIds"), dict) else {}
        doi = normalize_doi(_as_string(ids.get("DOI")))
        text = _material_text(title, item.get("abstract"), item.get("venue"))
        if not title or not _is_material(text):
            continue
        authors = item.get("authors") if isinstance(item.get("authors"), list) else []
        url = _as_string(item.get("url"))
        candidate = ExternalCandidate(
            key=_candidate_key(source_family="semantic_scholar", doi=doi, external_id=_as_string(item.get("paperId")), title=title),
            title=title,
            source_family="semantic_scholar",
            lane="literature",
            artifact_type="article",
            doi=doi,
            external_id=_as_string(item.get("paperId")),
            url=url,
            publication_date=_as_string(item.get("publicationDate")) or None,
            publication_year=_int_value(item.get("year"), 0) or None,
            authors=[_as_string(author.get("name")) for author in authors if isinstance(author, dict) and _as_string(author.get("name"))],
            venue=_as_string(item.get("venue")) or None,
            abstract=_as_string(item.get("abstract")) or None,
            terms=_terms(text),
            raw_locators=[f"{raw_path.as_posix()}#data/{index}"],
            source_urls=[url] if url else [],
            raw_payload=item,
        )
        _merge_candidate(candidates, candidate)


def _add_crossref_preprints(candidates: dict[str, ExternalCandidate], payload: dict[str, object], raw_path: Path) -> None:
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    items = message.get("items")
    if not isinstance(items, list):
        return
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        title = _first_text(item.get("title"))
        doi = normalize_doi(_as_string(item.get("DOI")))
        text = _material_text(title, item.get("abstract"), item.get("publisher"), item.get("container-title"), item.get("type"))
        if not title or not _is_material(text):
            continue
        url = _as_string(item.get("URL")) or (f"https://doi.org/{doi}" if doi else None)
        candidate = ExternalCandidate(
            key=_candidate_key(source_family="crossref_preprint", doi=doi, external_id=None, title=title),
            title=title,
            source_family="crossref_preprint",
            lane="literature",
            artifact_type="preprint",
            doi=doi,
            url=url,
            publication_date=_date_from_crossref_item(item),
            publication_year=_pub_year(_date_from_crossref_item(item)),
            venue=_first_text(item.get("container-title")) or None,
            publisher=_as_string(item.get("publisher")) or None,
            abstract=_as_string(item.get("abstract")) or None,
            terms=_terms(text),
            raw_locators=[f"{raw_path.as_posix()}#message/items/{index}"],
            source_urls=[url] if url else [],
            raw_payload=item,
        )
        _merge_candidate(candidates, candidate)


def _date_from_crossref_item(item: dict[str, object]) -> str | None:
    for key in ("issued", "published-online", "published-print", "posted"):
        payload = item.get(key)
        if not isinstance(payload, dict):
            continue
        parts = payload.get("date-parts")
        if not isinstance(parts, list) or not parts:
            continue
        first = parts[0]
        if not isinstance(first, list) or not first:
            continue
        values = [int(part) for part in first if isinstance(part, int) or str(part).isdigit()]
        if not values:
            continue
        if len(values) == 1:
            return str(values[0])
        if len(values) == 2:
            return f"{values[0]}-{values[1]:02d}"
        return f"{values[0]}-{values[1]:02d}-{values[2]:02d}"
    return None


def _add_datacite(candidates: dict[str, ExternalCandidate], payload: dict[str, object], raw_path: Path) -> None:
    results = payload.get("data")
    if not isinstance(results, list):
        return
    for index, item in enumerate(results):
        if not isinstance(item, dict):
            continue
        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        titles = attrs.get("titles") if isinstance(attrs.get("titles"), list) else []
        title = _first_text([title_item.get("title") for title_item in titles if isinstance(title_item, dict)])
        descriptions = attrs.get("descriptions") if isinstance(attrs.get("descriptions"), list) else []
        abstract = _first_text([desc.get("description") for desc in descriptions if isinstance(desc, dict)])
        doi = normalize_doi(_as_string(attrs.get("doi")) or _as_string(item.get("id")))
        text = _material_text(title, abstract, attrs.get("subjects"), attrs.get("publisher"), attrs.get("types"), attrs.get("container"))
        if not title or not _is_material(text):
            continue
        candidate = ExternalCandidate(
            key=_candidate_key(source_family="datacite", doi=doi, external_id=_as_string(item.get("id")), title=title),
            title=title,
            source_family="datacite",
            lane="datasets",
            artifact_type="dataset_manifest",
            doi=doi,
            external_id=_as_string(item.get("id")),
            url=_as_string(attrs.get("url")) or (f"https://doi.org/{doi}" if doi else None),
            publication_date=_as_string(attrs.get("published")) or None,
            publication_year=_pub_year(_as_string(attrs.get("published"))),
            publisher=_as_string(attrs.get("publisher")) or None,
            repository=_as_string(attrs.get("clientId")) or _as_string(attrs.get("providerId")) or None,
            abstract=abstract or None,
            terms=_terms(text),
            raw_locators=[f"{raw_path.as_posix()}#data/{index}"],
            source_urls=[_as_string(attrs.get("url"))] if _as_string(attrs.get("url")) else [],
            raw_payload=item,
        )
        _merge_candidate(candidates, candidate)


def _add_zenodo(candidates: dict[str, ExternalCandidate], payload: dict[str, object], raw_path: Path) -> None:
    hits = payload.get("hits") if isinstance(payload.get("hits"), dict) else {}
    results = hits.get("hits")
    if not isinstance(results, list):
        return
    for index, item in enumerate(results):
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        title = _as_string(metadata.get("title"))
        doi = normalize_doi(_as_string(metadata.get("doi")) or _as_string(item.get("doi")))
        text = _material_text(title, metadata.get("description"), metadata.get("keywords"), metadata.get("subjects"), item.get("files"))
        if not title or not _is_material(text):
            continue
        candidate = ExternalCandidate(
            key=_candidate_key(source_family="zenodo", doi=doi, external_id=_as_string(item.get("id")), title=title),
            title=title,
            source_family="zenodo",
            lane="datasets",
            artifact_type="repository_record",
            doi=doi,
            external_id=_as_string(item.get("id")),
            url=_as_string(item.get("links", {}).get("html")) if isinstance(item.get("links"), dict) else None,
            publication_date=_as_string(metadata.get("publication_date")) or None,
            publication_year=_pub_year(_as_string(metadata.get("publication_date"))),
            publisher="Zenodo",
            repository="zenodo",
            abstract=_as_string(metadata.get("description")) or None,
            terms=_terms(text),
            raw_locators=[f"{raw_path.as_posix()}#hits/hits/{index}"],
            source_urls=[_as_string(item.get("links", {}).get("html"))] if isinstance(item.get("links"), dict) and _as_string(item.get("links", {}).get("html")) else [],
            raw_payload=item,
        )
        _merge_candidate(candidates, candidate)


def _add_figshare(candidates: dict[str, ExternalCandidate], payload: object, raw_path: Path) -> None:
    if not isinstance(payload, list):
        return
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            continue
        title = _as_string(item.get("title"))
        doi = normalize_doi(_as_string(item.get("doi")))
        text = _material_text(title, item.get("description"), item.get("tags"), item.get("categories"), item.get("defined_type_name"))
        if not title or not _is_material(text):
            continue
        url = _as_string(item.get("url_public_html")) or _as_string(item.get("figshare_url"))
        candidate = ExternalCandidate(
            key=_candidate_key(source_family="figshare", doi=doi, external_id=_as_string(item.get("id")), title=title),
            title=title,
            source_family="figshare",
            lane="datasets",
            artifact_type="repository_record",
            doi=doi,
            external_id=_as_string(item.get("id")),
            url=url,
            publication_date=_as_string(item.get("published_date")) or None,
            publication_year=_pub_year(_as_string(item.get("published_date"))),
            publisher="Figshare",
            repository="figshare",
            abstract=_as_string(item.get("description")) or None,
            terms=_terms(text),
            raw_locators=[f"{raw_path.as_posix()}#/{index}"],
            source_urls=[url] if url else [],
            raw_payload=item,
        )
        _merge_candidate(candidates, candidate)


def _record_for_candidate(candidate: ExternalCandidate, *, retrieved_at: str) -> EvidenceRecord:
    suffix = candidate.key
    payload = {
        "title": candidate.title,
        "source_family": candidate.source_family,
        "artifact_type": candidate.artifact_type,
        "doi": candidate.doi,
        "external_id": candidate.external_id,
        "url": candidate.url,
        "publication_date": candidate.publication_date,
        "publication_year": candidate.publication_year,
        "authors": candidate.authors,
        "venue": candidate.venue,
        "publisher": candidate.publisher,
        "repository": candidate.repository,
        "terms": sorted(candidate.terms),
        "raw_locators": candidate.raw_locators,
        "source_urls": candidate.source_urls,
        "raw_payload": candidate.raw_payload,
        "scope": "External discovery metadata for mosquito repellent research from 2020 onward across OpenAlex, Europe PMC/AGRICOLA, Semantic Scholar, preprints, DataCite, Zenodo, Figshare, and patent-accessibility probes.",
    }
    text_parts = [
        candidate.title,
        f"{candidate.artifact_type} from {candidate.source_family}.",
        "External mosquito repellent discovery record since 2020.",
    ]
    for label, value in (
        ("doi", candidate.doi),
        ("external_id", candidate.external_id),
        ("publication_date", candidate.publication_date),
        ("venue", candidate.venue),
        ("publisher", candidate.publisher),
        ("repository", candidate.repository),
        ("terms", "; ".join(candidate.terms)),
    ):
        if value:
            text_parts.append(f"{label}={value}")
    if candidate.abstract:
        text_parts.append(candidate.abstract[:1000])
    return EvidenceRecord(
        record_id=f"{MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID}:{_safe_id(suffix)}",
        lane=candidate.lane,
        source=MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID,
        title=candidate.title,
        text=" ".join(text_parts),
        species="Culicidae",
        url=candidate.url,
        media_url=None,
        provenance=Provenance(
            source_id=MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID,
            locator=candidate.raw_locators[0] if candidate.raw_locators else "external discovery candidate",
            retrieved_at=retrieved_at,
            license=f"{candidate.source_family} public metadata; source terms apply",
            source_url=candidate.url,
        ),
        payload=payload,
    )


def _gap_record(gap: dict[str, object], *, retrieved_at: str) -> EvidenceRecord:
    reason = _as_string(gap.get("reason")) or "external_source_gap"
    family = _as_string(gap.get("source_family")) or _as_string(gap.get("family")) or "external"
    lane = _as_string(gap.get("lane")) or "literature"
    title = f"Mosquito repellent source gap: {family} {reason}"
    text = " ".join(
        part
        for part in (
            title,
            _as_string(gap.get("detail")),
            f"locator={_as_string(gap.get('locator'))}" if gap.get("locator") else "",
            f"error={_as_string(gap.get('error'))}" if gap.get("error") else "",
        )
        if part
    )
    return EvidenceRecord(
        record_id=f"{MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID}:gap:{_safe_id(family)}:{_safe_id(reason)}",
        lane=lane,
        source=MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID,
        title=title,
        text=text,
        species="Culicidae",
        url=_as_string(gap.get("source_url")) or None,
        media_url=None,
        provenance=Provenance(
            source_id=MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID,
            locator=_as_string(gap.get("locator")) or reason,
            retrieved_at=retrieved_at,
            license="source-gap record; no source data copied",
            source_url=_as_string(gap.get("source_url")) or None,
        ),
        payload=gap | {"retrieved_at": retrieved_at, "artifact_type": "source_gap"},
    )


def _fetch(
    *,
    fetch_json: Callable[[str, dict[str, object] | None], object],
    url: str,
    raw_dir: Path,
    raw_name: str,
    requested_urls: list[str],
    raw_artifacts: list[str],
    gaps: list[dict[str, object]],
    family: str,
    lane: str,
    retrieved_at: str,
    body_json: dict[str, object] | None = None,
) -> tuple[object | None, Path | None]:
    requested_urls.append(url)
    try:
        payload = fetch_json(url, body_json)
    except Exception as exc:
        gaps.append(
            {
                "source": MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID,
                "source_family": family,
                "lane": lane,
                "reason": f"{family}_fetch_failed",
                "locator": url,
                "retrieved_at": retrieved_at,
                "error": str(exc),
            }
        )
        return None, None
    raw_path = write_raw_json(raw_dir, raw_name, {"url": url, "body_json": body_json, "payload": payload})
    raw_artifacts.append(raw_path.as_posix())
    return payload, raw_path


def fetch_mosquito_repellent_external_discovery_records(
    *,
    raw_dir: Path,
    fetch_json: Callable[[str, dict[str, object] | None], object] | None = None,
    retrieved_at: str | None = None,
    max_results_per_source: int = 50,
) -> MosquitoRepellentExternalDiscoveryResult:
    retrieved = retrieved_at or utc_now()
    fetch = fetch_json or fetch_json_url
    limit = max(1, min(max_results_per_source, 100))
    requested_urls: list[str] = []
    raw_artifacts: list[str] = []
    gaps: list[dict[str, object]] = []
    candidates: dict[str, ExternalCandidate] = {}

    for query in EXTERNAL_QUERIES:
        query_id = _safe_id(query.lower())
        payload, raw_path = _fetch(
            fetch_json=fetch,
            url=_openalex_url(query, per_page=limit),
            raw_dir=raw_dir,
            raw_name=f"openalex_{query_id}.json",
            requested_urls=requested_urls,
            raw_artifacts=raw_artifacts,
            gaps=gaps,
            family="openalex",
            lane="literature",
            retrieved_at=retrieved,
        )
        if isinstance(payload, dict) and raw_path:
            _add_openalex(candidates, payload, raw_path)

        payload, raw_path = _fetch(
            fetch_json=fetch,
            url=_europepmc_url(query, source=None, page_size=limit),
            raw_dir=raw_dir,
            raw_name=f"europepmc_{query_id}.json",
            requested_urls=requested_urls,
            raw_artifacts=raw_artifacts,
            gaps=gaps,
            family="europepmc",
            lane="literature",
            retrieved_at=retrieved,
        )
        if isinstance(payload, dict) and raw_path:
            _add_europepmc(candidates, payload, raw_path, family="europepmc", lane="literature")

        payload, raw_path = _fetch(
            fetch_json=fetch,
            url=_semantic_scholar_url(query, limit=limit),
            raw_dir=raw_dir,
            raw_name=f"semantic_scholar_{query_id}.json",
            requested_urls=requested_urls,
            raw_artifacts=raw_artifacts,
            gaps=gaps,
            family="semantic_scholar",
            lane="literature",
            retrieved_at=retrieved,
        )
        if isinstance(payload, dict) and raw_path:
            _add_semantic_scholar(candidates, payload, raw_path)

        payload, raw_path = _fetch(
            fetch_json=fetch,
            url=_crossref_preprint_url(query, rows=limit),
            raw_dir=raw_dir,
            raw_name=f"crossref_preprint_{query_id}.json",
            requested_urls=requested_urls,
            raw_artifacts=raw_artifacts,
            gaps=gaps,
            family="crossref_preprint",
            lane="literature",
            retrieved_at=retrieved,
        )
        if isinstance(payload, dict) and raw_path:
            _add_crossref_preprints(candidates, payload, raw_path)

        payload, raw_path = _fetch(
            fetch_json=fetch,
            url=_datacite_url(query, page_size=limit),
            raw_dir=raw_dir,
            raw_name=f"datacite_{query_id}.json",
            requested_urls=requested_urls,
            raw_artifacts=raw_artifacts,
            gaps=gaps,
            family="datacite",
            lane="datasets",
            retrieved_at=retrieved,
        )
        if isinstance(payload, dict) and raw_path:
            _add_datacite(candidates, payload, raw_path)

        payload, raw_path = _fetch(
            fetch_json=fetch,
            url=_zenodo_url(query, size=limit),
            raw_dir=raw_dir,
            raw_name=f"zenodo_{query_id}.json",
            requested_urls=requested_urls,
            raw_artifacts=raw_artifacts,
            gaps=gaps,
            family="zenodo",
            lane="datasets",
            retrieved_at=retrieved,
        )
        if isinstance(payload, dict) and raw_path:
            _add_zenodo(candidates, payload, raw_path)

        payload, raw_path = _fetch(
            fetch_json=fetch,
            url=FIGSHARE_API_BASE,
            raw_dir=raw_dir,
            raw_name=f"figshare_{query_id}.json",
            requested_urls=requested_urls,
            raw_artifacts=raw_artifacts,
            gaps=gaps,
            family="figshare",
            lane="datasets",
            retrieved_at=retrieved,
            body_json={"search_for": query, "page_size": limit},
        )
        if raw_path:
            _add_figshare(candidates, payload, raw_path)

    agricola_query = "mosquito repellent"
    payload, raw_path = _fetch(
        fetch_json=fetch,
        url=_europepmc_url(agricola_query, source="AGR", page_size=limit),
        raw_dir=raw_dir,
        raw_name="europepmc_agricola_mosquito_repellent.json",
        requested_urls=requested_urls,
        raw_artifacts=raw_artifacts,
        gaps=gaps,
        family="europepmc_agricola",
        lane="literature",
        retrieved_at=retrieved,
    )
    if isinstance(payload, dict) and raw_path:
        _add_europepmc(candidates, payload, raw_path, family="europepmc_agricola", lane="literature")

    gaps.append(
        {
            "source": MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID,
            "source_family": "bioRxiv_medRxiv",
            "lane": "literature",
            "reason": "biorxiv_medrxiv_no_text_search_api",
            "locator": "https://api.biorxiv.org/details/[server]/[interval]/[cursor]/json",
            "source_url": "https://api.biorxiv.org/",
            "retrieved_at": retrieved,
            "detail": "The public bioRxiv/medRxiv endpoint is interval-based, not text-query-based. Crossref posted-content preprint queries are indexed as the accessible bounded preprint proxy.",
        }
    )
    for family, lane, source_url, reason, detail in (
        (
            "patentsview",
            "patents",
            "https://patentsview.org/apis/api-endpoints",
            "patentsview_migrated_or_unavailable_json_api",
            "PatentsView legacy endpoints returned the USPTO Open Data Portal HTML surface during live probe. The source remains a queryable gap until the new JSON endpoint is accessible without credentials.",
        ),
        (
            "uspto_open_data_portal",
            "patents",
            "https://data.uspto.gov/apis/patent-file-wrapper/search",
            "uspto_open_data_portal_requires_api_access",
            "The USPTO Open Data Portal search API is the appropriate current machine-readable patent surface, but live unauthenticated probes returned forbidden responses in this environment.",
        ),
        (
            "cabi",
            "literature",
            "https://www.cabi.org/",
            "cabi_no_public_metadata_api_configured",
            "CABI is not queried until a public metadata API, export, or licensed corpus is supplied. Ask Insects records this as an explicit source gap instead of scraping a protected search surface.",
        ),
        (
            "google_scholar",
            "literature",
            "https://scholar.google.com/",
            "google_scholar_no_public_api",
            "Google Scholar has no supported public API in this repo. The supported expansion surfaces are OpenAlex, Europe PMC, Semantic Scholar, Crossref, PubMed, and repository APIs.",
        ),
    ):
        gaps.append(
            {
                "source": MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID,
                "source_family": family,
                "lane": lane,
                "reason": reason,
                "locator": source_url,
                "source_url": source_url,
                "retrieved_at": retrieved,
                "detail": detail,
            }
        )

    records = [_record_for_candidate(candidate, retrieved_at=retrieved) for candidate in sorted(candidates.values(), key=lambda item: (item.lane, item.source_family, item.title.lower()))]
    records.extend(_gap_record(gap, retrieved_at=retrieved) for gap in gaps)
    if not any(record.payload and record.payload.get("artifact_type") != "source_gap" for record in records):
        gaps.append(
            {
                "source": MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID,
                "source_family": "external_discovery",
                "lane": "literature",
                "reason": "mosquito_repellent_external_no_candidates",
                "locator": "external repellent discovery queries",
                "retrieved_at": retrieved,
                "queries": list(EXTERNAL_QUERIES),
            }
        )

    source_counts: dict[str, int] = {}
    lane_counts: dict[str, int] = {}
    for record in records:
        family = str(record.payload.get("source_family")) if record.payload else record.source
        source_counts[family] = source_counts.get(family, 0) + 1
        lane_counts[record.lane] = lane_counts.get(record.lane, 0) + 1
    audit_payload = {
        "source": MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID,
        "queries": list(EXTERNAL_QUERIES),
        "source_counts": source_counts,
        "lane_counts": lane_counts,
        "candidate_count": len(records),
        "gap_count": len(gaps),
        "requested_urls": requested_urls,
        "retrieved_at": retrieved,
    }
    raw_artifacts.append(write_raw_json(raw_dir, "coverage_audit.json", audit_payload).as_posix())
    return MosquitoRepellentExternalDiscoveryResult(
        source_id=MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        source_counts=source_counts,
        lane_counts=lane_counts,
        candidate_count=len(records),
    )
