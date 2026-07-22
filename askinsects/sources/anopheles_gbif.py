from __future__ import annotations

from pathlib import Path
from typing import Callable

from .gbif import GBIFBuildResult, fetch_gbif_records
from .anopheles_ncbi_biosamples import ANOPHELES_NCBI_BIOSAMPLES_TARGET_TAXA


ANOPHELES_GBIF_SOURCE_ID = "anopheles_gbif_occurrences"
ANOPHELES_GBIF_RECORD_PREFIX = "anopheles_gbif"
ANOPHELES_GBIF_TARGET_TAXA = ANOPHELES_NCBI_BIOSAMPLES_TARGET_TAXA


def fetch_anopheles_gbif_records(
    *,
    raw_dir: Path,
    species_names: list[str] | tuple[str, ...] = ANOPHELES_GBIF_TARGET_TAXA,
    occurrence_limit: int = 25,
    occurrence_page_size: int = 100,
    occurrence_workers: int = 1,
    delay_seconds: float = 0.0,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
) -> GBIFBuildResult:
    return fetch_gbif_records(
        species_names,
        raw_dir=raw_dir,
        occurrence_limit=occurrence_limit,
        occurrence_page_size=occurrence_page_size,
        occurrence_workers=occurrence_workers,
        delay_seconds=delay_seconds,
        fetch_json=fetch_json,
        retrieved_at=retrieved_at,
        source_id=ANOPHELES_GBIF_SOURCE_ID,
        record_prefix=ANOPHELES_GBIF_RECORD_PREFIX,
    )
