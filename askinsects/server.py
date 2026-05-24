from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
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


def rewrite_artifact_references(staging: Path, artifact_dir: Path, result: dict[str, object]) -> dict[str, object]:
    old = str(staging)
    new = str(artifact_dir)
    for path in (staging / "source_status.json", staging / "source_receipt.json", staging / "gaps.json"):
        if path.exists():
            text = path.read_text(encoding="utf-8").replace(old, new)
            path.write_text(text, encoding="utf-8")
    db_path = staging / "source_index.sqlite"
    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE records SET provenance_json = replace(provenance_json, ?, ?)", (old, new))
            try:
                conn.execute("UPDATE record_payloads SET provenance_json = replace(provenance_json, ? , ?)", (old, new))
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
            raw_artifacts.append(raw_path.as_posix())
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
                        raw_path=raw_path,
                        retrieved_at=retrieved_at,
                    )
                )
                page_records.append(
                    media_record(
                        observation,
                        photo,
                        species=species,
                        raw_path=raw_path,
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
            shutil.copytree(artifact_dir, staging)
        else:
            staging.mkdir(parents=True, exist_ok=True)
        result = fetch_inaturalist_records_fn(
            species,
            raw_dir=staging / "raw" / "inaturalist",
            place=place,
            observation_limit=observation_limit,
            page_size=page_size,
            delay_seconds=delay_seconds,
        )
        index = SourceIndex(staging / "source_index.sqlite")
        index.initialize()
        index.delete_source(INATURALIST_SOURCE_ID)
        if fetch_inaturalist_records_fn is fetch_inaturalist_records:
            inaturalist_payload, new_gaps = stream_inaturalist_into_index(
                species,
                staging=staging,
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
        response = rewrite_artifact_references(staging, artifact_dir, response)
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
            shutil.copytree(artifact_dir, staging)
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
    fetch_inaturalist_records_fn: Callable[..., object] = fetch_inaturalist_records,
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
