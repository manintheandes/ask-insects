from __future__ import annotations

import csv
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
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
import sys
import tempfile
from typing import Callable, Iterable
from urllib.parse import quote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import zipfile

from askinsects.records import EvidenceRecord, Provenance


EXTRACTED_FACTS_SOURCE_ID = "aedes_extracted_facts"
INPUT_LITERATURE_SOURCE_ID = "aedes_literature_openalex"
SCHEMA_VERSION = "2026-05-24.v1"
MAX_CANDIDATE_TEXT_CHARS = 50_000
EXTERNAL_METADATA_TIMEOUT_SECONDS = 8
SUPPLEMENT_FILE_TIMEOUT_SECONDS = 30
SUPPLEMENT_DISCOVERY_WORKERS = 8
DEFAULT_MAX_SUPPLEMENT_BYTES = 10_000_000


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
    supplement_audit_record_count: int
    papers_with_supplement_manifest_count: int
    papers_with_parsed_supplement_rows_count: int
    papers_with_promoted_supplement_rows_count: int
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
    supplement_discovery_route_counts: dict[str, int]


FACT_FAMILIES: tuple[FactFamily, ...] = (
    FactFamily(
        fact_type="vector_competence",
        lane="vector_competence",
        context_terms=(
            "vector competence",
            "infection rate",
            "infected",
            "dissemination rate",
            "transmission rate",
            "zika virus",
            "zikv",
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
            "insecticide-resistant",
            "insecticide",
            "resistance",
            "bioassay",
            "discriminating concentration",
            "mortality",
            "knockdown",
            "lc50",
            "genotype frequency",
        ),
        field_terms={
            "insecticide": (
                "insecticide class",
                "permethrin",
                "deltamethrin",
                "cypermethrin",
                "temephos",
                "malathion",
                "bendiocarb",
                "pyrethroid",
                "pyrethroids",
                "carbamate",
                "carbamates",
                "organochlorine",
                "organochlorines",
                "organophosphate",
                "organophosphates",
            ),
            "assay": ("bioassay", "who tube", "cdc bottle", "exposure"),
            "discriminating_concentration": ("discriminating concentration", "discriminating concentrations"),
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
            "ecological",
            "habitat",
            "breeding site",
            "larval",
            "season",
            "range",
            "climate",
            "abundance",
            "mosquito abundance",
        ),
        field_terms={
            "habitat": ("habitat", "urban", "peri-urban", "rural"),
            "breeding_site": ("breeding site", "container", "water storage", "larval"),
            "climate": ("temperature", "rainfall", "rainy season", "humidity"),
            "seasonality": ("season", "rainy season", "dry season"),
            "range": ("range", "distribution", "survey"),
            "abundance": ("abundance", "total ae. aegypti caught", "mean per trap", "median per trap", "number of females"),
            "sampling": ("trap", "traps", "capture station", "month of collection"),
            "species": ("aedes aegypti", "ae. aegypti", "a. aegypti"),
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
            "larvicide",
            "larvicidal",
            "pyriproxyfen",
            "spinosad",
            "semi-field",
            "serotype",
            "wolbachia",
            "public health",
            "vector surveillance",
            "vector control",
            "検疫所",
            "サーベイランス",
            "報告書",
        ),
        field_terms={
            "case_metric": ("cases", "incidence", "outbreak"),
            "death_metric": ("deaths", "fatalities"),
            "intervention": (
                "wolbachia",
                "source reduction",
                "vector control",
                "intervention",
                "pyriproxyfen",
                "spinosad",
                "treatment (mixture)",
                "mixture mean",
                "control mean",
            ),
            "location": ("brazil", "kenya", "india", "thailand", "mexico", "colombia", "peru", "usa"),
            "date": ("2024", "2025", "2026"),
            "serotype": ("denv-1", "denv-2", "denv-3", "denv-4", "serotype"),
            "life_stage": ("larvae", "larva", "larval", "pupae", "pupa", "adult"),
            "biochemical_response": ("α-esterase", "beta-esterase", "β-esterase", "mfos", "gsts", "enzyme"),
            "effect_metric": ("mean (%)", "95% ci", "post hoc", "p -value"),
            "source": ("paho", "who", "cdc", "surveillance", "vector surveillance", "検疫所", "サーベイランス", "報告書"),
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
CROSSREF_WORKS_API_BASE = "https://api.crossref.org/works"
DATACITE_DOI_API_BASE = "https://api.datacite.org/dois"
UNPAYWALL_API_BASE = "https://api.unpaywall.org/v2"
UNPAYWALL_EMAIL = "sources@openinsects.org"
RESISTANCE_DISCOVERY_TERMS = (
    "insecticide resistance",
    "insecticide-resistant",
    "insecticide",
    "pyrethroid",
    "pyrethroids",
    "organophosphate",
    "organophosphates",
    "carbamate",
    "carbamates",
    "organochlorine",
    "organochlorines",
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
    "discriminating_concentration",
    "insecticide",
    "knockdown",
    "lc_value",
    "mortality",
    "mutation",
}
VECTOR_COMPETENCE_TABLE_STRONG_FIELDS = {
    "dissemination",
    "dose",
    "infection",
    "strain",
    "temperature",
    "timepoint",
    "tissue",
    "transmission",
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
    with urlopen(request, timeout=EXTERNAL_METADATA_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"URL returned non-object JSON for {url}")
    return payload


def _fetch_bytes_url(url: str, max_bytes: int) -> bytes:
    request = Request(url, headers={"User-Agent": "ask-insects/0.1"})
    with urlopen(request, timeout=SUPPLEMENT_FILE_TIMEOUT_SECONDS) as response:
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
    supplements.extend(_crossref_relation_supplements(request))
    supplements.extend(_datacite_relation_supplements(request))
    supplements.extend(_unpaywall_supplements(request))
    supplements.extend(_publisher_landing_page_supplements(request))
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


def _url_file_type(url: str) -> str | None:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in SUPPORTED_SUPPLEMENT_EXTENSIONS:
        return suffix.lstrip(".")
    return None


def _supplement_reference_score(url: str, label: str | None = None) -> int:
    haystack = f"{url} {label or ''}".lower()
    strong_terms = (
        "supplement",
        "supplementary",
        "supporting information",
        "supporting-information",
        "additional file",
        "additional-file",
        "appendix",
    )
    if any(term in haystack for term in strong_terms):
        return 3
    if re.search(r"\bsupp[-_ ]?\d*\b", haystack) or re.search(
        r"\bs\d{1,3}(?!\.\d)(?:[-_ ]?(?:table|data|file|fig|figure))?\b",
        haystack,
    ):
        return 2
    if "table" in haystack and _url_file_type(url):
        return 1
    return 0


def _looks_like_supplement_reference(url: str, label: str | None = None) -> bool:
    return bool(url and _supplement_reference_score(url, label) > 0)


def _doi_or_url_identifier(value: object, id_type: object = None) -> str | None:
    if not value:
        return None
    identifier = str(value).strip()
    lowered_type = str(id_type or "").lower()
    if not identifier:
        return None
    if lowered_type == "doi" or (identifier.lower().startswith("10.") and "/" in identifier):
        return f"https://doi.org/{_normalize_doi(identifier)}"
    if re.match(r"https?://", identifier, flags=re.I):
        return identifier
    return identifier


def _supplement_from_url(
    *,
    url: str,
    title: str,
    source: str,
    metadata_url: str | None = None,
    license_value: object = None,
    file_type: str | None = None,
) -> dict[str, object]:
    supplement: dict[str, object] = {
        "title": title,
        "url": url,
        "source": source,
    }
    inferred_file_type = file_type or _url_file_type(url)
    if inferred_file_type:
        supplement["file_type"] = inferred_file_type
    if metadata_url:
        supplement["metadata_url"] = metadata_url
    if isinstance(license_value, str) and license_value:
        supplement["license"] = license_value
    return supplement


def _crossref_relation_supplements(request: dict[str, object]) -> list[dict[str, object]]:
    doi = request.get("doi")
    if not doi:
        return []
    api_url = f"{CROSSREF_WORKS_API_BASE}/{quote(str(doi), safe='')}"
    try:
        payload = _fetch_json_url(api_url)
    except Exception:
        return []
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    relations = message.get("relation") if isinstance(message.get("relation"), dict) else {}
    supplements: list[dict[str, object]] = []
    for relation_type, entries in relations.items():
        relation_lower = str(relation_type).lower()
        relation_key = re.sub(r"[^a-z]", "", relation_lower)
        if relation_key == "issupplementto":
            continue
        if "supplement" not in relation_lower:
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            url = _doi_or_url_identifier(entry.get("id"), entry.get("id-type"))
            if not url:
                continue
            supplements.append(
                _supplement_from_url(
                    url=url,
                    title=f"Crossref {relation_type} supplement",
                    source="crossref_relation",
                    metadata_url=api_url,
                )
            )
    return supplements


def _datacite_relation_supplements(request: dict[str, object]) -> list[dict[str, object]]:
    doi = request.get("doi")
    if not doi:
        return []
    api_url = f"{DATACITE_DOI_API_BASE}/{quote(str(doi), safe='')}"
    try:
        payload = _fetch_json_url(api_url)
    except Exception:
        return []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    attributes = data.get("attributes") if isinstance(data.get("attributes"), dict) else {}
    related = attributes.get("relatedIdentifiers") if isinstance(attributes.get("relatedIdentifiers"), list) else []
    supplements: list[dict[str, object]] = []
    for entry in related:
        if not isinstance(entry, dict):
            continue
        relation_type = str(entry.get("relationType") or entry.get("relation_type") or "")
        relation_key = re.sub(r"[^a-z]", "", relation_type.lower())
        if relation_key == "issupplementto":
            continue
        raw_identifier = entry.get("relatedIdentifier") or entry.get("related_identifier")
        identifier_type = entry.get("relatedIdentifierType") or entry.get("related_identifier_type")
        url = _doi_or_url_identifier(raw_identifier, identifier_type)
        if not url:
            continue
        if "supplement" not in relation_type.lower() and not _looks_like_supplement_reference(url, relation_type):
            continue
        supplements.append(
            _supplement_from_url(
                url=url,
                title=f"DataCite {relation_type or 'related'} supplement",
                source="datacite_relation",
                metadata_url=api_url,
            )
        )
    return supplements


def _unpaywall_supplements(request: dict[str, object]) -> list[dict[str, object]]:
    doi = request.get("doi")
    if not doi:
        return []
    api_url = f"{UNPAYWALL_API_BASE}/{quote(str(doi), safe='')}?{urlencode({'email': UNPAYWALL_EMAIL})}"
    try:
        payload = _fetch_json_url(api_url)
    except Exception:
        return []
    locations: list[dict[str, object]] = []
    best = payload.get("best_oa_location")
    if isinstance(best, dict):
        locations.append(best)
    oa_locations = payload.get("oa_locations")
    if isinstance(oa_locations, list):
        locations.extend(item for item in oa_locations if isinstance(item, dict))
    supplements: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    for location in locations:
        license_value = location.get("license")
        for key in ("url_for_pdf", "url", "url_for_landing_page"):
            value = location.get(key)
            if not isinstance(value, str) or not value or value in seen_urls:
                continue
            if not _looks_like_supplement_reference(value, key):
                continue
            seen_urls.add(value)
            supplements.append(
                _supplement_from_url(
                    url=value,
                    title=f"Unpaywall OA supplement location ({key})",
                    source="unpaywall_oa_location",
                    metadata_url=api_url,
                    license_value=license_value,
                )
            )
    return supplements


class _SupplementLinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self._href_stack: list[str | None] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        href = next((str(value) for key, value in attrs if key.lower() == "href" and value), None)
        self._href_stack.append(self._current_href)
        self._current_href = href
        self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href and data.strip():
            self._current_text.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a":
            return
        if self._current_href:
            label = " ".join(self._current_text)
            self.links.append((urljoin(self.base_url, self._current_href), label))
        self._current_href = self._href_stack.pop() if self._href_stack else None
        self._current_text = []


def _publisher_landing_page_supplements(request: dict[str, object]) -> list[dict[str, object]]:
    landing_url = request.get("url")
    if not isinstance(landing_url, str) or not landing_url:
        return []
    parsed = urlparse(landing_url)
    if parsed.scheme not in {"http", "https"}:
        return []
    if parsed.netloc.lower() in {"doi.org", "dx.doi.org"}:
        return []
    try:
        html = _fetch_bytes_url(landing_url, 1_000_000)
    except Exception:
        return []
    parser = _SupplementLinkParser(landing_url)
    try:
        parser.feed(html.decode("utf-8", errors="replace"))
    except Exception:
        return []
    supplements: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    for url, label in parser.links:
        if url in seen_urls:
            continue
        if not _url_file_type(url):
            continue
        if not _looks_like_supplement_reference(url, label):
            continue
        seen_urls.add(url)
        supplements.append(
            _supplement_from_url(
                url=url,
                title=label or Path(urlparse(url).path).name or "Publisher supplementary file",
                source="publisher_landing_page",
                metadata_url=landing_url,
            )
        )
    return supplements


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


def _existing_supplement_manifest_supplements(
    conn: sqlite3.Connection,
    literature_rows: list[sqlite3.Row],
    *,
    source_record_ids: list[str] | None,
) -> list[dict[str, object]]:
    if not source_record_ids:
        return []
    literature_by_id = {str(paper["record_id"]): paper for paper in literature_rows}
    placeholders = ",".join("?" for _ in source_record_ids)
    try:
        rows = conn.execute(
            f"""
            SELECT payload_json
            FROM record_payloads
            WHERE source=?
              AND json_extract(payload_json, '$.fact_type')='supplement_manifest'
              AND json_extract(payload_json, '$.source_record_id') IN ({placeholders})
            ORDER BY rowid
            """,
            [EXTRACTED_FACTS_SOURCE_ID, *source_record_ids],
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    supplements: list[dict[str, object]] = []
    for row in rows:
        payload = _safe_json(row["payload_json"])
        source_record_id = str(payload.get("source_record_id") or "")
        if source_record_id not in literature_by_id:
            continue
        supplement = payload.get("supplement")
        if not isinstance(supplement, dict):
            continue
        supplements.append(
            {
                "source_record_id": source_record_id,
                "supplement": supplement,
            }
        )
    return supplements


def _supplement_candidates_with_discovery(
    literature_rows: list[sqlite3.Row],
    *,
    text_candidates: list[TextCandidate],
    existing_supplements: list[dict[str, object]],
    discover_supplements: bool,
    fetch_supplement_metadata_fn: Callable[[dict[str, object]], list[dict[str, object]]] | None,
    max_supplement_discovery_records: int | None,
    max_repository_supplement_discovery_records: int | None,
    gaps: list[dict[str, object]],
) -> tuple[list[SupplementCandidate], int, int, dict[str, int]]:
    if max_supplement_discovery_records is not None and max_supplement_discovery_records < 1:
        raise ValueError("max_supplement_discovery_records must be positive")
    if max_repository_supplement_discovery_records is not None and max_repository_supplement_discovery_records < 0:
        raise ValueError("max_repository_supplement_discovery_records must not be negative")
    candidates: list[SupplementCandidate] = []
    seen: set[tuple[str, str, str]] = set()
    discovered_count = 0
    discovery_record_count = 0
    route_counts: Counter[str] = Counter()

    def add_candidate(paper: sqlite3.Row, raw_supplement: dict[str, object], fallback_source: str) -> None:
        nonlocal candidates
        supplement = _normalize_supplement(raw_supplement)
        supplement.setdefault("source", fallback_source)
        key = (str(paper["record_id"]), str(supplement.get("url") or ""), str(supplement.get("title") or ""))
        if key in seen:
            return
        seen.add(key)
        route_counts[str(supplement.get("source") or fallback_source)] += 1
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

    literature_by_id = {str(paper["record_id"]): paper for paper in literature_rows}
    for existing in existing_supplements:
        paper = literature_by_id.get(str(existing.get("source_record_id") or ""))
        supplement = existing.get("supplement")
        if paper is None or not isinstance(supplement, dict):
            continue
        add_candidate(paper, supplement, "existing_manifest")

    for paper in literature_rows:
        payload = _safe_json(paper["payload_json"])
        for raw_supplement in _payload_supplements(payload):
            add_candidate(paper, raw_supplement, "record_payload")

    if discover_supplements:
        for text_candidate in text_candidates:
            paper = literature_by_id.get(text_candidate.source_record_id)
            if paper is None:
                continue
            for raw_supplement in _fulltext_link_supplements(text_candidate):
                add_candidate(paper, raw_supplement, "fulltext_link_mining")

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
        print(
            f"[aedes_extracted_facts] supplement discovery records={len(discovery_rows)}",
            file=sys.stderr,
            flush=True,
        )

        def fetch_for_paper(paper: sqlite3.Row) -> tuple[sqlite3.Row, list[dict[str, object]], str | None]:
            request = _identifier_request(paper)
            try:
                return paper, fetch_supplement_metadata_fn(request), None
            except Exception as exc:
                return paper, [], str(exc)

        worker_count = min(SUPPLEMENT_DISCOVERY_WORKERS, max(1, len(discovery_rows)))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            fetched_results = executor.map(fetch_for_paper, discovery_rows)
            for paper, fetched, error in fetched_results:
                discovery_record_count += 1
                if discovery_record_count == 1 or discovery_record_count % 100 == 0:
                    print(
                        "[aedes_extracted_facts] supplement discovery "
                        f"{discovery_record_count}/{len(discovery_rows)} "
                        f"candidates={len(candidates)} discovered={discovered_count}",
                        file=sys.stderr,
                        flush=True,
                    )
                if error is not None:
                    gaps.append(
                        {
                            "source": EXTRACTED_FACTS_SOURCE_ID,
                            "reason": "supplement_metadata_fetch_failed",
                            "record_id": str(paper["record_id"]),
                            "error": error,
                        }
                    )
                    continue
                discovered_count += len(fetched)
                for raw_supplement in fetched:
                    add_candidate(paper, raw_supplement, "metadata_fetch")
    return candidates, discovered_count, discovery_record_count, dict(sorted(route_counts.items()))


URL_RE = re.compile(r"https?://[^\s<>'\"\)\]\}]+", re.I)


def _fulltext_link_supplements(candidate: TextCandidate) -> list[dict[str, object]]:
    supplements: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    for match in URL_RE.finditer(candidate.text):
        url = match.group(0).rstrip(".,;:")
        if url in seen_urls:
            continue
        if not _url_file_type(url):
            continue
        context_start = max(0, match.start() - 120)
        context_end = min(len(candidate.text), match.end() + 120)
        context = candidate.text[context_start:context_end]
        if not _looks_like_supplement_reference(url, context):
            continue
        seen_urls.add(url)
        supplements.append(
            _supplement_from_url(
                url=url,
                title=Path(urlparse(url).path).name or "Full-text linked supplementary file",
                source="fulltext_link_mining",
                metadata_url=candidate.unit_url or candidate.paper_url,
                license_value=candidate.unit_license,
            )
        )
    return supplements


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


def _sniff_csv_delimiter(data: bytes) -> str:
    text = _decode_table_bytes(data)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        return ","
    return str(dialect.delimiter or ",")


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
        return _parse_delimited_rows(data, _sniff_csv_delimiter(data))
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


def _is_supported_parsed_vector_competence_row(
    row: dict[str, str] | None,
    fields: dict[str, list[str]],
    declared_fact_type: str | None,
) -> bool:
    if not row:
        return True
    if declared_fact_type == "vector_competence":
        return True
    return any(field in fields for field in VECTOR_COMPETENCE_TABLE_STRONG_FIELDS)


def _supplement_locator(candidate: SupplementCandidate, index: int, raw_file_path: str | None = None) -> str:
    locator_parts = [f"records#{candidate.source_record_id}", f"supplement#{index}"]
    if raw_file_path:
        locator_parts.append(raw_file_path)
    return ";".join(locator_parts)


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
) -> tuple[list[TextCandidate], list[EvidenceRecord], int, int, int, int, int]:
    if max_supplement_files < 1:
        raise ValueError("max_supplement_files must be positive")
    if max_supplement_bytes < 1:
        raise ValueError("max_supplement_bytes must be positive")
    if max_pdf_supplement_files < 0:
        raise ValueError("max_pdf_supplement_files must not be negative")
    raw_dir = artifact_dir / "raw" / "extracted_facts" / "supplements"
    raw_dir.mkdir(parents=True, exist_ok=True)
    candidates: list[TextCandidate] = []
    gap_records: list[EvidenceRecord] = []
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
        if index == 0 or (index + 1) % 50 == 0:
            print(
                "[aedes_extracted_facts] supplement download "
                f"{index + 1}/{len(supplement_candidates)} "
                f"downloaded={downloaded_count} parsed_files={parsed_file_count} parsed_rows={parsed_row_count}",
                file=sys.stderr,
                flush=True,
            )
        url = candidate.supplement.get("url")
        if not isinstance(url, str) or not url:
            gap_records.append(
                _record_for_supplement_file_gap(
                    candidate,
                    index=index,
                    reason="supplement_file_missing_url",
                    retrieved_at=retrieved_at,
                )
            )
            continue
        extension = _supplement_extension(candidate.supplement)
        if extension not in SUPPORTED_SUPPLEMENT_EXTENSIONS:
            gap_records.append(
                _record_for_supplement_file_gap(
                    candidate,
                    index=index,
                    reason="unsupported_supplement_type",
                    retrieved_at=retrieved_at,
                )
            )
            gaps.append(
                {
                    "source": EXTRACTED_FACTS_SOURCE_ID,
                    "reason": "unsupported_supplement_type",
                    "record_id": candidate.source_record_id,
                    "locator": _supplement_locator(candidate, index),
                    "url": url,
                    "file_type": candidate.supplement.get("file_type"),
                }
            )
            continue
        if extension == ".pdf" and parsed_pdf_count >= max_pdf_supplement_files:
            skipped_pdf_count += 1
            gap_records.append(
                _record_for_supplement_file_gap(
                    candidate,
                    index=index,
                    reason="pdf_supplement_file_limit_applied",
                    retrieved_at=retrieved_at,
                    extra_fields={"max_pdf_supplement_files": max_pdf_supplement_files},
                )
            )
            gaps.append(
                {
                    "source": EXTRACTED_FACTS_SOURCE_ID,
                    "reason": "pdf_supplement_file_limit_applied",
                    "record_id": candidate.source_record_id,
                    "locator": _supplement_locator(candidate, index),
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
            gap_records.append(
                _record_for_supplement_file_gap(
                    candidate,
                    index=index,
                    reason="supplement_table_parse_failed",
                    retrieved_at=retrieved_at,
                    extra_fields={"error": str(exc)},
                )
            )
            gaps.append(
                {
                    "source": EXTRACTED_FACTS_SOURCE_ID,
                    "reason": "supplement_table_parse_failed",
                    "record_id": candidate.source_record_id,
                    "locator": _supplement_locator(candidate, index),
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
            gap_records.append(
                _record_for_supplement_file_gap(
                    candidate,
                    index=index,
                    reason="supplement_table_no_rows",
                    retrieved_at=retrieved_at,
                    raw_file_path=raw_path.relative_to(artifact_dir).as_posix(),
                )
            )
            gaps.append(
                {
                    "source": EXTRACTED_FACTS_SOURCE_ID,
                    "reason": "supplement_table_no_rows",
                    "record_id": candidate.source_record_id,
                    "locator": _supplement_locator(candidate, index, raw_path.relative_to(artifact_dir).as_posix()),
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
    return candidates, gap_records, downloaded_count, parsed_file_count, parsed_row_count, parsed_pdf_count, skipped_pdf_count


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
            "fields": {
                "source_record_id": candidate.source_record_id,
                "title": title_text,
                "url": url,
                "file_type": supplement.get("file_type"),
                "source": supplement.get("source", "record_payload"),
                "license": supplement.get("license"),
                "size": supplement.get("size"),
            },
            "source_record_id": candidate.source_record_id,
            "fulltext_unit_id": None,
            "supplement": supplement,
            "evidence_text": text,
            "confidence": "manifest",
            "extraction_method": "payload_supplement_manifest",
            "source_provenance": candidate.source_provenance,
        },
    )


def _record_for_supplement_file_gap(
    candidate: SupplementCandidate,
    *,
    index: int,
    reason: str,
    retrieved_at: str,
    raw_file_path: str | None = None,
    extra_fields: dict[str, object] | None = None,
) -> EvidenceRecord:
    supplement = candidate.supplement
    title_text = str(supplement.get("title") or "Supplementary material")
    url = supplement.get("url")
    locator = _supplement_locator(candidate, index, raw_file_path)
    digest = _digest(candidate.source_record_id, index, reason, title_text, url)
    fields: dict[str, object] = {
        "reason": reason,
        "source_record_id": candidate.source_record_id,
        "title": title_text,
        "url": url,
        "file_type": supplement.get("file_type"),
        "source": supplement.get("source", "record_payload"),
        "license": supplement.get("license"),
        "size": supplement.get("size"),
        "raw_file_path": raw_file_path,
    }
    if extra_fields:
        fields.update(extra_fields)
    text = (
        f"Aedes aegypti supplement file gap for paper {candidate.source_title}. "
        f"Reason: {reason}. "
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
        record_id=f"extracted_fact:supplement_file_gap:{_normalize_id(candidate.source_record_id)}:{digest}",
        lane="literature",
        source=EXTRACTED_FACTS_SOURCE_ID,
        title=f"Aedes aegypti supplement file gap: {reason}",
        text=text,
        species=candidate.species or "Aedes aegypti",
        url=url if isinstance(url, str) else candidate.paper_url,
        media_url=None,
        provenance=provenance,
        payload={
            "fact_type": "supplement_file_gap",
            "schema_version": SCHEMA_VERSION,
            "fields": fields,
            "source_record_id": candidate.source_record_id,
            "fulltext_unit_id": None,
            "supplement": supplement,
            "evidence_text": text,
            "confidence": "gap",
            "extraction_method": "deterministic_supplement_file_gap",
            "source_provenance": candidate.source_provenance,
        },
    )


def _record_for_supplement_audit(
    paper: sqlite3.Row,
    *,
    supplement_candidate_count: int,
    parsed_supplement_row_count: int,
    promoted_supplement_row_count: int,
    discover_supplements: bool,
    download_supplements: bool,
    retrieved_at: str,
) -> EvidenceRecord:
    request = _identifier_request(paper)
    has_discovery_identifier = any(request.get(key) for key in ("doi", "pmid", "pmcid"))
    if promoted_supplement_row_count:
        coverage_status = "supplement_rows_promoted"
    elif parsed_supplement_row_count:
        coverage_status = "supplement_rows_parsed_no_structured_lane_match"
    elif supplement_candidate_count and download_supplements:
        coverage_status = "supplement_manifest_found_no_supported_table_rows_promoted"
    elif supplement_candidate_count:
        coverage_status = "supplement_manifest_found_table_download_not_run"
    elif discover_supplements and has_discovery_identifier:
        coverage_status = "no_supplement_metadata_found"
    elif discover_supplements:
        coverage_status = "supplement_discovery_missing_identifier"
    else:
        coverage_status = "supplement_discovery_not_run"

    title = str(paper["title"])
    source_record_id = str(paper["record_id"])
    fields = {
        "coverage_status": coverage_status,
        "supplement_candidate_count": supplement_candidate_count,
        "parsed_supplement_row_count": parsed_supplement_row_count,
        "promoted_supplement_row_count": promoted_supplement_row_count,
        "discover_supplements": discover_supplements,
        "download_supplements": download_supplements,
        "has_discovery_identifier": has_discovery_identifier,
    }
    text = (
        f"Aedes aegypti supplement audit for paper {title}. "
        f"Coverage status: {coverage_status}. "
        f"Supplement manifests: {supplement_candidate_count}. "
        f"Parsed supplement rows: {parsed_supplement_row_count}. "
        f"Promoted structured supplement rows: {promoted_supplement_row_count}."
    )
    provenance = Provenance(
        source_id=EXTRACTED_FACTS_SOURCE_ID,
        locator=f"records#{source_record_id};supplement_audit",
        retrieved_at=retrieved_at,
        license=None,
        source_url=paper["url"],
    )
    return EvidenceRecord(
        record_id=f"extracted_fact:supplement_audit:{_normalize_id(source_record_id)}",
        lane="literature",
        source=EXTRACTED_FACTS_SOURCE_ID,
        title="Aedes aegypti supplement audit",
        text=text,
        species=paper["species"] or "Aedes aegypti",
        url=paper["url"],
        media_url=None,
        provenance=provenance,
        payload={
            "fact_type": "supplement_audit",
            "schema_version": SCHEMA_VERSION,
            "fields": fields,
            "source_record_id": source_record_id,
            "fulltext_unit_id": None,
            "supplement": None,
            "evidence_text": text,
            "confidence": "audit",
            "extraction_method": "deterministic_per_paper_supplement_audit",
            "source_provenance": _safe_json(paper["provenance_json"]),
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
    source_locator_text = f"Source record: {candidate.source_record_id}."
    if candidate.unit_url:
        source_locator_text += f" Source URL: {candidate.unit_url}."
    if candidate.supplement:
        supplement_title = candidate.supplement.get("title")
        if supplement_title:
            source_locator_text += f" Supplement title: {supplement_title}."
    text = (
        f"{title} from {candidate.source_title}. "
        f"{source_locator_text} "
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


def _record_for_unpromoted_supplement_row(candidate: TextCandidate, *, retrieved_at: str) -> EvidenceRecord:
    row = candidate.table_row or {}
    row_index = candidate.table_row_index or 0
    raw_file = candidate.raw_file_path or "supplement"
    digest = _digest(candidate.source_record_id, raw_file, row_index, json.dumps(row, sort_keys=True))
    locator_parts = [f"records#{candidate.source_record_id}"]
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
    headers = list(row)
    text = (
        f"Aedes aegypti parsed supplement table row from {candidate.source_title}. "
        "This row was parsed but did not match a structured lane schema. "
        f"Headers: {', '.join(headers)}. "
        f"Values: {'; '.join(f'{key}: {value}' for key, value in row.items() if value)}"
    )
    return EvidenceRecord(
        record_id=f"extracted_fact:supplement_table_row:{_normalize_id(candidate.source_record_id)}:{digest}",
        lane="literature",
        source=EXTRACTED_FACTS_SOURCE_ID,
        title="Aedes aegypti parsed supplement table row",
        text=text,
        species=candidate.species or "Aedes aegypti",
        url=candidate.unit_url or candidate.paper_url,
        media_url=None,
        provenance=provenance,
        payload={
            "fact_type": "supplement_table_row",
            "schema_version": SCHEMA_VERSION,
            "fields": {
                "table_row": row,
                "table_headers": headers,
                "table_row_index": candidate.table_row_index,
                "non_promotion_reason": "no_structured_lane_schema_match",
            },
            "source_record_id": candidate.source_record_id,
            "fulltext_unit_id": candidate.unit_id,
            "supplement": candidate.supplement,
            "evidence_text": _table_row_text(row),
            "confidence": "parsed_no_structured_lane_match",
            "extraction_method": "deterministic_supplement_table_row_unpromoted",
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
    max_supplement_bytes: int = DEFAULT_MAX_SUPPLEMENT_BYTES,
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
            supplement_audit_record_count=0,
            papers_with_supplement_manifest_count=0,
            papers_with_parsed_supplement_rows_count=0,
            papers_with_promoted_supplement_rows_count=0,
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
            supplement_discovery_route_counts={},
        )

    conn = sqlite3.connect(index_path)
    conn.row_factory = sqlite3.Row
    try:
        literature_rows = _source_rows(conn, source_record_ids=source_record_ids)
        existing_supplements = _existing_supplement_manifest_supplements(
            conn,
            literature_rows,
            source_record_ids=source_record_ids,
        )
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
        supplement_discovery_route_counts,
    ) = _supplement_candidates_with_discovery(
        literature_rows,
        text_candidates=text_candidates,
        existing_supplements=existing_supplements,
        discover_supplements=discover_supplements,
        fetch_supplement_metadata_fn=fetch_supplement_metadata_fn,
        max_supplement_discovery_records=max_supplement_discovery_records,
        max_repository_supplement_discovery_records=max_repository_supplement_discovery_records,
        gaps=gaps,
    )
    for index, candidate in enumerate(supplement_candidates):
        records.append(_record_for_supplement(candidate, index=index, retrieved_at=retrieved_at))
    supplement_candidate_counts_by_paper = Counter(candidate.source_record_id for candidate in supplement_candidates)
    downloaded_supplement_file_count = 0
    parsed_supplement_file_count = 0
    parsed_supplement_row_count = 0
    parsed_pdf_supplement_file_count = 0
    skipped_pdf_supplement_file_count = 0
    supplement_text_candidates: list[TextCandidate] = []
    supplement_file_gap_records: list[EvidenceRecord] = []
    if download_supplements:
        supplement_file_fetcher = fetch_supplement_file_fn or _fetch_bytes_url
        print(
            f"[aedes_extracted_facts] supplement download candidates={len(supplement_candidates)} "
            f"max_files={max_supplement_files}",
            file=sys.stderr,
            flush=True,
        )
        (
            supplement_text_candidates,
            supplement_file_gap_records,
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
        records.extend(supplement_file_gap_records)
        text_candidates.extend(supplement_text_candidates)
        print(
            "[aedes_extracted_facts] supplement download completed "
            f"downloaded={downloaded_supplement_file_count} "
            f"parsed_files={parsed_supplement_file_count} "
            f"parsed_rows={parsed_supplement_row_count}",
            file=sys.stderr,
            flush=True,
        )
    parsed_supplement_row_counts_by_paper = Counter(candidate.source_record_id for candidate in supplement_text_candidates)

    fact_counts = {family.fact_type: 0 for family in FACT_FAMILIES}
    promoted_supplement_row_counts_by_paper: Counter[str] = Counter()
    print(
        f"[aedes_extracted_facts] fact extraction candidates={len(text_candidates)}",
        file=sys.stderr,
        flush=True,
    )
    for candidate_index, candidate in enumerate(text_candidates, start=1):
        if candidate_index == 1 or candidate_index % 5000 == 0:
            print(
                "[aedes_extracted_facts] fact extraction "
                f"{candidate_index}/{len(text_candidates)} records={len(records)}",
                file=sys.stderr,
                flush=True,
            )
        combined_text = "\n".join([candidate.source_title, candidate.text])
        declared_fact_type = _row_declared_fact_type(candidate.table_row)
        promoted_table_row = False
        for family in FACT_FAMILIES:
            if declared_fact_type and declared_fact_type != family.fact_type:
                continue
            fields = _field_matches(combined_text, family)
            context_hits = _matched_terms(combined_text, family.context_terms)
            if not fields or not context_hits:
                continue
            if family.fact_type == "vector_competence" and not _is_supported_parsed_vector_competence_row(
                candidate.table_row,
                fields,
                declared_fact_type,
            ):
                continue
            if family.fact_type == "resistance" and not _is_supported_parsed_resistance_row(
                candidate.table_row,
                fields,
                declared_fact_type,
            ):
                continue
            enriched_fields = _enrich_fields(combined_text, fields)
            records.append(_record_for_fact(candidate, family, enriched_fields, retrieved_at=retrieved_at))
            if candidate.table_row:
                promoted_supplement_row_counts_by_paper[candidate.source_record_id] += 1
                promoted_table_row = True
            fact_counts[family.fact_type] += 1
        if candidate.table_row and not promoted_table_row:
            records.append(_record_for_unpromoted_supplement_row(candidate, retrieved_at=retrieved_at))
    print(
        f"[aedes_extracted_facts] supplement audit records={len(literature_rows)}",
        file=sys.stderr,
        flush=True,
    )

    supplement_audit_records = [
        _record_for_supplement_audit(
            paper,
            supplement_candidate_count=supplement_candidate_counts_by_paper[str(paper["record_id"])],
            parsed_supplement_row_count=parsed_supplement_row_counts_by_paper[str(paper["record_id"])],
            promoted_supplement_row_count=promoted_supplement_row_counts_by_paper[str(paper["record_id"])],
            discover_supplements=discover_supplements,
            download_supplements=download_supplements,
            retrieved_at=retrieved_at,
        )
        for paper in literature_rows
    ]
    records.extend(supplement_audit_records)

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
        supplement_audit_record_count=len(supplement_audit_records),
        papers_with_supplement_manifest_count=len(supplement_candidate_counts_by_paper),
        papers_with_parsed_supplement_rows_count=len(parsed_supplement_row_counts_by_paper),
        papers_with_promoted_supplement_rows_count=len(promoted_supplement_row_counts_by_paper),
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
        supplement_discovery_route_counts=supplement_discovery_route_counts,
    )
