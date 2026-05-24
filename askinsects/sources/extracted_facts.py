from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Iterable

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


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@lru_cache(maxsize=None)
def _pattern_for_term(term: str) -> re.Pattern[str]:
    escaped = re.escape(term).replace(r"\ ", r"[\s-]+")
    return re.compile(r"(?<![A-Za-z0-9])" + escaped + r"(?![A-Za-z0-9])", re.I)


def _matched_terms(text: str, terms: Iterable[str]) -> list[str]:
    matches = []
    for term in terms:
        if _pattern_for_term(term).search(text):
            matches.append(term)
    return matches


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


def _source_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT r.record_id, r.title, r.text, r.species, r.url, r.provenance_json, p.payload_json
        FROM records r
        LEFT JOIN record_payloads p ON p.record_id = r.record_id
        WHERE r.lane='literature'
          AND r.source=?
          AND lower(coalesce(r.species, ''))='aedes aegypti'
        ORDER BY r.record_id
        """,
        (INPUT_LITERATURE_SOURCE_ID,),
    ).fetchall()


def _matches_prefilter(text: str) -> bool:
    lower = text.lower()
    return any(token in lower for token in PREFILTER_TOKENS)


def _looks_like_markup_noise(text: str) -> bool:
    lower = text[:20000].lower()
    if "<!doctype html" in lower or "<html" in lower:
        return True
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
        markup_tokens >= 6
        or css_tokens >= 10
        or css_declarations >= 8
        or (css_declarations >= 5 and css_rule_markers >= 5)
    )


def _bounded_fulltext_rows(
    conn: sqlite3.Connection,
    *,
    max_fulltext_units: int | None,
) -> list[sqlite3.Row]:
    query = """
        SELECT unit_id, record_id, unit_index, text, url, license, provenance_json
        FROM literature_fulltext_units
        ORDER BY rowid
    """
    params: list[object] = []
    if max_fulltext_units is not None:
        query += " LIMIT ?"
        params.append(max_fulltext_units + 1)
    return conn.execute(query, params).fetchall()


def _text_candidates(
    conn: sqlite3.Connection,
    literature_rows: list[sqlite3.Row],
    *,
    max_fulltext_units: int | None,
) -> tuple[list[TextCandidate], int, int, int, int]:
    if max_fulltext_units is not None and max_fulltext_units < 1:
        raise ValueError("max_fulltext_units must be positive")
    literature_by_id = {str(row["record_id"]): row for row in literature_rows}
    try:
        fulltext_rows = _bounded_fulltext_rows(
            conn,
            max_fulltext_units=max_fulltext_units,
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
    url = raw.get("url") or raw.get("href") or raw.get("download_url") or raw.get("fileUrl")
    file_type = raw.get("file_type") or raw.get("type") or raw.get("format") or raw.get("mimeType")
    license_value = raw.get("license") or raw.get("licence")
    size = raw.get("size") or raw.get("fileSize")
    source = raw.get("source") or raw.get("provider") or "record_payload"
    supplement = {
        "title": str(title or "Supplementary material"),
        "url": str(url) if url else None,
        "file_type": str(file_type) if file_type else None,
        "license": str(license_value) if license_value else None,
        "size": size if isinstance(size, int | float | str) else None,
        "source": str(source),
    }
    return {key: value for key, value in supplement.items() if value is not None}


def _supplement_candidates(literature_rows: list[sqlite3.Row]) -> list[SupplementCandidate]:
    candidates: list[SupplementCandidate] = []
    seen: set[tuple[str, str, str]] = set()
    for paper in literature_rows:
        payload = _safe_json(paper["payload_json"])
        for raw_supplement in _payload_supplements(payload):
            supplement = _normalize_supplement(raw_supplement)
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
    unit_part = candidate.unit_id or "literature-record"
    digest = _digest(candidate.source_record_id, unit_part, family.fact_type, json.dumps(fields, sort_keys=True))
    locator_parts = [f"records#{candidate.source_record_id}"]
    if candidate.unit_id:
        locator_parts.append(f"literature_fulltext_units#{candidate.unit_id}")
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
            "supplement": None,
            "evidence_text": evidence_text,
            "confidence": "candidate",
            "extraction_method": "deterministic_fulltext_term_extract",
            "source_provenance": candidate.source_provenance,
            "unit_provenance": candidate.unit_provenance,
        },
    )


def build_extracted_fact_records(
    artifact_dir: Path,
    *,
    retrieved_at: str | None = None,
    max_fulltext_units: int | None = 5000,
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
        )

    conn = sqlite3.connect(index_path)
    conn.row_factory = sqlite3.Row
    try:
        literature_rows = _source_rows(conn)
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
        )
    finally:
        conn.close()

    supplement_candidates = _supplement_candidates(literature_rows)
    for index, candidate in enumerate(supplement_candidates):
        records.append(_record_for_supplement(candidate, index=index, retrieved_at=retrieved_at))

    fact_counts = {family.fact_type: 0 for family in FACT_FAMILIES}
    for candidate in text_candidates:
        combined_text = "\n".join([candidate.source_title, candidate.text])
        for family in FACT_FAMILIES:
            fields = _field_matches(combined_text, family)
            context_hits = _matched_terms(combined_text, family.context_terms)
            if not fields or not context_hits:
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
        fact_counts=fact_counts,
    )
