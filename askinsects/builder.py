from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Callable

from .index import SourceIndex
from .sources.fixtures import FIXTURE_RETRIEVED_AT, FIXTURE_SOURCE_ID, load_fixture_records
from .sources.gbif import DEFAULT_GBIF_SPECIES, GBIF_SOURCE_ID, fetch_gbif_records
from .sources.inaturalist import DEFAULT_INATURALIST_SPECIES, INATURALIST_SOURCE_ID, fetch_inaturalist_records
from .sources.literature import LITERATURE_SOURCE_ID, fetch_literature_records
from .sources.ncbi_genome import (
    DEFAULT_ASSEMBLY_ACCESSION,
    NCBI_GENOME_SOURCE_ID,
    fetch_ncbi_genome_records,
)
from .sources.neurobiology import NEUROBIOLOGY_SOURCE_ID, fetch_neurobiology_records


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_DIR = Path(os.environ.get("ASK_INSECTS_ARTIFACT_DIR", REPO_ROOT / "artifacts/mosquito-v1"))
DEFAULT_FIXTURE_PATH = REPO_ROOT / "data/fixtures/mosquito_records.json"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_fixture_index(
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
) -> dict[str, object]:
    return build_source_index(
        include_fixtures=True,
        include_gbif=False,
        include_inaturalist=False,
        include_ncbi_genome=False,
        fixture_path=fixture_path,
        artifact_dir=artifact_dir,
    )


def build_source_index(
    *,
    include_fixtures: bool,
    include_gbif: bool,
    include_inaturalist: bool = False,
    include_literature: bool = False,
    include_ncbi_genome: bool = False,
    include_neurobiology: bool = False,
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    gbif_species: list[str] | tuple[str, ...] | None = None,
    occurrence_limit: int = 3,
    occurrence_page_size: int = 300,
    occurrence_workers: int = 1,
    gbif_delay_seconds: float = 0.0,
    gbif_fetch_json: Callable[[str], dict[str, object]] | None = None,
    inaturalist_species: list[str] | tuple[str, ...] | None = None,
    inaturalist_place: str | None = None,
    observation_limit: int = 10,
    page_size: int = 200,
    delay_seconds: float = 0.0,
    inaturalist_fetch_json: Callable[[str], dict[str, object]] | None = None,
    literature_species: str = "Aedes aegypti",
    literature_from_date: str = "2020-01-01",
    literature_to_date: str | None = None,
    literature_work_type: str = "article",
    include_topic_discovery: bool = False,
    literature_page_size: int = 200,
    literature_delay_seconds: float | None = None,
    literature_max_works: int | None = None,
    unpaywall_email: str | None = None,
    skip_fulltext: bool = False,
    skip_pubmed: bool = False,
    literature_fetch_json: Callable[[str], dict[str, object]] | None = None,
    literature_fetch_text: Callable[[str], str] | None = None,
    genome_package_dir: Path | None = None,
    genome_assembly_accession: str = DEFAULT_ASSEMBLY_ACCESSION,
    neurobiology_artifact_dir: Path | None = None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    if (
        not include_fixtures
        and not include_gbif
        and not include_inaturalist
        and not include_literature
        and not include_ncbi_genome
        and not include_neurobiology
    ):
        raise ValueError("at least one source must be selected")
    has_live_source = include_gbif or include_inaturalist or include_literature
    generated_at = retrieved_at or (utc_now() if has_live_source else FIXTURE_RETRIEVED_AT)
    literature_effective_to_date = literature_to_date or generated_at.split("T", 1)[0]
    gaps_path = artifact_dir / "gaps.json"

    artifact_dir.mkdir(parents=True, exist_ok=True)
    db_path = artifact_dir / "source_index.sqlite"
    if db_path.exists():
        db_path.unlink()

    records = []
    sources = []
    source_counts: dict[str, int] = {}
    gaps: list[dict[str, object]] = []
    receipt_sources: dict[str, object] = {}

    if include_fixtures:
        fixture_records = load_fixture_records(fixture_path)
        records.extend(fixture_records)
        sources.append(FIXTURE_SOURCE_ID)
        source_counts[FIXTURE_SOURCE_ID] = len(fixture_records)
        receipt_sources[FIXTURE_SOURCE_ID] = {
            "fixture_path": fixture_path.as_posix(),
            "record_count": len(fixture_records),
        }

    gbif_payload: dict[str, object] | None = None
    if include_gbif:
        gbif_result = fetch_gbif_records(
            gbif_species or DEFAULT_GBIF_SPECIES,
            raw_dir=artifact_dir / "raw" / "gbif",
            occurrence_limit=occurrence_limit,
            occurrence_page_size=occurrence_page_size,
            occurrence_workers=occurrence_workers,
            delay_seconds=gbif_delay_seconds,
            fetch_json=gbif_fetch_json,
            retrieved_at=generated_at,
        )
        records.extend(gbif_result.records)
        sources.append(GBIF_SOURCE_ID)
        source_counts[GBIF_SOURCE_ID] = len(gbif_result.records)
        gaps.extend(gbif_result.gaps)
        gbif_payload = {
            "requested_species": gbif_result.requested_species,
            "occurrence_limit": gbif_result.occurrence_limit,
            "occurrence_page_size": gbif_result.occurrence_page_size,
            "occurrence_workers": gbif_result.occurrence_workers,
            "total_results": gbif_result.total_results,
            "page_count": gbif_result.page_count,
            "taxon_keys": gbif_result.taxon_keys,
            "raw_artifacts": gbif_result.raw_artifacts,
            "record_count": len(gbif_result.records),
            "gap_count": len(gbif_result.gaps),
        }
        receipt_sources[GBIF_SOURCE_ID] = gbif_payload

    inaturalist_payload: dict[str, object] | None = None
    if include_inaturalist:
        inaturalist_result = fetch_inaturalist_records(
            inaturalist_species or DEFAULT_INATURALIST_SPECIES,
            raw_dir=artifact_dir / "raw" / "inaturalist",
            place=inaturalist_place,
            observation_limit=observation_limit,
            page_size=page_size,
            delay_seconds=delay_seconds,
            fetch_json=inaturalist_fetch_json,
            retrieved_at=generated_at,
        )
        records.extend(inaturalist_result.records)
        sources.append(INATURALIST_SOURCE_ID)
        source_counts[INATURALIST_SOURCE_ID] = len(inaturalist_result.records)
        gaps.extend(inaturalist_result.gaps)
        inaturalist_payload = {
            "requested_species": inaturalist_result.requested_species,
            "place": inaturalist_result.place,
            "observation_limit": inaturalist_result.observation_limit,
            "page_size": inaturalist_result.page_size,
            "delay_seconds": inaturalist_result.delay_seconds,
            "total_results": inaturalist_result.total_results,
            "raw_artifacts": inaturalist_result.raw_artifacts,
            "record_count": len(inaturalist_result.records),
            "gap_count": len(inaturalist_result.gaps),
        }
        receipt_sources[INATURALIST_SOURCE_ID] = inaturalist_payload

    literature_payload: dict[str, object] | None = None
    literature_result = None
    if include_literature:
        literature_result = fetch_literature_records(
            species=literature_species,
            from_date=literature_from_date,
            to_date=literature_effective_to_date,
            work_type=literature_work_type,
            include_topic_discovery=include_topic_discovery,
            raw_dir=artifact_dir / "raw" / "literature",
            page_size=literature_page_size,
            delay_seconds=delay_seconds if literature_delay_seconds is None else literature_delay_seconds,
            fetch_json=literature_fetch_json,
            fetch_text=None if skip_fulltext else literature_fetch_text,
            unpaywall_email=None if skip_fulltext else unpaywall_email,
            retrieved_at=generated_at,
            max_works=literature_max_works,
            skip_pubmed=skip_pubmed,
        )
        records.extend(literature_result.records)
        sources.append(LITERATURE_SOURCE_ID)
        source_counts[LITERATURE_SOURCE_ID] = len(literature_result.records)
        gaps.extend(literature_result.gaps)
        literature_payload = {
            "species": literature_species,
            "from_date": literature_from_date,
            "to_date": literature_effective_to_date,
            "work_type": literature_work_type,
            "include_topic_discovery": include_topic_discovery,
            "reported_total_count": literature_result.reported_total_count,
            "page_count": literature_result.page_count,
            "record_count": len(literature_result.records),
            "fulltext_unit_count": len(literature_result.fulltext_units),
            "gap_count": len(literature_result.gaps),
            "gaps_path": gaps_path.as_posix(),
            "raw_artifacts": literature_result.raw_artifacts,
            "topic_search_results": literature_result.topic_search_results,
            "accepted_topic_ids": literature_result.accepted_topic_ids,
            "inclusion_path_counts": literature_result.inclusion_path_counts,
            "doi_count": literature_result.doi_count,
            "unpaywall_queried_count": literature_result.unpaywall_queried_count,
            "open_fulltext_count": literature_result.open_fulltext_count,
            "skip_pubmed": skip_pubmed,
            "pubmed_skipped_count": literature_result.pubmed_skipped_count,
        }
        receipt_sources[LITERATURE_SOURCE_ID] = literature_payload

    ncbi_genome_payload: dict[str, object] | None = None
    if include_ncbi_genome:
        if genome_package_dir is None:
            raise ValueError("genome_package_dir is required when include_ncbi_genome is true")
        ncbi_genome_result = fetch_ncbi_genome_records(
            package_dir=genome_package_dir,
            assembly_accession=genome_assembly_accession,
            retrieved_at=generated_at,
        )
        records.extend(ncbi_genome_result.records)
        sources.append(NCBI_GENOME_SOURCE_ID)
        source_counts[NCBI_GENOME_SOURCE_ID] = len(ncbi_genome_result.records)
        gaps.extend(ncbi_genome_result.gaps)
        ncbi_genome_payload = {
            "package_dir": ncbi_genome_result.package_dir,
            "assembly_accession": ncbi_genome_result.assembly_accession,
            "raw_artifacts": ncbi_genome_result.raw_artifacts,
            "record_count": len(ncbi_genome_result.records),
            "gap_count": len(ncbi_genome_result.gaps),
        }
        receipt_sources[NCBI_GENOME_SOURCE_ID] = ncbi_genome_payload

    neurobiology_payload: dict[str, object] | None = None
    if include_neurobiology:
        neurobiology_result = fetch_neurobiology_records(
            artifact_dir=neurobiology_artifact_dir,
            retrieved_at=generated_at,
        )
        records.extend(neurobiology_result.records)
        sources.append(NEUROBIOLOGY_SOURCE_ID)
        source_counts[NEUROBIOLOGY_SOURCE_ID] = len(neurobiology_result.records)
        gaps.extend(neurobiology_result.gaps)
        neurobiology_payload = {
            "source_id": neurobiology_result.source_id,
            "artifact_dir": neurobiology_artifact_dir.as_posix() if neurobiology_artifact_dir else None,
            "raw_artifacts": neurobiology_result.raw_artifacts,
            "record_count": len(neurobiology_result.records),
            "gap_count": len(neurobiology_result.gaps),
        }
        receipt_sources[NEUROBIOLOGY_SOURCE_ID] = neurobiology_payload

    index = SourceIndex(db_path)
    index.initialize()
    if include_literature and literature_result is not None:
        index.upsert_records_and_fulltext_units(records, literature_result.fulltext_units)
    else:
        index.upsert_records(records)
    summary = index.summary()
    source_counts = {
        str(row["source"]): int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source", limit=1000)
    }
    if ncbi_genome_payload is not None:
        ncbi_genome_payload["record_count"] = source_counts.get(NCBI_GENOME_SOURCE_ID, 0)
    if neurobiology_payload is not None:
        neurobiology_payload["record_count"] = source_counts.get(NEUROBIOLOGY_SOURCE_ID, 0)

    status = {
        "ok": True,
        "source_id": sources[0],
        "sources": sources,
        "source_counts": source_counts,
        "boundary": "mosquitoes first",
        "generated_at": generated_at,
        "fully_parsed": True,
        "record_count": summary["record_count"],
        "species_count": summary["species_count"],
        "lanes": summary["lanes"],
        "gap_count": len(gaps),
    }
    receipt = {
        "source_id": sources[0],
        "sources": receipt_sources,
        "artifact_dir": artifact_dir.as_posix(),
        "sqlite_index": db_path.as_posix(),
        "generated_at": generated_at,
        "record_count": summary["record_count"],
        "lanes": summary["lanes"],
    }
    if gbif_payload is not None:
        receipt["gbif"] = gbif_payload
    if inaturalist_payload is not None:
        receipt["inaturalist"] = inaturalist_payload
    if literature_payload is not None:
        receipt["literature"] = literature_payload
    if ncbi_genome_payload is not None:
        receipt["ncbi_genome"] = ncbi_genome_payload
    if neurobiology_payload is not None:
        receipt["neurobiology"] = neurobiology_payload

    write_json(gaps_path, gaps)
    write_json(artifact_dir / "source_status.json", status)
    write_json(artifact_dir / "source_receipt.json", receipt)
    result = {"ok": True, "artifact_dir": artifact_dir.as_posix(), **status}
    if gbif_payload is not None:
        result["gbif"] = gbif_payload
    if inaturalist_payload is not None:
        result["inaturalist"] = inaturalist_payload
    if literature_payload is not None:
        result["literature"] = literature_payload
    if ncbi_genome_payload is not None:
        result["ncbi_genome"] = ncbi_genome_payload
    if neurobiology_payload is not None:
        result["neurobiology"] = neurobiology_payload
    return result
