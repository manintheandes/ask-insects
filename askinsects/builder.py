from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .index import SourceIndex
from .sources.fixtures import FIXTURE_RETRIEVED_AT, FIXTURE_SOURCE_ID, load_fixture_records
from .sources.gbif import DEFAULT_GBIF_SPECIES, GBIF_SOURCE_ID, fetch_gbif_records
from .sources.inaturalist import DEFAULT_INATURALIST_SPECIES, INATURALIST_SOURCE_ID, fetch_inaturalist_records


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts/mosquito-v1"
DEFAULT_FIXTURE_PATH = REPO_ROOT / "data/fixtures/mosquito_records.json"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_fixture_index(
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
) -> dict[str, object]:
    return build_source_index(
        include_fixtures=True,
        include_gbif=False,
        include_inaturalist=False,
        fixture_path=fixture_path,
        artifact_dir=artifact_dir,
    )


def build_source_index(
    *,
    include_fixtures: bool,
    include_gbif: bool,
    include_inaturalist: bool = False,
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    gbif_species: list[str] | tuple[str, ...] | None = None,
    occurrence_limit: int = 3,
    gbif_fetch_json: Callable[[str], dict[str, object]] | None = None,
    inaturalist_species: list[str] | tuple[str, ...] | None = None,
    inaturalist_place: str | None = None,
    observation_limit: int = 10,
    page_size: int = 200,
    delay_seconds: float = 0.0,
    inaturalist_fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str = FIXTURE_RETRIEVED_AT,
) -> dict[str, object]:
    if not include_fixtures and not include_gbif and not include_inaturalist:
        raise ValueError("at least one source must be selected")

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
            fetch_json=gbif_fetch_json,
            retrieved_at=retrieved_at,
        )
        records.extend(gbif_result.records)
        sources.append(GBIF_SOURCE_ID)
        source_counts[GBIF_SOURCE_ID] = len(gbif_result.records)
        gaps.extend(gbif_result.gaps)
        gbif_payload = {
            "requested_species": gbif_result.requested_species,
            "occurrence_limit": gbif_result.occurrence_limit,
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
            retrieved_at=retrieved_at,
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

    index = SourceIndex(db_path)
    index.initialize()
    index.upsert_records(records)
    summary = index.summary()

    status = {
        "ok": True,
        "source_id": sources[0],
        "sources": sources,
        "source_counts": source_counts,
        "boundary": "mosquitoes first",
        "generated_at": retrieved_at,
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
        "generated_at": retrieved_at,
        "record_count": summary["record_count"],
        "lanes": summary["lanes"],
    }
    if gbif_payload is not None:
        receipt["gbif"] = gbif_payload
    if inaturalist_payload is not None:
        receipt["inaturalist"] = inaturalist_payload

    write_json(artifact_dir / "gaps.json", gaps)
    write_json(artifact_dir / "source_status.json", status)
    write_json(artifact_dir / "source_receipt.json", receipt)
    result = {"ok": True, "artifact_dir": artifact_dir.as_posix(), **status}
    if gbif_payload is not None:
        result["gbif"] = gbif_payload
    if inaturalist_payload is not None:
        result["inaturalist"] = inaturalist_payload
    return result
