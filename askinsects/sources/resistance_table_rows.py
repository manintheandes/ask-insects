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
from askinsects.sources.resistance_markers import INSECTICIDE_TERMS, MARKER_SPECS


RESISTANCE_TABLE_ROW_SOURCE_ID = "aedes_resistance_table_rows"

METRIC_FIELDS = ("mortality", "knockdown", "lc_value", "genotype_frequency")
ASSAY_TERMS = (
    "bioassay",
    "WHO tube",
    "CDC bottle",
    "exposure",
    "mortality",
    "knockdown",
    "LC50",
    "LC90",
    "allele frequency",
    "genotype frequency",
    "haplotype",
)


@dataclass(frozen=True)
class ResistanceTableRowResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    parsed_table_row_count: int
    skipped_table_row_count: int
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


def _table_text(table_row: dict[str, object]) -> str:
    return ". ".join(f"{key}: {value}" for key, value in table_row.items())


def _field_values(fields: dict[str, object], keys: Iterable[str]) -> list[str]:
    values: list[str] = []
    for key in keys:
        values.extend(_as_list(fields.get(key)))
    return list(dict.fromkeys(values))


def _marker_terms(fields: dict[str, object], combined_text: str) -> list[str]:
    field_terms = _field_values(fields, ("mutation", "genotype_frequency", "knockdown"))
    matches: list[str] = []
    for value in field_terms:
        if re.search(r"\b[A-Z][0-9]{2,4}[A-Z]\b", value):
            matches.append(value)
    for spec in MARKER_SPECS:
        for alias in spec.aliases:
            if _pattern_for_term(alias).search(combined_text):
                matches.append(spec.marker_id if spec.specific else alias)
    return list(dict.fromkeys(matches))


def _metric_fields(fields: dict[str, object], combined_text: str) -> list[str]:
    metrics = [field for field in METRIC_FIELDS if _as_list(fields.get(field))]
    lower = combined_text.lower()
    if "mortality" in lower or re.search(r"\bmortality\s*%|\b\d+(?:\.\d+)?\s*%", lower):
        metrics.append("mortality")
    if "knockdown" in lower:
        metrics.append("knockdown")
    if "lc50" in lower or "lc90" in lower:
        metrics.append("lc_value")
    if "allele frequency" in lower or "genotype frequency" in lower or "haplotype" in lower:
        metrics.append("genotype_frequency")
    ordered = [field for field in METRIC_FIELDS if field in set(metrics)]
    return sorted(ordered)


def _records_from_parsed_rows(conn: sqlite3.Connection, *, retrieved_at: str) -> tuple[list[EvidenceRecord], int, int, int]:
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
          AND r.lane = 'resistance'
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
        if payload.get("fact_type") != "resistance" or payload.get("confidence") != "parsed":
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
        insecticide_terms = list(dict.fromkeys(_field_values(fields, ("insecticide",)) + _matched_terms(combined_text, INSECTICIDE_TERMS)))
        marker_terms = _marker_terms(fields, combined_text)
        assay_terms = list(dict.fromkeys(_field_values(fields, ("assay",)) + _matched_terms(combined_text, ASSAY_TERMS)))
        metric_fields = _metric_fields(fields, combined_text)
        if not metric_fields or not (insecticide_terms or marker_terms or assay_terms):
            skipped_rows += 1
            continue
        source_record_id = str(payload.get("source_record_id") or "")
        source_provenance = payload.get("source_provenance") if isinstance(payload.get("source_provenance"), dict) else {}
        extracted_provenance = json.loads(str(row["provenance_json"]))
        source_url = row["url"] or extracted_provenance.get("source_url") or source_provenance.get("source_url")
        locator_parts = [f"aedes_extracted_facts#{row['record_id']}"]
        if source_record_id:
            locator_parts.append(f"records#{source_record_id}")
        locator = extracted_provenance.get("locator")
        if locator:
            locator_parts.append(str(locator))
        table_headers = fields.get("table_headers") if isinstance(fields.get("table_headers"), list) else list(table_row)
        table_row_index = fields.get("table_row_index")
        digest = hashlib.sha1(f"{row['record_id']}|{json.dumps(table_row, sort_keys=True)}".encode("utf-8")).hexdigest()[:12]
        title_terms = " ".join(insecticide_terms[:2] + marker_terms[:2]).strip() or "resistance assay"
        title = f"Aedes aegypti parsed resistance table row: {title_terms}"
        text = (
            "Schema-validated parsed supplement table row for Aedes aegypti insecticide resistance. "
            "Validation status: schema_validated, not human_validated. "
            f"Insecticide terms: {', '.join(insecticide_terms) if insecticide_terms else 'not detected'}. "
            f"Marker terms: {', '.join(marker_terms) if marker_terms else 'not detected'}. "
            f"Assay terms: {', '.join(assay_terms) if assay_terms else 'not detected'}. "
            f"Metric fields: {', '.join(metric_fields)}. "
            f"Table row: {table_row_text}"
        )
        records.append(
            EvidenceRecord(
                record_id=f"resistance_table:{_normalize_id(str(row['record_id']))}:{digest}",
                lane="resistance",
                source=RESISTANCE_TABLE_ROW_SOURCE_ID,
                title=title,
                text=text,
                species=row["species"] or "Aedes aegypti",
                url=source_url,
                media_url=None,
                provenance=Provenance(
                    source_id=RESISTANCE_TABLE_ROW_SOURCE_ID,
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
                    "insecticide_terms": insecticide_terms,
                    "marker_terms": marker_terms,
                    "assay_terms": assay_terms,
                    "metric_fields": metric_fields,
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
    return records, parsed_rows_seen, skipped_rows, len(rows)


def _gap_record(
    *,
    reason: str,
    retrieved_at: str,
    extracted_fact_record_count: int,
    parsed_rows_seen: int,
    skipped_rows: int,
) -> EvidenceRecord:
    text = (
        "Aedes aegypti resistance table-row source gap. "
        f"Reason: {reason}. "
        f"Extracted resistance fact records checked: {extracted_fact_record_count}. "
        f"Parsed resistance table rows seen: {parsed_rows_seen}. "
        f"Rows skipped by schema validation: {skipped_rows}. "
        "No schema-validated insecticide-resistance table rows are currently queryable from this lane. "
        "Relevant future row types include V1016G frequency, F1534C frequency, genotype frequency, haplotype, mortality, knockdown, LC50, and LC90."
    )
    return EvidenceRecord(
        record_id=f"resistance_table:gap:{reason}",
        lane="resistance",
        source=RESISTANCE_TABLE_ROW_SOURCE_ID,
        title="Aedes aegypti resistance table-row source gap",
        text=text,
        species="Aedes aegypti",
        url=None,
        media_url=None,
        provenance=Provenance(
            source_id=RESISTANCE_TABLE_ROW_SOURCE_ID,
            locator=f"gaps.json#{reason}",
            retrieved_at=retrieved_at,
            license="derived source-gap metadata",
        ),
        payload={
            "atom_type": "source_gap",
            "reason": reason,
            "extracted_fact_record_count": extracted_fact_record_count,
            "parsed_table_rows_seen": parsed_rows_seen,
            "skipped_table_row_count": skipped_rows,
            "confidence": "source_gap",
            "validation_status": "no_promotable_rows",
            "human_validated": False,
        },
    )


def build_resistance_table_row_records(artifact_dir: Path, *, retrieved_at: str | None = None) -> ResistanceTableRowResult:
    db_path = artifact_dir / "source_index.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"missing source index: {db_path}")
    retrieved = retrieved_at or utc_now()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        records, parsed_rows_seen, skipped_rows, extracted_fact_count = _records_from_parsed_rows(conn, retrieved_at=retrieved)

    gaps: list[dict[str, object]] = []
    promoted_record_count = len(records)
    if not records:
        reason = "no_resistance_table_rows_detected"
        gaps.append(
            {
                "source": RESISTANCE_TABLE_ROW_SOURCE_ID,
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
                skipped_rows=skipped_rows,
            )
        )
    elif skipped_rows:
        gaps.append(
            {
                "source": RESISTANCE_TABLE_ROW_SOURCE_ID,
                "lane": "resistance",
                "reason": "parsed_resistance_table_rows_skipped_schema_validation",
                "parsed_table_rows_seen": parsed_rows_seen,
                "skipped_table_row_count": skipped_rows,
                "retrieved_at": retrieved,
            }
        )

    return ResistanceTableRowResult(
        source_id=RESISTANCE_TABLE_ROW_SOURCE_ID,
        records=records,
        gaps=gaps,
        parsed_table_row_count=promoted_record_count,
        skipped_table_row_count=skipped_rows,
        extracted_fact_record_count=extracted_fact_count,
    )
