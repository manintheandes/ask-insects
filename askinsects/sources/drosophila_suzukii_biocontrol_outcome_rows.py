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


DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID = "drosophila_suzukii_biocontrol_outcome_rows"
DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID = "drosophila_suzukii_extracted_facts"
DROSOPHILA_SUZUKII_SPECIES = "Drosophila suzukii"
DROSOPHILA_SUZUKII_COMMON_NAME = "spotted wing drosophila"

AGENT_TERMS = (
    "parasitoid",
    "ganaspis",
    "ganaspis brasiliensis",
    "pachycrepoideus",
    "pachycrepoideus vindemmiae",
    "trichopria",
    "trichopria drosophilae",
    "leptopilina",
    "predator",
    "pathogen",
    "entomopathogenic",
    "steinernema",
    "xenorhabdus",
)
ASSAY_TERMS = (
    "choice assay",
    "no-choice",
    "no choice",
    "field release",
    "release",
    "laboratory",
    "cage",
    "semifield",
    "field trial",
)
EFFECT_METRIC_TERMS = (
    "parasitism",
    "parasitization",
    "mortality",
    "emergence",
    "attack rate",
    "suppression",
    "survival",
    "host preference",
)
TARGET_STAGE_TERMS = ("egg", "larva", "larvae", "pupa", "pupae", "adult")


@dataclass(frozen=True)
class DrosophilaSuzukiiBiocontrolOutcomeResult:
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
    return [term for term in terms if _pattern_for_term(term).search(text)]


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
    agent_terms: list[str],
    assay_terms: list[str],
    effect_metric_terms: list[str],
    target_stage_terms: list[str],
    percent_values: list[str],
    temperature_values: list[str],
) -> dict[str, object]:
    source_provenance = payload.get("source_provenance") if isinstance(payload.get("source_provenance"), dict) else {}
    return {
        "source_extracted_fact_record_id": row["record_id"],
        "source_record_id": payload.get("source_record_id"),
        "source_title": payload.get("source_title") or row["title"],
        "source_confidence": payload.get("confidence"),
        "source_extraction_method": payload.get("extraction_method"),
        "human_validated": False,
        "agent_terms": agent_terms,
        "assay_terms": assay_terms,
        "effect_metric_terms": effect_metric_terms,
        "target_stage_terms": target_stage_terms,
        "percent_values": percent_values,
        "temperature_values": temperature_values,
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
    agent_terms: list[str],
    assay_terms: list[str],
    effect_metric_terms: list[str],
    target_stage_terms: list[str],
    percent_values: list[str],
    temperature_values: list[str],
    table_row: dict[str, object],
) -> EvidenceRecord:
    source_url = _source_url(row, payload, extracted_provenance)
    source_title = payload.get("source_title") or row["title"]
    table_row_text = _table_text(table_row)
    digest = hashlib.sha1(f"{row['record_id']}|{json.dumps(table_row, sort_keys=True)}".encode("utf-8")).hexdigest()[:12]
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    table_headers = fields.get("table_headers")
    if not isinstance(table_headers, list):
        table_headers = list(table_row)
    text = (
        "Schema-validated parsed supplement table row for Drosophila suzukii biological-control outcomes. "
        "Validation status: schema_validated, not human_validated. "
        f"Source record: {payload.get('source_record_id') or 'unknown'}. "
        f"Source title: {source_title}. "
        f"Agent terms: {', '.join(agent_terms)}. "
        f"Assay terms: {', '.join(assay_terms) if assay_terms else 'not detected'}. "
        f"Effect metric terms: {', '.join(effect_metric_terms) if effect_metric_terms else 'not detected'}. "
        f"Target stage terms: {', '.join(target_stage_terms) if target_stage_terms else 'not detected'}. "
        f"Table row: {table_row_text}"
    )
    record_payload = _record_payload_base(
        row,
        payload,
        extracted_provenance,
        agent_terms=agent_terms,
        assay_terms=assay_terms,
        effect_metric_terms=effect_metric_terms,
        target_stage_terms=target_stage_terms,
        percent_values=percent_values,
        temperature_values=temperature_values,
    )
    record_payload.update(
        {
            "extraction_source": "drosophila_suzukii_extracted_facts_parsed_biocontrol_table",
            "confidence": "parsed_table_schema_validated",
            "validation_status": "schema_validated",
            "table_headers": table_headers,
            "table_row": table_row,
            "table_row_index": fields.get("table_row_index"),
        }
    )
    source_provenance = payload.get("source_provenance") if isinstance(payload.get("source_provenance"), dict) else {}
    return EvidenceRecord(
        record_id=f"swd_biocontrol_table:{_normalize_id(str(row['record_id']))}:{digest}",
        lane="biocontrol",
        source=DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID,
        title=f"Drosophila suzukii biocontrol table row: {', '.join(agent_terms[:2])}",
        text=text,
        species=DROSOPHILA_SUZUKII_SPECIES,
        url=source_url,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID,
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
    agent_terms: list[str],
    assay_terms: list[str],
    effect_metric_terms: list[str],
    target_stage_terms: list[str],
    percent_values: list[str],
    temperature_values: list[str],
) -> EvidenceRecord:
    source_url = _source_url(row, payload, extracted_provenance)
    source_title = payload.get("source_title") or row["title"]
    evidence_text = str(payload.get("evidence_text") or row["text"] or "")
    digest = hashlib.sha1(f"{row['record_id']}|candidate".encode("utf-8")).hexdigest()[:12]
    text = (
        "Candidate literature evidence for Drosophila suzukii biological-control outcomes. "
        "Validation status: candidate_not_table_validated, not human_validated. "
        f"Source record: {payload.get('source_record_id') or 'unknown'}. "
        f"Source title: {source_title}. "
        f"Agent terms: {', '.join(agent_terms)}. "
        f"Assay terms: {', '.join(assay_terms) if assay_terms else 'not detected'}. "
        f"Effect metric terms: {', '.join(effect_metric_terms) if effect_metric_terms else 'not detected'}. "
        f"Target stage terms: {', '.join(target_stage_terms) if target_stage_terms else 'not detected'}. "
        f"Evidence: {evidence_text}"
    )
    record_payload = _record_payload_base(
        row,
        payload,
        extracted_provenance,
        agent_terms=agent_terms,
        assay_terms=assay_terms,
        effect_metric_terms=effect_metric_terms,
        target_stage_terms=target_stage_terms,
        percent_values=percent_values,
        temperature_values=temperature_values,
    )
    record_payload.update(
        {
            "extraction_source": "drosophila_suzukii_extracted_facts_candidate_biocontrol_fact",
            "confidence": "candidate_literature_evidence",
            "validation_status": "candidate_not_table_validated",
        }
    )
    source_provenance = payload.get("source_provenance") if isinstance(payload.get("source_provenance"), dict) else {}
    return EvidenceRecord(
        record_id=f"swd_biocontrol_candidate:{_normalize_id(str(row['record_id']))}:{digest}",
        lane="biocontrol",
        source=DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID,
        title=f"Drosophila suzukii biocontrol outcome evidence: {', '.join(agent_terms[:2])}",
        text=text,
        species=DROSOPHILA_SUZUKII_SPECIES,
        url=source_url,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID,
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
        "Drosophila suzukii biocontrol outcome source gap. "
        f"Reason: {reason}. "
        f"Extracted biocontrol fact records checked: {extracted_fact_record_count}. "
        f"Parsed biocontrol table rows seen: {parsed_rows_seen}. "
        f"Rows skipped by schema validation: {skipped_record_count}. "
        "This preserves the gap instead of treating generic management literature as validated biocontrol outcome tables."
    )
    return EvidenceRecord(
        record_id=f"swd_biocontrol:gap:{reason}",
        lane="biocontrol",
        source=DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID,
        title="Drosophila suzukii biocontrol outcome source gap",
        text=text,
        species=DROSOPHILA_SUZUKII_SPECIES,
        url=None,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID,
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
          AND r.lane = 'biocontrol'
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
        if payload.get("fact_type") != "biocontrol":
            continue
        fields = payload.get("fields")
        if not isinstance(fields, dict):
            skipped += 1
            continue
        evidence_text = str(payload.get("evidence_text") or "")
        table_row = fields.get("table_row")
        table_row_text = _table_text(table_row) if isinstance(table_row, dict) else ""
        combined_text = "\n".join([str(row["title"]), str(row["text"]), evidence_text, table_row_text])
        agent_terms = list(dict.fromkeys(_field_values(fields, ("agent",)) + _matched_terms(combined_text, AGENT_TERMS)))
        assay_terms = list(dict.fromkeys(_field_values(fields, ("assay",)) + _matched_terms(combined_text, ASSAY_TERMS)))
        effect_metric_terms = list(dict.fromkeys(_field_values(fields, ("effect_metric",)) + _matched_terms(combined_text, EFFECT_METRIC_TERMS)))
        target_stage_terms = list(dict.fromkeys(_field_values(fields, ("target_stage",)) + _matched_terms(combined_text, TARGET_STAGE_TERMS)))
        percent_values = _field_values(fields, ("percent_values",))
        temperature_values = _field_values(fields, ("temperature_values",))
        has_outcome_context = bool(assay_terms or effect_metric_terms or target_stage_terms or percent_values or temperature_values)
        if not agent_terms or not has_outcome_context:
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
                    agent_terms=agent_terms,
                    assay_terms=assay_terms,
                    effect_metric_terms=effect_metric_terms,
                    target_stage_terms=target_stage_terms,
                    percent_values=percent_values,
                    temperature_values=temperature_values,
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
                    agent_terms=agent_terms,
                    assay_terms=assay_terms,
                    effect_metric_terms=effect_metric_terms,
                    target_stage_terms=target_stage_terms,
                    percent_values=percent_values,
                    temperature_values=temperature_values,
                )
            )
        else:
            skipped += 1
    return records, parsed_rows_seen, candidate_count, skipped, len(rows)


def build_drosophila_suzukii_biocontrol_outcome_records(
    artifact_dir: Path,
    *,
    retrieved_at: str | None = None,
) -> DrosophilaSuzukiiBiocontrolOutcomeResult:
    db_path = artifact_dir / "source_index.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"missing source index: {db_path}")
    retrieved = retrieved_at or utc_now()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        records, parsed_rows_seen, candidate_count, skipped, extracted_fact_count = _records_from_extracted_facts(conn, retrieved_at=retrieved)

    gaps: list[dict[str, object]] = []
    if not records:
        reason = "no_swd_biocontrol_evidence_rows_detected"
        gaps.append(
            {
                "source": DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID,
                "lane": "biocontrol",
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
        reason = "no_parsed_swd_biocontrol_table_rows_detected"
        gaps.append(
            {
                "source": DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID,
                "lane": "biocontrol",
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

    return DrosophilaSuzukiiBiocontrolOutcomeResult(
        source_id=DROSOPHILA_SUZUKII_BIOCONTROL_OUTCOME_ROWS_SOURCE_ID,
        records=records,
        gaps=gaps,
        parsed_table_row_count=parsed_rows_seen,
        candidate_fact_count=candidate_count,
        skipped_record_count=skipped,
        extracted_fact_record_count=extracted_fact_count,
    )
