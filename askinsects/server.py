from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
from typing import Callable

from .answer import answer_question
from .builder import DEFAULT_ARTIFACT_DIR, build_source_index
from .index import SourceIndex
from .sources.dryad_behavior_videos import DRYAD_BEHAVIOR_VIDEO_SOURCE_ID, fetch_dryad_behavior_video_records
from .sources.gbif import (
    GBIF_SOURCE_ID,
    GBIFClient,
    fetch_gbif_records,
    fetch_occurrence_page,
    occurrence_record,
    safe_species_name,
    taxonomy_record,
    utc_now,
    write_raw_json,
)
from .sources.inaturalist import (
    INATURALIST_SOURCE_ID,
    INaturalistClient,
    fetch_inaturalist_records,
    media_record,
    observation_record,
    safe_name as inaturalist_safe_name,
    write_raw_json as write_inaturalist_raw_json,
)
from .sources.irmapper import DEFAULT_IRMAPPER_SPECIES, IRMAPPER_SOURCE_ID, fetch_irmapper_records
from .sources.mendeley_behavior_media import MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID, fetch_mendeley_behavior_media_records
from .sources.mosquito_alert import MOSQUITO_ALERT_SOURCE_ID, fetch_mosquito_alert_records
from .sources.ncbi_biosample import DEFAULT_BIOSAMPLE_SPECIES, fetch_ncbi_biosample_records
from .sources.osf_flighttrackai_videos import OSF_FLIGHTTRACKAI_SOURCE_ID, fetch_osf_flighttrackai_video_records
from .sources.pathogen_taxonomy import PATHOGEN_TAXONOMY_SOURCE_ID, fetch_pathogen_taxonomy_records
from .sources.paho_surveillance import (
    DEFAULT_PAHO_DENGUE_DASHBOARD_PAGES,
    DEFAULT_PAHO_DENGUE_REPORTS,
    PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
    fetch_paho_dengue_surveillance_records,
)
from .sources.public_health import (
    DEFAULT_PUBLIC_HEALTH_SOURCES,
    PUBLIC_HEALTH_SOURCE_ID,
    fetch_public_health_guidance_records,
)
from .sources.vectorbase_genomics import fetch_vectorbase_genomics_records


@dataclass(frozen=True)
class Response:
    status: int
    payload: dict[str, object]


def json_response(status: int, payload: dict[str, object]) -> Response:
    return Response(status=status, payload=payload)


def is_authorized(headers: object, token: str) -> bool:
    if not token:
        return False
    auth = headers.get("Authorization") if hasattr(headers, "get") else None
    return auth == f"Bearer {token}"


def read_sources(artifact_dir: Path) -> list[str]:
    status_path = artifact_dir / "source_status.json"
    if not status_path.exists():
        return []
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    sources = payload.get("sources")
    if isinstance(sources, list) and all(isinstance(source, str) for source in sources):
        return sources
    source_id = payload.get("source_id")
    if isinstance(source_id, str):
        return [source_id]
    return []


def health_payload(artifact_dir: Path) -> dict[str, object]:
    db_path = artifact_dir / "source_index.sqlite"
    status_path = artifact_dir / "source_status.json"
    payload: dict[str, object] = {
        "ok": db_path.exists() and status_path.exists(),
        "db_exists": db_path.exists(),
        "status_exists": status_path.exists(),
        "db_path": str(db_path),
        "artifact_dir": str(artifact_dir),
        "sources": read_sources(artifact_dir),
    }
    if db_path.exists():
        try:
            payload.update(SourceIndex(db_path).summary())
        except sqlite3.Error as exc:
            payload["ok"] = False
            payload["error"] = str(exc)
    return payload


def read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def replace_path_strings(value: object, old: str, new: str) -> object:
    return json.loads(json.dumps(value).replace(old, new))


def replace_record_path_strings(records: list[object], old: str, new: str) -> list[object]:
    rewritten = []
    for record in records:
        provenance = replace(record.provenance, locator=record.provenance.locator.replace(old, new))
        rewritten.append(replace(record, provenance=provenance))
    return rewritten


def rewrite_artifact_references(
    staging: Path,
    artifact_dir: Path,
    result: dict[str, object],
    *,
    rewrite_db: bool = True,
    source: str | None = None,
) -> dict[str, object]:
    old = str(staging)
    new = str(artifact_dir)
    for path in (staging / "source_status.json", staging / "source_receipt.json", staging / "gaps.json"):
        if path.exists():
            text = path.read_text(encoding="utf-8").replace(old, new)
            path.write_text(text, encoding="utf-8")
    db_path = staging / "source_index.sqlite"
    if rewrite_db and db_path.exists():
        with sqlite3.connect(db_path) as conn:
            if source:
                rows = conn.execute("SELECT record_id FROM records WHERE source=?", (source,)).fetchall()
                record_ids = [str(row[0]) for row in rows]
                for start in range(0, len(record_ids), 900):
                    chunk = record_ids[start : start + 900]
                    placeholders = ",".join("?" for _ in chunk)
                    conn.execute(
                        f"UPDATE records SET provenance_json = replace(provenance_json, ?, ?) WHERE record_id IN ({placeholders})",
                        (old, new, *chunk),
                    )
                    try:
                        conn.execute(
                            f"UPDATE record_payloads SET provenance_json = replace(provenance_json, ?, ?) WHERE record_id IN ({placeholders})",
                            (old, new, *chunk),
                        )
                    except sqlite3.OperationalError:
                        pass
                    try:
                        conn.execute(
                            f"UPDATE record_payloads SET payload_json = replace(payload_json, ?, ?) WHERE record_id IN ({placeholders})",
                            (old, new, *chunk),
                        )
                    except sqlite3.OperationalError:
                        pass
            else:
                conn.execute(
                    "UPDATE records SET provenance_json = replace(provenance_json, ?, ?) WHERE provenance_json LIKE ?",
                    (old, new, f"%{old}%"),
                )
                try:
                    conn.execute(
                        "UPDATE record_payloads SET provenance_json = replace(provenance_json, ?, ?) WHERE provenance_json LIKE ?",
                        (old, new, f"%{old}%"),
                    )
                except sqlite3.OperationalError:
                    pass
                try:
                    conn.execute(
                        "UPDATE record_payloads SET payload_json = replace(payload_json, ?, ?) WHERE payload_json LIKE ?",
                        (old, new, f"%{old}%"),
                    )
                except sqlite3.OperationalError:
                    pass
    rewritten = replace_path_strings(result, old, new)
    if not isinstance(rewritten, dict):
        return result
    return rewritten


def activate_staging_artifact(staging: Path, artifact_dir: Path) -> None:
    backup = artifact_dir.parent / f".{artifact_dir.name}.previous"
    if backup.exists():
        shutil.rmtree(backup)
    if artifact_dir.exists():
        artifact_dir.replace(backup)
    staging.replace(artifact_dir)
    if backup.exists():
        shutil.rmtree(backup)


MUTABLE_ARTIFACT_FILES = {
    "source_index.sqlite",
    "source_index.sqlite-shm",
    "source_index.sqlite-wal",
    "source_status.json",
    "source_receipt.json",
    "gaps.json",
}


def _copy_for_staging(src: str, dst: str) -> str:
    if Path(src).name in MUTABLE_ARTIFACT_FILES:
        return shutil.copy2(src, dst)
    try:
        os.link(src, dst)
        shutil.copystat(src, dst, follow_symlinks=False)
        return dst
    except OSError:
        return shutil.copy2(src, dst)


def copy_artifact_to_staging(artifact_dir: Path, staging: Path) -> None:
    shutil.copytree(artifact_dir, staging, copy_function=_copy_for_staging)


def prepare_mutable_staging(artifact_dir: Path, staging: Path) -> None:
    staging.mkdir(parents=True, exist_ok=True)
    for name in MUTABLE_ARTIFACT_FILES:
        source = artifact_dir / name
        if source.exists():
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def copy_relative_inputs_to_staging(artifact_dir: Path, staging: Path, paths: list[Path]) -> None:
    for path in paths:
        if path.is_absolute():
            continue
        source = artifact_dir / path
        target = staging / path
        if not source.exists() or target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, copy_function=_copy_for_staging)
        else:
            shutil.copy2(source, target)


def activate_source_staging(staging: Path, artifact_dir: Path, raw_relative_dir: Path) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    for name in MUTABLE_ARTIFACT_FILES:
        source = staging / name
        if source.exists():
            target = artifact_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source.replace(target)
    raw_source = staging / raw_relative_dir
    if raw_source.exists():
        raw_target = artifact_dir / raw_relative_dir
        raw_target.parent.mkdir(parents=True, exist_ok=True)
        backup = raw_target.parent / f".{raw_target.name}.previous"
        if backup.exists():
            shutil.rmtree(backup)
        if raw_target.exists():
            raw_target.replace(backup)
        raw_source.replace(raw_target)
        if backup.exists():
            shutil.rmtree(backup)
    shutil.rmtree(staging, ignore_errors=True)


def replace_source_records(index: SourceIndex, source: str, records: list[object]) -> None:
    index.replace_source_records(source, records)


def write_inaturalist_metadata(staging: Path, inaturalist_payload: dict[str, object], gaps: list[dict[str, object]]) -> dict[str, object]:
    index = SourceIndex(staging / "source_index.sqlite")
    summary = index.summary()
    counts = source_counts(index)
    generated_at = str(inaturalist_payload["retrieved_at"])
    sources = [source for source in counts if source != INATURALIST_SOURCE_ID]
    if counts.get(INATURALIST_SOURCE_ID):
        sources.append(INATURALIST_SOURCE_ID)

    status = read_json(staging / "source_status.json", {})
    if not isinstance(status, dict):
        status = {}
    status.update(
        {
            "ok": True,
            "source_id": sources[0] if sources else INATURALIST_SOURCE_ID,
            "sources": sources,
            "source_counts": counts,
            "boundary": "mosquitoes first",
            "generated_at": generated_at,
            "fully_parsed": True,
            "record_count": summary["record_count"],
            "species_count": summary["species_count"],
            "lanes": summary["lanes"],
            "gap_count": len(gaps),
        }
    )

    receipt = read_json(staging / "source_receipt.json", {})
    if not isinstance(receipt, dict):
        receipt = {}
    receipt_sources = receipt.get("sources")
    if not isinstance(receipt_sources, dict):
        receipt_sources = {}
    receipt_sources[INATURALIST_SOURCE_ID] = inaturalist_payload
    receipt.update(
        {
            "source_id": sources[0] if sources else INATURALIST_SOURCE_ID,
            "sources": receipt_sources,
            "artifact_dir": staging.as_posix(),
            "sqlite_index": (staging / "source_index.sqlite").as_posix(),
            "generated_at": generated_at,
            "record_count": summary["record_count"],
            "lanes": summary["lanes"],
            "inaturalist": inaturalist_payload,
        }
    )

    write_json(staging / "gaps.json", gaps)
    write_json(staging / "source_status.json", status)
    write_json(staging / "source_receipt.json", receipt)
    return {"ok": True, "artifact_dir": staging.as_posix(), **status, "inaturalist": inaturalist_payload}


def stream_inaturalist_into_index(
    species_names: list[str],
    *,
    staging: Path,
    artifact_dir: Path,
    place: str | None,
    observation_limit: int,
    page_size: int,
    delay_seconds: float,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if observation_limit < 0:
        raise ValueError("observation_limit must be zero or greater")
    if page_size <= 0:
        raise ValueError("page_size must be greater than zero")

    retrieved_at = utc_now()
    client = INaturalistClient()
    index = SourceIndex(staging / "source_index.sqlite")
    raw_dir = staging / "raw" / "inaturalist"
    raw_artifacts: list[str] = []
    gaps: list[dict[str, object]] = []
    total_results: dict[str, int] = {}
    seen_observations: set[str] = set()
    seen_media: set[str] = set()
    record_count = 0
    page_size = max(1, min(int(page_size), 200))

    for species in species_names:
        species_indexed_observations = 0
        species_seen_results = 0
        species_had_results = False
        photo_seen = False
        page = 1
        while species_indexed_observations < observation_limit:
            if page > 1 and delay_seconds > 0:
                time.sleep(delay_seconds)
            query_url, payload = client.observations(species, place=place, page=page, page_size=page_size)
            raw_path = write_inaturalist_raw_json(
                raw_dir,
                f"{inaturalist_safe_name(species)}_{inaturalist_safe_name(place)}_page_{page:03d}.json",
                payload,
            )
            final_raw_path = artifact_dir / raw_path.relative_to(staging)
            raw_artifacts.append(final_raw_path.as_posix())
            total_results[species] = int(payload.get("total_results") or payload.get("total_count") or 0)
            results = payload.get("results")
            if not isinstance(results, list) or not results:
                break
            species_had_results = True
            species_seen_results += len(results)

            page_records = []
            for observation in results:
                if species_indexed_observations >= observation_limit:
                    break
                if not isinstance(observation, dict) or not observation.get("id"):
                    continue
                observation_id = str(observation["id"])
                if observation_id in seen_observations:
                    continue
                photos = observation.get("photos")
                if not isinstance(photos, list):
                    continue
                photo = next((item for item in photos if isinstance(item, dict) and item.get("url")), None)
                if photo is None:
                    continue
                photo_id = str(photo.get("id") or observation_id)
                if photo_id in seen_media:
                    continue
                photo_seen = True
                seen_observations.add(observation_id)
                seen_media.add(photo_id)
                page_records.append(
                    observation_record(
                        observation,
                        photo,
                        species=species,
                        query_url=query_url,
                        raw_path=final_raw_path,
                        retrieved_at=retrieved_at,
                    )
                )
                page_records.append(
                    media_record(
                        observation,
                        photo,
                        species=species,
                        raw_path=final_raw_path,
                        retrieved_at=retrieved_at,
                    )
                )
                species_indexed_observations += 1
            if page_records:
                index.upsert_records(page_records)
                record_count += len(page_records)

            if species_seen_results >= total_results.get(species, 0):
                break
            page += 1

        if not species_had_results:
            gaps.append(
                {
                    "source": INATURALIST_SOURCE_ID,
                    "lane": "observations",
                    "species": species,
                    "place": place,
                    "reason": "iNaturalist returned no observations for this query.",
                }
            )
            continue
        if not photo_seen or species_indexed_observations == 0:
            gaps.append(
                {
                    "source": INATURALIST_SOURCE_ID,
                    "lane": "media",
                    "species": species,
                    "place": place,
                    "reason": "iNaturalist observations did not include usable licensed photos.",
                }
            )

    return (
        {
            "requested_species": species_names,
            "place": place,
            "observation_limit": observation_limit,
            "page_size": page_size,
            "delay_seconds": delay_seconds,
            "total_results": total_results,
            "raw_artifacts": raw_artifacts,
            "record_count": record_count,
            "gap_count": len(gaps),
            "retrieved_at": retrieved_at,
        },
        gaps,
    )


def ingest_inaturalist(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_inaturalist_records_fn: Callable[..., object] = fetch_inaturalist_records,
) -> dict[str, object]:
    species_value = payload.get("species") or ["Aedes aegypti"]
    if isinstance(species_value, str):
        species = [species_value]
    elif isinstance(species_value, list) and all(isinstance(item, str) for item in species_value):
        species = species_value
    else:
        raise ValueError("species must be a string or list of strings")

    observation_limit = int(payload.get("observation_limit", 10))
    page_size = int(payload.get("page_size", 200))
    delay_seconds = float(payload.get("delay_seconds", 0))
    place = payload.get("place")
    if place is not None and not isinstance(place, str):
        raise ValueError("place must be a string")

    staging = artifact_dir.parent / f".{artifact_dir.name}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        if artifact_dir.exists():
            prepare_mutable_staging(artifact_dir, staging)
        else:
            staging.mkdir(parents=True, exist_ok=True)
        index = SourceIndex(staging / "source_index.sqlite")
        index.initialize()
        index.delete_source(INATURALIST_SOURCE_ID)
        stream_default_fetch = fetch_inaturalist_records_fn is fetch_inaturalist_records
        if stream_default_fetch:
            inaturalist_payload, new_gaps = stream_inaturalist_into_index(
                species,
                staging=staging,
                artifact_dir=artifact_dir,
                place=place,
                observation_limit=observation_limit,
                page_size=page_size,
                delay_seconds=delay_seconds,
            )
        else:
            result = fetch_inaturalist_records_fn(
                species,
                raw_dir=staging / "raw" / "inaturalist",
                place=place,
                observation_limit=observation_limit,
                page_size=page_size,
                delay_seconds=delay_seconds,
            )
            index.upsert_records(result.records)
            retrieved_at = result.records[0].provenance.retrieved_at if result.records else utc_now()
            inaturalist_payload = {
                "requested_species": result.requested_species,
                "place": result.place,
                "observation_limit": result.observation_limit,
                "page_size": result.page_size,
                "delay_seconds": result.delay_seconds,
                "total_results": result.total_results,
                "raw_artifacts": result.raw_artifacts,
                "record_count": len(result.records),
                "gap_count": len(result.gaps),
                "retrieved_at": retrieved_at,
            }
            new_gaps = result.gaps
        old_gaps = read_json(staging / "gaps.json", [])
        if not isinstance(old_gaps, list):
            old_gaps = []
        gaps = [gap for gap in old_gaps if not (isinstance(gap, dict) and gap.get("source") == INATURALIST_SOURCE_ID)]
        gaps.extend(new_gaps)
        response = write_inaturalist_metadata(staging, inaturalist_payload, gaps)
        response = rewrite_artifact_references(staging, artifact_dir, response, rewrite_db=not stream_default_fetch)
        activate_staging_artifact(staging, artifact_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    response["activated_artifact_dir"] = str(artifact_dir)
    return response


def normalize_species(value: object, default: list[str]) -> list[str]:
    if value is None:
        return default
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise ValueError("species must be a string or list of strings")


def source_counts(index: SourceIndex) -> dict[str, int]:
    rows = index.sql("select source, count(*) as n from records group by source", limit=1000)
    return {str(row["source"]): int(row["n"]) for row in rows}


def write_gbif_metadata(staging: Path, gbif_payload: dict[str, object], gaps: list[dict[str, object]]) -> dict[str, object]:
    index = SourceIndex(staging / "source_index.sqlite")
    summary = index.summary()
    counts = source_counts(index)
    generated_at = str(gbif_payload["retrieved_at"])
    sources = [source for source in counts if source != GBIF_SOURCE_ID]
    if counts.get(GBIF_SOURCE_ID):
        sources.append(GBIF_SOURCE_ID)

    status = read_json(staging / "source_status.json", {})
    if not isinstance(status, dict):
        status = {}
    status.update(
        {
            "ok": True,
            "source_id": sources[0] if sources else GBIF_SOURCE_ID,
            "sources": sources,
            "source_counts": counts,
            "boundary": "mosquitoes first",
            "generated_at": generated_at,
            "fully_parsed": True,
            "record_count": summary["record_count"],
            "species_count": summary["species_count"],
            "lanes": summary["lanes"],
            "gap_count": len(gaps),
        }
    )

    receipt = read_json(staging / "source_receipt.json", {})
    if not isinstance(receipt, dict):
        receipt = {}
    receipt_sources = receipt.get("sources")
    if not isinstance(receipt_sources, dict):
        receipt_sources = {}
    receipt_sources[GBIF_SOURCE_ID] = gbif_payload
    receipt.update(
        {
            "source_id": sources[0] if sources else GBIF_SOURCE_ID,
            "sources": receipt_sources,
            "artifact_dir": staging.as_posix(),
            "sqlite_index": (staging / "source_index.sqlite").as_posix(),
            "generated_at": generated_at,
            "record_count": summary["record_count"],
            "lanes": summary["lanes"],
            "gbif": gbif_payload,
        }
    )

    write_json(staging / "gaps.json", gaps)
    write_json(staging / "source_status.json", status)
    write_json(staging / "source_receipt.json", receipt)
    return {"ok": True, "artifact_dir": staging.as_posix(), **status, "gbif": gbif_payload}


def process_gbif_page(
    page: tuple[int, str, dict[str, object], Path],
    *,
    species: str,
    index: SourceIndex,
    retrieved_at: str,
) -> int:
    _offset, occurrence_url, occurrence_payload, occurrence_path = page
    occurrence_results = occurrence_payload.get("results")
    if not isinstance(occurrence_results, list):
        return 0
    records = [
        occurrence_record(
            occurrence,
            species=species,
            occurrence_url=occurrence_url,
            raw_path=occurrence_path,
            retrieved_at=retrieved_at,
        )
        for occurrence in occurrence_results
        if isinstance(occurrence, dict) and occurrence.get("key")
    ]
    if records:
        index.upsert_records(records)
    return len(records)


def stream_gbif_into_index(
    species_names: list[str],
    *,
    staging: Path,
    occurrence_limit: int,
    occurrence_page_size: int,
    occurrence_workers: int,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if occurrence_limit < 0:
        raise ValueError("occurrence_limit must be zero or greater")
    if occurrence_page_size <= 0:
        raise ValueError("occurrence_page_size must be greater than zero")
    if occurrence_workers <= 0:
        raise ValueError("occurrence_workers must be greater than zero")

    retrieved_at = utc_now()
    client = GBIFClient()
    index = SourceIndex(staging / "source_index.sqlite")
    raw_dir = staging / "raw" / "gbif"
    raw_artifacts: list[str] = []
    taxon_keys: dict[str, int] = {}
    total_results: dict[str, int] = {}
    gaps: list[dict[str, object]] = []
    page_count = 0
    record_count = 0

    for requested_species in species_names:
        safe_name = safe_species_name(requested_species)
        match_url, match_payload = client.species_match(requested_species)
        match_path = write_raw_json(raw_dir, f"{safe_name}_match.json", match_payload)
        raw_artifacts.append(match_path.as_posix())
        usage_key = match_payload.get("usageKey")
        if not usage_key:
            gaps.append({"source": GBIF_SOURCE_ID, "lane": "taxonomy", "species": requested_species, "reason": "GBIF did not match this species name."})
            continue

        taxon_key = int(usage_key)
        taxon_keys[requested_species] = taxon_key
        taxonomy = taxonomy_record(
            requested_species,
            match_payload,
            match_url=match_url,
            raw_path=match_path,
            retrieved_at=retrieved_at,
        )
        index.upsert_records([taxonomy])
        record_count += 1

        if occurrence_limit == 0:
            continue
        first_page_limit = min(occurrence_page_size, occurrence_limit)
        first_page = fetch_occurrence_page(
            client,
            taxon_key=taxon_key,
            page_limit=first_page_limit,
            offset=0,
            raw_dir=raw_dir,
            safe_name=safe_name,
        )
        page_count += 1
        raw_artifacts.append(first_page[3].as_posix())
        first_payload = first_page[2]
        reported_count = int(first_payload.get("count") or 0)
        total_results[requested_species] = reported_count
        target_count = min(occurrence_limit, reported_count) if reported_count else occurrence_limit
        first_results = first_payload.get("results")
        first_result_count = len(first_results) if isinstance(first_results, list) else 0
        canonical_species = taxonomy.species or requested_species
        first_record_count = process_gbif_page(first_page, species=canonical_species, index=index, retrieved_at=retrieved_at)
        record_count += first_record_count
        if first_record_count == 0:
            gaps.append({"source": GBIF_SOURCE_ID, "lane": "observations", "species": requested_species, "reason": "GBIF returned no occurrence records for this species."})
            continue

        remaining_offsets = list(range(first_result_count, target_count, occurrence_page_size))
        batch_size = max(occurrence_workers * 2, occurrence_workers)
        for start in range(0, len(remaining_offsets), batch_size):
            offsets = remaining_offsets[start : start + batch_size]
            with ThreadPoolExecutor(max_workers=occurrence_workers) as executor:
                futures = [
                    executor.submit(
                        fetch_occurrence_page,
                        client,
                        taxon_key=taxon_key,
                        page_limit=min(occurrence_page_size, target_count - offset),
                        offset=offset,
                        raw_dir=raw_dir,
                        safe_name=safe_name,
                    )
                    for offset in offsets
                ]
                for future in as_completed(futures):
                    page = future.result()
                    page_count += 1
                    raw_artifacts.append(page[3].as_posix())
                    record_count += process_gbif_page(page, species=canonical_species, index=index, retrieved_at=retrieved_at)

    return (
        {
            "requested_species": species_names,
            "occurrence_limit": occurrence_limit,
            "occurrence_page_size": occurrence_page_size,
            "occurrence_workers": occurrence_workers,
            "total_results": total_results,
            "page_count": page_count,
            "taxon_keys": taxon_keys,
            "raw_artifacts": raw_artifacts,
            "record_count": record_count,
            "gap_count": len(gaps),
            "retrieved_at": retrieved_at,
        },
        gaps,
    )


def ingest_gbif(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_gbif_records_fn: Callable[..., object] = fetch_gbif_records,
) -> dict[str, object]:
    species = normalize_species(payload.get("species"), ["Aedes aegypti"])
    occurrence_limit = int(payload.get("occurrence_limit", 3))
    occurrence_page_size = int(payload.get("occurrence_page_size", 300))
    occurrence_workers = int(payload.get("occurrence_workers", 1))
    delay_seconds = float(payload.get("delay_seconds", 0))

    staging = artifact_dir.parent / f".{artifact_dir.name}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        if artifact_dir.exists():
            copy_artifact_to_staging(artifact_dir, staging)
        else:
            staging.mkdir(parents=True, exist_ok=True)
        index = SourceIndex(staging / "source_index.sqlite")
        index.initialize()
        index.delete_source(GBIF_SOURCE_ID)
        if fetch_gbif_records_fn is fetch_gbif_records:
            gbif_payload, new_gaps = stream_gbif_into_index(
                species,
                staging=staging,
                occurrence_limit=occurrence_limit,
                occurrence_page_size=occurrence_page_size,
                occurrence_workers=occurrence_workers,
            )
        else:
            result = fetch_gbif_records_fn(
                species,
                raw_dir=staging / "raw" / "gbif",
                occurrence_limit=occurrence_limit,
                occurrence_page_size=occurrence_page_size,
                occurrence_workers=occurrence_workers,
                delay_seconds=delay_seconds,
            )
            index.upsert_records(result.records)
            retrieved_at = result.records[0].provenance.retrieved_at if result.records else ""
            gbif_payload = {
                "requested_species": result.requested_species,
                "occurrence_limit": result.occurrence_limit,
                "occurrence_page_size": result.occurrence_page_size,
                "occurrence_workers": result.occurrence_workers,
                "total_results": result.total_results,
                "page_count": result.page_count,
                "taxon_keys": result.taxon_keys,
                "raw_artifacts": result.raw_artifacts,
                "record_count": len(result.records),
                "gap_count": len(result.gaps),
                "retrieved_at": retrieved_at,
            }
            new_gaps = result.gaps

        old_gaps = read_json(staging / "gaps.json", [])
        if not isinstance(old_gaps, list):
            old_gaps = []
        gaps = [gap for gap in old_gaps if not (isinstance(gap, dict) and gap.get("source") == GBIF_SOURCE_ID)]
        gaps.extend(new_gaps)
        response = write_gbif_metadata(staging, gbif_payload, gaps)
        response = rewrite_artifact_references(staging, artifact_dir, response)
        activate_staging_artifact(staging, artifact_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    response["activated_artifact_dir"] = str(artifact_dir)
    return response


def write_irmapper_metadata(staging: Path, irmapper_payload: dict[str, object], gaps: list[dict[str, object]]) -> dict[str, object]:
    index = SourceIndex(staging / "source_index.sqlite")
    summary = index.summary()
    counts = source_counts(index)
    generated_at = str(irmapper_payload["retrieved_at"])
    sources = [source for source in counts if source != IRMAPPER_SOURCE_ID]
    if counts.get(IRMAPPER_SOURCE_ID):
        sources.append(IRMAPPER_SOURCE_ID)

    status = read_json(staging / "source_status.json", {})
    if not isinstance(status, dict):
        status = {}
    status.update(
        {
            "ok": True,
            "source_id": sources[0] if sources else IRMAPPER_SOURCE_ID,
            "sources": sources,
            "source_counts": counts,
            "boundary": "Aedes aegypti first",
            "generated_at": generated_at,
            "fully_parsed": True,
            "record_count": summary["record_count"],
            "species_count": summary["species_count"],
            "lanes": summary["lanes"],
            "gap_count": len(gaps),
        }
    )

    receipt = read_json(staging / "source_receipt.json", {})
    if not isinstance(receipt, dict):
        receipt = {}
    receipt_sources = receipt.get("sources")
    if not isinstance(receipt_sources, dict):
        receipt_sources = {}
    receipt_sources[IRMAPPER_SOURCE_ID] = irmapper_payload
    receipt.update(
        {
            "source_id": sources[0] if sources else IRMAPPER_SOURCE_ID,
            "sources": receipt_sources,
            "artifact_dir": staging.as_posix(),
            "sqlite_index": (staging / "source_index.sqlite").as_posix(),
            "generated_at": generated_at,
            "record_count": summary["record_count"],
            "lanes": summary["lanes"],
            "irmapper": irmapper_payload,
        }
    )

    write_json(staging / "gaps.json", gaps)
    write_json(staging / "source_status.json", status)
    write_json(staging / "source_receipt.json", receipt)
    return {"ok": True, "artifact_dir": staging.as_posix(), **status, "irmapper": irmapper_payload}


def ingest_irmapper(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_irmapper_records_fn: Callable[..., object] = fetch_irmapper_records,
) -> dict[str, object]:
    species = str(payload.get("species") or DEFAULT_IRMAPPER_SPECIES)
    staging = artifact_dir.parent / f".{artifact_dir.name}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        if artifact_dir.exists():
            copy_artifact_to_staging(artifact_dir, staging)
        else:
            staging.mkdir(parents=True, exist_ok=True)
        index = SourceIndex(staging / "source_index.sqlite")
        index.initialize()
        index.delete_source(IRMAPPER_SOURCE_ID)
        retrieved_at = utc_now()
        result = fetch_irmapper_records_fn(
            raw_dir=staging / "raw" / "irmapper",
            species=species,
            retrieved_at=retrieved_at,
        )
        index.upsert_records(result.records)
        old_gaps = read_json(staging / "gaps.json", [])
        if not isinstance(old_gaps, list):
            old_gaps = []
        gaps = [gap for gap in old_gaps if not (isinstance(gap, dict) and gap.get("source") == IRMAPPER_SOURCE_ID)]
        gaps.extend(result.gaps)
        irmapper_payload = {
            "requested_species": result.requested_species,
            "fetched_row_count": result.fetched_row_count,
            "raw_artifacts": result.raw_artifacts,
            "record_count": len(result.records),
            "gap_count": len(result.gaps),
            "retrieved_at": retrieved_at,
        }
        response = write_irmapper_metadata(staging, irmapper_payload, gaps)
        response = rewrite_artifact_references(staging, artifact_dir, response)
        activate_staging_artifact(staging, artifact_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    response["activated_artifact_dir"] = str(artifact_dir)
    return response


def write_public_health_metadata(staging: Path, source_payload: dict[str, object], gaps: list[dict[str, object]]) -> dict[str, object]:
    index = SourceIndex(staging / "source_index.sqlite")
    summary = index.summary()
    counts = source_counts(index)
    generated_at = str(source_payload["retrieved_at"])
    sources = [source for source in counts if source != PUBLIC_HEALTH_SOURCE_ID]
    if counts.get(PUBLIC_HEALTH_SOURCE_ID):
        sources.append(PUBLIC_HEALTH_SOURCE_ID)

    status = read_json(staging / "source_status.json", {})
    if not isinstance(status, dict):
        status = {}
    status.update(
        {
            "ok": True,
            "source_id": sources[0] if sources else PUBLIC_HEALTH_SOURCE_ID,
            "sources": sources,
            "source_counts": counts,
            "boundary": "Aedes aegypti first",
            "generated_at": generated_at,
            "fully_parsed": True,
            "record_count": summary["record_count"],
            "species_count": summary["species_count"],
            "lanes": summary["lanes"],
            "gap_count": len(gaps),
        }
    )

    receipt = read_json(staging / "source_receipt.json", {})
    if not isinstance(receipt, dict):
        receipt = {}
    receipt_sources = receipt.get("sources")
    if not isinstance(receipt_sources, dict):
        receipt_sources = {}
    receipt_sources[PUBLIC_HEALTH_SOURCE_ID] = source_payload
    receipt.update(
        {
            "source_id": sources[0] if sources else PUBLIC_HEALTH_SOURCE_ID,
            "sources": receipt_sources,
            "artifact_dir": staging.as_posix(),
            "sqlite_index": (staging / "source_index.sqlite").as_posix(),
            "generated_at": generated_at,
            "record_count": summary["record_count"],
            "lanes": summary["lanes"],
            "public_health_guidance": source_payload,
        }
    )

    write_json(staging / "gaps.json", gaps)
    write_json(staging / "source_status.json", status)
    write_json(staging / "source_receipt.json", receipt)
    return {"ok": True, "artifact_dir": staging.as_posix(), **status, "public_health_guidance": source_payload}


def write_paho_dengue_surveillance_metadata(staging: Path, source_payload: dict[str, object], gaps: list[dict[str, object]]) -> dict[str, object]:
    index = SourceIndex(staging / "source_index.sqlite")
    summary = index.summary()
    counts = source_counts(index)
    generated_at = str(source_payload["retrieved_at"])
    sources = [source for source in counts if source != PAHO_DENGUE_SURVEILLANCE_SOURCE_ID]
    if counts.get(PAHO_DENGUE_SURVEILLANCE_SOURCE_ID):
        sources.append(PAHO_DENGUE_SURVEILLANCE_SOURCE_ID)

    status = read_json(staging / "source_status.json", {})
    if not isinstance(status, dict):
        status = {}
    status.update(
        {
            "ok": True,
            "source_id": sources[0] if sources else PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
            "sources": sources,
            "source_counts": counts,
            "boundary": "Aedes aegypti first",
            "generated_at": generated_at,
            "fully_parsed": not gaps,
            "parsed_scope": "PAHO dengue report/page grain; dashboard row-level data is complete only when no source gaps are present",
            "record_count": summary["record_count"],
            "species_count": summary["species_count"],
            "lanes": summary["lanes"],
            "gap_count": len(gaps),
        }
    )

    receipt = read_json(staging / "source_receipt.json", {})
    if not isinstance(receipt, dict):
        receipt = {}
    receipt_sources = receipt.get("sources")
    if not isinstance(receipt_sources, dict):
        receipt_sources = {}
    receipt_sources[PAHO_DENGUE_SURVEILLANCE_SOURCE_ID] = source_payload
    receipt.update(
        {
            "source_id": sources[0] if sources else PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
            "sources": receipt_sources,
            "artifact_dir": staging.as_posix(),
            "sqlite_index": (staging / "source_index.sqlite").as_posix(),
            "generated_at": generated_at,
            "record_count": summary["record_count"],
            "lanes": summary["lanes"],
            "aedes_paho_dengue_surveillance": source_payload,
        }
    )

    write_json(staging / "gaps.json", gaps)
    write_json(staging / "source_status.json", status)
    write_json(staging / "source_receipt.json", receipt)
    return {"ok": True, "artifact_dir": staging.as_posix(), **status, "aedes_paho_dengue_surveillance": source_payload}


def ingest_public_health(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_public_health_guidance_records_fn: Callable[..., object] = fetch_public_health_guidance_records,
) -> dict[str, object]:
    source_urls = payload.get("source_urls")
    if source_urls is None or source_urls == []:
        guidance_sources = list(DEFAULT_PUBLIC_HEALTH_SOURCES)
    elif isinstance(source_urls, list) and all(isinstance(item, str) for item in source_urls):
        guidance_sources = [
            {"organization": "custom", "url": url, "topic": "Aedes aegypti public health guidance"}
            for url in source_urls
        ]
    else:
        raise ValueError("source_urls must be a list of strings")

    raw_staging = artifact_dir.parent / f".{artifact_dir.name}.public-health-raw-staging"
    raw_final = artifact_dir / "raw" / "public_health_guidance"
    raw_backup = raw_final.parent / f".{raw_final.name}.previous"
    raw_activated = False
    if raw_staging.exists():
        shutil.rmtree(raw_staging)
    try:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        db_path = artifact_dir / "source_index.sqlite"
        index = SourceIndex(db_path)
        if not db_path.exists():
            index.initialize()
        retrieved_at = utc_now()
        result = fetch_public_health_guidance_records_fn(
            guidance_sources,
            raw_dir=raw_staging,
            retrieved_at=retrieved_at,
        )
        raw_staging.mkdir(parents=True, exist_ok=True)
        records = replace_record_path_strings(result.records, str(raw_staging), str(raw_final))
        raw_artifacts = [artifact.replace(str(raw_staging), str(raw_final)) for artifact in result.raw_artifacts]
        if raw_backup.exists():
            shutil.rmtree(raw_backup)
        if raw_final.exists():
            raw_final.replace(raw_backup)
        raw_final.parent.mkdir(parents=True, exist_ok=True)
        raw_staging.replace(raw_final)
        raw_activated = True
        replace_source_records(index, PUBLIC_HEALTH_SOURCE_ID, records)
        old_gaps = read_json(artifact_dir / "gaps.json", [])
        if not isinstance(old_gaps, list):
            old_gaps = []
        gaps = [gap for gap in old_gaps if not (isinstance(gap, dict) and gap.get("source") == PUBLIC_HEALTH_SOURCE_ID)]
        gaps.extend(result.gaps)
        source_payload = {
            "requested_urls": result.requested_urls,
            "raw_artifacts": raw_artifacts,
            "record_count": len(records),
            "gap_count": len(result.gaps),
            "retrieved_at": retrieved_at,
        }
        response = write_public_health_metadata(artifact_dir, source_payload, gaps)
    except Exception:
        shutil.rmtree(raw_staging, ignore_errors=True)
        if raw_activated and raw_backup.exists():
            if raw_final.exists():
                shutil.rmtree(raw_final)
            raw_backup.replace(raw_final)
        raise
    if raw_backup.exists():
        shutil.rmtree(raw_backup)
    response["activated_artifact_dir"] = str(artifact_dir)
    return response


def ingest_paho_dengue_surveillance(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_paho_dengue_surveillance_records_fn: Callable[..., object] = fetch_paho_dengue_surveillance_records,
) -> dict[str, object]:
    report_urls = payload.get("report_urls")
    if report_urls is None or report_urls == []:
        reports = list(DEFAULT_PAHO_DENGUE_REPORTS)
    elif isinstance(report_urls, list) and all(isinstance(item, str) for item in report_urls):
        reports = [
            {
                "organization": "PAHO/WHO",
                "url": url,
                "landing_url": url,
                "topic": "custom PAHO dengue surveillance report",
            }
            for url in report_urls
        ]
    else:
        raise ValueError("report_urls must be a list of strings")

    dashboard_pages = payload.get("dashboard_pages")
    if dashboard_pages is None or dashboard_pages == []:
        dashboard_urls = list(DEFAULT_PAHO_DENGUE_DASHBOARD_PAGES)
    elif isinstance(dashboard_pages, list) and all(isinstance(item, str) for item in dashboard_pages):
        dashboard_urls = dashboard_pages
    else:
        raise ValueError("dashboard_pages must be a list of strings")

    staging = artifact_dir.parent / f".{artifact_dir.name}.paho-dengue-surveillance-staging"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        if artifact_dir.exists():
            copy_artifact_to_staging(artifact_dir, staging)
        else:
            staging.mkdir(parents=True, exist_ok=True)
        index = SourceIndex(staging / "source_index.sqlite")
        index.initialize()
        index.delete_source(PAHO_DENGUE_SURVEILLANCE_SOURCE_ID)
        retrieved_at = utc_now()
        result = fetch_paho_dengue_surveillance_records_fn(
            reports,
            raw_dir=staging / "raw" / "paho_dengue_surveillance",
            retrieved_at=retrieved_at,
            dashboard_pages=dashboard_urls,
        )
        index.upsert_records(result.records)
        old_gaps = read_json(staging / "gaps.json", [])
        if not isinstance(old_gaps, list):
            old_gaps = []
        gaps = [gap for gap in old_gaps if not (isinstance(gap, dict) and gap.get("source") == PAHO_DENGUE_SURVEILLANCE_SOURCE_ID)]
        gaps.extend(result.gaps)
        source_payload = {
            "requested_urls": result.requested_urls,
            "raw_artifacts": result.raw_artifacts,
            "record_count": len(result.records),
            "gap_count": len(result.gaps),
            "report_count": result.report_count,
            "dashboard_page_count": result.dashboard_page_count,
            "retrieved_at": retrieved_at,
        }
        response = write_paho_dengue_surveillance_metadata(staging, source_payload, gaps)
        response = rewrite_artifact_references(staging, artifact_dir, response)
        activate_staging_artifact(staging, artifact_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    response["activated_artifact_dir"] = str(artifact_dir)
    return response


def write_mosquito_alert_metadata(staging: Path, source_payload: dict[str, object], gaps: list[dict[str, object]]) -> dict[str, object]:
    index = SourceIndex(staging / "source_index.sqlite")
    summary = index.summary()
    counts = source_counts(index)
    generated_at = str(source_payload["retrieved_at"])
    sources = [source for source in counts if source != MOSQUITO_ALERT_SOURCE_ID]
    if counts.get(MOSQUITO_ALERT_SOURCE_ID):
        sources.append(MOSQUITO_ALERT_SOURCE_ID)

    status = read_json(staging / "source_status.json", {})
    if not isinstance(status, dict):
        status = {}
    status.update(
        {
            "ok": True,
            "source_id": sources[0] if sources else MOSQUITO_ALERT_SOURCE_ID,
            "sources": sources,
            "source_counts": counts,
            "boundary": "Aedes aegypti first",
            "generated_at": generated_at,
            "fully_parsed": True,
            "record_count": summary["record_count"],
            "species_count": summary["species_count"],
            "lanes": summary["lanes"],
            "gap_count": len(gaps),
        }
    )

    receipt = read_json(staging / "source_receipt.json", {})
    if not isinstance(receipt, dict):
        receipt = {}
    receipt_sources = receipt.get("sources")
    if not isinstance(receipt_sources, dict):
        receipt_sources = {}
    receipt_sources[MOSQUITO_ALERT_SOURCE_ID] = source_payload
    receipt.update(
        {
            "source_id": sources[0] if sources else MOSQUITO_ALERT_SOURCE_ID,
            "sources": receipt_sources,
            "artifact_dir": staging.as_posix(),
            "sqlite_index": (staging / "source_index.sqlite").as_posix(),
            "generated_at": generated_at,
            "record_count": summary["record_count"],
            "lanes": summary["lanes"],
            "mosquito_alert": source_payload,
        }
    )

    write_json(staging / "gaps.json", gaps)
    write_json(staging / "source_status.json", status)
    write_json(staging / "source_receipt.json", receipt)
    return {"ok": True, "artifact_dir": staging.as_posix(), **status, "mosquito_alert": source_payload}


def ingest_mosquito_alert(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_mosquito_alert_records_fn: Callable[..., object] = fetch_mosquito_alert_records,
) -> dict[str, object]:
    occurrence_limit = int(payload.get("occurrence_limit") or 1000)
    occurrence_page_size = int(payload.get("occurrence_page_size") or 300)
    staging = artifact_dir.parent / f".{artifact_dir.name}.mosquito-alert-staging"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        staging.mkdir(parents=True, exist_ok=True)
        retrieved_at = utc_now()
        result = fetch_mosquito_alert_records_fn(
            raw_dir=staging / "raw" / "mosquito_alert",
            occurrence_limit=occurrence_limit,
            occurrence_page_size=occurrence_page_size,
            retrieved_at=retrieved_at,
        )
        old = staging.as_posix()
        new = artifact_dir.as_posix()
        records = replace_record_path_strings(result.records, old, new)
        raw_target = artifact_dir / "raw" / "mosquito_alert"
        raw_backup = raw_target.parent / ".mosquito_alert.previous"
        raw_target.parent.mkdir(parents=True, exist_ok=True)
        if raw_backup.exists():
            shutil.rmtree(raw_backup)
        if raw_target.exists():
            raw_target.replace(raw_backup)
        (staging / "raw" / "mosquito_alert").replace(raw_target)
        if raw_backup.exists():
            shutil.rmtree(raw_backup)

        index = SourceIndex(artifact_dir / "source_index.sqlite")
        index.initialize()
        index.replace_source_records(MOSQUITO_ALERT_SOURCE_ID, records)
        old_gaps = read_json(artifact_dir / "gaps.json", [])
        if not isinstance(old_gaps, list):
            old_gaps = []
        gaps = [gap for gap in old_gaps if not (isinstance(gap, dict) and gap.get("source") == MOSQUITO_ALERT_SOURCE_ID)]
        gaps.extend(result.gaps)
        raw_artifacts = replace_path_strings(result.raw_artifacts, old, new)
        if not isinstance(raw_artifacts, list):
            raw_artifacts = result.raw_artifacts
        source_payload = {
            "dataset_key": result.dataset_key,
            "dataset_doi": result.dataset_doi,
            "taxon_key": result.taxon_key,
            "occurrence_limit": result.occurrence_limit,
            "occurrence_page_size": result.occurrence_page_size,
            "total_results": result.total_results,
            "page_count": result.page_count,
            "raw_artifacts": raw_artifacts,
            "record_count": len(records),
            "gap_count": len(result.gaps),
            "retrieved_at": retrieved_at,
        }
        response = write_mosquito_alert_metadata(artifact_dir, source_payload, gaps)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(staging, ignore_errors=True)
    response["activated_artifact_dir"] = str(artifact_dir)
    return response


def write_dryad_behavior_video_metadata(staging: Path, source_payload: dict[str, object], gaps: list[dict[str, object]]) -> dict[str, object]:
    index = SourceIndex(staging / "source_index.sqlite")
    summary = index.summary()
    counts = source_counts(index)
    generated_at = str(source_payload["retrieved_at"])
    sources = [source for source in counts if source != DRYAD_BEHAVIOR_VIDEO_SOURCE_ID]
    if counts.get(DRYAD_BEHAVIOR_VIDEO_SOURCE_ID):
        sources.append(DRYAD_BEHAVIOR_VIDEO_SOURCE_ID)

    status = read_json(staging / "source_status.json", {})
    if not isinstance(status, dict):
        status = {}
    status.update(
        {
            "ok": True,
            "source_id": sources[0] if sources else DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
            "sources": sources,
            "source_counts": counts,
            "boundary": "Aedes aegypti first",
            "generated_at": generated_at,
            "fully_parsed": True,
            "record_count": summary["record_count"],
            "species_count": summary["species_count"],
            "lanes": summary["lanes"],
            "gap_count": len(gaps),
        }
    )

    receipt = read_json(staging / "source_receipt.json", {})
    if not isinstance(receipt, dict):
        receipt = {}
    receipt_sources = receipt.get("sources")
    if not isinstance(receipt_sources, dict):
        receipt_sources = {}
    receipt_sources[DRYAD_BEHAVIOR_VIDEO_SOURCE_ID] = source_payload
    receipt.update(
        {
            "source_id": sources[0] if sources else DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
            "sources": receipt_sources,
            "artifact_dir": staging.as_posix(),
            "sqlite_index": (staging / "source_index.sqlite").as_posix(),
            "generated_at": generated_at,
            "record_count": summary["record_count"],
            "lanes": summary["lanes"],
            "dryad_behavior_videos": source_payload,
        }
    )

    write_json(staging / "gaps.json", gaps)
    write_json(staging / "source_status.json", status)
    write_json(staging / "source_receipt.json", receipt)
    return {"ok": True, "artifact_dir": staging.as_posix(), **status, "dryad_behavior_videos": source_payload}


def ingest_dryad_behavior_videos(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_dryad_behavior_video_records_fn: Callable[..., object] = fetch_dryad_behavior_video_records,
) -> dict[str, object]:
    dois_payload = payload.get("dois")
    if dois_payload is not None and not (
        isinstance(dois_payload, list) and all(isinstance(doi, str) for doi in dois_payload)
    ):
        raise ValueError("dois must be a list of DOI strings")
    staging = artifact_dir.parent / f".{artifact_dir.name}.dryad-behavior-videos-staging"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        staging.mkdir(parents=True, exist_ok=True)
        retrieved_at = utc_now()
        if dois_payload:
            from .sources.dryad_behavior_videos import DryadDatasetSpec

            dataset_specs = [DryadDatasetSpec(doi=doi, behavior_labels=("behavior", "video")) for doi in dois_payload]
            result = fetch_dryad_behavior_video_records_fn(
                dataset_specs,
                raw_dir=staging / "raw" / "dryad_behavior_videos",
                retrieved_at=retrieved_at,
            )
        else:
            result = fetch_dryad_behavior_video_records_fn(
                raw_dir=staging / "raw" / "dryad_behavior_videos",
                retrieved_at=retrieved_at,
            )
        old = staging.as_posix()
        new = artifact_dir.as_posix()
        records = replace_record_path_strings(result.records, old, new)
        raw_target = artifact_dir / "raw" / "dryad_behavior_videos"
        raw_backup = raw_target.parent / ".dryad_behavior_videos.previous"
        raw_target.parent.mkdir(parents=True, exist_ok=True)
        if raw_backup.exists():
            shutil.rmtree(raw_backup)
        staged_raw = staging / "raw" / "dryad_behavior_videos"
        if staged_raw.exists():
            if raw_target.exists():
                raw_target.replace(raw_backup)
            staged_raw.replace(raw_target)
            if raw_backup.exists():
                shutil.rmtree(raw_backup)

        index = SourceIndex(artifact_dir / "source_index.sqlite")
        index.initialize()
        index.replace_source_records(DRYAD_BEHAVIOR_VIDEO_SOURCE_ID, records)
        old_gaps = read_json(artifact_dir / "gaps.json", [])
        if not isinstance(old_gaps, list):
            old_gaps = []
        gaps = [
            gap
            for gap in old_gaps
            if not (isinstance(gap, dict) and gap.get("source") == DRYAD_BEHAVIOR_VIDEO_SOURCE_ID)
        ]
        gaps.extend(result.gaps)
        raw_artifacts = replace_path_strings(result.raw_artifacts, old, new)
        if not isinstance(raw_artifacts, list):
            raw_artifacts = result.raw_artifacts
        source_payload = {
            "requested_dois": result.requested_dois,
            "dataset_count": result.dataset_count,
            "file_count": result.file_count,
            "media_file_count": result.media_file_count,
            "raw_artifacts": raw_artifacts,
            "record_count": len(records),
            "gap_count": len(result.gaps),
            "retrieved_at": retrieved_at,
        }
        response = write_dryad_behavior_video_metadata(artifact_dir, source_payload, gaps)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(staging, ignore_errors=True)
    response["activated_artifact_dir"] = str(artifact_dir)
    return response


def write_mendeley_behavior_media_metadata(staging: Path, source_payload: dict[str, object], gaps: list[dict[str, object]]) -> dict[str, object]:
    index = SourceIndex(staging / "source_index.sqlite")
    summary = index.summary()
    counts = source_counts(index)
    generated_at = str(source_payload["retrieved_at"])
    sources = [source for source in counts if source != MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID]
    if counts.get(MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID):
        sources.append(MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID)

    status = read_json(staging / "source_status.json", {})
    if not isinstance(status, dict):
        status = {}
    status.update(
        {
            "ok": True,
            "source_id": sources[0] if sources else MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
            "sources": sources,
            "source_counts": counts,
            "boundary": "Aedes aegypti first",
            "generated_at": generated_at,
            "fully_parsed": True,
            "record_count": summary["record_count"],
            "species_count": summary["species_count"],
            "lanes": summary["lanes"],
            "gap_count": len(gaps),
        }
    )

    receipt = read_json(staging / "source_receipt.json", {})
    if not isinstance(receipt, dict):
        receipt = {}
    receipt_sources = receipt.get("sources")
    if not isinstance(receipt_sources, dict):
        receipt_sources = {}
    receipt_sources[MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID] = source_payload
    receipt.update(
        {
            "source_id": sources[0] if sources else MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
            "sources": receipt_sources,
            "artifact_dir": staging.as_posix(),
            "sqlite_index": (staging / "source_index.sqlite").as_posix(),
            "generated_at": generated_at,
            "record_count": summary["record_count"],
            "lanes": summary["lanes"],
            "mendeley_behavior_media": source_payload,
        }
    )

    write_json(staging / "gaps.json", gaps)
    write_json(staging / "source_status.json", status)
    write_json(staging / "source_receipt.json", receipt)
    return {"ok": True, "artifact_dir": staging.as_posix(), **status, "mendeley_behavior_media": source_payload}


def ingest_mendeley_behavior_media(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_mendeley_behavior_media_records_fn: Callable[..., object] = fetch_mendeley_behavior_media_records,
) -> dict[str, object]:
    datasets_payload = payload.get("datasets")
    if datasets_payload is not None and not (
        isinstance(datasets_payload, list) and all(isinstance(dataset, str) for dataset in datasets_payload)
    ):
        raise ValueError("datasets must be a list of DATASET_ID:VERSION strings")
    staging = artifact_dir.parent / f".{artifact_dir.name}.mendeley-behavior-media-staging"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        staging.mkdir(parents=True, exist_ok=True)
        retrieved_at = utc_now()
        if datasets_payload:
            from .sources.mendeley_behavior_media import DEFAULT_MENDELEY_DATASETS, MendeleyDatasetSpec

            known = {f"{spec.dataset_id}:{spec.version}": spec for spec in DEFAULT_MENDELEY_DATASETS}
            dataset_specs = []
            for value in datasets_payload:
                dataset_id, _, version_text = value.partition(":")
                if not dataset_id or not version_text:
                    raise ValueError("datasets must be formatted as DATASET_ID:VERSION")
                version = int(version_text)
                dataset_specs.append(
                    known.get(
                        f"{dataset_id}:{version}",
                        MendeleyDatasetSpec(dataset_id=dataset_id, version=version, behavior_labels=("behavior", "media")),
                    )
                )
            result = fetch_mendeley_behavior_media_records_fn(
                dataset_specs,
                raw_dir=staging / "raw" / "mendeley_behavior_media",
                retrieved_at=retrieved_at,
            )
        else:
            result = fetch_mendeley_behavior_media_records_fn(
                raw_dir=staging / "raw" / "mendeley_behavior_media",
                retrieved_at=retrieved_at,
            )
        old = staging.as_posix()
        new = artifact_dir.as_posix()
        records = replace_record_path_strings(result.records, old, new)
        raw_target = artifact_dir / "raw" / "mendeley_behavior_media"
        raw_backup = raw_target.parent / ".mendeley_behavior_media.previous"
        raw_target.parent.mkdir(parents=True, exist_ok=True)
        if raw_backup.exists():
            shutil.rmtree(raw_backup)
        staged_raw = staging / "raw" / "mendeley_behavior_media"
        if staged_raw.exists():
            if raw_target.exists():
                raw_target.replace(raw_backup)
            staged_raw.replace(raw_target)
            if raw_backup.exists():
                shutil.rmtree(raw_backup)

        index = SourceIndex(artifact_dir / "source_index.sqlite")
        index.initialize()
        index.replace_source_records(MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID, records)
        old_gaps = read_json(artifact_dir / "gaps.json", [])
        if not isinstance(old_gaps, list):
            old_gaps = []
        gaps = [
            gap
            for gap in old_gaps
            if not (isinstance(gap, dict) and gap.get("source") == MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID)
        ]
        gaps.extend(result.gaps)
        raw_artifacts = replace_path_strings(result.raw_artifacts, old, new)
        if not isinstance(raw_artifacts, list):
            raw_artifacts = result.raw_artifacts
        source_payload = {
            "requested_datasets": result.requested_datasets,
            "dataset_count": result.dataset_count,
            "folder_count": result.folder_count,
            "file_count": result.file_count,
            "media_file_count": result.media_file_count,
            "table_file_count": result.table_file_count,
            "parsed_table_file_count": result.parsed_table_file_count,
            "skipped_table_file_count": result.skipped_table_file_count,
            "table_sheet_count": result.table_sheet_count,
            "table_row_count": result.table_row_count,
            "raw_artifacts": raw_artifacts,
            "record_count": len(records),
            "gap_count": len(result.gaps),
            "retrieved_at": retrieved_at,
        }
        response = write_mendeley_behavior_media_metadata(artifact_dir, source_payload, gaps)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(staging, ignore_errors=True)
    response["activated_artifact_dir"] = str(artifact_dir)
    return response


def ingest_osf_flighttrackai_videos(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_osf_flighttrackai_video_records_fn: Callable[..., object] = fetch_osf_flighttrackai_video_records,
) -> dict[str, object]:
    if payload:
        unexpected = sorted(payload)
        if unexpected:
            raise ValueError(f"unexpected OSF FlightTrackAI option(s): {', '.join(unexpected)}")
    from scripts.ingest_osf_flighttrackai_videos import ingest_osf_flighttrackai_videos as ingest_local

    result = ingest_local(
        artifact_dir=artifact_dir,
        fetch_json=None,
        retrieved_at=utc_now(),
    ) if fetch_osf_flighttrackai_video_records_fn is fetch_osf_flighttrackai_video_records else None
    if result is not None:
        result["activated_artifact_dir"] = str(artifact_dir)
        return result

    from scripts.ingest_osf_flighttrackai_videos import _update_metadata

    retrieved_at = utc_now()
    source_result = fetch_osf_flighttrackai_video_records_fn(
        raw_dir=artifact_dir / "raw" / "osf_flighttrackai_videos",
        retrieved_at=retrieved_at,
    )
    records = source_result.records
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.replace_source_records(OSF_FLIGHTTRACKAI_SOURCE_ID, records)
    response = _update_metadata(artifact_dir, source_result, retrieved_at)
    response["activated_artifact_dir"] = str(artifact_dir)
    return response


def write_pathogen_taxonomy_metadata(staging: Path, source_payload: dict[str, object], gaps: list[dict[str, object]]) -> dict[str, object]:
    index = SourceIndex(staging / "source_index.sqlite")
    summary = index.summary()
    counts = source_counts(index)
    generated_at = str(source_payload["retrieved_at"])
    sources = [source for source in counts if source != PATHOGEN_TAXONOMY_SOURCE_ID]
    if counts.get(PATHOGEN_TAXONOMY_SOURCE_ID):
        sources.append(PATHOGEN_TAXONOMY_SOURCE_ID)

    status = read_json(staging / "source_status.json", {})
    if not isinstance(status, dict):
        status = {}
    status.update(
        {
            "ok": True,
            "source_id": sources[0] if sources else PATHOGEN_TAXONOMY_SOURCE_ID,
            "sources": sources,
            "source_counts": counts,
            "boundary": "Aedes aegypti first",
            "generated_at": generated_at,
            "fully_parsed": True,
            "record_count": summary["record_count"],
            "species_count": summary["species_count"],
            "lanes": summary["lanes"],
            "gap_count": len(gaps),
        }
    )

    receipt = read_json(staging / "source_receipt.json", {})
    if not isinstance(receipt, dict):
        receipt = {}
    receipt_sources = receipt.get("sources")
    if not isinstance(receipt_sources, dict):
        receipt_sources = {}
    receipt_sources[PATHOGEN_TAXONOMY_SOURCE_ID] = source_payload
    receipt.update(
        {
            "source_id": sources[0] if sources else PATHOGEN_TAXONOMY_SOURCE_ID,
            "sources": receipt_sources,
            "artifact_dir": staging.as_posix(),
            "sqlite_index": (staging / "source_index.sqlite").as_posix(),
            "generated_at": generated_at,
            "record_count": summary["record_count"],
            "lanes": summary["lanes"],
            "pathogen_taxonomy": source_payload,
        }
    )

    write_json(staging / "gaps.json", gaps)
    write_json(staging / "source_status.json", status)
    write_json(staging / "source_receipt.json", receipt)
    return {"ok": True, "artifact_dir": staging.as_posix(), **status, "pathogen_taxonomy": source_payload}


def ingest_pathogen_taxonomy(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_pathogen_taxonomy_records_fn: Callable[..., object] = fetch_pathogen_taxonomy_records,
) -> dict[str, object]:
    staging = artifact_dir.parent / f".{artifact_dir.name}.pathogen-taxonomy-staging"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        staging.mkdir(parents=True, exist_ok=True)
        retrieved_at = utc_now()
        result = fetch_pathogen_taxonomy_records_fn(
            raw_dir=staging / "raw" / "pathogen_taxonomy",
            retrieved_at=retrieved_at,
        )
        old = staging.as_posix()
        new = artifact_dir.as_posix()
        records = replace_record_path_strings(result.records, old, new)
        raw_target = artifact_dir / "raw" / "pathogen_taxonomy"
        raw_backup = raw_target.parent / ".pathogen_taxonomy.previous"
        raw_target.parent.mkdir(parents=True, exist_ok=True)
        if raw_backup.exists():
            shutil.rmtree(raw_backup)
        staged_raw = staging / "raw" / "pathogen_taxonomy"
        if staged_raw.exists():
            if raw_target.exists():
                raw_target.replace(raw_backup)
            staged_raw.replace(raw_target)
            if raw_backup.exists():
                shutil.rmtree(raw_backup)

        index = SourceIndex(artifact_dir / "source_index.sqlite")
        index.initialize()
        index.replace_source_records(PATHOGEN_TAXONOMY_SOURCE_ID, records)
        old_gaps = read_json(artifact_dir / "gaps.json", [])
        if not isinstance(old_gaps, list):
            old_gaps = []
        gaps = [
            gap
            for gap in old_gaps
            if not (isinstance(gap, dict) and gap.get("source") == PATHOGEN_TAXONOMY_SOURCE_ID)
        ]
        gaps.extend(result.gaps)
        raw_artifacts = replace_path_strings(result.raw_artifacts, old, new)
        if not isinstance(raw_artifacts, list):
            raw_artifacts = result.raw_artifacts
        source_payload = {
            "requested_taxids": result.requested_taxids,
            "pathogen_count": result.pathogen_count,
            "raw_artifacts": raw_artifacts,
            "record_count": len(records),
            "gap_count": len(result.gaps),
            "retrieved_at": retrieved_at,
        }
        response = write_pathogen_taxonomy_metadata(artifact_dir, source_payload, gaps)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(staging, ignore_errors=True)
    response["activated_artifact_dir"] = str(artifact_dir)
    return response


def ingest_resistance_markers(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_resistance_markers import ingest_resistance_markers as ingest_resistance_markers_script

    _ = payload
    return ingest_resistance_markers_script(artifact_dir=artifact_dir)


def ingest_occurrence_ecology(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_occurrence_ecology import ingest_occurrence_ecology as ingest_occurrence_ecology_script

    _ = payload
    return ingest_occurrence_ecology_script(artifact_dir=artifact_dir)


def ingest_vectorbase_genomics_staged(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_vectorbase_genomics_records_fn: Callable[..., object],
) -> dict[str, object]:
    from scripts.ingest_vectorbase_genomics import ingest_vectorbase_genomics

    file_urls = payload.get("file_urls")
    if file_urls is not None and not isinstance(file_urls, dict):
        raise ValueError("file_urls must be an object")

    staging = artifact_dir.parent / f".{artifact_dir.name}.vectorbase-staging"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        if artifact_dir.exists():
            prepare_mutable_staging(artifact_dir, staging)
        else:
            staging.mkdir(parents=True, exist_ok=True)
        result = ingest_vectorbase_genomics(
            artifact_dir=staging,
            file_urls=file_urls,
            fetch_vectorbase_genomics_records_fn=fetch_vectorbase_genomics_records_fn,
        )
        response = rewrite_artifact_references(staging, artifact_dir, result)
        activate_source_staging(staging, artifact_dir, Path("raw") / "vectorbase_genomics")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    response["activated_artifact_dir"] = str(artifact_dir)
    response["staged"] = True
    return response


def ingest_ncbi_biosamples_staged(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_ncbi_biosample_records_fn: Callable[..., object],
) -> dict[str, object]:
    from scripts.ingest_ncbi_biosamples import ingest_ncbi_biosamples

    staging = artifact_dir.parent / f".{artifact_dir.name}.ncbi-biosamples-staging"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        if artifact_dir.exists():
            prepare_mutable_staging(artifact_dir, staging)
        else:
            staging.mkdir(parents=True, exist_ok=True)
        result = ingest_ncbi_biosamples(
            artifact_dir=staging,
            species=str(payload.get("species") or DEFAULT_BIOSAMPLE_SPECIES),
            limit=int(payload.get("limit") or 1000),
            page_size=int(payload.get("page_size") or 200),
            delay_seconds=float(payload.get("delay_seconds") if payload.get("delay_seconds") is not None else 0.34),
            fetch_ncbi_biosample_records_fn=fetch_ncbi_biosample_records_fn,
        )
        response = rewrite_artifact_references(staging, artifact_dir, result)
        activate_source_staging(staging, artifact_dir, Path("raw") / "ncbi_biosamples")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    response["activated_artifact_dir"] = str(artifact_dir)
    response["staged"] = True
    return response


def ingest_extracted_facts_staged(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_extracted_facts import ingest_extracted_facts

    retrieved_at = payload.get("retrieved_at")
    if retrieved_at is not None and not isinstance(retrieved_at, str):
        raise ValueError("retrieved_at must be a string")
    max_fulltext_units_value = payload.get("max_fulltext_units")
    max_fulltext_units = 5000 if max_fulltext_units_value is None else int(max_fulltext_units_value)
    if max_fulltext_units < 1:
        raise ValueError("max_fulltext_units must be positive")
    discover_supplements = bool(payload.get("discover_supplements"))
    download_supplements = bool(payload.get("download_supplements"))
    max_supplement_discovery_records_value = payload.get("max_supplement_discovery_records")
    max_supplement_discovery_records = (
        500 if max_supplement_discovery_records_value is None else int(max_supplement_discovery_records_value)
    )
    if max_supplement_discovery_records < 1:
        raise ValueError("max_supplement_discovery_records must be positive")
    max_supplement_files_value = payload.get("max_supplement_files")
    max_supplement_files = 100 if max_supplement_files_value is None else int(max_supplement_files_value)
    if max_supplement_files < 1:
        raise ValueError("max_supplement_files must be positive")
    max_supplement_bytes_value = payload.get("max_supplement_bytes")
    max_supplement_bytes = 2_000_000 if max_supplement_bytes_value is None else int(max_supplement_bytes_value)
    if max_supplement_bytes < 1:
        raise ValueError("max_supplement_bytes must be positive")

    staging = artifact_dir.parent / f".{artifact_dir.name}.extracted-facts-staging"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        if artifact_dir.exists():
            prepare_mutable_staging(artifact_dir, staging)
        else:
            staging.mkdir(parents=True, exist_ok=True)
        result = ingest_extracted_facts(
            artifact_dir=staging,
            retrieved_at=retrieved_at,
            max_fulltext_units=max_fulltext_units,
            discover_supplements=discover_supplements,
            download_supplements=download_supplements,
            max_supplement_discovery_records=max_supplement_discovery_records,
            max_supplement_files=max_supplement_files,
            max_supplement_bytes=max_supplement_bytes,
        )
        response = rewrite_artifact_references(staging, artifact_dir, result, source="aedes_extracted_facts")
        activate_source_staging(staging, artifact_dir, Path("raw") / "extracted_facts")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    response["activated_artifact_dir"] = str(artifact_dir)
    response["staged"] = True
    return response


def _payload_bool(payload: dict[str, object], key: str, default: bool = False) -> bool:
    value = payload.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _payload_string_list(payload: dict[str, object], key: str) -> list[str]:
    value = payload.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise ValueError(f"{key} must be a list of strings")


def ingest_video_atoms_staged(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_video_atoms import ingest_video_atoms

    retrieved_at = payload.get("retrieved_at")
    if retrieved_at is not None and not isinstance(retrieved_at, str):
        raise ValueError("retrieved_at must be a string")
    max_video_bytes = int(payload.get("max_video_bytes") or 750_000_000)
    if max_video_bytes < 1:
        raise ValueError("max_video_bytes must be positive")
    max_discovery_results = int(payload.get("max_discovery_results") or 1000)
    if max_discovery_results < 1:
        raise ValueError("max_discovery_results must be positive")
    allowed_licenses = _payload_string_list(payload, "allowed_licenses") or None
    motion_table_paths = [Path(path) for path in _payload_string_list(payload, "motion_table_paths")]

    staging = artifact_dir.parent / f".{artifact_dir.name}.video-atoms-staging"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        if artifact_dir.exists():
            prepare_mutable_staging(artifact_dir, staging)
            copy_relative_inputs_to_staging(artifact_dir, staging, motion_table_paths)
        else:
            staging.mkdir(parents=True, exist_ok=True)
        result = ingest_video_atoms(
            artifact_dir=staging,
            retrieved_at=retrieved_at,
            max_video_bytes=max_video_bytes,
            mirror_videos=_payload_bool(payload, "mirror_videos"),
            generate_artifacts=_payload_bool(payload, "generate_artifacts"),
            discover_sources=_payload_bool(payload, "discover_sources"),
            allow_unclear_license=_payload_bool(payload, "allow_unclear_license"),
            allowed_licenses=allowed_licenses,
            max_discovery_results=max_discovery_results,
            motion_table_paths=motion_table_paths,
        )
        response = rewrite_artifact_references(staging, artifact_dir, result, source="aedes_video_atoms")
        activate_source_staging(staging, artifact_dir, Path("raw") / "video_atoms")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    response["activated_artifact_dir"] = str(artifact_dir)
    response["staged"] = True
    return response


def dispatch_request(
    method: str,
    path: str,
    payload: dict[str, object] | None,
    *,
    headers: object,
    artifact_dir: Path,
    token: str,
    build_source_index_fn: Callable[..., dict[str, object]] = build_source_index,
    fetch_gbif_records_fn: Callable[..., object] = fetch_gbif_records,
    fetch_dryad_behavior_video_records_fn: Callable[..., object] = fetch_dryad_behavior_video_records,
    fetch_inaturalist_records_fn: Callable[..., object] = fetch_inaturalist_records,
    fetch_irmapper_records_fn: Callable[..., object] = fetch_irmapper_records,
    fetch_mendeley_behavior_media_records_fn: Callable[..., object] = fetch_mendeley_behavior_media_records,
    fetch_mosquito_alert_records_fn: Callable[..., object] = fetch_mosquito_alert_records,
    fetch_ncbi_biosample_records_fn: Callable[..., object] = fetch_ncbi_biosample_records,
    fetch_osf_flighttrackai_video_records_fn: Callable[..., object] = fetch_osf_flighttrackai_video_records,
    fetch_pathogen_taxonomy_records_fn: Callable[..., object] = fetch_pathogen_taxonomy_records,
    fetch_public_health_guidance_records_fn: Callable[..., object] = fetch_public_health_guidance_records,
    fetch_paho_dengue_surveillance_records_fn: Callable[..., object] = fetch_paho_dengue_surveillance_records,
    fetch_vectorbase_genomics_records_fn: Callable[..., object] = fetch_vectorbase_genomics_records,
) -> Response:
    if not is_authorized(headers, token):
        return json_response(401, {"ok": False, "error": "unauthorized"})

    index = SourceIndex(artifact_dir / "source_index.sqlite")
    try:
        if method == "GET" and path == "/health":
            return json_response(200, health_payload(artifact_dir))
        if method == "GET" and path == "/summary":
            return json_response(200, index.summary())
        if method == "GET" and path == "/sources":
            return json_response(200, {"ok": True, "sources": read_sources(artifact_dir), "artifact_dir": str(artifact_dir)})
        if method == "POST" and path == "/ask":
            body = payload or {}
            question = str(body.get("question", ""))
            limit = int(body.get("limit", 5))
            return json_response(200, answer_question(question, artifact_dir=artifact_dir, limit=limit))
        if method == "POST" and path == "/search":
            body = payload or {}
            query = str(body.get("query", ""))
            lane_value = body.get("lane")
            lane = str(lane_value) if lane_value is not None else None
            limit = int(body.get("limit", 10))
            if lane == "literature_fulltext":
                rows = [record.to_row() for record in index.search_literature_fulltext(query, limit=limit)]
            else:
                rows = [record.to_row() for record in index.search(query, lane=lane, limit=limit)]
            return json_response(200, {"ok": True, "rows": rows})
        if method == "POST" and path == "/sql":
            body = payload or {}
            sql = str(body.get("sql", ""))
            limit = int(body.get("limit", 100))
            return json_response(200, {"ok": True, "rows": index.sql(sql, limit=limit)})
        if method == "POST" and path == "/ingest/inaturalist":
            result = ingest_inaturalist(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_inaturalist_records_fn=fetch_inaturalist_records_fn,
            )
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/gbif":
            result = ingest_gbif(payload or {}, artifact_dir=artifact_dir, fetch_gbif_records_fn=fetch_gbif_records_fn)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/irmapper":
            result = ingest_irmapper(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_irmapper_records_fn=fetch_irmapper_records_fn,
            )
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/public-health":
            result = ingest_public_health(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_public_health_guidance_records_fn=fetch_public_health_guidance_records_fn,
            )
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/paho-dengue-surveillance":
            result = ingest_paho_dengue_surveillance(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_paho_dengue_surveillance_records_fn=fetch_paho_dengue_surveillance_records_fn,
            )
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/vectorbase-genomics":
            result = ingest_vectorbase_genomics_staged(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_vectorbase_genomics_records_fn=fetch_vectorbase_genomics_records_fn,
            )
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/mosquito-alert":
            result = ingest_mosquito_alert(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_mosquito_alert_records_fn=fetch_mosquito_alert_records_fn,
            )
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/dryad-behavior-videos":
            result = ingest_dryad_behavior_videos(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_dryad_behavior_video_records_fn=fetch_dryad_behavior_video_records_fn,
            )
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/mendeley-behavior-media":
            result = ingest_mendeley_behavior_media(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_mendeley_behavior_media_records_fn=fetch_mendeley_behavior_media_records_fn,
            )
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/osf-flighttrackai-videos":
            result = ingest_osf_flighttrackai_videos(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_osf_flighttrackai_video_records_fn=fetch_osf_flighttrackai_video_records_fn,
            )
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/pathogen-taxonomy":
            result = ingest_pathogen_taxonomy(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_pathogen_taxonomy_records_fn=fetch_pathogen_taxonomy_records_fn,
            )
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/ncbi-biosamples":
            result = ingest_ncbi_biosamples_staged(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_ncbi_biosample_records_fn=fetch_ncbi_biosample_records_fn,
            )
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/vector-competence-assays":
            from scripts.ingest_vector_competence_assays import ingest_vector_competence_assays

            result = ingest_vector_competence_assays(artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/resistance-markers":
            result = ingest_resistance_markers(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/extracted-facts":
            result = ingest_extracted_facts_staged(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/video-atoms":
            result = ingest_video_atoms_staged(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/occurrence-ecology":
            result = ingest_occurrence_ecology(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
    except (sqlite3.Error, ValueError) as exc:
        return json_response(400, {"ok": False, "error": str(exc)})
    except Exception as exc:
        return json_response(500, {"ok": False, "error": str(exc)})

    return json_response(404, {"ok": False, "error": f"unknown route: {method} {path}"})


class AskInsectsHandler(BaseHTTPRequestHandler):
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR
    token: str = ""

    def _read_payload(self) -> dict[str, object] | None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return None
        raw = self.rfile.read(length).decode("utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("request JSON must be an object")
        return payload

    def _send(self, response: Response) -> None:
        body = json.dumps(response.payload, sort_keys=True).encode("utf-8")
        self.send_response(response.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        response = dispatch_request(
            "GET",
            self.path.split("?", 1)[0],
            None,
            headers=self.headers,
            artifact_dir=self.artifact_dir,
            token=self.token,
        )
        self._send(response)

    def do_POST(self) -> None:
        try:
            payload = self._read_payload()
            response = dispatch_request(
                "POST",
                self.path.split("?", 1)[0],
                payload,
                headers=self.headers,
                artifact_dir=self.artifact_dir,
                token=self.token,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            response = json_response(400, {"ok": False, "error": str(exc)})
        self._send(response)


def run_server(host: str, port: int, artifact_dir: Path, token: str) -> None:
    handler = type("ConfiguredAskInsectsHandler", (AskInsectsHandler,), {"artifact_dir": artifact_dir, "token": token})
    server = ThreadingHTTPServer((host, port), handler)
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ask-insects-server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    args = parser.parse_args(argv)

    token = os.environ.get("ASK_INSECTS_TOKEN", "")
    if not token:
        raise SystemExit("ASK_INSECTS_TOKEN is required")
    run_server(args.host, args.port, Path(args.artifact_dir), token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
