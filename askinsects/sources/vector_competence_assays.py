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
    parsed_table_row_count: int


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
        # Mixed-species source: candidates come from a literature corpus (lane='literature',
        # not species-filtered) that can cover other species. Keep the source record's own
        # species; do not fabricate.
        species=candidate.species,
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


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _table_text(table_row: dict[str, object]) -> str:
    parts = []
    for key, value in table_row.items():
        parts.append(f"{key}: {value}")
    return ". ".join(parts)


def _field_hits_from_parsed_fields(fields: dict[str, object], combined_text: str) -> dict[str, list[str]]:
    field_hits = _assay_field_matches(combined_text)
    for field in ASSAY_FIELD_TERMS:
        if field in fields:
            hits = _as_list(fields.get(field))
            if hits:
                field_hits.setdefault(field, [])
                field_hits[field].extend(hit for hit in hits if hit not in field_hits[field])
    if fields.get("dose_values"):
        field_hits.setdefault("dose", [])
        field_hits["dose"].extend(hit for hit in _as_list(fields.get("dose_values")) if hit not in field_hits["dose"])
    if fields.get("temperature_values"):
        field_hits.setdefault("temperature", [])
        field_hits["temperature"].extend(hit for hit in _as_list(fields.get("temperature_values")) if hit not in field_hits["temperature"])
    if TEMPERATURE_RE.search(combined_text):
        field_hits.setdefault("temperature", []).append("temperature value")
    if DOSE_RE.search(combined_text):
        field_hits.setdefault("dose", []).append("dose value")
    return {key: list(dict.fromkeys(value)) for key, value in field_hits.items() if value}


def _pathogen_hits_from_parsed_fields(fields: dict[str, object], combined_text: str) -> dict[str, list[str]]:
    hits = _pathogen_matches(combined_text)
    for value in _as_list(fields.get("pathogen")):
        for pathogen, terms in PATHOGEN_TERMS.items():
            if value.lower() in {term.lower() for term in terms} or _pattern_for_term(value).search(" ".join(terms)):
                hits.setdefault(pathogen, [])
                if value not in hits[pathogen]:
                    hits[pathogen].append(value)
    return hits


def _records_from_parsed_extracted_fact_rows(
    conn: sqlite3.Connection,
    *,
    retrieved_at: str,
) -> tuple[list[EvidenceRecord], int, int]:
    rows = conn.execute(
        """
        SELECT
          r.record_id,
          r.title,
          r.text,
          r.species,
          r.url,
          r.provenance_json,
          p.payload_json
        FROM records r
        JOIN record_payloads p ON p.record_id = r.record_id
        WHERE r.source = 'aedes_extracted_facts'
          AND r.lane = 'vector_competence'
        ORDER BY r.record_id
        """
    ).fetchall()
    records: list[EvidenceRecord] = []
    parsed_rows_seen = 0
    skipped_rows = 0
    for row in rows:
        try:
            payload = json.loads(str(row["payload_json"]))
        except json.JSONDecodeError:
            skipped_rows += 1
            continue
        if payload.get("fact_type") != "vector_competence" or payload.get("confidence") != "parsed":
            continue
        fields = payload.get("fields")
        if not isinstance(fields, dict):
            skipped_rows += 1
            continue
        table_row = fields.get("table_row")
        if not isinstance(table_row, dict) or not table_row:
            skipped_rows += 1
            continue
        parsed_rows_seen += 1
        table_row_text = _table_text(table_row)
        evidence_text = str(payload.get("evidence_text") or "")
        combined_text = "\n".join([str(row["title"]), str(row["text"]), evidence_text, table_row_text])
        pathogen_hits = _pathogen_hits_from_parsed_fields(fields, combined_text)
        field_hits = _field_hits_from_parsed_fields(fields, combined_text)
        metric_fields = set(field_hits) & {"infection", "dissemination", "transmission"}
        if not pathogen_hits or not metric_fields:
            skipped_rows += 1
            continue
        source_record_id = str(payload.get("source_record_id") or "")
        source_provenance = payload.get("source_provenance") if isinstance(payload.get("source_provenance"), dict) else {}
        extracted_provenance = json.loads(str(row["provenance_json"]))
        table_headers = fields.get("table_headers") if isinstance(fields.get("table_headers"), list) else list(table_row)
        table_row_index = fields.get("table_row_index")
        dose_values = _as_list(fields.get("dose_values"))
        temperature_values = _as_list(fields.get("temperature_values"))
        for pathogen, pathogen_terms in pathogen_hits.items():
            digest = hashlib.sha1(f"{row['record_id']}|{pathogen}|{json.dumps(table_row, sort_keys=True)}".encode("utf-8")).hexdigest()[:12]
            source_url = row["url"] or extracted_provenance.get("source_url") or source_provenance.get("source_url")
            locator_parts = [f"aedes_extracted_facts#{row['record_id']}"]
            if source_record_id:
                locator_parts.append(f"records#{source_record_id}")
            locator = extracted_provenance.get("locator")
            if locator:
                locator_parts.append(str(locator))
            title = f"Aedes aegypti parsed vector competence table row: {pathogen}"
            text = (
                f"Schema-validated parsed supplement table row for {pathogen} in Aedes aegypti. "
                f"Validation status: schema_validated, not human_validated. "
                f"Detected assay fields: {', '.join(sorted(field_hits))}. "
                f"Table row: {table_row_text}"
            )
            records.append(
                EvidenceRecord(
                    record_id=f"assay_table:vector_competence:{_normalize_id(str(row['record_id']))}:{digest}",
                    lane="vector_competence",
                    source=VECTOR_COMPETENCE_ASSAY_SOURCE_ID,
                    title=title,
                    text=text,
                    # Mixed-species source: parsed supplement tables (source filter only,
                    # not species filter) can describe other species. Keep the row's own
                    # species; do not fabricate a default.
                    species=row["species"] or None,
                    url=source_url,
                    media_url=None,
                    provenance=Provenance(
                        source_id=VECTOR_COMPETENCE_ASSAY_SOURCE_ID,
                        locator=";".join(locator_parts),
                        retrieved_at=retrieved_at,
                        license=extracted_provenance.get("license") or source_provenance.get("license"),
                        source_url=source_url,
                    ),
                    payload={
                        "source_extracted_fact_record_id": row["record_id"],
                        "source_record_id": source_record_id or None,
                        "source_title": payload.get("source_title") or row["title"],
                        "source_confidence": payload.get("confidence"),
                        "source_extraction_method": payload.get("extraction_method"),
                        "extraction_source": "aedes_extracted_facts_parsed_supplement_table",
                        "confidence": "parsed_table_schema_validated",
                        "validation_status": "schema_validated",
                        "human_validated": False,
                        "pathogen": pathogen,
                        "pathogen_terms": pathogen_terms,
                        "assay_fields": field_hits,
                        "metric_fields": sorted(metric_fields),
                        "dose_values": dose_values,
                        "temperature_values": temperature_values,
                        "table_headers": table_headers,
                        "table_row": table_row,
                        "table_row_index": table_row_index,
                        "evidence_text": evidence_text,
                        "source_payload_schema_version": payload.get("schema_version"),
                        "source_provenance": source_provenance,
                        "extracted_fact_provenance": extracted_provenance,
                    },
                )
            )
    return records, parsed_rows_seen, skipped_rows


def build_vector_competence_assay_records(artifact_dir: Path, *, retrieved_at: str | None = None) -> VectorCompetenceAssayResult:
    db_path = artifact_dir / "source_index.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"missing source index: {db_path}")
    retrieved = retrieved_at or utc_now()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        candidates, literature_count, fulltext_count = _candidate_rows(conn)
        parsed_table_records, parsed_table_rows_seen, skipped_parsed_table_rows = _records_from_parsed_extracted_fact_rows(
            conn,
            retrieved_at=retrieved,
        )

    records: list[EvidenceRecord] = list(parsed_table_records)
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
    elif skipped_parsed_table_rows:
        gaps.append(
            {
                "source": VECTOR_COMPETENCE_ASSAY_SOURCE_ID,
                "lane": "vector_competence",
                "reason": "parsed_vector_competence_table_rows_skipped_schema_validation",
                "parsed_table_rows_seen": parsed_table_rows_seen,
                "skipped_parsed_table_rows": skipped_parsed_table_rows,
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
        parsed_table_row_count=len(parsed_table_records),
    )
