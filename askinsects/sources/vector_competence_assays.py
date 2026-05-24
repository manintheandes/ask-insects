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


VECTOR_COMPETENCE_ASSAY_SOURCE_ID = "aedes_vector_competence_assays"


PATHOGEN_TERMS: dict[str, tuple[str, ...]] = {
    "dengue virus": ("dengue", "denv", "dengue virus"),
    "Zika virus": ("zika", "zikv", "zika virus"),
    "chikungunya virus": ("chikungunya", "chikv", "chikungunya virus"),
    "yellow fever virus": ("yellow fever", "yfv", "yellow fever virus"),
    "West Nile virus": ("west nile", "wnv", "west nile virus"),
    "Mayaro virus": ("mayaro", "mayv", "mayaro virus"),
}

ASSAY_FIELD_TERMS: dict[str, tuple[str, ...]] = {
    "infection": ("infection rate", "infected", "midgut infection", "body infection", "infection prevalence"),
    "dissemination": ("dissemination rate", "disseminated", "disseminated infection", "legs", "wings"),
    "transmission": ("transmission rate", "transmission efficiency", "saliva", "salivary gland", "transmitted"),
    "dose": ("pfu", "plaque forming", "tcid50", "viral titer", "viral titre", "viral dose", "blood meal titer", "moi"),
    "temperature": ("temperature", "extrinsic incubation", "incubation temperature", "eip"),
    "tissue": ("midgut", "saliva", "salivary gland", "head", "thorax", "abdomen", "body", "legs", "wings"),
    "strain_population": ("strain", "population", "colony", "rockefeller", "liverpool", "field collected", "field population"),
    "timepoint": ("days post infection", "dpi", "days after infection", "post-infection", "extrinsic incubation"),
}

ASSAY_CONTEXT_TERMS = (
    "vector competence",
    "oral infection",
    "blood meal",
    "artificial blood",
    "infection rate",
    "dissemination rate",
    "transmission rate",
    "extrinsic incubation",
    "saliva",
    "midgut",
)

CORE_ASSAY_FIELDS = {"infection", "dissemination", "transmission", "dose", "temperature", "tissue", "timepoint"}

TEMPERATURE_RE = re.compile(r"\b\d{1,2}(?:\.\d+)?\s?(?:°\s?)?C\b|\b\d{1,2}(?:\.\d+)?\s?degrees\s?C\b", re.I)
DOSE_RE = re.compile(
    r"\b(?:10\^?\d+|\d+(?:\.\d+)?)\s?(?:pfu|ffu|tcid50|focus-forming units|plaque-forming units|log10|log)\b",
    re.I,
)


@dataclass(frozen=True)
class AssayCandidate:
    source_record_id: str
    source_title: str
    species: str | None
    paper_url: str | None
    paper_source: str
    source_provenance: dict[str, object]
    extraction_source: str
    unit_id: str | None
    unit_index: int | None
    unit_url: str | None
    unit_license: str | None
    unit_provenance: dict[str, object] | None
    text: str


@dataclass(frozen=True)
class VectorCompetenceAssayResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    candidate_count: int
    source_record_count: int
    fulltext_unit_count: int


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", value).strip("_") or "unknown"


@lru_cache(maxsize=None)
def _pattern_for_term(term: str) -> re.Pattern[str]:
    escaped = re.escape(term.lower()).replace(r"\ ", r"[\s-]+")
    return re.compile(r"\b" + escaped + r"\b", re.I)


def _matched_terms(text: str, terms: Iterable[str]) -> list[str]:
    matches = []
    for term in terms:
        if _pattern_for_term(term).search(text):
            matches.append(term)
    return matches


def _pathogen_matches(text: str) -> dict[str, list[str]]:
    matches: dict[str, list[str]] = {}
    for pathogen, terms in PATHOGEN_TERMS.items():
        hits = _matched_terms(text, terms)
        if hits:
            matches[pathogen] = hits
    return matches


def _assay_field_matches(text: str) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for field, terms in ASSAY_FIELD_TERMS.items():
        hits = _matched_terms(text, terms)
        if hits:
            fields[field] = hits
    return fields


def _snippet(text: str, terms: Iterable[str], limit: int = 700) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return ""
    lower = compact.lower()
    positions = [lower.find(term.lower()) for term in terms if lower.find(term.lower()) >= 0]
    start = max(0, min(positions) - 160) if positions else 0
    snippet = compact[start : start + limit]
    if start > 0:
        snippet = "..." + snippet
    if start + limit < len(compact):
        snippet += "..."
    return snippet


def _candidate_rows(conn: sqlite3.Connection) -> tuple[list[AssayCandidate], int, int]:
    literature_rows = conn.execute(
        """
        SELECT record_id, title, text, species, url, source, provenance_json
        FROM records
        WHERE lane='literature'
        ORDER BY record_id
        """
    ).fetchall()
    literature_by_id = {str(row["record_id"]): row for row in literature_rows}
    fulltext_total_count = int(conn.execute("SELECT count(*) FROM literature_fulltext_units").fetchone()[0])
    all_pathogen_terms = [term for terms in PATHOGEN_TERMS.values() for term in terms]
    pathogen_query = _fts_or_query(all_pathogen_terms)
    all_context_terms = list(ASSAY_CONTEXT_TERMS) + [term for terms in ASSAY_FIELD_TERMS.values() for term in terms]
    context_query = _fts_or_query(all_context_terms)
    if pathogen_query and context_query:
        try:
            fulltext_rows = conn.execute(
                """
                SELECT DISTINCT
                  u.unit_id, u.record_id, u.unit_index, u.text, u.url, u.license, u.provenance_json
                FROM literature_fulltext_fts f
                JOIN literature_fulltext_units u ON u.unit_id = f.unit_id
                WHERE literature_fulltext_fts MATCH ?
                ORDER BY u.record_id, u.unit_index
                """,
                (f"({pathogen_query}) AND ({context_query})",),
            ).fetchall()
        except sqlite3.Error:
            fulltext_rows = conn.execute(
                """
                SELECT unit_id, record_id, unit_index, text, url, license, provenance_json
                FROM literature_fulltext_units
                ORDER BY record_id, unit_index
                """
            ).fetchall()
    else:
        fulltext_rows = []

    candidates: list[AssayCandidate] = []
    for unit in fulltext_rows:
        paper = literature_by_id.get(str(unit["record_id"]))
        if paper is None:
            continue
        candidates.append(
            AssayCandidate(
                source_record_id=str(paper["record_id"]),
                source_title=str(paper["title"]),
                species=paper["species"],
                paper_url=paper["url"],
                paper_source=str(paper["source"]),
                source_provenance=json.loads(str(paper["provenance_json"])),
                extraction_source="literature_fulltext_units",
                unit_id=str(unit["unit_id"]),
                unit_index=int(unit["unit_index"]),
                unit_url=unit["url"],
                unit_license=unit["license"],
                unit_provenance=json.loads(str(unit["provenance_json"])),
                text=str(unit["text"]),
            )
        )

    fulltext_record_ids = {str(row["record_id"]) for row in fulltext_rows}
    for paper in literature_rows:
        if str(paper["record_id"]) in fulltext_record_ids:
            continue
        candidates.append(
            AssayCandidate(
                source_record_id=str(paper["record_id"]),
                source_title=str(paper["title"]),
                species=paper["species"],
                paper_url=paper["url"],
                paper_source=str(paper["source"]),
                source_provenance=json.loads(str(paper["provenance_json"])),
                extraction_source="literature_record",
                unit_id=None,
                unit_index=None,
                unit_url=None,
                unit_license=None,
                unit_provenance=None,
                text="\n".join([str(paper["title"]), str(paper["text"])]),
            )
        )

    return candidates, len(literature_rows), fulltext_total_count


def _fts_term(term: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", term)
    if not tokens:
        return ""
    if len(tokens) == 1:
        return tokens[0]
    return '"' + " ".join(tokens) + '"'


def _fts_or_query(terms: Iterable[str]) -> str:
    parts = [_fts_term(term) for term in terms]
    parts = [part for part in parts if part]
    return " OR ".join(dict.fromkeys(parts))


def _record_for_candidate(candidate: AssayCandidate, pathogen: str, pathogen_terms: list[str], field_terms: dict[str, list[str]], *, retrieved_at: str) -> EvidenceRecord:
    combined_text = "\n".join([candidate.source_title, candidate.text])
    flat_field_terms = [term for terms in field_terms.values() for term in terms]
    context_hits = _matched_terms(combined_text, ASSAY_CONTEXT_TERMS)
    all_terms = list(dict.fromkeys(pathogen_terms + flat_field_terms + context_hits))
    temperatures = list(dict.fromkeys(TEMPERATURE_RE.findall(combined_text)))[:8]
    doses = list(dict.fromkeys(DOSE_RE.findall(combined_text)))[:8]
    snippet = _snippet(combined_text, all_terms)
    field_names = sorted(field_terms)
    unit_part = candidate.unit_id or "literature-record"
    digest = hashlib.sha1(f"{candidate.source_record_id}|{unit_part}|{pathogen}".encode("utf-8")).hexdigest()[:12]
    locator_parts = [f"records#{candidate.source_record_id}"]
    if candidate.unit_id:
        locator_parts.append(f"literature_fulltext_units#{candidate.unit_id}")
    title = f"Aedes aegypti vector competence assay candidate: {pathogen}"
    text = (
        f"Structured assay-candidate extraction for {pathogen} in Aedes aegypti. "
        f"Detected assay fields: {', '.join(field_names)}. "
        f"Matched terms: {', '.join(all_terms[:14])}. "
        f"Temperature values: {', '.join(temperatures) if temperatures else 'not detected'}. "
        f"Dose values: {', '.join(doses) if doses else 'not detected'}. "
        f"Snippet: {snippet}"
    )
    source_url = candidate.unit_url or candidate.paper_url
    return EvidenceRecord(
        record_id=f"assay_candidate:vector_competence:{_normalize_id(candidate.source_record_id)}:{digest}",
        lane="vector_competence",
        source=VECTOR_COMPETENCE_ASSAY_SOURCE_ID,
        title=title,
        text=text,
        species=candidate.species or "Aedes aegypti",
        url=source_url,
        media_url=None,
        provenance=Provenance(
            source_id=VECTOR_COMPETENCE_ASSAY_SOURCE_ID,
            locator=";".join(locator_parts),
            retrieved_at=retrieved_at,
            license=candidate.unit_license or str(candidate.source_provenance.get("license") or "source literature metadata and legal full text where available"),
            source_url=source_url,
        ),
        payload={
            "source_record_id": candidate.source_record_id,
            "source_record_source": candidate.paper_source,
            "source_title": candidate.source_title,
            "extraction_source": candidate.extraction_source,
            "unit_id": candidate.unit_id,
            "unit_index": candidate.unit_index,
            "pathogen": pathogen,
            "pathogen_terms": pathogen_terms,
            "assay_fields": field_terms,
            "context_terms": context_hits,
            "temperature_values": temperatures,
            "dose_values": doses,
            "snippet": snippet,
        },
    )


def build_vector_competence_assay_records(artifact_dir: Path, *, retrieved_at: str | None = None) -> VectorCompetenceAssayResult:
    db_path = artifact_dir / "source_index.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"missing source index: {db_path}")
    retrieved = retrieved_at or utc_now()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        candidates, literature_count, fulltext_count = _candidate_rows(conn)

    records: list[EvidenceRecord] = []
    for candidate in candidates:
        combined_text = "\n".join([candidate.source_title, candidate.text])
        pathogen_hits = _pathogen_matches(combined_text)
        if not pathogen_hits:
            continue
        field_hits = _assay_field_matches(combined_text)
        if TEMPERATURE_RE.search(combined_text):
            field_hits.setdefault("temperature", []).append("temperature value")
        if DOSE_RE.search(combined_text):
            field_hits.setdefault("dose", []).append("dose value")
        context_hits = _matched_terms(combined_text, ASSAY_CONTEXT_TERMS)
        if not field_hits or not context_hits:
            continue
        if not (set(field_hits) & CORE_ASSAY_FIELDS):
            continue
        for pathogen, pathogen_terms in pathogen_hits.items():
            records.append(_record_for_candidate(candidate, pathogen, pathogen_terms, field_hits, retrieved_at=retrieved))

    gaps: list[dict[str, object]] = []
    if not records:
        gaps.append(
            {
                "source": VECTOR_COMPETENCE_ASSAY_SOURCE_ID,
                "lane": "vector_competence",
                "reason": "no_vector_competence_assay_candidates_detected",
                "literature_record_count": literature_count,
                "fulltext_unit_count": fulltext_count,
                "retrieved_at": retrieved,
            }
        )

    return VectorCompetenceAssayResult(
        source_id=VECTOR_COMPETENCE_ASSAY_SOURCE_ID,
        records=records,
        gaps=gaps,
        candidate_count=len(records),
        source_record_count=literature_count,
        fulltext_unit_count=fulltext_count,
    )
