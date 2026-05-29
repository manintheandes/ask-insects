from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.ncbi_snp_variation import fetch_ncbi_snp_variation_records


DROSOPHILA_SUZUKII_NCBI_SNP_VARIATION_SOURCE_ID = "drosophila_suzukii_ncbi_snp_variation"
DROSOPHILA_SUZUKII_SPECIES = "Drosophila suzukii"


@dataclass(frozen=True)
class DrosophilaSuzukiiNcbiSnpVariationResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    species: str
    total_count: int
    requested_limit: int
    fetched_count: int
    page_count: int


def _retarget_gap(gap: dict[str, object]) -> dict[str, object]:
    reason = str(gap.get("reason") or "")
    if reason == "ncbi_snp_no_aedes_records":
        reason = "ncbi_snp_no_swd_records"
    return {
        **gap,
        "source": DROSOPHILA_SUZUKII_NCBI_SNP_VARIATION_SOURCE_ID,
        "species": DROSOPHILA_SUZUKII_SPECIES,
        "reason": reason,
    }


def _retarget_record(record: EvidenceRecord) -> EvidenceRecord:
    payload = dict(record.payload or {})
    if isinstance(payload.get("gap"), dict):
        payload["gap"] = _retarget_gap(dict(payload["gap"]))
    record_id = record.record_id
    title = record.title.replace("Aedes aegypti", DROSOPHILA_SUZUKII_SPECIES)
    text = record.text.replace("Aedes aegypti", DROSOPHILA_SUZUKII_SPECIES)
    if "ncbi_snp_no_aedes_records" in record_id:
        record_id = "swd_ncbi_snp_variation:gap:drosophila_suzukii:ncbi_snp_no_swd_records"
        title = "Drosophila suzukii NCBI dbSNP variation source gap: ncbi_snp_no_swd_records"
        text = (
            "NCBI dbSNP returned zero records for Drosophila suzukii using the bounded organism query. "
            "Ask Insects records this as an explicit variant-source gap instead of implying dbSNP variants are indexed."
        )
    elif record_id.startswith("ncbi_snp_variation:"):
        record_id = record_id.replace("ncbi_snp_variation:", "swd_ncbi_snp_variation:", 1)
    return replace(
        record,
        record_id=record_id,
        source=DROSOPHILA_SUZUKII_NCBI_SNP_VARIATION_SOURCE_ID,
        title=title,
        text=text,
        species=DROSOPHILA_SUZUKII_SPECIES,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_NCBI_SNP_VARIATION_SOURCE_ID,
            locator=record.provenance.locator.replace("ncbi_snp_no_aedes_records", "ncbi_snp_no_swd_records"),
            retrieved_at=record.provenance.retrieved_at,
            license=record.provenance.license,
            source_url=record.provenance.source_url,
        ),
        payload=payload,
    )


def fetch_drosophila_suzukii_ncbi_snp_variation_records(
    *,
    raw_dir: Path,
    limit: int = 1000,
    page_size: int = 200,
    delay_seconds: float = 0.34,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
) -> DrosophilaSuzukiiNcbiSnpVariationResult:
    result = fetch_ncbi_snp_variation_records(
        species=DROSOPHILA_SUZUKII_SPECIES,
        raw_dir=raw_dir,
        limit=limit,
        page_size=page_size,
        delay_seconds=delay_seconds,
        fetch_json=fetch_json,
        retrieved_at=retrieved_at,
    )
    return DrosophilaSuzukiiNcbiSnpVariationResult(
        source_id=DROSOPHILA_SUZUKII_NCBI_SNP_VARIATION_SOURCE_ID,
        records=[_retarget_record(record) for record in result.records],
        gaps=[_retarget_gap(gap) for gap in result.gaps],
        raw_artifacts=result.raw_artifacts,
        species=DROSOPHILA_SUZUKII_SPECIES,
        total_count=result.total_count,
        requested_limit=result.requested_limit,
        fetched_count=result.fetched_count,
        page_count=result.page_count,
    )
