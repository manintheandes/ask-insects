from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable

from askinsects.records import EvidenceRecord

from .uniprot_proteins import fetch_uniprot_protein_records


ANOPHELES_UNIPROT_SOURCE_ID = "anopheles_uniprot_proteins"
ANOPHELES_UNIPROT_RECORD_PREFIX = "anopheles_uniprot"
ANOPHELES_UNIPROT_TARGET_TAXA = (
    ("Anopheles gambiae", 7165),
    ("Anopheles coluzzii", 1518534),
    ("Anopheles funestus", 62324),
    ("Anopheles stephensi", 30069),
    ("Anopheles arabiensis", 7173),
    ("Anopheles dirus", 7168),
    ("Anopheles minimus", 112268),
    ("Anopheles sinensis", 74873),
)


@dataclass(frozen=True)
class AnophelesUniProtResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    target_taxa: tuple[tuple[str, int], ...]
    record_counts: dict[str, int]
    protein_limit_per_taxon: int
    proteome_limit_per_taxon: int


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def fetch_anopheles_uniprot_records(
    *,
    raw_dir: Path,
    target_taxa: list[tuple[str, int]] | tuple[tuple[str, int], ...] = ANOPHELES_UNIPROT_TARGET_TAXA,
    protein_limit_per_taxon: int = 500,
    proteome_limit_per_taxon: int = 10,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str,
) -> AnophelesUniProtResult:
    records_by_id: dict[str, EvidenceRecord] = {}
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []
    record_counts: dict[str, int] = {}
    requested_taxa = tuple((str(species), int(taxonomy_id)) for species, taxonomy_id in target_taxa)

    for species, taxonomy_id in requested_taxa:
        result = fetch_uniprot_protein_records(
            raw_dir=raw_dir,
            fetch_json=fetch_json,
            retrieved_at=retrieved_at,
            protein_limit=protein_limit_per_taxon,
            proteome_limit=proteome_limit_per_taxon,
            taxonomy_id=taxonomy_id,
            species_name=species,
            source_id=ANOPHELES_UNIPROT_SOURCE_ID,
            record_prefix=ANOPHELES_UNIPROT_RECORD_PREFIX,
            raw_prefix=_safe_name(species),
        )
        record_counts[species] = len(result.records)
        raw_artifacts.extend(result.raw_artifacts)
        requested_urls.extend(result.requested_urls)
        gaps.extend(result.gaps)
        protein_count = sum(record.record_id.startswith(f"{ANOPHELES_UNIPROT_RECORD_PREFIX}:protein:") for record in result.records)
        if protein_count >= max(1, protein_limit_per_taxon):
            gaps.append(
                {
                    "source": ANOPHELES_UNIPROT_SOURCE_ID,
                    "lane": "proteins",
                    "reason": "uniprot_protein_limit_reached",
                    "species": species,
                    "taxonomy_id": taxonomy_id,
                    "record_count": protein_count,
                    "limit": protein_limit_per_taxon,
                    "retrieved_at": retrieved_at,
                }
            )
        for record in result.records:
            records_by_id[record.record_id] = record

    return AnophelesUniProtResult(
        source_id=ANOPHELES_UNIPROT_SOURCE_ID,
        records=list(records_by_id.values()),
        gaps=gaps,
        raw_artifacts=list(dict.fromkeys(raw_artifacts)),
        requested_urls=requested_urls,
        target_taxa=requested_taxa,
        record_counts=record_counts,
        protein_limit_per_taxon=max(1, int(protein_limit_per_taxon)),
        proteome_limit_per_taxon=max(1, int(proteome_limit_per_taxon)),
    )
