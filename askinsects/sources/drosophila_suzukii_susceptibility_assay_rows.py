from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Iterable

from askinsects.records import EvidenceRecord, Provenance


DROSOPHILA_SUZUKII_SUSCEPTIBILITY_ASSAY_ROWS_SOURCE_ID = "drosophila_suzukii_susceptibility_assay_rows"
DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID = "drosophila_suzukii_extracted_facts"
DROSOPHILA_SUZUKII_SPECIES = "Drosophila suzukii"
DROSOPHILA_SUZUKII_COMMON_NAME = "spotted wing drosophila"

INSECTICIDE_TERMS = (
    "spinosad",
    "spinetoram",
    "malathion",
    "lambda-cyhalothrin",
    "zeta-cypermethrin",
    "deltamethrin",
    "cypermethrin",
    "pyrethroid",
    "organophosphate",
    "phosmet",
    "dimethoate",
    "cyantraniliprole",
    "acetamiprid",
    "thiamethoxam",
    "thiacloprid",
    "imidacloprid",
    "emamectin-benzoate",
    "neonicotinoid",
)
ASSAY_TERMS = (
    "bioassay",
    "vial bioassay",
    "dose response",
    "dose-response",
    "diagnostic dose",
    "exposure",
    "field population",
    "residue longevity",
)
METRIC_FIELDS = (
    "mortality",
    "survival",
    "lc_value",
    "ld_value",
    "knockdown",
    "resistance_ratio",
    "fecundity",
    "egg_laying",
    "hatching",
    "emergence",
)


@dataclass(frozen=True)
class DrosophilaSuzukiiSusceptibilityAssayResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    parsed_table_row_count: int
    candidate_fact_count: int
    skipped_record_count: int
    extracted_fact_record_count: int


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", value).strip("_") or "unknown"


def _pattern_for_term(term: str) -> re.Pattern[str]:
    escaped = re.escape(term).replace(r"\ ", r"[\s-]+")
    return re.compile(r"(?<![A-Za-z0-9])" + escaped + r"(?![A-Za-z0-9])", re.I)


def _matched_terms(text: str, terms: Iterable[str]) -> list[str]:
    matches = []
    for term in terms:
        if _pattern_for_term(term).search(text):
            matches.append(term)
    return matches


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _field_values(fields: dict[str, object], keys: Iterable[str]) -> list[str]:
    values: list[str] = []
    for key in keys:
        values.extend(_as_list(fields.get(key)))
    return list(dict.fromkeys(values))


def _table_text(table_row: dict[str, object]) -> str:
    return ". ".join(f"{key}: {value}" for key, value in table_row.items())


def _metric_fields(fields: dict[str, object], combined_text: str) -> list[str]:
    metrics = [field for field in METRIC_FIELDS if _as_list(fields.get(field))]
    lower = combined_text.lower()
    if "mortality" in lower or re.search(r"\b\d+(?:\.\d+)?\s*%", lower):
        metrics.append("mortality")
    if "survival" in lower or "survivorship" in lower:
        metrics.append("survival")
    if "lc50" in lower or "lc90" in lower:
        metrics.append("lc_value")
    if "ld50" in lower or "ld90" in lower:
        metrics.append("ld_value")
    if "knockdown" in lower:
        metrics.append("knockdown")
    if "resistance ratio" in lower:
        metrics.append("resistance_ratio")
    if "fecundity" in lower:
        metrics.append("fecundity")
    if "egg" in lower and ("laying" in lower or "hatching" in lower):
        metrics.append("egg_laying")
    if "emergence" in lower or "emerging" in lower:
        metrics.append("emergence")
    return [field for field in METRIC_FIELDS if field in set(metrics)]


def _source_url(row: sqlite3.Row, payload: dict[str, object], extracted_provenance: dict[str, object]) -> str | None:
    source_provenance = payload.get("source_provenance") if isinstance(payload.get("source_provenance"), dict) else {}
    return str(row["url"] or extracted_provenance.get("source_url") or source_provenance.get("source_url") or "") or None


def _locator_parts(row: sqlite3.Row, payload: dict[str, object], extracted_provenance: dict[str, object]) -> list[str]:
    parts = [f"{DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID}#{row['record_id']}"]
    source_record_id = str(payload.get("source_record_id") or "")
    if source_record_id:
        parts.append(f"records#{source_record_id}")
    locator = extracted_provenance.get("locator")
    if locator:
        parts.append(str(locator))
    return parts


def _record_payload_base(
    row: sqlite3.Row,
    payload: dict[str, object],
    extracted_provenance: dict[str, object],
    *,
    insecticide_terms: list[str],
    assay_terms: list[str],
    metric_fields: list[str],
) -> dict[str, object]:
    source_provenance = payload.get("source_provenance") if isinstance(payload.get("source_provenance"), dict) else {}
    return {
        "source_extracted_fact_record_id": row["record_id"],
        "source_record_id": payload.get("source_record_id"),
        "source_title": payload.get("source_title") or row["title"],
        "source_confidence": payload.get("confidence"),
        "source_extraction_method": payload.get("extraction_method"),
        "human_validated": False,
        "insecticide_terms": insecticide_terms,
        "assay_terms": assay_terms,
        "metric_fields": metric_fields,
        "evidence_text": payload.get("evidence_text"),
        "source_payload_schema_version": payload.get("schema_version"),
        "source_provenance": source_provenance,
        "extracted_fact_provenance": extracted_provenance,
    }


def _parsed_table_record(
    row: sqlite3.Row,
    payload: dict[str, object],
    extracted_provenance: dict[str, object],
    *,
    retrieved_at: str,
    insecticide_terms: list[str],
    assay_terms: list[str],
    metric_fields: list[str],
    table_row: dict[str, object],
) -> EvidenceRecord:
    source_url = _source_url(row, payload, extracted_provenance)
    source_title = payload.get("source_title") or row["title"]
    table_headers = payload.get("fields", {}).get("table_headers") if isinstance(payload.get("fields"), dict) else None
    if not isinstance(table_headers, list):
        table_headers = list(table_row)
    table_row_text = _table_text(table_row)
    digest = hashlib.sha1(f"{row['record_id']}|{json.dumps(table_row, sort_keys=True)}".encode("utf-8")).hexdigest()[:12]
    text = (
        "Schema-validated parsed supplement table row for Drosophila suzukii insecticide susceptibility or resistance. "
        "Validation status: schema_validated, not human_validated. "
        f"Source record: {payload.get('source_record_id') or 'unknown'}. "
        f"Source title: {source_title}. "
        f"Insecticide terms: {', '.join(insecticide_terms)}. "
        f"Assay terms: {', '.join(assay_terms) if assay_terms else 'not detected'}. "
        f"Metric fields: {', '.join(metric_fields)}. "
        f"Table row: {table_row_text}"
    )
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    record_payload = _record_payload_base(
        row,
        payload,
        extracted_provenance,
        insecticide_terms=insecticide_terms,
        assay_terms=assay_terms,
        metric_fields=metric_fields,
    )
    record_payload.update(
        {
            "extraction_source": "drosophila_suzukii_extracted_facts_parsed_supplement_table",
            "confidence": "parsed_table_schema_validated",
            "validation_status": "schema_validated",
            "table_headers": table_headers,
            "table_row": table_row,
            "table_row_index": fields.get("table_row_index"),
        }
    )
    source_provenance = payload.get("source_provenance") if isinstance(payload.get("source_provenance"), dict) else {}
    return EvidenceRecord(
        record_id=f"swd_susceptibility_table:{_normalize_id(str(row['record_id']))}:{digest}",
        lane="resistance",
        source=DROSOPHILA_SUZUKII_SUSCEPTIBILITY_ASSAY_ROWS_SOURCE_ID,
        title=f"Drosophila suzukii susceptibility table row: {', '.join(insecticide_terms[:2])}",
        text=text,
        species=DROSOPHILA_SUZUKII_SPECIES,
        url=source_url,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_SUSCEPTIBILITY_ASSAY_ROWS_SOURCE_ID,
            locator=";".join(_locator_parts(row, payload, extracted_provenance)),
            retrieved_at=retrieved_at,
            license=extracted_provenance.get("license") or source_provenance.get("license"),
            source_url=source_url,
        ),
        payload=record_payload,
    )


def _candidate_record(
    row: sqlite3.Row,
    payload: dict[str, object],
    extracted_provenance: dict[str, object],
    *,
    retrieved_at: str,
    insecticide_terms: list[str],
    assay_terms: list[str],
    metric_fields: list[str],
) -> EvidenceRecord:
    source_url = _source_url(row, payload, extracted_provenance)
    source_title = payload.get("source_title") or row["title"]
    evidence_text = str(payload.get("evidence_text") or row["text"] or "")
    digest = hashlib.sha1(f"{row['record_id']}|candidate".encode("utf-8")).hexdigest()[:12]
    text = (
        "Candidate literature evidence for Drosophila suzukii insecticide susceptibility or resistance. "
        "Validation status: candidate_not_table_validated, not human_validated. "
        f"Source record: {payload.get('source_record_id') or 'unknown'}. "
        f"Source title: {source_title}. "
        f"Insecticide terms: {', '.join(insecticide_terms)}. "
        f"Assay terms: {', '.join(assay_terms) if assay_terms else 'not detected'}. "
        f"Metric fields: {', '.join(metric_fields)}. "
        f"Evidence: {evidence_text}"
    )
    record_payload = _record_payload_base(
        row,
        payload,
        extracted_provenance,
        insecticide_terms=insecticide_terms,
        assay_terms=assay_terms,
        metric_fields=metric_fields,
    )
    record_payload.update(
        {
            "extraction_source": "drosophila_suzukii_extracted_facts_candidate_resistance_fact",
            "confidence": "candidate_literature_evidence",
            "validation_status": "candidate_not_table_validated",
        }
    )
    source_provenance = payload.get("source_provenance") if isinstance(payload.get("source_provenance"), dict) else {}
    return EvidenceRecord(
        record_id=f"swd_susceptibility_candidate:{_normalize_id(str(row['record_id']))}:{digest}",
        lane="resistance",
        source=DROSOPHILA_SUZUKII_SUSCEPTIBILITY_ASSAY_ROWS_SOURCE_ID,
        title=f"Drosophila suzukii susceptibility evidence: {', '.join(insecticide_terms[:2])}",
        text=text,
        species=DROSOPHILA_SUZUKII_SPECIES,
        url=source_url,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_SUSCEPTIBILITY_ASSAY_ROWS_SOURCE_ID,
            locator=";".join(_locator_parts(row, payload, extracted_provenance)),
            retrieved_at=retrieved_at,
            license=extracted_provenance.get("license") or source_provenance.get("license"),
            source_url=source_url,
        ),
        payload=record_payload,
    )


def _gap_record(
    *,
    reason: str,
    retrieved_at: str,
    extracted_fact_record_count: int,
    parsed_rows_seen: int,
    skipped_record_count: int,
) -> EvidenceRecord:
    text = (
        "Drosophila suzukii susceptibility assay source gap. "
        f"Reason: {reason}. "
        f"Extracted resistance fact records checked: {extracted_fact_record_count}. "
        f"Parsed susceptibility table rows seen: {parsed_rows_seen}. "
        f"Rows skipped by schema validation: {skipped_record_count}. "
        "This preserves the gap instead of treating generic resistance-gene annotations as insecticide susceptibility assays."
    )
    return EvidenceRecord(
        record_id=f"swd_susceptibility:gap:{reason}",
        lane="resistance",
        source=DROSOPHILA_SUZUKII_SUSCEPTIBILITY_ASSAY_ROWS_SOURCE_ID,
        title="Drosophila suzukii susceptibility assay source gap",
        text=text,
        species=DROSOPHILA_SUZUKII_SPECIES,
        url=None,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_SUSCEPTIBILITY_ASSAY_ROWS_SOURCE_ID,
            locator=f"gaps.json#{reason}",
            retrieved_at=retrieved_at,
            license="derived source-gap metadata",
        ),
        payload={
            "atom_type": "source_gap",
            "reason": reason,
            "extracted_fact_record_count": extracted_fact_record_count,
            "parsed_table_rows_seen": parsed_rows_seen,
            "skipped_record_count": skipped_record_count,
            "confidence": "source_gap",
            "validation_status": "source_gap",
            "human_validated": False,
        },
    )


def _records_from_extracted_facts(conn: sqlite3.Connection, *, retrieved_at: str) -> tuple[list[EvidenceRecord], int, int, int, int]:
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
        WHERE r.source = ?
          AND r.lane = 'resistance'
        ORDER BY r.record_id
        """,
        (DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID,),
    ).fetchall()
    records: list[EvidenceRecord] = []
    parsed_rows_seen = 0
    candidate_count = 0
    skipped = 0
    for row in rows:
        try:
            payload = json.loads(str(row["payload_json"]))
            extracted_provenance = json.loads(str(row["provenance_json"]))
        except json.JSONDecodeError:
            skipped += 1
            continue
        if payload.get("fact_type") != "resistance":
            continue
        fields = payload.get("fields")
        if not isinstance(fields, dict):
            skipped += 1
            continue
        evidence_text = str(payload.get("evidence_text") or "")
        table_row = fields.get("table_row")
        table_row_text = _table_text(table_row) if isinstance(table_row, dict) else ""
        combined_text = "\n".join([str(row["title"]), str(row["text"]), evidence_text, table_row_text])
        insecticide_terms = list(dict.fromkeys(_field_values(fields, ("insecticide",)) + _matched_terms(combined_text, INSECTICIDE_TERMS)))
        assay_terms = list(dict.fromkeys(_field_values(fields, ("assay",)) + _matched_terms(combined_text, ASSAY_TERMS)))
        metric_fields = _metric_fields(fields, combined_text)
        if not insecticide_terms or not (assay_terms or metric_fields):
            skipped += 1
            continue
        confidence = payload.get("confidence")
        if confidence == "parsed" and isinstance(table_row, dict) and table_row:
            parsed_rows_seen += 1
            records.append(
                _parsed_table_record(
                    row,
                    payload,
                    extracted_provenance,
                    retrieved_at=retrieved_at,
                    insecticide_terms=insecticide_terms,
                    assay_terms=assay_terms,
                    metric_fields=metric_fields,
                    table_row=table_row,
                )
            )
        elif confidence == "candidate":
            candidate_count += 1
            records.append(
                _candidate_record(
                    row,
                    payload,
                    extracted_provenance,
                    retrieved_at=retrieved_at,
                    insecticide_terms=insecticide_terms,
                    assay_terms=assay_terms,
                    metric_fields=metric_fields,
                )
            )
        else:
            skipped += 1
    return records, parsed_rows_seen, candidate_count, skipped, len(rows)


def build_drosophila_suzukii_susceptibility_assay_records(
    artifact_dir: Path,
    *,
    retrieved_at: str | None = None,
) -> DrosophilaSuzukiiSusceptibilityAssayResult:
    db_path = artifact_dir / "source_index.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"missing source index: {db_path}")
    retrieved = retrieved_at or utc_now()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        records, parsed_rows_seen, candidate_count, skipped, extracted_fact_count = _records_from_extracted_facts(conn, retrieved_at=retrieved)

    gaps: list[dict[str, object]] = []
    if not records:
        reason = "no_swd_susceptibility_evidence_rows_detected"
        gaps.append(
            {
                "source": DROSOPHILA_SUZUKII_SUSCEPTIBILITY_ASSAY_ROWS_SOURCE_ID,
                "lane": "resistance",
                "reason": reason,
                "extracted_fact_record_count": extracted_fact_count,
                "parsed_table_rows_seen": parsed_rows_seen,
                "retrieved_at": retrieved,
            }
        )
        records.append(
            _gap_record(
                reason=reason,
                retrieved_at=retrieved,
                extracted_fact_record_count=extracted_fact_count,
                parsed_rows_seen=parsed_rows_seen,
                skipped_record_count=skipped,
            )
        )
    elif parsed_rows_seen == 0:
        reason = "no_parsed_swd_susceptibility_table_rows_detected"
        gaps.append(
            {
                "source": DROSOPHILA_SUZUKII_SUSCEPTIBILITY_ASSAY_ROWS_SOURCE_ID,
                "lane": "resistance",
                "reason": reason,
                "extracted_fact_record_count": extracted_fact_count,
                "candidate_fact_count": candidate_count,
                "retrieved_at": retrieved,
            }
        )
        records.append(
            _gap_record(
                reason=reason,
                retrieved_at=retrieved,
                extracted_fact_record_count=extracted_fact_count,
                parsed_rows_seen=parsed_rows_seen,
                skipped_record_count=skipped,
            )
        )

    return DrosophilaSuzukiiSusceptibilityAssayResult(
        source_id=DROSOPHILA_SUZUKII_SUSCEPTIBILITY_ASSAY_ROWS_SOURCE_ID,
        records=records,
        gaps=gaps,
        parsed_table_row_count=parsed_rows_seen,
        candidate_fact_count=candidate_count,
        skipped_record_count=skipped,
        extracted_fact_record_count=extracted_fact_count,
    )
