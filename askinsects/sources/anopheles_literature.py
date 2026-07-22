from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path

from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.anopheles_ncbi_biosamples import ANOPHELES_NCBI_BIOSAMPLES_TARGET_TAXA
from askinsects.sources.literature import LiteratureBuildResult, LiteratureSearchQuery, fetch_literature_records


ANOPHELES_LITERATURE_SOURCE_ID = "anopheles_literature_openalex"
ANOPHELES_TARGET_TAXA = ("Anopheles gambiae complex", *ANOPHELES_NCBI_BIOSAMPLES_TARGET_TAXA)
ANOPHELES_LITERATURE_SEARCH_TERMS = [
    *(LiteratureSearchQuery(term=species, topic_group="target_taxon") for species in ANOPHELES_TARGET_TAXA),
    LiteratureSearchQuery(term="Anopheles repellent", mode="search", topic_group="repellents", confidence="openalex_search_candidate"),
    LiteratureSearchQuery(term="Anopheles spatial repellent", mode="search", topic_group="repellents", confidence="openalex_search_candidate"),
    LiteratureSearchQuery(term="Anopheles host seeking", mode="search", topic_group="behavior", confidence="openalex_search_candidate"),
    LiteratureSearchQuery(term="Anopheles blood feeding", mode="search", topic_group="behavior", confidence="openalex_search_candidate"),
    LiteratureSearchQuery(term="Anopheles oviposition", mode="search", topic_group="behavior", confidence="openalex_search_candidate"),
    LiteratureSearchQuery(term="Anopheles larval ecology", mode="search", topic_group="ecology", confidence="openalex_search_candidate"),
    LiteratureSearchQuery(term="Anopheles olfaction", mode="search", topic_group="sensory_olfaction", confidence="openalex_search_candidate"),
    LiteratureSearchQuery(term="Anopheles neurobiology", mode="search", topic_group="neurobiology", confidence="openalex_search_candidate"),
    LiteratureSearchQuery(term="Anopheles microbiome symbiont", mode="search", topic_group="microbiome_symbionts_pathogens", confidence="openalex_search_candidate"),
    LiteratureSearchQuery(term="Anopheles population genomics", mode="search", topic_group="expression_population_genomics", confidence="openalex_search_candidate"),
    LiteratureSearchQuery(term="Anopheles insecticide resistance", mode="search", topic_group="resistance", confidence="openalex_search_candidate"),
    LiteratureSearchQuery(term="Anopheles vector competence", mode="search", topic_group="vector_competence", confidence="openalex_search_candidate"),
    LiteratureSearchQuery(term="Anopheles Plasmodium transmission", mode="search", topic_group="vector_competence", confidence="openalex_search_candidate"),
]


def _retarget_record(record: EvidenceRecord) -> EvidenceRecord:
    original_record_id = record.record_id
    record_id = f"anopheles_openalex:{original_record_id.split(':', 1)[-1]}"
    payload = dict(record.payload or {})
    payload["original_record_id"] = original_record_id
    payload["target_taxa"] = ANOPHELES_TARGET_TAXA
    return replace(
        record,
        record_id=record_id,
        source=ANOPHELES_LITERATURE_SOURCE_ID,
        species="Anopheles",
        provenance=Provenance(
            source_id=ANOPHELES_LITERATURE_SOURCE_ID,
            locator=record.provenance.locator,
            retrieved_at=record.provenance.retrieved_at,
            license=record.provenance.license,
            source_url=record.provenance.source_url,
        ),
        payload=payload,
    )


def _retarget_gap(gap: dict[str, object]) -> dict[str, object]:
    retargeted = dict(gap)
    retargeted["source"] = ANOPHELES_LITERATURE_SOURCE_ID
    record_id = retargeted.get("record_id")
    if isinstance(record_id, str) and record_id.startswith("openalex:"):
        retargeted["record_id"] = f"anopheles_openalex:{record_id.split(':', 1)[-1]}"
        retargeted["original_record_id"] = record_id
    retargeted["target_taxa"] = ANOPHELES_TARGET_TAXA
    return retargeted


def fetch_anopheles_literature_records(
    *,
    raw_dir: Path,
    from_date: str,
    to_date: str,
    max_works: int,
    page_size: int = 100,
    delay_seconds: float = 0.0,
    fetch_json=None,
    retrieved_at: str | None = None,
) -> LiteratureBuildResult:
    per_query_limit = max(1, math.ceil(max_works / len(ANOPHELES_LITERATURE_SEARCH_TERMS)))
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    inclusion_path_counts: dict[str, int] = {}
    reported_total_count = 0
    page_count = 0
    doi_count = 0
    pubmed_skipped_count = 0
    seen_work_ids: set[str] = set()
    for query in ANOPHELES_LITERATURE_SEARCH_TERMS:
        if len(records) >= max_works:
            break
        remaining = max_works - len(records)
        result = fetch_literature_records(
            species="Anopheles",
            from_date=from_date,
            to_date=to_date,
            work_type="article",
            include_topic_discovery=False,
            raw_dir=raw_dir,
            page_size=min(page_size, per_query_limit, remaining),
            delay_seconds=delay_seconds,
            fetch_json=fetch_json,
            fetch_text=None,
            unpaywall_email=None,
            retrieved_at=retrieved_at,
            max_works=min(per_query_limit, remaining),
            skip_pubmed=True,
            search_terms=[query],
            source_id=ANOPHELES_LITERATURE_SOURCE_ID,
        )
        for record in result.records:
            if record.record_id in seen_work_ids:
                continue
            seen_work_ids.add(record.record_id)
            records.append(record)
        gaps.extend(result.gaps)
        raw_artifacts.extend(result.raw_artifacts)
        for key, value in result.inclusion_path_counts.items():
            inclusion_path_counts[key] = inclusion_path_counts.get(key, 0) + value
        reported_total_count += result.reported_total_count
        page_count += result.page_count
        doi_count += result.doi_count
        pubmed_skipped_count += result.pubmed_skipped_count
    return LiteratureBuildResult(
        source_id=ANOPHELES_LITERATURE_SOURCE_ID,
        records=[_retarget_record(record) for record in records],
        fulltext_units=[],
        gaps=[_retarget_gap(gap) for gap in gaps],
        raw_artifacts=raw_artifacts,
        topic_search_results=[],
        accepted_topic_ids=[],
        inclusion_path_counts=inclusion_path_counts,
        reported_total_count=reported_total_count,
        page_count=page_count,
        doi_count=doi_count,
        unpaywall_queried_count=0,
        open_fulltext_count=0,
        pubmed_skipped_count=pubmed_skipped_count,
    )
