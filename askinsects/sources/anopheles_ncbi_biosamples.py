from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from askinsects.records import EvidenceRecord

from .ncbi_biosample import NCBIBioSampleResult, fetch_ncbi_biosample_records


ANOPHELES_NCBI_BIOSAMPLES_SOURCE_ID = "anopheles_ncbi_biosamples"
ANOPHELES_NCBI_BIOSAMPLES_RECORD_PREFIX = "anopheles_ncbi"
ANOPHELES_NCBI_BIOSAMPLES_TARGET_TAXA = (
    "Anopheles gambiae",
    "Anopheles coluzzii",
    "Anopheles funestus",
    "Anopheles stephensi",
    "Anopheles arabiensis",
    "Anopheles dirus",
    "Anopheles minimus",
    "Anopheles sinensis",
    "Anopheles albimanus",
    "Anopheles darlingi",
    "Anopheles culicifacies",
    "Anopheles aquasalis",
    "Anopheles melas",
    "Anopheles merus",
    "Anopheles nili",
    "Anopheles moucheti",
    "Anopheles atroparvus",
    "Anopheles labranchiae",
    "Anopheles sacharovi",
    "Anopheles freeborni",
)


@dataclass(frozen=True)
class AnophelesNCBIBioSampleResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    target_taxa: tuple[str, ...]
    total_counts: dict[str, int]
    fetched_counts: dict[str, int]
    page_counts: dict[str, int]
    requested_limit_per_taxon: int


def _retag_record(record: EvidenceRecord, *, target_taxon: str) -> EvidenceRecord:
    accession = str(record.payload.get("accession") or record.record_id.rsplit(":", 1)[-1])
    payload = dict(record.payload)
    payload.update(
        {
            "anopheles_target_taxon": target_taxon,
            "upstream_source_id": record.source,
            "upstream_record_id": record.record_id,
        }
    )
    return replace(
        record,
        record_id=f"{ANOPHELES_NCBI_BIOSAMPLES_RECORD_PREFIX}:biosample:{accession}",
        source=ANOPHELES_NCBI_BIOSAMPLES_SOURCE_ID,
        provenance=replace(record.provenance, source_id=ANOPHELES_NCBI_BIOSAMPLES_SOURCE_ID),
        payload=payload,
    )


def _retag_gap(gap: dict[str, object], *, target_taxon: str) -> dict[str, object]:
    return {
        **gap,
        "source": ANOPHELES_NCBI_BIOSAMPLES_SOURCE_ID,
        "target_taxon": target_taxon,
        "upstream_source_id": gap.get("source"),
    }


def fetch_anopheles_ncbi_biosample_records(
    *,
    raw_dir: Path,
    target_taxa: list[str] | tuple[str, ...] = ANOPHELES_NCBI_BIOSAMPLES_TARGET_TAXA,
    limit_per_taxon: int = 250,
    page_size: int = 200,
    delay_seconds: float = 0.34,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
) -> AnophelesNCBIBioSampleResult:
    records_by_id: dict[str, EvidenceRecord] = {}
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    total_counts: dict[str, int] = {}
    fetched_counts: dict[str, int] = {}
    page_counts: dict[str, int] = {}
    requested_taxa = tuple(dict.fromkeys(str(taxon).strip() for taxon in target_taxa if str(taxon).strip()))

    for target_taxon in requested_taxa:
        result: NCBIBioSampleResult = fetch_ncbi_biosample_records(
            species=target_taxon,
            raw_dir=raw_dir,
            limit=limit_per_taxon,
            page_size=page_size,
            delay_seconds=delay_seconds,
            fetch_json=fetch_json,
            retrieved_at=retrieved_at,
        )
        total_counts[target_taxon] = result.total_count
        fetched_counts[target_taxon] = result.fetched_count
        page_counts[target_taxon] = result.page_count
        raw_artifacts.extend(result.raw_artifacts)
        gaps.extend(_retag_gap(gap, target_taxon=target_taxon) for gap in result.gaps)
        for record in result.records:
            retagged = _retag_record(record, target_taxon=target_taxon)
            records_by_id[retagged.record_id] = retagged

    return AnophelesNCBIBioSampleResult(
        source_id=ANOPHELES_NCBI_BIOSAMPLES_SOURCE_ID,
        records=list(records_by_id.values()),
        gaps=gaps,
        raw_artifacts=list(dict.fromkeys(raw_artifacts)),
        target_taxa=requested_taxa,
        total_counts=total_counts,
        fetched_counts=fetched_counts,
        page_counts=page_counts,
        requested_limit_per_taxon=max(0, limit_per_taxon),
    )
