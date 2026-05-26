from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from html.parser import HTMLParser
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
from typing import Callable, Iterable
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import zipfile

from askinsects.records import EvidenceRecord, Provenance


EXTRACTED_FACTS_SOURCE_ID = "aedes_extracted_facts"
INPUT_LITERATURE_SOURCE_ID = "aedes_literature_openalex"
SCHEMA_VERSION = "2026-05-24.v1"
MAX_CANDIDATE_TEXT_CHARS = 50_000


@dataclass(frozen=True)
class FactFamily:
    fact_type: str
    lane: str
    context_terms: tuple[str, ...]
    field_terms: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class TextCandidate:
    source_record_id: str
    source_title: str
    species: str | None
    paper_url: str | None
    source_provenance: dict[str, object]
    extraction_source: str
    unit_id: str | None
    unit_index: int | None
    unit_url: str | None
    unit_license: str | None
    unit_provenance: dict[str, object] | None
    text: str
    supplement: dict[str, object] | None = None
    supplement_index: int | None = None
    table_row_index: int | None = None
    table_row: dict[str, str] | None = None
    raw_file_path: str | None = None


@dataclass(frozen=True)
class SupplementCandidate:
    source_record_id: str
    source_title: str
    species: str | None
    paper_url: str | None
    source_provenance: dict[str, object]
    supplement: dict[str, object]


@dataclass(frozen=True)
class ExtractedFactsResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    candidate_count: int
    source_record_count: int
    fulltext_unit_count: int
    max_fulltext_units: int | None
    selected_fulltext_unit_count: int
    truncated_fulltext_unit_count: int
    selected_record_text_count: int
    supplement_manifest_count: int
    supplement_discovery_record_count: int
    max_repository_supplement_discovery_records: int | None
    discovered_supplement_count: int
    downloaded_supplement_file_count: int
    parsed_supplement_file_count: int
    parsed_supplement_row_count: int
    max_pdf_supplement_files: int
    parsed_pdf_supplement_file_count: int
    skipped_pdf_supplement_file_count: int
    fact_counts: dict[str, int]


FACT_FAMILIES: tuple[FactFamily, ...] = (
    FactFamily(
        fact_type="vector_competence",
        lane="vector_competence",
        context_terms=(
            "vector competence",
            "infection rate",
            "dissemination rate",
            "transmission rate",
            "blood meal",
            "saliva",
            "dpi",
        ),
        field_terms={
            "pathogen": ("dengue virus", "dengue", "denv", "zika virus", "zikv", "chikungunya", "yellow fever", "mayaro"),
            "infection": ("infection rate", "infected", "midgut infection"),
            "dissemination": ("dissemination rate", "disseminated"),
            "transmission": ("transmission rate", "transmission efficiency", "saliva"),
            "dose": ("pfu", "tcid50", "viral titer", "blood meal"),
            "temperature": ("temperature", "extrinsic incubation"),
            "tissue": ("midgut", "saliva", "salivary gland", "legs", "wings"),
            "strain": ("strain", "rockefeller", "liverpool", "field population"),
            "timepoint": ("dpi", "days post infection", "days after infection"),
        },
    ),
    FactFamily(
        fact_type="resistance",
        lane="resistance",
        context_terms=(
            "insecticide resistance",
            "resistance",
            "bioassay",
            "mortality",
            "knockdown",
            "lc50",
            "genotype frequency",
        ),
        field_terms={
            "insecticide": ("permethrin", "deltamethrin", "cypermethrin", "temephos", "malathion", "bendiocarb", "pyrethroid"),
            "assay": ("bioassay", "who tube", "cdc bottle", "exposure"),
            "mortality": ("mortality", "mortality rate"),
            "knockdown": ("knockdown", "kdr"),
            "lc_value": ("lc50", "lc90"),
            "mutation": ("vgsc", "v1016g", "f1534c", "v410l", "s989p", "i1011m", "i1011v"),
            "genotype_frequency": ("genotype frequency", "allele frequency", "haplotype"),
            "country": ("brazil", "kenya", "india", "thailand", "mexico", "colombia", "peru", "usa"),
        },
    ),
    FactFamily(
        fact_type="behavior",
        lane="behavior",
        context_terms=(
            "behavior",
            "assay",
            "olfactometer",
            "stimulus",
            "response rate",
            "flight",
            "host seeking",
        ),
        field_terms={
            "assay": ("y-tube", "olfactometer", "flight assay", "choice assay", "wind tunnel"),
            "stimulus": ("lactic acid", "co2", "odor", "stimulus", "human scent"),
            "sex": ("female", "male"),
            "age": ("day old", "days old", "5 day"),
            "strain": ("rockefeller", "liverpool", "strain"),
            "response_metric": ("response rate", "attraction", "landing", "flight speed"),
        },
    ),
    FactFamily(
        fact_type="ecology",
        lane="ecology",
        context_terms=(
            "ecology",
            "habitat",
            "breeding site",
            "larval",
            "season",
            "range",
            "climate",
        ),
        field_terms={
            "habitat": ("habitat", "urban", "peri-urban", "rural"),
            "breeding_site": ("breeding site", "container", "water storage", "larval"),
            "climate": ("temperature", "rainfall", "rainy season", "humidity"),
            "seasonality": ("season", "rainy season", "dry season"),
            "range": ("range", "distribution", "survey"),
            "location": ("brazil", "kenya", "india", "thailand", "mexico", "colombia", "peru", "usa"),
        },
    ),
    FactFamily(
        fact_type="public_health",
        lane="public_health",
        context_terms=(
            "dengue cases",
            "cases",
            "deaths",
            "intervention",
            "serotype",
            "wolbachia",
            "public health",
        ),
        field_terms={
            "case_metric": ("cases", "incidence", "outbreak"),
            "death_metric": ("deaths", "fatalities"),
            "intervention": ("wolbachia", "source reduction", "vector control", "intervention"),
            "location": ("brazil", "kenya", "india", "thailand", "mexico", "colombia", "peru", "usa"),
            "date": ("2024", "2025", "2026"),
            "serotype": ("denv-1", "denv-2", "denv-3", "denv-4", "serotype"),
            "source": ("paho", "who", "cdc", "surveillance"),
        },
    ),
)

PREFILTER_STOPWORDS = {
    "after",
    "assay",
    "blood",
    "cases",
    "days",
    "field",
    "meal",
    "public",
    "rate",
    "source",
    "strain",
}


def _prefilter_tokens() -> tuple[str, ...]:
    tokens: set[str] = set()
    for family in FACT_FAMILIES:
        for term in family.context_terms:
            for token in re.findall(r"[A-Za-z0-9]+", term.lower()):
                if len(token) >= 4 and token not in PREFILTER_STOPWORDS:
                    tokens.add(token)
    return tuple(sorted(tokens))


PREFILTER_TOKENS = _prefilter_tokens()

TEMPERATURE_RE = re.compile(r"\b\d{1,2}(?:\.\d+)?\s?(?:degrees\s*)?(?:°\s*)?C\b", re.I)
PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s?%")
DOSE_RE = re.compile(r"\b(?:10\^?\d+|\d+(?:\.\d+)?)\s?(?:pfu|ffu|tcid50|focus-forming units|plaque-forming units|log10|log)\b", re.I)
MUTATION_RE = re.compile(r"\b[A-Z][0-9]{2,4}[A-Z]\b")
CASE_RE = re.compile(r"\b(?:cases|deaths|fatalities)\s+\d[\d,]*|\b\d[\d,]*\s+(?:cases|deaths|fatalities)\b", re.I)
SUPPORTED_TABLE_SUPPLEMENT_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".docx", ".xml", ".html", ".htm"}
SUPPORTED_TEXT_SUPPLEMENT_EXTENSIONS = {".txt", ".md", ".log", ".r", ".pdf"}
SUPPORTED_SUPPLEMENT_EXTENSIONS = SUPPORTED_TABLE_SUPPLEMENT_EXTENSIONS | SUPPORTED_TEXT_SUPPLEMENT_EXTENSIONS
EUROPE_PMC_SEARCH_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
PMC_OA_SERVICE_BASE = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
FIGSHARE_ARTICLE_API_BASE = "https://api.figshare.com/v2/articles"
ZENODO_RECORD_API_BASE = "https://zenodo.org/api/records"
RESISTANCE_DISCOVERY_TERMS = (
    "insecticide resistance",
    "insecticide",
    "pyrethroid",
    "organophosphate",
    "carbamate",
    "temephos",
    "permethrin",
    "deltamethrin",
    "malathion",
    "bendiocarb",
    "kdr",
    "knockdown resistance",
    "vgsc",
    "v1016g",
    "f1534c",
    "v410l",
    "s989p",
    "lc50",
    "lc90",
    "mortality",
)
RESISTANCE_TABLE_STRONG_FIELDS = {
    "genotype_frequency",
    "insecticide",
    "knockdown",
    "lc_value",
    "mortality",
    "mutation",
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@lru_cache(maxsize=None)
def _pattern_for_term(term: str) -> re.Pattern[str]:
    escaped = re.escape(term).replace(r"\ ", r"[\s-]+")
    return re.compile(r"(?<![A-Za-z0-9])" + escaped + r"(?![A-Za-z0-9])", re.I)


def _matched_terms(text: str, terms: Iterable[str]) -> list[str]:
    lower = text.lower()
    matches = []
    for term in terms:
        if not _might_contain_term(lower, term):
            continue
        if _pattern_for_term(term).search(text):
            matches.append(term)
    return matches


def _might_contain_term(lower_text: str, term: str) -> bool:
    lower_term = term.lower()
    if lower_term in lower_text:
        return True
    if " " in lower_term and lower_term.replace(" ", "-") in lower_text:
        return True
    tokens = re.findall(r"[a-z0-9]+", lower_term)
    return bool(tokens) and all(token in lower_text for token in tokens)


def _safe_json(raw: object) -> dict[str, object]:
    if not raw:
        return {}
    try:
        payload = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", value).strip("_") or "unknown"


def _digest(*parts: object) -> str:
    payload = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _fetch_json_url(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": "ask-insects/0.1"})
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"URL returned non-object JSON for {url}")
    return payload


def _fetch_bytes_url(url: str, max_bytes: int) -> bytes:
    request = Request(url, headers={"User-Agent": "ask-insects/0.1"})
    with urlopen(request, timeout=60) as response:
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > max_bytes:
            raise ValueError(f"supplement exceeds max bytes: {content_length} > {max_bytes}")
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"supplement exceeds max bytes: {len(data)} > {max_bytes}")
    return data


def _snippet(text: str, terms: Iterable[str], limit: int = 760) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return ""
    lower = compact.lower()
    positions = [lower.find(term.lower()) for term in terms if lower.find(term.lower()) >= 0]
    start = max(0, min(positions) - 180) if positions else 0
    snippet = compact[start : start + limit]
    if start > 0:
        snippet = "..." + snippet
    if start + limit < len(compact):
        snippet += "..."
    return snippet


def _dedup(values: Iterable[str]) -> list[str]:
    return [value for value in dict.fromkeys(value for value in values if value)]


def _field_matches(text: str, family: FactFamily) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for name, terms in family.field_terms.items():
        hits = _matched_terms(text, terms)
        if hits:
            fields[name] = hits
    return fields


def _enrich_fields(text: str, fields: dict[str, list[str]]) -> dict[str, object]:
    enriched: dict[str, object] = {key: value for key, value in fields.items()}
    temperatures = _dedup(match.strip() for match in TEMPERATURE_RE.findall(text))
    percentages = _dedup(match.strip() for match in PERCENT_RE.findall(text))
    doses = _dedup(match.strip() for match in DOSE_RE.findall(text))
    mutations = _dedup(match.strip() for match in MUTATION_RE.findall(text))
    case_metrics = _dedup(match.strip() for match in CASE_RE.findall(text))
    if temperatures:
        enriched["temperature_values"] = temperatures[:10]
    if percentages:
        enriched["percent_values"] = percentages[:12]
    if doses:
        enriched["dose_values"] = doses[:10]
    if mutations:
        enriched["mutation_values"] = mutations[:12]
    if case_metrics:
        enriched["case_values"] = case_metrics[:12]
    return enriched


def _source_rows(conn: sqlite3.Connection, *, source_record_ids: list[str] | None = None) -> list[sqlite3.Row]:
    where = """
        SELECT r.record_id, r.title, r.text, r.species, r.url, r.provenance_json, p.payload_json
        FROM records r
        LEFT JOIN record_payloads p ON p.record_id = r.record_id
        WHERE r.lane='literature'
          AND r.source=?
          AND lower(coalesce(r.species, ''))='aedes aegypti'
    """
    params: list[object] = [INPUT_LITERATURE_SOURCE_ID]
    if source_record_ids:
        placeholders = ",".join("?" for _ in source_record_ids)
        where += f" AND r.record_id IN ({placeholders})"
        params.extend(source_record_ids)
    where += " ORDER BY r.record_id"
    return conn.execute(where, params).fetchall()


def _nested_get(payload: dict[str, object], *keys: str) -> object:
    current: object = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _identifier_request(paper: sqlite3.Row) -> dict[str, object]:
    payload = _safe_json(paper["payload_json"])
    ids = payload.get("ids") if isinstance(payload.get("ids"), dict) else {}
    pubmed = payload.get("pubmed") if isinstance(payload.get("pubmed"), dict) else {}
    doi = (
        payload.get("doi")
        or _nested_get(payload, "ids", "doi")
        or _nested_get(payload, "openalex", "doi")
        or _nested_get(payload, "raw_openalex_work", "doi")
        or _nested_get(payload, "raw_openalex_work", "ids", "doi")
        or _pubmed_article_id(pubmed, "doi")
        or paper["url"]
    )
    pmid = payload.get("pmid") or _nested_get(payload, "ids", "pmid") or pubmed.get("pmid") or _pubmed_article_id(pubmed, "pubmed")
    pmcid = payload.get("pmcid") or _nested_get(payload, "ids", "pmcid") or pubmed.get("pmcid") or _pubmed_article_id(pubmed, "pmcid", "pmc")
    if isinstance(ids, dict):
        pmid = pmid or ids.get("pmid")
        pmcid = pmcid or ids.get("pmcid")
    return {
        "record_id": str(paper["record_id"]),
        "title": str(paper["title"]),
        "url": paper["url"],
        "doi": _normalize_doi(doi),
        "pmid": _normalize_pmid(pmid),
        "pmcid": _normalize_pmcid(pmcid),
    }


def fetch_public_supplement_metadata(request: dict[str, object]) -> list[dict[str, object]]:
    supplements: list[dict[str, object]] = []
    query_parts = []
    if request.get("pmcid"):
        query_parts.append(f"PMCID:{request['pmcid']}")
    if request.get("pmid"):
        query_parts.append(f"EXT_ID:{request['pmid']}")
    if request.get("doi"):
        query_parts.append(f'DOI:"{request["doi"]}"')
    if query_parts:
        url = f"{EUROPE_PMC_SEARCH_BASE}?{urlencode({'query': ' OR '.join(query_parts), 'format': 'json', 'pageSize': '1'})}"
        payload = _fetch_json_url(url)
        for item in _payload_supplements(payload):
            item = dict(item)
            item.setdefault("source", "europe_pmc")
            supplements.append(item)
    pmcid = request.get("pmcid")
    if pmcid:
        oa_url = f"{PMC_OA_SERVICE_BASE}?{urlencode({'id': str(pmcid)})}"
        try:
            oa_xml = _fetch_bytes_url(oa_url, 1_000_000)
            supplements.extend(_pmc_oa_supplements(oa_xml, source_url=oa_url))
        except Exception:
            pass
    supplements.extend(_figshare_supplements(request))
    supplements.extend(_zenodo_supplements(request))
    return supplements


def _pubmed_article_id(pubmed: dict[str, object], *idtypes: str) -> str | None:
    wanted = {idtype.lower() for idtype in idtypes}
    articleids = _nested_get(pubmed, "match", "articleids")
    if not isinstance(articleids, list):
        return None
    for article_id in articleids:
        if not isinstance(article_id, dict):
            continue
        idtype = str(article_id.get("idtype") or "").lower()
        if idtype in wanted and article_id.get("value"):
            return str(article_id["value"])
    return None


def _normalize_doi(value: object) -> str | None:
    if not value:
        return None
    doi = str(value).strip()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.I)
    return doi.strip() or None


def _normalize_pmid(value: object) -> str | None:
    if not value:
        return None
    match = re.search(r"\d+", str(value))
    return match.group(0) if match else str(value).strip() or None


def _normalize_pmcid(value: object) -> str | None:
    if not value:
        return None
    match = re.search(r"PMC\d+", str(value), re.I)
    return match.group(0).upper() if match else str(value).strip() or None


def _figshare_article_id_from_request(request: dict[str, object]) -> str | None:
    haystack = " ".join(str(request.get(key) or "") for key in ("doi", "url"))
    match = re.search(r"figshare\.(\d+)", haystack, re.I)
    if match:
        return match.group(1)
    match = re.search(r"figshare\.com/articles/(?:[^/]+/)?(\d+)", haystack, re.I)
    return match.group(1) if match else None


def _figshare_supplements(request: dict[str, object]) -> list[dict[str, object]]:
    article_id = _figshare_article_id_from_request(request)
    if not article_id:
        return []
    api_url = f"{FIGSHARE_ARTICLE_API_BASE}/{article_id}"
    try:
        payload = _fetch_json_url(api_url)
    except Exception:
        return []
    files = payload.get("files") if isinstance(payload.get("files"), list) else []
    license_payload = payload.get("license") if isinstance(payload.get("license"), dict) else {}
    license_value = license_payload.get("name") or license_payload.get("url")
    supplements: list[dict[str, object]] = []
    for file_payload in files:
        if not isinstance(file_payload, dict):
            continue
        url = file_payload.get("download_url")
        if not isinstance(url, str) or not url:
            continue
        name = str(file_payload.get("name") or "Figshare supplementary file")
        extension = Path(urlparse(name).path).suffix.lower()
        mimetype = str(file_payload.get("mimetype") or "")
        supplements.append(
            {
                "title": name,
                "url": url,
                "file_type": extension.lstrip(".") or mimetype,
                "license": license_value,
                "size": file_payload.get("size"),
                "source": "figshare",
                "metadata_url": api_url,
                "checksum_md5": file_payload.get("computed_md5") or file_payload.get("supplied_md5"),
            }
        )
    return supplements


def _zenodo_record_id_from_request(request: dict[str, object]) -> str | None:
    haystack = " ".join(str(request.get(key) or "") for key in ("doi", "url"))
    match = re.search(r"zenodo\.(\d+)", haystack, re.I)
    if match:
        return match.group(1)
    match = re.search(r"zenodo\.org/(?:records?|record)/(\d+)", haystack, re.I)
    return match.group(1) if match else None


def _zenodo_supplements(request: dict[str, object]) -> list[dict[str, object]]:
    record_id = _zenodo_record_id_from_request(request)
    if not record_id:
        return []
    api_url = f"{ZENODO_RECORD_API_BASE}/{record_id}"
    try:
        payload = _fetch_json_url(api_url)
    except Exception:
        return []
    files = payload.get("files") if isinstance(payload.get("files"), list) else []
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    license_payload = metadata.get("license") if isinstance(metadata.get("license"), dict) else {}
    license_value = license_payload.get("id") or license_payload.get("title") or metadata.get("license")
    supplements: list[dict[str, object]] = []
    for file_payload in files:
        if not isinstance(file_payload, dict):
            continue
        links = file_payload.get("links") if isinstance(file_payload.get("links"), dict) else {}
        url = links.get("self") or links.get("download")
        if not isinstance(url, str) or not url:
            continue
        name = str(file_payload.get("key") or Path(urlparse(url).path).name or "Zenodo supplementary file")
        extension = Path(name).suffix.lower() or Path(urlparse(url).path).suffix.lower()
        mimetype = str(file_payload.get("type") or file_payload.get("mimetype") or "")
        supplements.append(
            {
                "title": name,
                "url": url,
                "file_type": extension.lstrip(".") or mimetype,
                "license": license_value if isinstance(license_value, str) else None,
                "size": file_payload.get("size"),
                "source": "zenodo",
                "metadata_url": api_url,
                "checksum": file_payload.get("checksum"),
            }
        )
    return supplements


def _matches_prefilter(text: str) -> bool:
    lower = text.lower()
    return any(token in lower for token in PREFILTER_TOKENS)


def _looks_like_markup_noise(text: str) -> bool:
    lower = text[:20000].lower()
    if "<!doctype html" in lower or "<html" in lower:
        return True
    if any(token in lower for token in ("<head", "<body", "<meta", "itemprop=", "property=\"og:", "name=\"citation_")):
        return True
    encoded_state_tokens = sum(
        lower.count(token)
        for token in (
            "&q;",
            "rotatable-typeahead",
            "requestuuids",
            "servertimecompleted",
            "server/api",
            "statistics/statlets",
            "dc.contributor.",
        )
    )
    markup_tokens = sum(lower.count(token) for token in ("<div", "<style", "<script", "</", "{--", "font-family", "box-sizing"))
    css_tokens = lower.count("--") + lower.count("!important") + lower.count("var(")
    css_declarations = sum(
        lower.count(token)
        for token in (
            "align-items:",
            "background-color:",
            "border-color:",
            "border-radius:",
            "box-shadow:",
            "display:",
            "font-size:",
            "font-weight:",
            "line-height:",
            "padding:",
            "text-align:",
            "transition:",
            "user-select:",
            "vertical-align:",
        )
    )
    css_rule_markers = sum(lower.count(token) for token in ("{", "}", "@media", ".btn", ":hover", ":focus"))
    return (
        encoded_state_tokens >= 12
        or (lower.count("&q;") >= 8 and ("server/api" in lower or "rotatable-typeahead" in lower or "requestuuids" in lower))
        or markup_tokens >= 6
        or css_tokens >= 10
        or css_declarations >= 8
        or (css_declarations >= 5 and css_rule_markers >= 5)
    )


def _bounded_fulltext_rows(
    conn: sqlite3.Connection,
    *,
    max_fulltext_units: int | None,
    source_record_ids: list[str] | None = None,
) -> list[sqlite3.Row]:
    query = """
        SELECT unit_id, record_id, unit_index, text, url, license, provenance_json
        FROM literature_fulltext_units
    """
    params: list[object] = []
    if source_record_ids:
        placeholders = ",".join("?" for _ in source_record_ids)
        query += f" WHERE record_id IN ({placeholders})"
        params.extend(source_record_ids)
    query += " ORDER BY rowid"
    if max_fulltext_units is not None:
        query += " LIMIT ?"
        params.append(max_fulltext_units + 1)
    return conn.execute(query, params).fetchall()


def _text_candidates(
    conn: sqlite3.Connection,
    literature_rows: list[sqlite3.Row],
    *,
    max_fulltext_units: int | None,
    source_record_ids: list[str] | None = None,
) -> tuple[list[TextCandidate], int, int, int, int]:
    if max_fulltext_units is not None and max_fulltext_units < 1:
        raise ValueError("max_fulltext_units must be positive")
    literature_by_id = {str(row["record_id"]): row for row in literature_rows}
    try:
        fulltext_rows = _bounded_fulltext_rows(
            conn,
            max_fulltext_units=max_fulltext_units,
            source_record_ids=source_record_ids,
        )
        fulltext_total = len(fulltext_rows)
        if max_fulltext_units is not None and len(fulltext_rows) > max_fulltext_units:
            fulltext_rows = fulltext_rows[:max_fulltext_units]
    except sqlite3.OperationalError:
        fulltext_rows = []
        fulltext_total = 0

    candidates: list[TextCandidate] = []
    truncated_fulltext_unit_count = 0
    fulltext_record_ids: set[str] = set()
    for unit in fulltext_rows:
        paper = literature_by_id.get(str(unit["record_id"]))
        if paper is None:
            continue
        unit_text = str(unit["text"])
        if _looks_like_markup_noise(unit_text):
            continue
        if len(unit_text) > MAX_CANDIDATE_TEXT_CHARS:
            unit_text = unit_text[:MAX_CANDIDATE_TEXT_CHARS]
            truncated_fulltext_unit_count += 1
        if not _matches_prefilter("\n".join([str(paper["title"]), unit_text])):
            continue
        fulltext_record_ids.add(str(unit["record_id"]))
        candidates.append(
            TextCandidate(
                source_record_id=str(paper["record_id"]),
                source_title=str(paper["title"]),
                species=paper["species"],
                paper_url=paper["url"],
                source_provenance=_safe_json(paper["provenance_json"]),
                extraction_source="literature_fulltext_units",
                unit_id=str(unit["unit_id"]),
                unit_index=int(unit["unit_index"]),
                unit_url=unit["url"],
                unit_license=unit["license"],
                unit_provenance=_safe_json(unit["provenance_json"]),
                text=unit_text,
            )
        )

    selected_record_text_count = 0
    for paper in literature_rows:
        if str(paper["record_id"]) in fulltext_record_ids:
            continue
        record_text = "\n".join([str(paper["title"]), str(paper["text"])])
        if not _matches_prefilter(record_text):
            continue
        if max_fulltext_units is not None and selected_record_text_count >= max_fulltext_units:
            break
        candidates.append(
            TextCandidate(
                source_record_id=str(paper["record_id"]),
                source_title=str(paper["title"]),
                species=paper["species"],
                paper_url=paper["url"],
                source_provenance=_safe_json(paper["provenance_json"]),
                extraction_source="literature_record",
                unit_id=None,
                unit_index=None,
                unit_url=None,
                unit_license=None,
                unit_provenance=None,
                text=record_text,
            )
        )
        selected_record_text_count += 1
    return candidates, fulltext_total, len(fulltext_rows), truncated_fulltext_unit_count, selected_record_text_count


def _as_supplement_list(value: object) -> list[dict[str, object]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _payload_supplements(payload: dict[str, object]) -> list[dict[str, object]]:
    supplements: list[dict[str, object]] = []
    for key in ("supplementary_materials", "supplements", "supplementaryMaterials", "supplementary_material"):
        supplements.extend(_as_supplement_list(payload.get(key)))
    result = payload.get("result")
    if isinstance(result, dict):
        supplements.extend(_payload_supplements(result))
    result_list = payload.get("resultList")
    if isinstance(result_list, dict):
        results = result_list.get("result")
        if isinstance(results, list):
            for result_item in results:
                if isinstance(result_item, dict):
                    supplements.extend(_payload_supplements(result_item))
    supplement_list = payload.get("supplementaryMaterialList")
    if isinstance(supplement_list, dict):
        supplements.extend(_as_supplement_list(supplement_list.get("supplementaryMaterial")))
    return supplements


def _normalize_supplement(raw: dict[str, object]) -> dict[str, object]:
    title = raw.get("title") or raw.get("caption") or raw.get("description") or raw.get("label")
    url = raw.get("url") or raw.get("href") or raw.get("download_url") or raw.get("fileUrl") or raw.get("downloadUrl") or raw.get("location")
    file_type = raw.get("file_type") or raw.get("type") or raw.get("format") or raw.get("mimeType") or raw.get("mime_type")
    license_value = raw.get("license") or raw.get("licence")
    size = raw.get("size") or raw.get("fileSize")
    source = raw.get("source") or raw.get("provider")
    supplement = {
        "title": str(title or "Supplementary material"),
        "url": str(url) if url else None,
        "file_type": str(file_type) if file_type else None,
        "license": str(license_value) if license_value else None,
        "size": size if isinstance(size, int | float | str) else None,
        "source": str(source) if source else None,
    }
    return {key: value for key, value in supplement.items() if value is not None}


def _supplement_candidates(literature_rows: list[sqlite3.Row]) -> list[SupplementCandidate]:
    candidates: list[SupplementCandidate] = []
    seen: set[tuple[str, str, str]] = set()
    for paper in literature_rows:
        payload = _safe_json(paper["payload_json"])
        for raw_supplement in _payload_supplements(payload):
            supplement = _normalize_supplement(raw_supplement)
            supplement.setdefault("source", "record_payload")
            key = (str(paper["record_id"]), str(supplement.get("url") or ""), str(supplement.get("title") or ""))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                SupplementCandidate(
                    source_record_id=str(paper["record_id"]),
                    source_title=str(paper["title"]),
                    species=paper["species"],
                    paper_url=paper["url"],
                    source_provenance=_safe_json(paper["provenance_json"]),
                    supplement=supplement,
                )
            )
    return candidates


def _supplement_candidates_with_discovery(
    literature_rows: list[sqlite3.Row],
    *,
    discover_supplements: bool,
    fetch_supplement_metadata_fn: Callable[[dict[str, object]], list[dict[str, object]]] | None,
    max_supplement_discovery_records: int | None,
    max_repository_supplement_discovery_records: int | None,
    gaps: list[dict[str, object]],
) -> tuple[list[SupplementCandidate], int, int]:
    if max_supplement_discovery_records is not None and max_supplement_discovery_records < 1:
        raise ValueError("max_supplement_discovery_records must be positive")
    if max_repository_supplement_discovery_records is not None and max_repository_supplement_discovery_records < 0:
        raise ValueError("max_repository_supplement_discovery_records must not be negative")
    candidates: list[SupplementCandidate] = []
    seen: set[tuple[str, str, str]] = set()
    discovered_count = 0
    discovery_record_count = 0

    def add_candidate(paper: sqlite3.Row, raw_supplement: dict[str, object], fallback_source: str) -> None:
        nonlocal candidates
        supplement = _normalize_supplement(raw_supplement)
        supplement.setdefault("source", fallback_source)
        key = (str(paper["record_id"]), str(supplement.get("url") or ""), str(supplement.get("title") or ""))
        if key in seen:
            return
        seen.add(key)
        candidates.append(
            SupplementCandidate(
                source_record_id=str(paper["record_id"]),
                source_title=str(paper["title"]),
                species=paper["species"],
                paper_url=paper["url"],
                source_provenance=_safe_json(paper["provenance_json"]),
                supplement=supplement,
            )
        )

    for paper in literature_rows:
        payload = _safe_json(paper["payload_json"])
        for raw_supplement in _payload_supplements(payload):
            add_candidate(paper, raw_supplement, "record_payload")

    if discover_supplements and fetch_supplement_metadata_fn is not None:
        discovery_rows = _prioritized_supplement_discovery_rows(literature_rows)
        if max_supplement_discovery_records is not None and len(discovery_rows) > max_supplement_discovery_records:
            bounded_rows = discovery_rows[:max_supplement_discovery_records]
            bounded_record_ids = {str(row["record_id"]) for row in bounded_rows}
            repository_rows = [
                row
                for row in discovery_rows[max_supplement_discovery_records:]
                if _is_repository_supplement_row(row) and str(row["record_id"]) not in bounded_record_ids
            ]
            repository_rows_before_cap = len(repository_rows)
            if max_repository_supplement_discovery_records is not None:
                repository_rows = repository_rows[:max_repository_supplement_discovery_records]
            gaps.append(
                {
                    "source": EXTRACTED_FACTS_SOURCE_ID,
                    "reason": "supplement_discovery_record_limit_applied",
                    "max_supplement_discovery_records": max_supplement_discovery_records,
                    "max_repository_supplement_discovery_records": max_repository_supplement_discovery_records,
                    "source_record_count": len(literature_rows),
                    "discoverable_source_record_count": len(discovery_rows),
                    "repository_backed_records_added_after_limit": len(repository_rows),
                    "repository_backed_records_available_after_limit": repository_rows_before_cap,
                }
            )
            discovery_rows = bounded_rows + repository_rows
        for paper in discovery_rows:
            request = _identifier_request(paper)
            discovery_record_count += 1
            try:
                fetched = fetch_supplement_metadata_fn(request)
                discovered_count += len(fetched)
                for raw_supplement in fetched:
                    add_candidate(paper, raw_supplement, "metadata_fetch")
            except Exception as exc:
                gaps.append(
                    {
                        "source": EXTRACTED_FACTS_SOURCE_ID,
                        "reason": "supplement_metadata_fetch_failed",
                        "record_id": str(paper["record_id"]),
                        "error": str(exc),
                    }
                )
    return candidates, discovered_count, discovery_record_count


def _repository_supplement_rank(request: dict[str, object], url: str) -> int:
    if _figshare_article_id_from_request(request) or _zenodo_record_id_from_request(request):
        return 1
    lowered = url.lower()
    if "figshare" in lowered or "zenodo" in lowered:
        return 1
    return 0


def _is_repository_supplement_row(paper: sqlite3.Row) -> bool:
    request = _identifier_request(paper)
    return bool(_repository_supplement_rank(request, str(paper["url"] or "")))


def _supplement_discovery_score(paper: sqlite3.Row) -> tuple[int, int, int, int, int, str]:
    request = _identifier_request(paper)
    if not any(request.get(key) for key in ("doi", "pmid", "pmcid")):
        return (0, 0, 0, 0, 0, str(paper["record_id"]))
    title = str(paper["title"] or "").lower()
    text = str(paper["text"] or "").lower()
    payload = str(paper["payload_json"] or "").lower()
    url = str(paper["url"] or "").lower()
    resistance_relevant = 1 if any(term in f"{title}\n{text}\n{payload}" for term in RESISTANCE_DISCOVERY_TERMS) else 0
    repository = _repository_supplement_rank(request, url)
    figshare = 1 if _figshare_article_id_from_request(request) else 0
    supplementish = 1 if any(term in title for term in ("additional file", "supplementary", "supplement ", " table", "dataset")) else 0
    pmc_or_pubmed = 1 if request.get("pmcid") or request.get("pmid") else 0
    if "figshare" in url:
        figshare = 1
    return (resistance_relevant, repository, figshare, supplementish, pmc_or_pubmed, str(paper["record_id"]))


def _prioritized_supplement_discovery_rows(literature_rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    discoverable = [
        paper
        for paper in literature_rows
        if any(_identifier_request(paper).get(key) for key in ("doi", "pmid", "pmcid"))
    ]
    return sorted(discoverable, key=_supplement_discovery_score, reverse=True)


def _supplement_extension(supplement: dict[str, object]) -> str:
    file_type = str(supplement.get("file_type") or "").lower()
    url = str(supplement.get("url") or "")
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in SUPPORTED_SUPPLEMENT_EXTENSIONS:
        return suffix
    if "csv" in file_type:
        return ".csv"
    if "tsv" in file_type or "tab" in file_type:
        return ".tsv"
    if "spreadsheet" in file_type or "xlsx" in file_type:
        return ".xlsx"
    if "docx" in file_type or "wordprocessingml.document" in file_type:
        return ".docx"
    if "html" in file_type:
        return ".html"
    if "xml" in file_type:
        return ".xml"
    if file_type in {"pdf", "application/pdf"} or "pdf" in file_type:
        return ".pdf"
    if file_type in {"txt", "text", "text/plain", "plain"}:
        return ".txt"
    if file_type in {"md", "markdown", "text/markdown"}:
        return ".md"
    if file_type in {"log", "text/x-log"}:
        return ".log"
    if file_type in {"r", "rscript", "text/x-r", "application/r"}:
        return ".r"
    return suffix


def _safe_raw_filename(candidate: SupplementCandidate, index: int, extension: str) -> str:
    digest = _digest(candidate.source_record_id, candidate.supplement.get("url"), index)
    suffix = extension if extension in SUPPORTED_SUPPLEMENT_EXTENSIONS else ".dat"
    return f"{_normalize_id(candidate.source_record_id)}_{index}_{digest}{suffix}"


def _decode_table_bytes(data: bytes) -> str:
    return data.decode("utf-8-sig", errors="replace")


def _parse_delimited_rows(data: bytes, delimiter: str) -> list[dict[str, str]]:
    text = _decode_table_bytes(data)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows: list[dict[str, str]] = []
    for row in reader:
        cleaned = {str(key).strip(): str(value).strip() for key, value in row.items() if key and value is not None and str(value).strip()}
        if cleaned:
            rows.append(cleaned)
    return rows


def _xml_text(element: ET.Element) -> str:
    return " ".join(part.strip() for part in element.itertext() if part and part.strip())


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _parse_xml_rows(data: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(data)
    table_rows: list[list[str]] = []
    for tr in root.iter():
        if _strip_ns(tr.tag) != "tr":
            continue
        values = [_xml_text(child) for child in list(tr) if _strip_ns(child.tag) in {"th", "td"}]
        if values:
            table_rows.append(values)
    if table_rows:
        headers = table_rows[0]
        return [
            {headers[index]: value for index, value in enumerate(row) if index < len(headers) and headers[index] and value}
            for row in table_rows[1:]
        ]

    rows: list[dict[str, str]] = []
    for row in root.iter():
        if _strip_ns(row.tag) not in {"row", "record"}:
            continue
        values = {
            _strip_ns(child.tag).replace("_", " "): _xml_text(child)
            for child in list(row)
            if _xml_text(child)
        }
        if values:
            rows.append(values)
    return rows


class _SimpleHTMLTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_cell = False
        self._cell_parts: list[str] = []
        self._current_row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() == "tr":
            self._current_row = []
        if tag.lower() in {"td", "th"}:
            self._in_cell = True
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_cell and data.strip():
            self._cell_parts.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._in_cell:
            self._current_row.append(" ".join(self._cell_parts))
            self._cell_parts = []
            self._in_cell = False
        if tag == "tr" and self._current_row:
            self.rows.append(self._current_row)
            self._current_row = []


def _parse_html_rows(data: bytes) -> list[dict[str, str]]:
    parser = _SimpleHTMLTableParser()
    parser.feed(_decode_table_bytes(data))
    if len(parser.rows) < 2:
        return []
    headers = parser.rows[0]
    return [
        {headers[index]: value for index, value in enumerate(row) if index < len(headers) and headers[index] and value}
        for row in parser.rows[1:]
    ]


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values: list[str] = []
    for item in root.iter():
        if _strip_ns(item.tag) != "si":
            continue
        values.append(_xml_text(item))
    return values


def _column_index(cell_ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", cell_ref.upper())
    value = 0
    for letter in letters:
        value = value * 26 + (ord(letter) - ord("A") + 1)
    return max(0, value - 1)


def _parse_xlsx_rows(data: bytes) -> list[dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        shared_strings = _xlsx_shared_strings(archive)
        sheet_name = "xl/worksheets/sheet1.xml"
        root = ET.fromstring(archive.read(sheet_name))
    table: list[list[str]] = []
    for row in root.iter():
        if _strip_ns(row.tag) != "row":
            continue
        values: dict[int, str] = {}
        for cell in list(row):
            if _strip_ns(cell.tag) != "c":
                continue
            cell_ref = str(cell.attrib.get("r", "A1"))
            value_node = next((child for child in list(cell) if _strip_ns(child.tag) == "v"), None)
            raw_value = _xml_text(value_node) if value_node is not None else ""
            if cell.attrib.get("t") == "s" and raw_value.isdigit() and int(raw_value) < len(shared_strings):
                raw_value = shared_strings[int(raw_value)]
            values[_column_index(cell_ref)] = raw_value
        if values:
            max_index = max(values)
            table.append([values.get(index, "") for index in range(max_index + 1)])
    if len(table) < 2:
        return []
    headers = table[0]
    return [
        {headers[index]: value for index, value in enumerate(row) if index < len(headers) and headers[index] and value}
        for row in table[1:]
    ]


def _parse_docx_rows(data: bytes) -> list[dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    rows: list[dict[str, str]] = []
    for table in root.iter():
        if _strip_ns(table.tag) != "tbl":
            continue
        table_rows: list[list[str]] = []
        for row in list(table):
            if _strip_ns(row.tag) != "tr":
                continue
            values: list[str] = []
            for cell in list(row):
                if _strip_ns(cell.tag) != "tc":
                    continue
                value = _xml_text(cell)
                if value:
                    values.append(value)
            if values:
                table_rows.append(values)
        if len(table_rows) < 2:
            continue
        headers = table_rows[0]
        rows.extend(
            {headers[index]: value for index, value in enumerate(row) if index < len(headers) and headers[index] and value}
            for row in table_rows[1:]
        )
    return rows


def _parse_supported_table_rows(data: bytes, extension: str) -> list[dict[str, str]]:
    if extension == ".csv":
        return _parse_delimited_rows(data, ",")
    if extension == ".tsv":
        return _parse_delimited_rows(data, "\t")
    if extension == ".xlsx":
        return _parse_xlsx_rows(data)
    if extension == ".docx":
        return _parse_docx_rows(data)
    if extension == ".xml":
        return _parse_xml_rows(data)
    if extension in {".html", ".htm"}:
        return _parse_html_rows(data)
    return []


def _parse_supported_text(data: bytes, extension: str) -> str:
    if extension not in SUPPORTED_TEXT_SUPPLEMENT_EXTENSIONS:
        return ""
    if extension == ".pdf":
        return _parse_pdf_text(data)
    text = data.decode("utf-8", errors="replace")
    return re.sub(r"\s+", " ", text).strip()


def _parse_pdf_text(data: bytes) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / "supplement.pdf"
        pdf_path.write_bytes(data)
        result = subprocess.run(
            ["pdftotext", "-layout", pdf_path.as_posix(), "-"],
            check=True,
            capture_output=True,
            timeout=30,
        )
    return re.sub(r"\s+", " ", result.stdout.decode("utf-8", errors="replace")).strip()


def _pmc_oa_supplements(data: bytes, *, source_url: str) -> list[dict[str, object]]:
    root = ET.fromstring(data)
    supplements: list[dict[str, object]] = []
    for node in root.iter():
        if _strip_ns(node.tag) not in {"file", "link"}:
            continue
        href = node.attrib.get("href") or node.attrib.get("url")
        if not href:
            continue
        extension = Path(urlparse(href).path).suffix.lower()
        if extension not in SUPPORTED_TABLE_SUPPLEMENT_EXTENSIONS:
            continue
        supplements.append(
            {
                "title": node.attrib.get("title") or Path(urlparse(href).path).name or "PMC OA supplementary file",
                "url": href,
                "file_type": extension.lstrip("."),
                "license": node.attrib.get("license"),
                "source": "pmc_oa",
                "metadata_url": source_url,
            }
        )
    return supplements


def _table_row_text(row: dict[str, str]) -> str:
    return "Supplement table row. " + ". ".join(f"{key}: {value}" for key, value in row.items() if value)


def _row_declared_fact_type(row: dict[str, str] | None) -> str | None:
    if not row:
        return None
    for key in ("domain", "fact_type", "fact type", "lane"):
        for row_key, value in row.items():
            if row_key.lower().strip() == key and value:
                return value.lower().strip().replace(" ", "_")
    return None


def _is_supported_parsed_resistance_row(
    row: dict[str, str] | None,
    fields: dict[str, list[str]],
    declared_fact_type: str | None,
) -> bool:
    if not row:
        return True
    if declared_fact_type == "resistance":
        return True
    return any(field in fields for field in RESISTANCE_TABLE_STRONG_FIELDS)


def _download_and_parse_supplement_rows(
    supplement_candidates: list[SupplementCandidate],
    *,
    artifact_dir: Path,
    retrieved_at: str,
    fetch_supplement_file_fn: Callable[[str, int], bytes],
    max_supplement_files: int,
    max_supplement_bytes: int,
    max_pdf_supplement_files: int,
    gaps: list[dict[str, object]],
) -> tuple[list[TextCandidate], int, int, int, int, int]:
    if max_supplement_files < 1:
        raise ValueError("max_supplement_files must be positive")
    if max_supplement_bytes < 1:
        raise ValueError("max_supplement_bytes must be positive")
    if max_pdf_supplement_files < 0:
        raise ValueError("max_pdf_supplement_files must not be negative")
    raw_dir = artifact_dir / "raw" / "extracted_facts" / "supplements"
    raw_dir.mkdir(parents=True, exist_ok=True)
    candidates: list[TextCandidate] = []
    downloaded_count = 0
    parsed_file_count = 0
    parsed_row_count = 0
    parsed_pdf_count = 0
    skipped_pdf_count = 0
    for index, candidate in enumerate(supplement_candidates):
        if downloaded_count >= max_supplement_files:
            gaps.append(
                {
                    "source": EXTRACTED_FACTS_SOURCE_ID,
                    "reason": "supplement_file_limit_applied",
                    "max_supplement_files": max_supplement_files,
                }
            )
            break
        url = candidate.supplement.get("url")
        if not isinstance(url, str) or not url:
            continue
        extension = _supplement_extension(candidate.supplement)
        if extension not in SUPPORTED_SUPPLEMENT_EXTENSIONS:
            gaps.append(
                {
                    "source": EXTRACTED_FACTS_SOURCE_ID,
                    "reason": "unsupported_supplement_type",
                    "record_id": candidate.source_record_id,
                    "url": url,
                    "file_type": candidate.supplement.get("file_type"),
                }
            )
            continue
        if extension == ".pdf" and parsed_pdf_count >= max_pdf_supplement_files:
            skipped_pdf_count += 1
            gaps.append(
                {
                    "source": EXTRACTED_FACTS_SOURCE_ID,
                    "reason": "pdf_supplement_file_limit_applied",
                    "record_id": candidate.source_record_id,
                    "url": url,
                    "title": candidate.supplement.get("title"),
                    "max_pdf_supplement_files": max_pdf_supplement_files,
                }
            )
            continue
        try:
            data = fetch_supplement_file_fn(url, max_supplement_bytes)
            downloaded_count += 1
            raw_path = raw_dir / _safe_raw_filename(candidate, index, extension)
            raw_path.write_bytes(data)
            if extension in SUPPORTED_TEXT_SUPPLEMENT_EXTENSIONS:
                text = _parse_supported_text(data, extension)
                rows = []
            else:
                text = ""
                rows = _parse_supported_table_rows(data, extension)
        except Exception as exc:
            gaps.append(
                {
                    "source": EXTRACTED_FACTS_SOURCE_ID,
                    "reason": "supplement_table_parse_failed",
                    "record_id": candidate.source_record_id,
                    "url": url,
                    "error": str(exc),
                }
            )
            continue
        if text:
            parsed_file_count += 1
            if extension == ".pdf":
                parsed_pdf_count += 1
            candidates.append(
                TextCandidate(
                    source_record_id=candidate.source_record_id,
                    source_title=candidate.source_title,
                    species=candidate.species,
                    paper_url=candidate.paper_url,
                    source_provenance=candidate.source_provenance,
                    extraction_source="supplement_text",
                    unit_id=None,
                    unit_index=None,
                    unit_url=url,
                    unit_license=candidate.supplement.get("license") if isinstance(candidate.supplement.get("license"), str) else None,
                    unit_provenance={
                        "source_id": EXTRACTED_FACTS_SOURCE_ID,
                        "locator": raw_path.relative_to(artifact_dir).as_posix(),
                        "retrieved_at": retrieved_at,
                        "source_url": url,
                    },
                    text=text[:MAX_CANDIDATE_TEXT_CHARS],
                    supplement=candidate.supplement,
                    supplement_index=index,
                    raw_file_path=raw_path.relative_to(artifact_dir).as_posix(),
                )
            )
            continue
        if not rows:
            gaps.append(
                {
                    "source": EXTRACTED_FACTS_SOURCE_ID,
                    "reason": "supplement_table_no_rows",
                    "record_id": candidate.source_record_id,
                    "url": url,
                }
            )
            continue
        parsed_file_count += 1
        for row_index, row in enumerate(rows, start=1):
            parsed_row_count += 1
            candidates.append(
                TextCandidate(
                    source_record_id=candidate.source_record_id,
                    source_title=candidate.source_title,
                    species=candidate.species,
                    paper_url=candidate.paper_url,
                    source_provenance=candidate.source_provenance,
                    extraction_source="supplement_table_row",
                    unit_id=None,
                    unit_index=None,
                    unit_url=url,
                    unit_license=candidate.supplement.get("license") if isinstance(candidate.supplement.get("license"), str) else None,
                    unit_provenance={
                        "source_id": EXTRACTED_FACTS_SOURCE_ID,
                        "locator": f"{raw_path.relative_to(artifact_dir).as_posix()}#row/{row_index}",
                        "retrieved_at": retrieved_at,
                        "source_url": url,
                    },
                    text=_table_row_text(row),
                    supplement=candidate.supplement,
                    supplement_index=index,
                    table_row_index=row_index,
                    table_row=row,
                    raw_file_path=raw_path.relative_to(artifact_dir).as_posix(),
                )
            )
    return candidates, downloaded_count, parsed_file_count, parsed_row_count, parsed_pdf_count, skipped_pdf_count


def _record_for_supplement(candidate: SupplementCandidate, *, index: int, retrieved_at: str) -> EvidenceRecord:
    supplement = candidate.supplement
    title_text = str(supplement.get("title") or "Supplementary material")
    url = supplement.get("url")
    digest = _digest(candidate.source_record_id, title_text, url, index)
    locator = f"records#{candidate.source_record_id};supplement#{index}"
    text = (
        f"Supplement manifest for Aedes aegypti paper {candidate.source_title}. "
        f"Title: {title_text}. "
        f"File type: {supplement.get('file_type', 'unknown')}. "
        f"Source: {supplement.get('source', 'record_payload')}."
    )
    provenance = Provenance(
        source_id=EXTRACTED_FACTS_SOURCE_ID,
        locator=locator,
        retrieved_at=retrieved_at,
        license=supplement.get("license") if isinstance(supplement.get("license"), str) else None,
        source_url=url if isinstance(url, str) else candidate.paper_url,
    )
    return EvidenceRecord(
        record_id=f"extracted_fact:supplement_manifest:{_normalize_id(candidate.source_record_id)}:{digest}",
        lane="literature",
        source=EXTRACTED_FACTS_SOURCE_ID,
        title=f"Aedes aegypti supplement manifest: {title_text}",
        text=text,
        species=candidate.species or "Aedes aegypti",
        url=url if isinstance(url, str) else candidate.paper_url,
        media_url=None,
        provenance=provenance,
        payload={
            "fact_type": "supplement_manifest",
            "schema_version": SCHEMA_VERSION,
            "fields": {},
            "source_record_id": candidate.source_record_id,
            "fulltext_unit_id": None,
            "supplement": supplement,
            "evidence_text": text,
            "confidence": "manifest",
            "extraction_method": "payload_supplement_manifest",
            "source_provenance": candidate.source_provenance,
        },
    )


def _record_for_fact(candidate: TextCandidate, family: FactFamily, fields: dict[str, object], *, retrieved_at: str) -> EvidenceRecord:
    combined_text = "\n".join([candidate.source_title, candidate.text])
    flat_terms = [term for values in fields.values() if isinstance(values, list) for term in values if isinstance(term, str)]
    context_hits = _matched_terms(combined_text, family.context_terms)
    evidence_text = _snippet(combined_text, _dedup(flat_terms + context_hits))
    if candidate.table_row:
        fields = {
            **fields,
            "table_row": candidate.table_row,
            "table_headers": list(candidate.table_row),
            "table_row_index": candidate.table_row_index,
        }
    unit_part = candidate.unit_id or candidate.raw_file_path or "literature-record"
    digest = _digest(candidate.source_record_id, unit_part, family.fact_type, json.dumps(fields, sort_keys=True))
    locator_parts = [f"records#{candidate.source_record_id}"]
    if candidate.unit_id:
        locator_parts.append(f"literature_fulltext_units#{candidate.unit_id}")
    if candidate.supplement_index is not None:
        locator_parts.append(f"supplement#{candidate.supplement_index}")
    if candidate.raw_file_path:
        locator_parts.append(candidate.raw_file_path)
    if candidate.table_row_index is not None:
        locator_parts.append(f"row#{candidate.table_row_index}")
    provenance = Provenance(
        source_id=EXTRACTED_FACTS_SOURCE_ID,
        locator=";".join(locator_parts),
        retrieved_at=retrieved_at,
        license=candidate.unit_license,
        source_url=candidate.unit_url or candidate.paper_url,
    )
    title = f"Aedes aegypti extracted {family.fact_type.replace('_', ' ')} fact"
    text = (
        f"{title} from {candidate.source_title}. "
        f"Matched fields: {', '.join(sorted(fields))}. "
        f"Evidence: {evidence_text}"
    )
    return EvidenceRecord(
        record_id=f"extracted_fact:{family.fact_type}:{_normalize_id(candidate.source_record_id)}:{digest}",
        lane=family.lane,
        source=EXTRACTED_FACTS_SOURCE_ID,
        title=title,
        text=text,
        species=candidate.species or "Aedes aegypti",
        url=candidate.unit_url or candidate.paper_url,
        media_url=None,
        provenance=provenance,
        payload={
            "fact_type": family.fact_type,
            "schema_version": SCHEMA_VERSION,
            "fields": fields,
            "source_record_id": candidate.source_record_id,
            "fulltext_unit_id": candidate.unit_id,
            "supplement": candidate.supplement,
            "evidence_text": evidence_text,
            "confidence": "parsed" if candidate.table_row else "candidate",
            "extraction_method": (
                "deterministic_supplement_table_row_extract"
                if candidate.table_row
                else "deterministic_supplement_text_extract"
                if candidate.raw_file_path
                else "deterministic_fulltext_term_extract"
            ),
            "source_provenance": candidate.source_provenance,
            "unit_provenance": candidate.unit_provenance,
        },
    )


def build_extracted_fact_records(
    artifact_dir: Path,
    *,
    retrieved_at: str | None = None,
    max_fulltext_units: int | None = 5000,
    discover_supplements: bool = False,
    download_supplements: bool = False,
    fetch_supplement_metadata_fn: Callable[[dict[str, object]], list[dict[str, object]]] | None = None,
    fetch_supplement_file_fn: Callable[[str, int], bytes] | None = None,
    max_supplement_discovery_records: int | None = 500,
    max_repository_supplement_discovery_records: int | None = 100,
    max_supplement_files: int = 100,
    max_supplement_bytes: int = 2_000_000,
    max_pdf_supplement_files: int = 10,
    source_record_ids: list[str] | None = None,
) -> ExtractedFactsResult:
    retrieved_at = retrieved_at or utc_now()
    index_path = artifact_dir / "source_index.sqlite"
    gaps: list[dict[str, object]] = []
    records: list[EvidenceRecord] = []
    if not index_path.exists():
        return ExtractedFactsResult(
            source_id=EXTRACTED_FACTS_SOURCE_ID,
            records=[],
            gaps=[
                {
                    "source": EXTRACTED_FACTS_SOURCE_ID,
                    "reason": "missing_source_index",
                    "artifact_dir": artifact_dir.as_posix(),
                }
            ],
            candidate_count=0,
            source_record_count=0,
            fulltext_unit_count=0,
            max_fulltext_units=max_fulltext_units,
            supplement_manifest_count=0,
            fact_counts={family.fact_type: 0 for family in FACT_FAMILIES},
            selected_fulltext_unit_count=0,
            truncated_fulltext_unit_count=0,
            selected_record_text_count=0,
            supplement_discovery_record_count=0,
            max_repository_supplement_discovery_records=max_repository_supplement_discovery_records,
            discovered_supplement_count=0,
            downloaded_supplement_file_count=0,
            parsed_supplement_file_count=0,
            parsed_supplement_row_count=0,
            max_pdf_supplement_files=max_pdf_supplement_files,
            parsed_pdf_supplement_file_count=0,
            skipped_pdf_supplement_file_count=0,
        )

    conn = sqlite3.connect(index_path)
    conn.row_factory = sqlite3.Row
    try:
        literature_rows = _source_rows(conn, source_record_ids=source_record_ids)
        (
            text_candidates,
            fulltext_unit_count,
            selected_fulltext_unit_count,
            truncated_fulltext_unit_count,
            selected_record_text_count,
        ) = _text_candidates(
            conn,
            literature_rows,
            max_fulltext_units=max_fulltext_units,
            source_record_ids=source_record_ids,
        )
    finally:
        conn.close()

    if discover_supplements and fetch_supplement_metadata_fn is None:
        fetch_supplement_metadata_fn = fetch_public_supplement_metadata
    (
        supplement_candidates,
        discovered_supplement_count,
        supplement_discovery_record_count,
    ) = _supplement_candidates_with_discovery(
        literature_rows,
        discover_supplements=discover_supplements,
        fetch_supplement_metadata_fn=fetch_supplement_metadata_fn,
        max_supplement_discovery_records=max_supplement_discovery_records,
        max_repository_supplement_discovery_records=max_repository_supplement_discovery_records,
        gaps=gaps,
    )
    for index, candidate in enumerate(supplement_candidates):
        records.append(_record_for_supplement(candidate, index=index, retrieved_at=retrieved_at))
    downloaded_supplement_file_count = 0
    parsed_supplement_file_count = 0
    parsed_supplement_row_count = 0
    parsed_pdf_supplement_file_count = 0
    skipped_pdf_supplement_file_count = 0
    if download_supplements:
        supplement_file_fetcher = fetch_supplement_file_fn or _fetch_bytes_url
        (
            supplement_text_candidates,
            downloaded_supplement_file_count,
            parsed_supplement_file_count,
            parsed_supplement_row_count,
            parsed_pdf_supplement_file_count,
            skipped_pdf_supplement_file_count,
        ) = _download_and_parse_supplement_rows(
            supplement_candidates,
            artifact_dir=artifact_dir,
            retrieved_at=retrieved_at,
            fetch_supplement_file_fn=supplement_file_fetcher,
            max_supplement_files=max_supplement_files,
            max_supplement_bytes=max_supplement_bytes,
            max_pdf_supplement_files=max_pdf_supplement_files,
            gaps=gaps,
        )
        text_candidates.extend(supplement_text_candidates)

    fact_counts = {family.fact_type: 0 for family in FACT_FAMILIES}
    for candidate in text_candidates:
        combined_text = "\n".join([candidate.source_title, candidate.text])
        declared_fact_type = _row_declared_fact_type(candidate.table_row)
        for family in FACT_FAMILIES:
            if declared_fact_type and declared_fact_type != family.fact_type:
                continue
            fields = _field_matches(combined_text, family)
            context_hits = _matched_terms(combined_text, family.context_terms)
            if not fields or not context_hits:
                continue
            if family.fact_type == "resistance" and not _is_supported_parsed_resistance_row(
                candidate.table_row,
                fields,
                declared_fact_type,
            ):
                continue
            enriched_fields = _enrich_fields(combined_text, fields)
            records.append(_record_for_fact(candidate, family, enriched_fields, retrieved_at=retrieved_at))
            fact_counts[family.fact_type] += 1

    if not literature_rows:
        gaps.append(
            {
                "source": EXTRACTED_FACTS_SOURCE_ID,
                "reason": "no_literature_records",
                "artifact_dir": artifact_dir.as_posix(),
            }
        )
    if literature_rows and not supplement_candidates:
        gaps.append(
            {
                "source": EXTRACTED_FACTS_SOURCE_ID,
                "reason": "no_supplement_metadata_found",
                "source_record_count": len(literature_rows),
            }
        )
    if literature_rows and not any(fact_counts.values()):
        gaps.append(
            {
                "source": EXTRACTED_FACTS_SOURCE_ID,
                "reason": "no_cross_lane_fact_candidates",
                "candidate_count": len(text_candidates),
            }
        )
    if max_fulltext_units is not None and selected_fulltext_unit_count >= max_fulltext_units:
        gaps.append(
            {
                "source": EXTRACTED_FACTS_SOURCE_ID,
                "reason": "fulltext_prefilter_limit_applied",
                "max_fulltext_units": max_fulltext_units,
                "fulltext_unit_count": fulltext_unit_count,
                "selected_fulltext_unit_count": selected_fulltext_unit_count,
            }
        )
    if max_fulltext_units is not None and selected_record_text_count >= max_fulltext_units:
        gaps.append(
            {
                "source": EXTRACTED_FACTS_SOURCE_ID,
                "reason": "record_text_window_applied",
                "max_record_text_candidates": max_fulltext_units,
                "selected_record_text_count": selected_record_text_count,
            }
        )
    if truncated_fulltext_unit_count:
        gaps.append(
            {
                "source": EXTRACTED_FACTS_SOURCE_ID,
                "reason": "fulltext_text_window_applied",
                "max_candidate_text_chars": MAX_CANDIDATE_TEXT_CHARS,
                "truncated_fulltext_unit_count": truncated_fulltext_unit_count,
            }
        )

    return ExtractedFactsResult(
        source_id=EXTRACTED_FACTS_SOURCE_ID,
        records=records,
        gaps=gaps,
        candidate_count=len(text_candidates),
        source_record_count=len(literature_rows),
        fulltext_unit_count=fulltext_unit_count,
        max_fulltext_units=max_fulltext_units,
        selected_fulltext_unit_count=selected_fulltext_unit_count,
        truncated_fulltext_unit_count=truncated_fulltext_unit_count,
        selected_record_text_count=selected_record_text_count,
        supplement_manifest_count=len(supplement_candidates),
        supplement_discovery_record_count=supplement_discovery_record_count,
        max_repository_supplement_discovery_records=max_repository_supplement_discovery_records,
        discovered_supplement_count=discovered_supplement_count,
        downloaded_supplement_file_count=downloaded_supplement_file_count,
        parsed_supplement_file_count=parsed_supplement_file_count,
        parsed_supplement_row_count=parsed_supplement_row_count,
        max_pdf_supplement_files=max_pdf_supplement_files,
        parsed_pdf_supplement_file_count=parsed_pdf_supplement_file_count,
        skipped_pdf_supplement_file_count=skipped_pdf_supplement_file_count,
        fact_counts=fact_counts,
    )
