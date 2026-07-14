from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
import re
from pathlib import Path
from typing import Callable

from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.bold_barcodes import fetch_bold_barcode_records
from askinsects.sources.gbif import fetch_gbif_records
from askinsects.sources.inaturalist import fetch_inaturalist_records
from askinsects.sources.literature import fetch_literature_records


DROSOPHILA_SUZUKII_SOURCE_ID = "drosophila_suzukii_core"
DROSOPHILA_SUZUKII_SPECIES = "Drosophila suzukii"
DROSOPHILA_SUZUKII_COMMON_NAME = "spotted wing drosophila"
DROSOPHILA_SUZUKII_EXACT_LITERATURE_SEARCH_TERMS = [
    DROSOPHILA_SUZUKII_SPECIES,
    DROSOPHILA_SUZUKII_COMMON_NAME,
    "spotted-wing drosophila",
]
DROSOPHILA_SUZUKII_PRODUCT_TOPIC_SEARCH_TERMS = [
    {"term": "Drosophila suzukii repellent", "mode": "search", "topic_group": "repellency", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii repellency", "mode": "search", "topic_group": "repellency", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii oviposition deterrent", "mode": "search", "topic_group": "repellency", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii essential oil", "mode": "search", "topic_group": "repellency", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii insecticide", "mode": "search", "topic_group": "susceptibility_resistance", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii resistance", "mode": "search", "topic_group": "susceptibility_resistance", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii spinosad", "mode": "search", "topic_group": "susceptibility_resistance", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii pyrethroid", "mode": "search", "topic_group": "susceptibility_resistance", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii phytotoxicity", "mode": "search", "topic_group": "assay_safety", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii fumigation", "mode": "search", "topic_group": "assay_safety", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii biocontrol", "mode": "search", "topic_group": "biocontrol", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii parasitoid", "mode": "search", "topic_group": "biocontrol", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii entomopathogenic fungus", "mode": "search", "topic_group": "biocontrol", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii oviposition", "mode": "search", "topic_group": "behavior", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii behavior", "mode": "search", "topic_group": "behavior", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii olfaction", "mode": "search", "topic_group": "behavior", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii volatile", "mode": "search", "topic_group": "behavior", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii odor", "mode": "search", "topic_group": "behavior", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii genomics", "mode": "search", "topic_group": "omics", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii transcriptome", "mode": "search", "topic_group": "omics", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii proteomics", "mode": "search", "topic_group": "omics", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii microbiome", "mode": "search", "topic_group": "omics", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii chemoreceptor", "mode": "search", "topic_group": "omics", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii monitoring", "mode": "search", "topic_group": "monitoring_ipm", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii trap", "mode": "search", "topic_group": "monitoring_ipm", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii lure", "mode": "search", "topic_group": "monitoring_ipm", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii IPM", "mode": "search", "topic_group": "monitoring_ipm", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii management", "mode": "search", "topic_group": "monitoring_ipm", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii blueberry", "mode": "search", "topic_group": "crop_context", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii cherry", "mode": "search", "topic_group": "crop_context", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii raspberry", "mode": "search", "topic_group": "crop_context", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii strawberry", "mode": "search", "topic_group": "crop_context", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii grape", "mode": "search", "topic_group": "crop_context", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii climate", "mode": "search", "topic_group": "ecology_distribution", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii ecology", "mode": "search", "topic_group": "ecology_distribution", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii phenology", "mode": "search", "topic_group": "ecology_distribution", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii landscape", "mode": "search", "topic_group": "ecology_distribution", "confidence": "openalex_search_candidate"},
    {"term": "Drosophila suzukii", "mode": "search", "topic_group": "broad_swd_search", "confidence": "openalex_search_candidate"},
    {"term": "spotted wing drosophila", "mode": "search", "topic_group": "broad_swd_search", "confidence": "openalex_search_candidate"},
]
DROSOPHILA_SUZUKII_LITERATURE_SEARCH_TERMS: list[object] = [
    *DROSOPHILA_SUZUKII_EXACT_LITERATURE_SEARCH_TERMS,
    *DROSOPHILA_SUZUKII_PRODUCT_TOPIC_SEARCH_TERMS,
]


@dataclass(frozen=True)
class DrosophilaSuzukiiBuildResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    upstream_sources: dict[str, dict[str, object]]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "unknown"


def _search_term_name(term: object) -> str:
    if isinstance(term, dict):
        return str(term.get("term") or "")
    return str(term)


def _search_term_mode(term: object) -> str:
    if isinstance(term, dict):
        return str(term.get("mode") or "title_and_abstract")
    return "title_and_abstract"


def _search_term_topic_group(term: object) -> str | None:
    if isinstance(term, dict) and term.get("topic_group"):
        return str(term["topic_group"])
    return None


def _literature_search_term_names() -> list[str]:
    return [_search_term_name(term) for term in DROSOPHILA_SUZUKII_LITERATURE_SEARCH_TERMS if _search_term_name(term)]


def _literature_search_modes() -> list[str]:
    modes: list[str] = []
    for term in DROSOPHILA_SUZUKII_LITERATURE_SEARCH_TERMS:
        mode = _search_term_mode(term)
        if mode not in modes:
            modes.append(mode)
    return modes


def _literature_topic_groups() -> list[str]:
    groups: list[str] = []
    for term in DROSOPHILA_SUZUKII_LITERATURE_SEARCH_TERMS:
        group = _search_term_topic_group(term)
        if group and group not in groups:
            groups.append(group)
    return groups


def _retarget_record(record: EvidenceRecord, *, upstream_source: str) -> EvidenceRecord:
    payload = dict(record.payload or {})
    payload["upstream_source"] = upstream_source
    payload["upstream_record_id"] = record.record_id
    payload["primary_taxon"] = DROSOPHILA_SUZUKII_SPECIES
    payload["common_name"] = DROSOPHILA_SUZUKII_COMMON_NAME
    alias_text = f" Common name: {DROSOPHILA_SUZUKII_COMMON_NAME}."
    text = record.text if DROSOPHILA_SUZUKII_COMMON_NAME in record.text.lower() else record.text + alias_text
    return replace(
        record,
        record_id=f"swd:{_safe_id(upstream_source)}:{record.record_id}",
        source=DROSOPHILA_SUZUKII_SOURCE_ID,
        text=text,
        species=DROSOPHILA_SUZUKII_SPECIES,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_SOURCE_ID,
            locator=f"{record.provenance.locator};upstream_source={upstream_source};upstream_record_id={record.record_id}",
            retrieved_at=record.provenance.retrieved_at,
            license=record.provenance.license,
            source_url=record.provenance.source_url,
        ),
        payload=payload,
    )


def _retarget_gap(gap: dict[str, object], *, upstream_source: str, retrieved_at: str) -> dict[str, object]:
    return {
        **gap,
        "source": DROSOPHILA_SUZUKII_SOURCE_ID,
        "species": DROSOPHILA_SUZUKII_SPECIES,
        "common_name": DROSOPHILA_SUZUKII_COMMON_NAME,
        "upstream_source": upstream_source,
        "upstream_gap_source": gap.get("source"),
        "retrieved_at": gap.get("retrieved_at") or retrieved_at,
    }


def _coverage_record(
    *,
    domain: str,
    status: str,
    current_sources: list[str],
    missing_sources: list[str],
    retrieved_at: str,
    index: int,
) -> EvidenceRecord:
    record_id = f"swd:coverage:{_safe_id(domain)}"
    current = "; ".join(current_sources) if current_sources else "none yet"
    missing = "; ".join(missing_sources) if missing_sources else "none recorded"
    return EvidenceRecord(
        record_id=record_id,
        lane="source_coverage",
        source=DROSOPHILA_SUZUKII_SOURCE_ID,
        title=f"Spotted wing drosophila coverage: {domain}",
        text=(
            f"Source coverage for {DROSOPHILA_SUZUKII_SPECIES} ({DROSOPHILA_SUZUKII_COMMON_NAME}), domain {domain}. "
            f"Status: {status}. Current source rows: {current}. Missing or next source work: {missing}."
        ),
        species=DROSOPHILA_SUZUKII_SPECIES,
        url=None,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_SOURCE_ID,
            locator=f"repo:drosophila_suzukii_core#coverage/{index}",
            retrieved_at=retrieved_at,
            license="Repository source coverage record",
        ),
        payload={
            "atom_type": "source_coverage_domain",
            "domain": domain,
            "status": status,
            "current_sources": current_sources,
            "missing_sources": missing_sources,
            "primary_taxon": DROSOPHILA_SUZUKII_SPECIES,
            "common_name": DROSOPHILA_SUZUKII_COMMON_NAME,
        },
    )


def _coverage_records(upstream_sources: dict[str, dict[str, object]], *, retrieved_at: str) -> list[EvidenceRecord]:
    records = [
        EvidenceRecord(
            record_id="swd:coverage:overview",
            lane="source_coverage",
            source=DROSOPHILA_SUZUKII_SOURCE_ID,
            title="Spotted wing drosophila source-plane overview",
            text=(
                f"Ask Insects boundary for {DROSOPHILA_SUZUKII_SPECIES} ({DROSOPHILA_SUZUKII_COMMON_NAME}). "
                "This first source-grade pass maps taxonomy, public observations, licensed still images, literature metadata, "
                "DNA barcodes, and per-domain coverage status. Follow-on lanes now promote genome files, supplement audits, "
                "PubMed literature reconciliation, GenBank nucleotide cross-checks, dbSNP variation audits, Figshare MK selection rows, "
                "GenBank mitochondrial/nuclear marker reviews, extension/IPM guidance, literature-derived crop damage, "
                "management, resistance, candidate biocontrol outcome rows, behavior, ecology, and the first inspectable video atoms."
            ),
            species=DROSOPHILA_SUZUKII_SPECIES,
            url=None,
            media_url=None,
            provenance=Provenance(
                source_id=DROSOPHILA_SUZUKII_SOURCE_ID,
                locator="repo:drosophila_suzukii_core#coverage/overview",
                retrieved_at=retrieved_at,
                license="Repository source coverage record",
            ),
            payload={
                "atom_type": "source_coverage_overview",
                "primary_taxon": DROSOPHILA_SUZUKII_SPECIES,
                "common_name": DROSOPHILA_SUZUKII_COMMON_NAME,
                "upstream_sources": upstream_sources,
            },
        )
    ]
    specs = [
        (
            "taxonomy",
            "mapped_queryable",
            ["GBIF species match"],
            [],
        ),
        (
            "observations_and_images",
            "mapped_queryable",
            [
                "GBIF occurrence records",
                "iNaturalist licensed photo observations",
                "Ohio State crop scout trap-report rows",
                "Dryad southeast U.S. blueberry landscape monitoring rows",
            ],
            ["additional regional monitoring networks beyond Ohio and southeast U.S. blueberry Dryad", "additional crop scout trap datasets"],
        ),
        (
            "literature",
            "mapped_queryable_bounded",
            [
                "multi-term OpenAlex title/abstract metadata since 2020",
                "legal direct full-text units",
                "per-paper supplement audits and parsed public supplement rows",
                "PubMed reconciliation metadata",
            ],
            ["human-reviewed literature claim extraction", "Crossref/Europe PMC/Semantic Scholar breadth audit beyond OpenAlex and PubMed"],
        ),
        (
            "dna_barcodes",
            "mapped_queryable_bounded",
            [
                "BOLD public combined TSV",
                "NCBI GenBank/nuccore COI and barcode metadata cross-check",
                "NCBI GenBank/nuccore mitochondrial and nuclear marker review",
            ],
            ["human-reviewed sequence equivalence validation"],
        ),
        (
            "behavior_video",
            "partial_source_grade",
            ["repository candidates", "supplement manifests and behavior rows", "first verified video atoms"],
            ["broader repository sweeps", "queryable motion tables and track rows beyond current explicit gaps"],
        ),
        (
            "genomics",
            "mapped_queryable_deep",
            [
                "NCBI assembly, BioProject, BioSample, and SRA metadata",
                "UniProt/proteome metadata",
                "parsed NCBI GFF and protein FASTA rows",
                "NCBI Gene ortholog pairs and GeneID-to-GFF mapping",
                "Ensembl Metazoa release 62 current gene IDs, GeneID xrefs, and Dmel homolog rows",
                "GEO differential-expression matrix rows for cold acclimation and insecticide-response studies",
                "NCBI dbSNP organism-query audit",
                "Figshare McDonald-Kreitman selection table rows",
                "Dryad population-variant VCF manifest, checksum, byte size, and explicit non-mirrored row gaps",
            ],
            [
                "Ensembl Metazoa stable-ID history tables are present but empty",
                "Dryad VCF row mirroring/parsing and broader non-dbSNP variant tables",
                "broader publisher-hosted expression matrices and raw count matrices",
            ],
        ),
        (
            "traits_ecology_crop_damage",
            "partial_source_grade",
            [
                "GBIF/iNaturalist occurrence context",
                "literature-derived crop damage and ecology candidate rows",
                "parsed supplement rows when available",
                "JKI DrosoMon trap-deployment capture rows",
                "JKI DrosoMon trap-coordinate and habitat rows",
                "PLOS global climate-suitability model supplement manifests and table rows",
                "Ohio State weekly crop scout trap-report rows",
                "Dryad southeast U.S. blueberry SWD trap-count and landscape-metric rows",
            ],
            ["raw climate suitability raster grids", "additional regional/crop scout phenology feeds beyond Ohio and southeast U.S. blueberry Dryad", "human-validated crop damage tables"],
        ),
        (
            "management_resistance_biocontrol",
            "partial_source_grade",
            [
                "extension/IPM guidance pages",
                "literature-derived management, resistance, and biocontrol candidate rows",
                "dedicated susceptibility/resistance evidence rows from extracted facts",
                "dedicated candidate biocontrol outcome rows from extracted facts",
                "supplement manifests and parsed rows when available",
            ],
            ["broader parsed susceptibility and biocontrol table coverage", "human-validated biocontrol outcome review"],
        ),
    ]
    for index, (domain, status, current_sources, missing_sources) in enumerate(specs, start=1):
        records.append(
            _coverage_record(
                domain=domain,
                status=status,
                current_sources=current_sources,
                missing_sources=missing_sources,
                retrieved_at=retrieved_at,
                index=index,
            )
        )
    return records


def _fetch_or_gap(
    source_name: str,
    gaps: list[dict[str, object]],
    retrieved_at: str,
    func,
):
    try:
        return func()
    except Exception as exc:
        gaps.append(
            {
                "source": DROSOPHILA_SUZUKII_SOURCE_ID,
                "lane": "source_coverage",
                "species": DROSOPHILA_SUZUKII_SPECIES,
                "common_name": DROSOPHILA_SUZUKII_COMMON_NAME,
                "upstream_source": source_name,
                "reason": f"{source_name}_fetch_failed",
                "error": str(exc),
                "retrieved_at": retrieved_at,
            }
        )
        return None


def fetch_drosophila_suzukii_records(
    *,
    raw_dir: Path,
    retrieved_at: str | None = None,
    gbif_occurrence_limit: int = 100,
    gbif_occurrence_page_size: int = 100,
    inaturalist_observation_limit: int = 100,
    inaturalist_page_size: int = 100,
    literature_from_date: str = "2020-01-01",
    literature_to_date: str | None = None,
    literature_max_works: int = 100,
    bold_limit: int = 100,
    include_literature: bool = True,
    include_bold: bool = True,
    gbif_fetch_json: Callable[[str], dict[str, object]] | None = None,
    inaturalist_fetch_json: Callable[[str], dict[str, object]] | None = None,
    literature_fetch_json: Callable[[str], dict[str, object]] | None = None,
    bold_fetch_text: Callable[[str], str] | None = None,
) -> DrosophilaSuzukiiBuildResult:
    retrieved = retrieved_at or utc_now()
    literature_to = literature_to_date or retrieved.split("T", 1)[0]
    raw_dir.mkdir(parents=True, exist_ok=True)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    upstream_sources: dict[str, dict[str, object]] = {}

    gbif_result = _fetch_or_gap(
        "gbif",
        gaps,
        retrieved,
        lambda: fetch_gbif_records(
            [DROSOPHILA_SUZUKII_SPECIES],
            raw_dir=raw_dir / "gbif",
            occurrence_limit=gbif_occurrence_limit,
            occurrence_page_size=gbif_occurrence_page_size,
            occurrence_workers=1,
            fetch_json=gbif_fetch_json,
            retrieved_at=retrieved,
        ),
    )
    if gbif_result is not None:
        records.extend(_retarget_record(record, upstream_source="gbif") for record in gbif_result.records)
        gaps.extend(_retarget_gap(gap, upstream_source="gbif", retrieved_at=retrieved) for gap in gbif_result.gaps)
        raw_artifacts.extend(gbif_result.raw_artifacts)
        upstream_sources["gbif"] = {
            "record_count": len(gbif_result.records),
            "gap_count": len(gbif_result.gaps),
            "requested_species": gbif_result.requested_species,
            "total_results": gbif_result.total_results,
            "taxon_keys": gbif_result.taxon_keys,
        }

    inat_result = _fetch_or_gap(
        "inaturalist",
        gaps,
        retrieved,
        lambda: fetch_inaturalist_records(
            [DROSOPHILA_SUZUKII_SPECIES],
            raw_dir=raw_dir / "inaturalist",
            observation_limit=inaturalist_observation_limit,
            page_size=inaturalist_page_size,
            fetch_json=inaturalist_fetch_json,
            retrieved_at=retrieved,
        ),
    )
    if inat_result is not None:
        records.extend(_retarget_record(record, upstream_source="inaturalist") for record in inat_result.records)
        gaps.extend(_retarget_gap(gap, upstream_source="inaturalist", retrieved_at=retrieved) for gap in inat_result.gaps)
        raw_artifacts.extend(inat_result.raw_artifacts)
        upstream_sources["inaturalist"] = {
            "record_count": len(inat_result.records),
            "gap_count": len(inat_result.gaps),
            "requested_species": inat_result.requested_species,
            "total_results": inat_result.total_results,
        }

    if include_literature:
        literature_result = _fetch_or_gap(
            "openalex_literature",
            gaps,
            retrieved,
            lambda: fetch_literature_records(
                species=DROSOPHILA_SUZUKII_SPECIES,
                from_date=literature_from_date,
                to_date=literature_to,
                work_type="article",
                include_topic_discovery=True,
                raw_dir=raw_dir / "literature",
                page_size=min(max(literature_max_works, 1), 200),
                delay_seconds=0.0,
                fetch_json=literature_fetch_json,
                fetch_text=None,
                unpaywall_email=None,
                retrieved_at=retrieved,
                max_works=literature_max_works,
                skip_pubmed=True,
                search_terms=DROSOPHILA_SUZUKII_LITERATURE_SEARCH_TERMS,
            ),
        )
        if literature_result is not None:
            records.extend(_retarget_record(record, upstream_source="openalex_literature") for record in literature_result.records)
            gaps.extend(_retarget_gap(gap, upstream_source="openalex_literature", retrieved_at=retrieved) for gap in literature_result.gaps)
            raw_artifacts.extend(literature_result.raw_artifacts)
            upstream_sources["openalex_literature"] = {
                "record_count": len(literature_result.records),
                "gap_count": len(literature_result.gaps),
                "reported_total_count": literature_result.reported_total_count,
                "from_date": literature_from_date,
                "to_date": literature_to,
                "search_terms": _literature_search_term_names(),
                "search_modes": _literature_search_modes(),
                "topic_groups": _literature_topic_groups(),
                "inclusion_path_counts": literature_result.inclusion_path_counts,
            }

    if include_bold:
        bold_result = _fetch_or_gap(
            "bold",
            gaps,
            retrieved,
            lambda: fetch_bold_barcode_records(
                species=DROSOPHILA_SUZUKII_SPECIES,
                raw_dir=raw_dir / "bold",
                limit=bold_limit,
                fetch_text=bold_fetch_text,
                retrieved_at=retrieved,
            ),
        )
        if bold_result is not None:
            records.extend(_retarget_record(record, upstream_source="bold") for record in bold_result.records)
            gaps.extend(_retarget_gap(gap, upstream_source="bold", retrieved_at=retrieved) for gap in bold_result.gaps)
            raw_artifacts.extend(bold_result.raw_artifacts)
            upstream_sources["bold"] = {
                "record_count": len(bold_result.records),
                "gap_count": len(bold_result.gaps),
                "requested_limit": bold_result.requested_limit,
                "fetched_row_count": bold_result.fetched_row_count,
            }

    records.extend(_coverage_records(upstream_sources, retrieved_at=retrieved))
    return DrosophilaSuzukiiBuildResult(
        source_id=DROSOPHILA_SUZUKII_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        upstream_sources=upstream_sources,
    )
