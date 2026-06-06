from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
import hashlib
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
from .sources.extracted_facts import DEFAULT_MAX_SUPPLEMENT_BYTES
from .sources.aedes_deep_sources import fetch_aedes_deep_source_records
from .sources.cdc_dengue_surveillance import (
    CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
    DEFAULT_CDC_DENGUE_PAGES,
    fetch_cdc_dengue_surveillance_records,
)
from .sources.ncvbdc_dengue_surveillance import (
    DEFAULT_NCVBDC_DENGUE_PAGE,
    NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID,
    fetch_ncvbdc_dengue_surveillance_records,
)
from .sources.opendatasus_dengue_surveillance import (
    OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID,
    default_opendatasus_dengue_file_specs,
    fetch_opendatasus_dengue_surveillance_records,
)
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
from .sources.harvard_dataverse_suitability import fetch_harvard_dataverse_suitability_records
from .sources.irmapper import DEFAULT_IRMAPPER_SPECIES, IRMAPPER_SOURCE_ID, fetch_irmapper_records
from .sources.mendeley_behavior_media import MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID, fetch_mendeley_behavior_media_records
from .sources.mosquito_alert import MOSQUITO_ALERT_SOURCE_ID, fetch_mosquito_alert_records
from .sources.ncbi_biosample import DEFAULT_BIOSAMPLE_SPECIES, fetch_ncbi_biosample_records
from .sources.ncbi_snp_variation import DEFAULT_SNP_SPECIES, fetch_ncbi_snp_variation_records
from .sources.osf_flighttrackai_videos import OSF_FLIGHTTRACKAI_SOURCE_ID, fetch_osf_flighttrackai_video_records
from .sources.pathogen_taxonomy import PATHOGEN_TAXONOMY_SOURCE_ID, fetch_pathogen_taxonomy_records
from .sources.pmc_videos import PMC_VIDEO_SOURCE_ID, fetch_pmc_video_records
from .sources.paho_surveillance import (
    DEFAULT_PAHO_CORE_INDICATOR_PAGES,
    DEFAULT_PAHO_DENGUE_DASHBOARD_PAGES,
    DEFAULT_PAHO_DENGUE_REPORTS,
    PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
    fetch_paho_dengue_surveillance_records,
)
from .sources.who_dengue_surveillance import (
    DEFAULT_WHO_DENGUE_SURVEILLANCE_PAGES,
    WHO_DENGUE_SURVEILLANCE_SOURCE_ID,
    fetch_who_dengue_surveillance_records,
    who_dengue_source_spec,
)
from .sources.who_malaria_threats_resistance import fetch_who_malaria_threats_resistance_records
from .sources.public_health import (
    DEFAULT_PUBLIC_HEALTH_SOURCES,
    PUBLIC_HEALTH_SOURCE_ID,
    fetch_public_health_guidance_records,
)
from .sources.figshare_aedes_videos import DEFAULT_FIGSHARE_PAGE_SIZE, FIGSHARE_AEDES_VIDEO_SOURCE_ID, fetch_figshare_aedes_video_records
from .sources.vectorbase_genomics import fetch_vectorbase_genomics_records
from .sources.vectornet_surveillance import (
    DEFAULT_VECTORNET_SPECIES,
    VECTORNET_SOURCE_ID,
    fetch_vectornet_surveillance_records,
)
from .sources.zenodo_aedes_videos import DEFAULT_ZENODO_SIZE, ZENODO_AEDES_VIDEO_SOURCE_ID, fetch_zenodo_aedes_video_records


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


def source_index_readiness(artifact_dir: Path) -> tuple[bool, str | None]:
    db_path = artifact_dir / "source_index.sqlite"
    if not db_path.exists():
        return False, "source_index_missing"
    if db_path.stat().st_size == 0:
        return False, "source_index_empty"
    try:
        with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True) as conn:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='records'"
            ).fetchone()
    except sqlite3.Error as exc:
        return False, f"source_index_unreadable:{exc}"
    if row is None:
        return False, "source_index_missing_records_table"
    return True, None


def source_index_unavailable_response(artifact_dir: Path, reason: str | None) -> Response:
    db_path = artifact_dir / "source_index.sqlite"
    return json_response(
        503,
        {
            "ok": False,
            "error": "source_index_unavailable",
            "reason": reason or "unknown",
            "artifact_dir": str(artifact_dir),
            "db_path": str(db_path),
            "db_exists": db_path.exists(),
            "status_exists": (artifact_dir / "source_status.json").exists(),
        },
    )


def health_payload(artifact_dir: Path) -> dict[str, object]:
    db_path = artifact_dir / "source_index.sqlite"
    status_path = artifact_dir / "source_status.json"
    ready, reason = source_index_readiness(artifact_dir)
    payload: dict[str, object] = {
        "ok": ready and status_path.exists(),
        "db_exists": db_path.exists(),
        "status_exists": status_path.exists(),
        "db_path": str(db_path),
        "artifact_dir": str(artifact_dir),
        "sources": read_sources(artifact_dir),
    }
    if not ready:
        payload["error"] = "source_index_unavailable"
        payload["reason"] = reason
    else:
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
        payload = record.payload
        if payload is not None:
            rewritten_payload = replace_path_strings(payload, old, new)
            if not isinstance(rewritten_payload, dict):
                rewritten_payload = payload
        else:
            rewritten_payload = None
        rewritten.append(replace(record, provenance=provenance, payload=rewritten_payload))
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
    moved_to_backup = False
    if artifact_dir.exists():
        artifact_dir.replace(backup)
        moved_to_backup = True
    try:
        staging.replace(artifact_dir)
    except Exception:
        # Roll back: if the swap-in failed, restore the live directory we moved
        # aside so a failed activation never strands the live index in .previous.
        if moved_to_backup and not artifact_dir.exists():
            backup.replace(artifact_dir)
        raise
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

VOLATILE_ARTIFACT_FILES = {
    "source_index.sqlite-journal",
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
    shutil.copytree(
        artifact_dir,
        staging,
        ignore=shutil.ignore_patterns(*VOLATILE_ARTIFACT_FILES),
        copy_function=_copy_for_staging,
    )


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


def copy_default_video_motion_inputs_to_staging(artifact_dir: Path, staging: Path) -> None:
    copy_relative_inputs_to_staging(
        artifact_dir,
        staging,
        [
            Path("raw") / "video_atoms",
            Path("raw") / "mendeley_behavior_media" / "table_files",
            Path("raw") / "mendeley_behavior_media",
        ],
    )


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


def _record_content_parts(record: object) -> tuple[object, ...]:
    return (
        getattr(record, "record_id"),
        getattr(record, "lane"),
        getattr(record, "source"),
        getattr(record, "title"),
        getattr(record, "text"),
        getattr(record, "species"),
        getattr(record, "url"),
        getattr(record, "media_url"),
        getattr(record, "payload"),
    )


def records_content_digest(records: list[object]) -> str:
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: str(getattr(item, "record_id"))):
        digest.update(json.dumps(_record_content_parts(record), sort_keys=True, default=str).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def source_content_digest(index: SourceIndex, source: str) -> str:
    digest = hashlib.sha256()
    with index.connect() as conn:
        rows = conn.execute(
            """
            SELECT
              r.record_id,
              r.lane,
              r.source,
              r.title,
              r.text,
              r.species,
              r.url,
              r.media_url,
              p.payload_json
            FROM records r
            LEFT JOIN record_payloads p ON p.record_id = r.record_id
            WHERE r.source = ?
            ORDER BY r.record_id
            """,
            (source,),
        ).fetchall()
    for row in rows:
        payload = json.loads(row["payload_json"]) if row["payload_json"] else None
        digest.update(
            json.dumps(
                (
                    row["record_id"],
                    row["lane"],
                    row["source"],
                    row["title"],
                    row["text"],
                    row["species"],
                    row["url"],
                    row["media_url"],
                    payload,
                ),
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        )
        digest.update(b"\n")
    return digest.hexdigest()


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
    artifact_dir.mkdir(parents=True, exist_ok=True)
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    retrieved_at = utc_now()
    result = fetch_irmapper_records_fn(
        raw_dir=artifact_dir / "raw" / "irmapper",
        species=species,
        retrieved_at=retrieved_at,
    )
    existing_digest = source_content_digest(index, IRMAPPER_SOURCE_ID)
    fetched_digest = records_content_digest(result.records)
    records_unchanged = existing_digest == fetched_digest
    if not records_unchanged:
        index.replace_source_records(IRMAPPER_SOURCE_ID, result.records)
    old_gaps = read_json(artifact_dir / "gaps.json", [])
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
        "records_unchanged": records_unchanged,
    }
    response = write_irmapper_metadata(artifact_dir, irmapper_payload, gaps)
    response["activated_artifact_dir"] = str(artifact_dir)
    response["staged"] = False
    response["records_unchanged"] = records_unchanged
    return response


def ingest_who_malaria_threats_resistance(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_who_malaria_threats_resistance_records_fn: Callable[..., object] = fetch_who_malaria_threats_resistance_records,
) -> dict[str, object]:
    from scripts.ingest_who_malaria_threats_resistance import ingest_who_malaria_threats_resistance as ingest_script

    return ingest_script(
        artifact_dir=artifact_dir,
        species=str(payload.get("species") or "Aedes aegypti"),
        sample_limit=int(payload.get("sample_limit") or 5),
        aedes_limit=int(payload.get("aedes_limit") or 100),
        fetch_who_malaria_threats_resistance_records_fn=fetch_who_malaria_threats_resistance_records_fn,
    )


def ingest_harvard_dataverse_suitability(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_harvard_dataverse_suitability_records_fn: Callable[..., object] = fetch_harvard_dataverse_suitability_records,
) -> dict[str, object]:
    from askinsects.sources.harvard_dataverse_suitability import DEFAULT_QUERIES
    from scripts.ingest_harvard_dataverse_suitability import ingest_harvard_dataverse_suitability as ingest_script

    queries = payload.get("queries")
    query_tuple = tuple(str(query) for query in queries) if isinstance(queries, list) and queries else DEFAULT_QUERIES
    return ingest_script(
        artifact_dir=artifact_dir,
        queries=query_tuple,
        per_page=int(payload.get("per_page") or 25),
        dataset_limit=int(payload.get("dataset_limit") or 12),
        fetch_harvard_dataverse_suitability_records_fn=fetch_harvard_dataverse_suitability_records_fn,
    )


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
            "parsed_scope": "PAHO dengue report/page grain plus annual Core Indicators ZIP/CSV rows; weekly dashboard row-level data is complete only when no source gaps are present",
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


def write_who_dengue_surveillance_metadata(staging: Path, source_payload: dict[str, object], gaps: list[dict[str, object]]) -> dict[str, object]:
    index = SourceIndex(staging / "source_index.sqlite")
    summary = index.summary()
    counts = source_counts(index)
    generated_at = str(source_payload["retrieved_at"])
    sources = [source for source in counts if source != WHO_DENGUE_SURVEILLANCE_SOURCE_ID]
    if counts.get(WHO_DENGUE_SURVEILLANCE_SOURCE_ID):
        sources.append(WHO_DENGUE_SURVEILLANCE_SOURCE_ID)

    status = read_json(staging / "source_status.json", {})
    if not isinstance(status, dict):
        status = {}
    status.update(
        {
            "ok": True,
            "source_id": sources[0] if sources else WHO_DENGUE_SURVEILLANCE_SOURCE_ID,
            "sources": sources,
            "source_counts": counts,
            "boundary": "Aedes aegypti first",
            "generated_at": generated_at,
            "fully_parsed": not gaps,
            "parsed_scope": "WHO page/report/dashboard-locator grain; dashboard row-level data is complete only when no WHO source gaps are present",
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
    receipt_sources[WHO_DENGUE_SURVEILLANCE_SOURCE_ID] = source_payload
    receipt.update(
        {
            "source_id": sources[0] if sources else WHO_DENGUE_SURVEILLANCE_SOURCE_ID,
            "sources": receipt_sources,
            "source_counts": counts,
            "artifact_dir": staging.as_posix(),
            "sqlite_index": (staging / "source_index.sqlite").as_posix(),
            "generated_at": generated_at,
            "record_count": summary["record_count"],
            "lanes": summary["lanes"],
            WHO_DENGUE_SURVEILLANCE_SOURCE_ID: source_payload,
        }
    )

    write_json(staging / "gaps.json", gaps)
    write_json(staging / "source_status.json", status)
    write_json(staging / "source_receipt.json", receipt)
    return {"ok": True, "artifact_dir": staging.as_posix(), **status, WHO_DENGUE_SURVEILLANCE_SOURCE_ID: source_payload}


def write_cdc_dengue_surveillance_metadata(staging: Path, source_payload: dict[str, object], gaps: list[dict[str, object]]) -> dict[str, object]:
    index = SourceIndex(staging / "source_index.sqlite")
    summary = index.summary()
    counts = source_counts(index)
    generated_at = str(source_payload["retrieved_at"])
    sources = [source for source in counts if source != CDC_DENGUE_SURVEILLANCE_SOURCE_ID]
    if counts.get(CDC_DENGUE_SURVEILLANCE_SOURCE_ID):
        sources.append(CDC_DENGUE_SURVEILLANCE_SOURCE_ID)

    status = read_json(staging / "source_status.json", {})
    if not isinstance(status, dict):
        status = {}
    status.update(
        {
            "ok": True,
            "source_id": sources[0] if sources else CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
            "sources": sources,
            "source_counts": counts,
            "boundary": "Aedes aegypti first",
            "generated_at": generated_at,
            "fully_parsed": not gaps,
            "parsed_scope": "CDC dengue current and historic pages, visualization configs, linked CSV datasets, and ArboNET limitations",
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
    receipt_sources[CDC_DENGUE_SURVEILLANCE_SOURCE_ID] = source_payload
    receipt.update(
        {
            "source_id": sources[0] if sources else CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
            "sources": receipt_sources,
            "source_counts": counts,
            "artifact_dir": staging.as_posix(),
            "sqlite_index": (staging / "source_index.sqlite").as_posix(),
            "generated_at": generated_at,
            "record_count": summary["record_count"],
            "lanes": summary["lanes"],
            CDC_DENGUE_SURVEILLANCE_SOURCE_ID: source_payload,
        }
    )

    write_json(staging / "gaps.json", gaps)
    write_json(staging / "source_status.json", status)
    write_json(staging / "source_receipt.json", receipt)
    return {"ok": True, "artifact_dir": staging.as_posix(), **status, CDC_DENGUE_SURVEILLANCE_SOURCE_ID: source_payload}


def write_ncvbdc_dengue_surveillance_metadata(staging: Path, source_payload: dict[str, object], gaps: list[dict[str, object]]) -> dict[str, object]:
    index = SourceIndex(staging / "source_index.sqlite")
    summary = index.summary()
    counts = source_counts(index)
    generated_at = str(source_payload["retrieved_at"])
    sources = [source for source in counts if source != NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID]
    if counts.get(NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID):
        sources.append(NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID)

    status = read_json(staging / "source_status.json", {})
    if not isinstance(status, dict):
        status = {}
    status.update(
        {
            "ok": True,
            "source_id": sources[0] if sources else NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID,
            "sources": sources,
            "source_counts": counts,
            "boundary": "Aedes aegypti first",
            "generated_at": generated_at,
            "fully_parsed": not gaps,
            "parsed_scope": "India NCVBDC dengue cases/deaths table at state/UT-year, country-year, and recent complete-year summary grain",
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
    receipt_sources[NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID] = source_payload
    receipt.update(
        {
            "source_id": sources[0] if sources else NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID,
            "sources": receipt_sources,
            "source_counts": counts,
            "artifact_dir": staging.as_posix(),
            "sqlite_index": (staging / "source_index.sqlite").as_posix(),
            "generated_at": generated_at,
            "record_count": summary["record_count"],
            "lanes": summary["lanes"],
            NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID: source_payload,
        }
    )

    write_json(staging / "gaps.json", gaps)
    write_json(staging / "source_status.json", status)
    write_json(staging / "source_receipt.json", receipt)
    return {"ok": True, "artifact_dir": staging.as_posix(), **status, NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID: source_payload}


def write_opendatasus_dengue_surveillance_metadata(staging: Path, source_payload: dict[str, object], gaps: list[dict[str, object]]) -> dict[str, object]:
    index = SourceIndex(staging / "source_index.sqlite")
    summary = index.summary()
    counts = source_counts(index)
    generated_at = str(source_payload["retrieved_at"])
    sources = [source for source in counts if source != OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID]
    if counts.get(OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID):
        sources.append(OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID)

    status = read_json(staging / "source_status.json", {})
    if not isinstance(status, dict):
        status = {}
    status.update(
        {
            "ok": True,
            "source_id": sources[0] if sources else OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID,
            "sources": sources,
            "source_counts": counts,
            "boundary": "Aedes aegypti first",
            "generated_at": generated_at,
            "fully_parsed": not gaps,
            "parsed_scope": "Brazil OpenDataSUS dengue CSV ZIPs aggregated by source file, country-year, state-year, country-week, and residence-state-week",
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
    receipt_sources[OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID] = source_payload
    receipt.update(
        {
            "source_id": sources[0] if sources else OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID,
            "sources": receipt_sources,
            "source_counts": counts,
            "artifact_dir": staging.as_posix(),
            "sqlite_index": (staging / "source_index.sqlite").as_posix(),
            "generated_at": generated_at,
            "record_count": summary["record_count"],
            "lanes": summary["lanes"],
            OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID: source_payload,
        }
    )

    write_json(staging / "gaps.json", gaps)
    write_json(staging / "source_status.json", status)
    write_json(staging / "source_receipt.json", receipt)
    return {"ok": True, "artifact_dir": staging.as_posix(), **status, OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID: source_payload}


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

    core_indicator_pages = payload.get("core_indicator_pages")
    if core_indicator_pages is None or core_indicator_pages == []:
        core_pages = list(DEFAULT_PAHO_CORE_INDICATOR_PAGES)
    elif isinstance(core_indicator_pages, list) and all(isinstance(item, str) for item in core_indicator_pages):
        core_pages = core_indicator_pages
    else:
        raise ValueError("core_indicator_pages must be a list of strings")

    raw_staging = artifact_dir.parent / f".{artifact_dir.name}.paho-dengue-surveillance-raw-staging"
    raw_final = artifact_dir / "raw" / "paho_dengue_surveillance"
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
        result = fetch_paho_dengue_surveillance_records_fn(
            reports,
            raw_dir=raw_staging,
            retrieved_at=retrieved_at,
            dashboard_pages=dashboard_urls,
            core_indicator_pages=core_pages,
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
        replace_source_records(index, PAHO_DENGUE_SURVEILLANCE_SOURCE_ID, records)
        old_gaps = read_json(artifact_dir / "gaps.json", [])
        if not isinstance(old_gaps, list):
            old_gaps = []
        gaps = [gap for gap in old_gaps if not (isinstance(gap, dict) and gap.get("source") == PAHO_DENGUE_SURVEILLANCE_SOURCE_ID)]
        gaps.extend(result.gaps)
        source_payload = {
            "requested_urls": result.requested_urls,
            "raw_artifacts": raw_artifacts,
            "record_count": len(records),
            "gap_count": len(result.gaps),
            "report_count": result.report_count,
            "dashboard_page_count": result.dashboard_page_count,
            "core_indicator_page_count": result.core_indicator_page_count,
            "core_indicator_download_count": result.core_indicator_download_count,
            "core_indicator_row_count": result.core_indicator_row_count,
            "retrieved_at": retrieved_at,
            "method": "official PAHO dengue situation report HTML plus PAHO/EIH Open Data Core Indicators ZIP/CSV dengue rows parsed into Aedes aegypti-relevant public-health surveillance records; weekly dashboard cells remain a source gap until stable weekly CSV or JSON access is proven",
        }
        response = write_paho_dengue_surveillance_metadata(artifact_dir, source_payload, gaps)
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


def ingest_who_dengue_surveillance(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_who_dengue_surveillance_records_fn: Callable[..., object] = fetch_who_dengue_surveillance_records,
) -> dict[str, object]:
    source_urls = payload.get("source_urls")
    if source_urls is None or source_urls == []:
        sources = list(DEFAULT_WHO_DENGUE_SURVEILLANCE_PAGES)
    elif isinstance(source_urls, list) and all(isinstance(item, str) for item in source_urls):
        sources = [who_dengue_source_spec(url, index=index + 1) for index, url in enumerate(source_urls)]
    else:
        raise ValueError("source_urls must be a list of strings")

    raw_staging = artifact_dir.parent / f".{artifact_dir.name}.who-dengue-surveillance-raw-staging"
    raw_final = artifact_dir / "raw" / "who_dengue_surveillance"
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
        result = fetch_who_dengue_surveillance_records_fn(
            sources,
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
        replace_source_records(index, WHO_DENGUE_SURVEILLANCE_SOURCE_ID, records)
        old_gaps = read_json(artifact_dir / "gaps.json", [])
        if not isinstance(old_gaps, list):
            old_gaps = []
        gaps = [gap for gap in old_gaps if not (isinstance(gap, dict) and gap.get("source") == WHO_DENGUE_SURVEILLANCE_SOURCE_ID)]
        gaps.extend(result.gaps)
        source_payload = {
            "requested_urls": result.requested_urls,
            "raw_artifacts": raw_artifacts,
            "record_count": len(records),
            "gap_count": len(result.gaps),
            "page_count": result.page_count,
            "situation_report_count": result.situation_report_count,
            "archive_count": result.archive_count,
            "publication_count": result.publication_count,
            "dashboard_locator_count": result.dashboard_locator_count,
            "export_locator_count": result.export_locator_count,
            "retrieved_at": retrieved_at,
            "method": "official WHO dengue surveillance pages, WER global update page, WPRO situation-update links, and WPRO Health Data Platform dashboard locators parsed into Aedes aegypti-relevant public-health records; dashboard row extraction remains a structured source gap unless stable direct exports are exposed",
        }
        response = write_who_dengue_surveillance_metadata(artifact_dir, source_payload, gaps)
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


def ingest_cdc_dengue_surveillance(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_cdc_dengue_surveillance_records_fn: Callable[..., object] = fetch_cdc_dengue_surveillance_records,
) -> dict[str, object]:
    source_urls = payload.get("source_urls")
    if source_urls is None or source_urls == []:
        sources = list(DEFAULT_CDC_DENGUE_PAGES)
    elif isinstance(source_urls, list) and all(isinstance(item, str) for item in source_urls):
        sources = [
            {
                "organization": "CDC",
                "url": url,
                "page_kind": f"custom_{index + 1}",
                "topic": "custom CDC dengue surveillance page",
            }
            for index, url in enumerate(source_urls)
        ]
    else:
        raise ValueError("source_urls must be a list of strings")

    raw_staging = artifact_dir.parent / f".{artifact_dir.name}.cdc-dengue-surveillance-raw-staging"
    raw_final = artifact_dir / "raw" / "cdc_dengue_surveillance"
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
        result = fetch_cdc_dengue_surveillance_records_fn(
            sources,
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
        replace_source_records(index, CDC_DENGUE_SURVEILLANCE_SOURCE_ID, records)
        old_gaps = read_json(artifact_dir / "gaps.json", [])
        if not isinstance(old_gaps, list):
            old_gaps = []
        gaps = [gap for gap in old_gaps if not (isinstance(gap, dict) and gap.get("source") == CDC_DENGUE_SURVEILLANCE_SOURCE_ID)]
        gaps.extend(result.gaps)
        source_payload = {
            "requested_urls": result.requested_urls,
            "raw_artifacts": raw_artifacts,
            "record_count": len(records),
            "gap_count": len(result.gaps),
            "page_count": result.page_count,
            "config_count": result.config_count,
            "dataset_count": result.dataset_count,
            "dataset_row_count": result.dataset_row_count,
            "limitation_count": result.limitation_count,
            "retrieved_at": retrieved_at,
            "method": "official CDC dengue current/historic ArboNET HTML pages, CDC WCMS visualization JSON configs, and linked CDC CSV datasets parsed into Aedes aegypti-relevant public-health surveillance records",
        }
        response = write_cdc_dengue_surveillance_metadata(artifact_dir, source_payload, gaps)
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


def ingest_ncvbdc_dengue_surveillance(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_ncvbdc_dengue_surveillance_records_fn: Callable[..., object] = fetch_ncvbdc_dengue_surveillance_records,
) -> dict[str, object]:
    source_urls = payload.get("source_urls")
    if source_urls is None or source_urls == []:
        sources = [DEFAULT_NCVBDC_DENGUE_PAGE]
    elif isinstance(source_urls, list) and all(isinstance(item, str) for item in source_urls):
        sources = [
            {
                "organization": "NCVBDC",
                "url": url,
                "page_kind": f"custom_{index + 1}",
                "topic": "custom India NCVBDC dengue surveillance page",
            }
            for index, url in enumerate(source_urls)
        ]
    else:
        raise ValueError("source_urls must be a list of strings")

    raw_staging = artifact_dir.parent / f".{artifact_dir.name}.ncvbdc-dengue-surveillance-raw-staging"
    raw_final = artifact_dir / "raw" / "ncvbdc_dengue_surveillance"
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
        result = fetch_ncvbdc_dengue_surveillance_records_fn(
            sources,
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
        replace_source_records(index, NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID, records)
        old_gaps = read_json(artifact_dir / "gaps.json", [])
        if not isinstance(old_gaps, list):
            old_gaps = []
        gaps = [gap for gap in old_gaps if not (isinstance(gap, dict) and gap.get("source") == NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID)]
        gaps.extend(result.gaps)
        source_payload = {
            "requested_urls": result.requested_urls,
            "raw_artifacts": raw_artifacts,
            "record_count": len(records),
            "gap_count": len(result.gaps),
            "page_count": result.page_count,
            "table_row_count": result.table_row_count,
            "state_year_record_count": result.state_year_record_count,
            "national_year_record_count": result.national_year_record_count,
            "recent_summary_count": result.recent_summary_count,
            "retrieved_at": retrieved_at,
            "method": "official India NCVBDC dengue situation HTML table parsed into state/UT-year, country-year, and two-latest-complete-year summary public-health records for Aedes aegypti intelligence",
        }
        response = write_ncvbdc_dengue_surveillance_metadata(artifact_dir, source_payload, gaps)
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


def ingest_opendatasus_dengue_surveillance(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_opendatasus_dengue_surveillance_records_fn: Callable[..., object] = fetch_opendatasus_dengue_surveillance_records,
) -> dict[str, object]:
    years_payload = payload.get("years")
    if years_payload is None or years_payload == []:
        years: list[int] = []
    elif isinstance(years_payload, list) and all(isinstance(item, int) for item in years_payload):
        years = years_payload
    else:
        raise ValueError("years must be a list of integers")
    file_urls = payload.get("file_urls")
    if file_urls is None or file_urls == []:
        specs = default_opendatasus_dengue_file_specs(years or None)
    elif isinstance(file_urls, list) and all(isinstance(item, str) for item in file_urls):
        selected_years = years or list(range(1, len(file_urls) + 1))
        if len(selected_years) != len(file_urls):
            raise ValueError("years count must match file_urls count")
        from .sources.opendatasus_dengue_surveillance import OpenDataSusDengueFileSpec

        specs = [OpenDataSusDengueFileSpec(year=year, url=url) for year, url in zip(selected_years, file_urls, strict=True)]
    else:
        raise ValueError("file_urls must be a list of strings")

    raw_staging = artifact_dir.parent / f".{artifact_dir.name}.opendatasus-dengue-surveillance-raw-staging"
    raw_final = artifact_dir / "raw" / "opendatasus_dengue_surveillance"
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
        result = fetch_opendatasus_dengue_surveillance_records_fn(
            specs,
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
        replace_source_records(index, OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID, records)
        old_gaps = read_json(artifact_dir / "gaps.json", [])
        if not isinstance(old_gaps, list):
            old_gaps = []
        gaps = [gap for gap in old_gaps if not (isinstance(gap, dict) and gap.get("source") == OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID)]
        gaps.extend(result.gaps)
        source_payload = {
            "requested_urls": result.requested_urls,
            "raw_artifacts": raw_artifacts,
            "record_count": len(records),
            "gap_count": len(result.gaps),
            "file_count": result.file_count,
            "source_file_record_count": result.source_file_record_count,
            "country_year_record_count": result.country_year_record_count,
            "state_year_record_count": result.state_year_record_count,
            "country_week_record_count": result.country_week_record_count,
            "state_week_record_count": result.state_week_record_count,
            "input_csv_row_count": result.row_count,
            "years": result.years,
            "retrieved_at": retrieved_at,
            "method": "official Brazil OpenDataSUS SINAN dengue CSV ZIP files parsed into source-file, country-year, state-year, country-week, and residence-state-week aggregate public-health records for Aedes aegypti intelligence",
        }
        response = write_opendatasus_dengue_surveillance_metadata(artifact_dir, source_payload, gaps)
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


def write_vectornet_surveillance_metadata(staging: Path, source_payload: dict[str, object], gaps: list[dict[str, object]]) -> dict[str, object]:
    index = SourceIndex(staging / "source_index.sqlite")
    summary = index.summary()
    counts = source_counts(index)
    generated_at = str(source_payload["retrieved_at"])
    sources = [source for source in counts if source != VECTORNET_SOURCE_ID]
    if counts.get(VECTORNET_SOURCE_ID):
        sources.append(VECTORNET_SOURCE_ID)

    status = read_json(staging / "source_status.json", {})
    if not isinstance(status, dict):
        status = {}
    status.update(
        {
            "ok": True,
            "source_id": sources[0] if sources else VECTORNET_SOURCE_ID,
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
    receipt_sources[VECTORNET_SOURCE_ID] = source_payload
    receipt.update(
        {
            "source_id": sources[0] if sources else VECTORNET_SOURCE_ID,
            "sources": receipt_sources,
            "artifact_dir": staging.as_posix(),
            "sqlite_index": (staging / "source_index.sqlite").as_posix(),
            "generated_at": generated_at,
            "record_count": summary["record_count"],
            "source_counts": counts,
            "lanes": summary["lanes"],
            "vectornet_surveillance": source_payload,
        }
    )

    write_json(staging / "gaps.json", gaps)
    write_json(staging / "source_status.json", status)
    write_json(staging / "source_receipt.json", receipt)
    return {"ok": True, "artifact_dir": staging.as_posix(), **status, "vectornet_surveillance": source_payload}


def ingest_vectornet_surveillance(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_vectornet_surveillance_records_fn: Callable[..., object] = fetch_vectornet_surveillance_records,
) -> dict[str, object]:
    species = str(payload.get("species") or DEFAULT_VECTORNET_SPECIES)
    archive_url_value = payload.get("archive_url")
    archive_url = str(archive_url_value) if archive_url_value else None
    max_records_value = payload.get("max_records")
    max_records = int(max_records_value) if max_records_value is not None else None
    raw_staging = artifact_dir.parent / f".{artifact_dir.name}.vectornet-surveillance-raw-staging"
    raw_final = artifact_dir / "raw" / "vectornet_surveillance"
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
        fetch_kwargs: dict[str, object] = {
            "raw_dir": raw_staging,
            "species": species,
            "max_records": max_records,
            "retrieved_at": retrieved_at,
        }
        if archive_url:
            fetch_kwargs["archive_url"] = archive_url
        result = fetch_vectornet_surveillance_records_fn(**fetch_kwargs)
        raw_staging.mkdir(parents=True, exist_ok=True)
        old = raw_staging.as_posix()
        new = raw_final.as_posix()
        records = replace_record_path_strings(result.records, old, new)
        raw_artifacts = replace_path_strings(result.raw_artifacts, old, new)
        if not isinstance(raw_artifacts, list):
            raw_artifacts = result.raw_artifacts
        filtered_rows_path = result.filtered_rows_path.replace(old, new) if result.filtered_rows_path else None
        if raw_backup.exists():
            shutil.rmtree(raw_backup)
        if raw_final.exists():
            raw_final.replace(raw_backup)
        raw_final.parent.mkdir(parents=True, exist_ok=True)
        raw_staging.replace(raw_final)
        raw_activated = True
        replace_source_records(index, VECTORNET_SOURCE_ID, records)
        old_gaps = read_json(artifact_dir / "gaps.json", [])
        if not isinstance(old_gaps, list):
            old_gaps = []
        gaps = [gap for gap in old_gaps if not (isinstance(gap, dict) and gap.get("source") == VECTORNET_SOURCE_ID)]
        gaps.extend(result.gaps)
        source_payload = {
            "dataset_key": result.dataset_key,
            "dataset_title": result.dataset_title,
            "species": result.species,
            "archive_url": result.archive_url,
            "resource_url": result.resource_url,
            "license": result.license,
            "pub_date": result.pub_date,
            "row_count": result.row_count,
            "matched_row_count": result.matched_row_count,
            "observation_record_count": result.observation_record_count,
            "ecology_record_count": result.ecology_record_count,
            "record_count": len(records),
            "raw_artifacts": raw_artifacts,
            "filtered_rows_path": filtered_rows_path,
            "gap_count": len(result.gaps),
            "retrieved_at": retrieved_at,
        }
        response = write_vectornet_surveillance_metadata(artifact_dir, source_payload, gaps)
    except Exception:
        shutil.rmtree(raw_staging, ignore_errors=True)
        if raw_activated and raw_backup.exists():
            if raw_final.exists():
                shutil.rmtree(raw_final)
            raw_backup.replace(raw_final)
        raise
    if raw_backup.exists():
        shutil.rmtree(raw_backup)
    shutil.rmtree(raw_staging, ignore_errors=True)
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
            "dryad_behavior_videos": source_payload,
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
            "source_counts": counts,
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
            "table_file_count": result.table_file_count,
            "parsed_table_file_count": result.parsed_table_file_count,
            "skipped_table_file_count": result.skipped_table_file_count,
            "table_sheet_count": result.table_sheet_count,
            "table_row_count": result.table_row_count,
            "landing_page_count": result.landing_page_count,
            "assay_method_count": result.assay_method_count,
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
            "audio_file_count": result.audio_file_count,
            "acoustic_assay_record_count": result.acoustic_assay_record_count,
            "decoded_audio_file_count": result.decoded_audio_file_count,
            "audio_metadata_record_count": result.audio_metadata_record_count,
            "skipped_audio_file_count": result.skipped_audio_file_count,
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


def ingest_pmc_videos(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_pmc_video_records_fn: Callable[..., object] = fetch_pmc_video_records,
) -> dict[str, object]:
    article_urls = payload.get("article_urls")
    if article_urls is not None and not (
        isinstance(article_urls, list) and all(isinstance(value, str) for value in article_urls)
    ):
        raise ValueError("article_urls must be a list of strings")
    retrieved_at = payload.get("retrieved_at")
    if retrieved_at is not None and not isinstance(retrieved_at, str):
        raise ValueError("retrieved_at must be a string")

    from scripts.ingest_pmc_videos import ingest_pmc_videos as ingest_local

    if fetch_pmc_video_records_fn is fetch_pmc_video_records:
        result = ingest_local(
            artifact_dir=artifact_dir,
            article_urls=article_urls,
            retrieved_at=retrieved_at or utc_now(),
        )
        result["activated_artifact_dir"] = str(artifact_dir)
        return result

    from scripts.ingest_pmc_videos import _update_metadata

    source_result = fetch_pmc_video_records_fn(
        article_urls=article_urls,
        raw_dir=artifact_dir / "raw" / "pmc_videos",
        retrieved_at=retrieved_at or utc_now(),
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.replace_source_records(PMC_VIDEO_SOURCE_ID, source_result.records)
    response = _update_metadata(artifact_dir, source_result)
    response["activated_artifact_dir"] = str(artifact_dir)
    return response


def ingest_zenodo_aedes_videos(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_zenodo_aedes_video_records_fn: Callable[..., object] = fetch_zenodo_aedes_video_records,
) -> dict[str, object]:
    query = payload.get("query", '"Aedes aegypti" (video OR movie OR mp4 OR tracking)')
    size = payload.get("size", DEFAULT_ZENODO_SIZE)
    if not isinstance(query, str):
        raise ValueError("query must be a string")
    if not isinstance(size, int):
        raise ValueError("size must be an integer")
    if fetch_zenodo_aedes_video_records_fn is fetch_zenodo_aedes_video_records:
        from scripts.ingest_zenodo_aedes_videos import ingest_zenodo_aedes_videos as ingest_local

        result = ingest_local(artifact_dir=artifact_dir, query=query, size=size, retrieved_at=utc_now())
        result["activated_artifact_dir"] = str(artifact_dir)
        return result

    from scripts.ingest_zenodo_aedes_videos import _update_metadata

    retrieved_at = utc_now()
    source_result = fetch_zenodo_aedes_video_records_fn(
        raw_dir=artifact_dir / "raw" / "zenodo_aedes_videos",
        retrieved_at=retrieved_at,
        query=query,
        size=size,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.replace_source_records(ZENODO_AEDES_VIDEO_SOURCE_ID, source_result.records)
    response = _update_metadata(artifact_dir, source_result, retrieved_at)
    response["activated_artifact_dir"] = str(artifact_dir)
    return response


def ingest_figshare_aedes_videos(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_figshare_aedes_video_records_fn: Callable[..., object] = fetch_figshare_aedes_video_records,
) -> dict[str, object]:
    query = payload.get("query", "Aedes aegypti video")
    page_size = payload.get("page_size", DEFAULT_FIGSHARE_PAGE_SIZE)
    if not isinstance(query, str):
        raise ValueError("query must be a string")
    if not isinstance(page_size, int):
        raise ValueError("page_size must be an integer")
    if fetch_figshare_aedes_video_records_fn is fetch_figshare_aedes_video_records:
        from scripts.ingest_figshare_aedes_videos import ingest_figshare_aedes_videos as ingest_local

        result = ingest_local(artifact_dir=artifact_dir, query=query, page_size=page_size, retrieved_at=utc_now())
        result["activated_artifact_dir"] = str(artifact_dir)
        return result

    from scripts.ingest_figshare_aedes_videos import _update_metadata

    retrieved_at = utc_now()
    source_result = fetch_figshare_aedes_video_records_fn(
        raw_dir=artifact_dir / "raw" / "figshare_aedes_videos",
        retrieved_at=retrieved_at,
        query=query,
        page_size=page_size,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.replace_source_records(FIGSHARE_AEDES_VIDEO_SOURCE_ID, source_result.records)
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


def ingest_resistance_table_rows(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_resistance_table_rows import ingest_resistance_table_rows as ingest_resistance_table_rows_script

    _ = payload
    return ingest_resistance_table_rows_script(artifact_dir=artifact_dir)


def ingest_occurrence_ecology(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_occurrence_ecology import ingest_occurrence_ecology as ingest_occurrence_ecology_script

    _ = payload
    return ingest_occurrence_ecology_script(artifact_dir=artifact_dir)


def ingest_drosophila_suzukii_occurrence_ecology(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_occurrence_ecology import ingest_drosophila_suzukii_occurrence_ecology as ingest_script

    _ = payload
    return ingest_script(artifact_dir=artifact_dir)


def ingest_observation_climate(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_observation_climate import ingest_observation_climate as ingest_observation_climate_script

    input_sources = payload.get("input_sources")
    if input_sources is not None and not isinstance(input_sources, list):
        raise ValueError("input_sources must be a list")
    worldclim_zip_path = payload.get("worldclim_zip_path")
    if worldclim_zip_path is not None and not isinstance(worldclim_zip_path, str):
        raise ValueError("worldclim_zip_path must be a string")
    return ingest_observation_climate_script(
        artifact_dir=artifact_dir,
        worldclim_zip_path=Path(worldclim_zip_path) if worldclim_zip_path else None,
        limit=int(payload.get("limit") or 1000),
        input_sources=tuple(str(source) for source in input_sources) if input_sources else None,
    )


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
        response = rewrite_artifact_references(staging, artifact_dir, result, source="vectorbase_aedes_genomics")
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


def ingest_ncbi_snp_variation_staged(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    fetch_ncbi_snp_variation_records_fn: Callable[..., object],
) -> dict[str, object]:
    from scripts.ingest_ncbi_snp_variation import ingest_ncbi_snp_variation

    staging = artifact_dir.parent / f".{artifact_dir.name}.ncbi-snp-variation-staging"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        if artifact_dir.exists():
            prepare_mutable_staging(artifact_dir, staging)
        else:
            staging.mkdir(parents=True, exist_ok=True)
        result = ingest_ncbi_snp_variation(
            artifact_dir=staging,
            species=str(payload.get("species") or DEFAULT_SNP_SPECIES),
            limit=int(payload.get("limit") or 1000),
            page_size=int(payload.get("page_size") or 200),
            delay_seconds=float(payload.get("delay_seconds") if payload.get("delay_seconds") is not None else 0.34),
            fetch_ncbi_snp_variation_records_fn=fetch_ncbi_snp_variation_records_fn,
        )
        response = rewrite_artifact_references(staging, artifact_dir, result)
        activate_source_staging(staging, artifact_dir, Path("raw") / "ncbi_snp_variation")
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
    max_repository_supplement_discovery_records_value = payload.get("max_repository_supplement_discovery_records")
    max_repository_supplement_discovery_records = (
        100
        if max_repository_supplement_discovery_records_value is None
        else int(max_repository_supplement_discovery_records_value)
    )
    if max_repository_supplement_discovery_records < 0:
        raise ValueError("max_repository_supplement_discovery_records must not be negative")
    max_supplement_files_value = payload.get("max_supplement_files")
    max_supplement_files = 100 if max_supplement_files_value is None else int(max_supplement_files_value)
    if max_supplement_files < 1:
        raise ValueError("max_supplement_files must be positive")
    max_supplement_bytes_value = payload.get("max_supplement_bytes")
    max_supplement_bytes = (
        DEFAULT_MAX_SUPPLEMENT_BYTES if max_supplement_bytes_value is None else int(max_supplement_bytes_value)
    )
    if max_supplement_bytes < 1:
        raise ValueError("max_supplement_bytes must be positive")
    max_pdf_supplement_files_value = payload.get("max_pdf_supplement_files")
    max_pdf_supplement_files = 10 if max_pdf_supplement_files_value is None else int(max_pdf_supplement_files_value)
    if max_pdf_supplement_files < 0:
        raise ValueError("max_pdf_supplement_files must not be negative")
    source_record_ids_value = payload.get("source_record_ids")
    source_record_ids: list[str] | None = None
    if source_record_ids_value is not None:
        if not isinstance(source_record_ids_value, list):
            raise ValueError("source_record_ids must be a list")
        source_record_ids = [str(source_record_id) for source_record_id in source_record_ids_value if str(source_record_id)]
    merge_existing = bool(payload.get("merge_existing", False))
    if merge_existing and not source_record_ids:
        raise ValueError("merge_existing requires at least one source_record_id")

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
            max_repository_supplement_discovery_records=max_repository_supplement_discovery_records,
            max_supplement_files=max_supplement_files,
            max_supplement_bytes=max_supplement_bytes,
            max_pdf_supplement_files=max_pdf_supplement_files,
            source_record_ids=source_record_ids,
            merge_existing=merge_existing,
        )
        response = rewrite_artifact_references(staging, artifact_dir, result, source="aedes_extracted_facts")
        activate_source_staging(staging, artifact_dir, Path("raw") / "extracted_facts")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    response["activated_artifact_dir"] = str(artifact_dir)
    response["staged"] = True
    return response


def ingest_drosophila_suzukii_extracted_facts_staged(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_extracted_facts import ingest_drosophila_suzukii_extracted_facts

    staged_payload = dict(payload)
    source_record_ids_value = staged_payload.get("source_record_ids")
    if source_record_ids_value is not None and not isinstance(source_record_ids_value, list):
        raise ValueError("source_record_ids must be a list")
    source_record_ids = [
        str(source_record_id)
        for source_record_id in source_record_ids_value or []
        if str(source_record_id)
    ] or None
    merge_existing = bool(staged_payload.get("merge_existing", False))
    if merge_existing and not source_record_ids:
        raise ValueError("merge_existing requires at least one source_record_id")
    staging = artifact_dir.parent / f".{artifact_dir.name}.drosophila-suzukii-extracted-facts-staging"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        if artifact_dir.exists():
            prepare_mutable_staging(artifact_dir, staging)
        else:
            staging.mkdir(parents=True, exist_ok=True)
        result = ingest_drosophila_suzukii_extracted_facts(
            artifact_dir=staging,
            retrieved_at=staged_payload.get("retrieved_at") if isinstance(staged_payload.get("retrieved_at"), str) else None,
            max_fulltext_units=int(staged_payload.get("max_fulltext_units") or 5000),
            discover_supplements=bool(staged_payload.get("discover_supplements")),
            download_supplements=bool(staged_payload.get("download_supplements")),
            max_supplement_discovery_records=int(staged_payload.get("max_supplement_discovery_records") or 500),
            max_repository_supplement_discovery_records=int(staged_payload.get("max_repository_supplement_discovery_records") or 100),
            max_supplement_files=int(staged_payload.get("max_supplement_files") or 100),
            max_supplement_bytes=int(staged_payload.get("max_supplement_bytes") or DEFAULT_MAX_SUPPLEMENT_BYTES),
            max_pdf_supplement_files=int(staged_payload.get("max_pdf_supplement_files") or 10),
            source_record_ids=source_record_ids,
            merge_existing=merge_existing,
        )
        response = rewrite_artifact_references(staging, artifact_dir, result, source="drosophila_suzukii_extracted_facts")
        activate_source_staging(staging, artifact_dir, Path("raw") / "drosophila_suzukii_extracted_facts")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    response["activated_artifact_dir"] = str(artifact_dir)
    response["staged"] = True
    return response


def ingest_drosophila_suzukii_video_atoms_staged(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_video_atoms import ingest_drosophila_suzukii_video_atoms

    retrieved_at = payload.get("retrieved_at")
    if retrieved_at is not None and not isinstance(retrieved_at, str):
        raise ValueError("retrieved_at must be a string")
    max_video_bytes = int(payload.get("max_video_bytes") or 750_000_000)
    if max_video_bytes < 1:
        raise ValueError("max_video_bytes must be positive")
    allowed_licenses = _payload_string_list(payload, "allowed_licenses") or None
    staging = artifact_dir.parent / f".{artifact_dir.name}.drosophila-suzukii-video-atoms-staging"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        if artifact_dir.exists():
            prepare_mutable_staging(artifact_dir, staging)
        else:
            staging.mkdir(parents=True, exist_ok=True)
        result = ingest_drosophila_suzukii_video_atoms(
            artifact_dir=staging,
            retrieved_at=retrieved_at,
            max_video_bytes=max_video_bytes,
            mirror_videos=_payload_bool(payload, "mirror_videos"),
            generate_artifacts=_payload_bool(payload, "generate_artifacts"),
            allow_unclear_license=_payload_bool(payload, "allow_unclear_license"),
            allowed_licenses=allowed_licenses,
        )
        response = rewrite_artifact_references(staging, artifact_dir, result, source="drosophila_suzukii_video_atoms")
        activate_source_staging(staging, artifact_dir, Path("raw") / "drosophila_suzukii_video_atoms")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    response["activated_artifact_dir"] = str(artifact_dir)
    response["staged"] = True
    return response


def ingest_drosophila_suzukii_dryad_table_rows_staged(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_dryad_table_rows import ingest_drosophila_suzukii_dryad_table_rows

    retrieved_at = payload.get("retrieved_at")
    if retrieved_at is not None and not isinstance(retrieved_at, str):
        raise ValueError("retrieved_at must be a string")
    max_table_files = int(payload.get("max_table_files") or 50)
    max_table_rows_per_file = int(payload.get("max_table_rows_per_file") or 500)
    if max_table_files < 1:
        raise ValueError("max_table_files must be positive")
    if max_table_rows_per_file < 1:
        raise ValueError("max_table_rows_per_file must be positive")
    staging = artifact_dir.parent / f".{artifact_dir.name}.drosophila-suzukii-dryad-table-rows-staging"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        if artifact_dir.exists():
            prepare_mutable_staging(artifact_dir, staging)
        else:
            staging.mkdir(parents=True, exist_ok=True)
        result = ingest_drosophila_suzukii_dryad_table_rows(
            artifact_dir=staging,
            retrieved_at=retrieved_at,
            max_table_files=max_table_files,
            max_table_rows_per_file=max_table_rows_per_file,
        )
        response = rewrite_artifact_references(staging, artifact_dir, result, source="drosophila_suzukii_dryad_table_rows")
        activate_source_staging(staging, artifact_dir, Path("raw") / "drosophila_suzukii_dryad_table_rows")
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
    motion_table_paths = [Path(path) for path in _payload_string_list(payload, "motion_table_paths")] or None
    discovery_repositories = _payload_string_list(payload, "discovery_repositories") or None
    merge_existing = _payload_bool(payload, "merge_existing")
    parse_motion_rows = True if "parse_motion_rows" not in payload else _payload_bool(payload, "parse_motion_rows")
    if discovery_repositories and not merge_existing:
        raise ValueError("discovery_repositories requires merge_existing")

    if discovery_repositories and merge_existing:
        result = ingest_video_atoms(
            artifact_dir=artifact_dir,
            retrieved_at=retrieved_at,
            max_video_bytes=max_video_bytes,
            mirror_videos=_payload_bool(payload, "mirror_videos"),
            generate_artifacts=_payload_bool(payload, "generate_artifacts"),
            discover_sources=_payload_bool(payload, "discover_sources"),
            allow_unclear_license=_payload_bool(payload, "allow_unclear_license"),
            allowed_licenses=allowed_licenses,
            discovery_repositories=discovery_repositories,
            max_discovery_results=max_discovery_results,
            motion_table_paths=motion_table_paths,
            merge_existing=merge_existing,
            parse_motion_rows=parse_motion_rows,
        )
        result["activated_artifact_dir"] = str(artifact_dir)
        result["staged"] = False
        result["updated_in_place"] = True
        return result

    staging = artifact_dir.parent / f".{artifact_dir.name}.video-atoms-staging"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        if artifact_dir.exists():
            prepare_mutable_staging(artifact_dir, staging)
            if motion_table_paths is None:
                copy_default_video_motion_inputs_to_staging(artifact_dir, staging)
            else:
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
            discovery_repositories=discovery_repositories,
            max_discovery_results=max_discovery_results,
            motion_table_paths=motion_table_paths,
            merge_existing=merge_existing,
            parse_motion_rows=parse_motion_rows,
        )
        response = rewrite_artifact_references(staging, artifact_dir, result, source="aedes_video_atoms")
        activate_source_staging(staging, artifact_dir, Path("raw") / "video_atoms")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    response["activated_artifact_dir"] = str(artifact_dir)
    response["staged"] = True
    return response


def ingest_image_atoms_staged(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_image_atoms import ingest_image_atoms

    retrieved_at = payload.get("retrieved_at")
    if retrieved_at is not None and not isinstance(retrieved_at, str):
        raise ValueError("retrieved_at must be a string")
    mirror_images = _payload_bool(payload, "mirror_images", False)
    max_image_bytes = int(payload.get("max_image_bytes") or 5_000_000)
    max_image_mirrors = int(payload.get("max_image_mirrors") or 250)
    allow_unclear_license = _payload_bool(payload, "allow_unclear_license", False)
    allowed_licenses = tuple(_payload_string_list(payload, "allowed_licenses")) or None
    staging = artifact_dir.parent / f".{artifact_dir.name}.image-atoms-staging"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    response = ingest_image_atoms(
        artifact_dir=artifact_dir,
        retrieved_at=retrieved_at,
        mirror_images=mirror_images,
        max_image_bytes=max_image_bytes,
        max_image_mirrors=max_image_mirrors,
        allow_unclear_license=allow_unclear_license,
        allowed_licenses=allowed_licenses,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["staged"] = False
    response["updated_in_place"] = True
    return response


def ingest_source_coverage_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_source_coverage import ingest_source_coverage

    coverage_path = payload.get("coverage_path") or "config/mosquito-intelligence-coverage.json"
    if not isinstance(coverage_path, str):
        raise ValueError("coverage_path must be a string")
    response = ingest_source_coverage(artifact_dir=artifact_dir, coverage_path=Path(coverage_path))
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_expression_omics_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_expression_omics import ingest_expression_omics

    geo_limit = int(payload.get("geo_limit", 25))
    sra_limit = int(payload.get("sra_limit", 25))
    response = ingest_expression_omics(artifact_dir=artifact_dir, geo_limit=geo_limit, sra_limit=sra_limit)
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_uniprot_proteins_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_uniprot_proteins import ingest_uniprot_proteins

    protein_limit = int(payload.get("protein_limit", 250))
    proteome_limit = int(payload.get("proteome_limit", 10))
    response = ingest_uniprot_proteins(artifact_dir=artifact_dir, protein_limit=protein_limit, proteome_limit=proteome_limit)
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_wolbachia_interventions_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_wolbachia_interventions import ingest_wolbachia_interventions

    source_urls = payload.get("source_urls")
    if source_urls is None:
        source_urls_list: list[str] | None = None
    elif isinstance(source_urls, list) and all(isinstance(item, str) for item in source_urls):
        source_urls_list = source_urls
    else:
        raise ValueError("source_urls must be a list of strings")
    response = ingest_wolbachia_interventions(artifact_dir=artifact_dir, source_urls=source_urls_list)
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_vectorbyte_traits_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_vectorbyte_traits import ingest_vectorbyte_traits

    query = str(payload.get("query") or "Aedes aegypti")
    dataset_limit = int(payload.get("dataset_limit", 20))
    row_limit = int(payload.get("row_limit", 5000))
    search_limit = int(payload.get("search_limit", 50))
    response = ingest_vectorbyte_traits(
        artifact_dir=artifact_dir,
        query=query,
        dataset_limit=dataset_limit,
        row_limit=row_limit,
        search_limit=search_limit,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_vectorbyte_abundance_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_vectorbyte_abundance import ingest_vectorbyte_abundance

    query = str(payload.get("query") or "Aedes aegypti")
    dataset_limit = int(payload.get("dataset_limit", 5))
    row_limit = int(payload.get("row_limit", 5000))
    search_page_limit = int(payload.get("search_page_limit", 3))
    dataset_page_limit = int(payload.get("dataset_page_limit", 100))
    merge_existing = bool(payload.get("merge_existing", False))
    raw_dataset_ids = payload.get("dataset_ids")
    dataset_ids = [str(item) for item in raw_dataset_ids] if isinstance(raw_dataset_ids, list) else None
    response = ingest_vectorbyte_abundance(
        artifact_dir=artifact_dir,
        query=query,
        dataset_limit=dataset_limit,
        row_limit=row_limit,
        search_page_limit=search_page_limit,
        dataset_page_limit=dataset_page_limit,
        dataset_ids=dataset_ids,
        merge_existing=merge_existing,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_aedes_deep_sources_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_aedes_deep_sources import ingest_aedes_deep_sources

    compendium_row_limit = int(payload.get("compendium_row_limit", 5000))
    bioproject_limit = int(payload.get("bioproject_limit", 20))
    worldclim_sample_limit = int(payload.get("worldclim_sample_limit", 0))
    response = ingest_aedes_deep_sources(
        artifact_dir=artifact_dir,
        compendium_row_limit=compendium_row_limit,
        bioproject_limit=bioproject_limit,
        worldclim_sample_limit=worldclim_sample_limit,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii import ingest_drosophila_suzukii

    response = ingest_drosophila_suzukii(
        artifact_dir=artifact_dir,
        gbif_occurrence_limit=int(payload.get("gbif_occurrence_limit", 100)),
        inaturalist_observation_limit=int(payload.get("inaturalist_observation_limit", 100)),
        literature_max_works=int(payload.get("literature_max_works", 100)),
        bold_limit=int(payload.get("bold_limit", 100)),
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_deep_sources_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_deep_sources import ingest_drosophila_suzukii_deep_sources

    response = ingest_drosophila_suzukii_deep_sources(
        artifact_dir=artifact_dir,
        ncbi_limit=int(payload.get("ncbi_limit", 50)),
        protein_limit=int(payload.get("protein_limit", 100)),
        proteome_limit=int(payload.get("proteome_limit", 10)),
        repository_limit=int(payload.get("repository_limit", 50)),
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_genome_files_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_genome_files import ingest_drosophila_suzukii_genome_files

    response = ingest_drosophila_suzukii_genome_files(
        artifact_dir=artifact_dir,
        assembly_accession=str(payload.get("assembly_accession") or "GCF_043229965.1"),
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
        max_download_bytes=int(payload.get("max_download_bytes") or 100_000_000),
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_literature_fulltext_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_literature_fulltext import ingest_drosophila_suzukii_literature_fulltext

    raw_limit = payload.get("limit", 25)
    response = ingest_drosophila_suzukii_literature_fulltext(
        artifact_dir=artifact_dir,
        email=str(payload["email"]) if payload.get("email") else None,
        limit=int(raw_limit) if raw_limit is not None else None,
        delay_seconds=float(payload.get("delay_seconds", 0.0)),
        max_fulltext_bytes=int(payload.get("max_fulltext_bytes", 60_000_000)),
        include_unpaywall=bool(payload.get("include_unpaywall", False)),
        resume=bool(payload.get("resume", True)),
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_pubmed_literature_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_pubmed_literature import ingest_drosophila_suzukii_pubmed_literature

    response = ingest_drosophila_suzukii_pubmed_literature(
        artifact_dir=artifact_dir,
        max_results=int(payload.get("max_results", 1000)),
        page_size=int(payload.get("page_size", 100)),
        delay_seconds=float(payload.get("delay_seconds", 0.34)),
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_neurobiology_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_neurobiology import ingest_drosophila_suzukii_neurobiology

    response = ingest_drosophila_suzukii_neurobiology(
        artifact_dir=artifact_dir,
        max_results=int(payload.get("max_results", 200)),
        page_size=int(payload.get("page_size", 100)),
        delay_seconds=float(payload.get("delay_seconds", 0.34)),
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_olfaction_literature_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_olfaction_literature import ingest_drosophila_suzukii_olfaction_literature

    response = ingest_drosophila_suzukii_olfaction_literature(
        artifact_dir=artifact_dir,
        max_results=int(payload.get("max_results", 1000)),
        page_size=int(payload.get("page_size", 100)),
        delay_seconds=float(payload.get("delay_seconds", 0.34)),
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_traits_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_traits import ingest_drosophila_suzukii_traits

    response = ingest_drosophila_suzukii_traits(
        artifact_dir=artifact_dir,
        max_results=int(payload.get("max_results", 1000)),
        page_size=int(payload.get("page_size", 100)),
        delay_seconds=float(payload.get("delay_seconds", 0.34)),
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_ncbi_nucleotide_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_ncbi_nucleotide import ingest_drosophila_suzukii_ncbi_nucleotide

    response = ingest_drosophila_suzukii_ncbi_nucleotide(
        artifact_dir=artifact_dir,
        max_results=int(payload.get("max_results", 1000)),
        page_size=int(payload.get("page_size", 100)),
        delay_seconds=float(payload.get("delay_seconds", 0.34)),
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_ncbi_marker_review_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_ncbi_marker_review import ingest_drosophila_suzukii_ncbi_marker_review

    response = ingest_drosophila_suzukii_ncbi_marker_review(
        artifact_dir=artifact_dir,
        max_results=int(payload.get("max_results", 2000)),
        page_size=int(payload.get("page_size", 100)),
        delay_seconds=float(payload.get("delay_seconds", 0.34)),
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_ncbi_snp_variation_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_ncbi_snp_variation import ingest_drosophila_suzukii_ncbi_snp_variation

    response = ingest_drosophila_suzukii_ncbi_snp_variation(
        artifact_dir=artifact_dir,
        limit=int(payload.get("limit", 1000)),
        page_size=int(payload.get("page_size", 200)),
        delay_seconds=float(payload.get("delay_seconds", 0.34)),
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_ncbi_gene_orthologs_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_ncbi_gene_orthologs import ingest_drosophila_suzukii_ncbi_gene_orthologs

    response = ingest_drosophila_suzukii_ncbi_gene_orthologs(
        artifact_dir=artifact_dir,
        max_download_bytes=int(payload.get("max_download_bytes", 200_000_000)),
        max_rows=int(payload["max_rows"]) if payload.get("max_rows") else None,
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_ensembl_metazoa_orthology_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_ensembl_metazoa_orthology import ingest_drosophila_suzukii_ensembl_metazoa_orthology

    response = ingest_drosophila_suzukii_ensembl_metazoa_orthology(
        artifact_dir=artifact_dir,
        max_download_bytes=int(payload.get("max_download_bytes", 50_000_000)),
        max_rows_per_file=int(payload["max_rows_per_file"]) if payload.get("max_rows_per_file") else None,
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_geo_expression_matrices_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_geo_expression_matrices import ingest_drosophila_suzukii_geo_expression_matrices

    response = ingest_drosophila_suzukii_geo_expression_matrices(
        artifact_dir=artifact_dir,
        max_download_bytes=int(payload.get("max_download_bytes", 10_000_000)),
        max_rows_per_file=int(payload["max_rows_per_file"]) if payload.get("max_rows_per_file") else None,
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_figshare_mk_selection_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_figshare_mk_selection import ingest_drosophila_suzukii_figshare_mk_selection

    response = ingest_drosophila_suzukii_figshare_mk_selection(
        artifact_dir=artifact_dir,
        max_download_bytes=int(payload.get("max_download_bytes", 10_000_000)),
        max_rows=int(payload["max_rows"]) if payload.get("max_rows") else None,
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_population_genomics_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_population_genomics import ingest_drosophila_suzukii_population_genomics

    response = ingest_drosophila_suzukii_population_genomics(
        artifact_dir=artifact_dir,
        limit=int(payload.get("limit", 100)),
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_dryad_population_variants_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_dryad_population_variants import ingest_drosophila_suzukii_dryad_population_variants

    response = ingest_drosophila_suzukii_dryad_population_variants(
        artifact_dir=artifact_dir,
        max_mirror_bytes=int(payload.get("max_mirror_bytes", 1_000_000_000)),
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_extension_guidance_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_extension_guidance import ingest_drosophila_suzukii_extension_guidance

    source_urls = payload.get("source_urls") or None
    response = ingest_drosophila_suzukii_extension_guidance(
        artifact_dir=artifact_dir,
        source_urls=list(source_urls) if isinstance(source_urls, list) else None,
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_jki_drosomon_trap_captures_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_jki_drosomon_trap_captures import (
        ingest_drosophila_suzukii_jki_drosomon_trap_captures,
    )

    response = ingest_drosophila_suzukii_jki_drosomon_trap_captures(
        artifact_dir=artifact_dir,
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_plos_climate_suitability_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_plos_climate_suitability import (
        ingest_drosophila_suzukii_plos_climate_suitability,
    )

    response = ingest_drosophila_suzukii_plos_climate_suitability(
        artifact_dir=artifact_dir,
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_osu_trap_reports_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_osu_trap_reports import ingest_drosophila_suzukii_osu_trap_reports

    response = ingest_drosophila_suzukii_osu_trap_reports(
        artifact_dir=artifact_dir,
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_dryad_landscape_monitoring_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_dryad_landscape_monitoring import (
        ingest_drosophila_suzukii_dryad_landscape_monitoring,
    )

    response = ingest_drosophila_suzukii_dryad_landscape_monitoring(
        artifact_dir=artifact_dir,
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_umn_flight_assay_rows_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_umn_flight_assay_rows import ingest_drosophila_suzukii_umn_flight_assay_rows

    max_download_bytes = int(payload.get("max_download_bytes", 1_000_000))
    max_rows = payload.get("max_rows")
    response = ingest_drosophila_suzukii_umn_flight_assay_rows(
        artifact_dir=artifact_dir,
        max_download_bytes=max_download_bytes,
        max_rows=int(max_rows) if max_rows is not None else None,
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_susceptibility_assay_rows_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_susceptibility_assay_rows import (
        ingest_drosophila_suzukii_susceptibility_assay_rows,
    )

    response = ingest_drosophila_suzukii_susceptibility_assay_rows(
        artifact_dir=artifact_dir,
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_drosophila_suzukii_biocontrol_outcome_rows_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_biocontrol_outcome_rows import (
        ingest_drosophila_suzukii_biocontrol_outcome_rows,
    )

    response = ingest_drosophila_suzukii_biocontrol_outcome_rows(
        artifact_dir=artifact_dir,
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_aedes_olfaction_literature_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_aedes_olfaction_literature import ingest_aedes_olfaction_literature

    max_results = int(payload.get("max_results", 500))
    page_size = int(payload.get("page_size", 100))
    fulltext_limit = payload.get("fulltext_limit")
    parsed_fulltext_limit = int(fulltext_limit) if fulltext_limit is not None else None
    response = ingest_aedes_olfaction_literature(
        artifact_dir=artifact_dir,
        max_results=max_results,
        page_size=page_size,
        include_fulltext=bool(payload.get("include_fulltext", True)),
        unpaywall_email=str(payload.get("unpaywall_email") or "") or None,
        fulltext_limit=parsed_fulltext_limit,
        delay_seconds=float(payload.get("delay_seconds", 1.0)),
        max_fulltext_bytes=int(payload.get("max_fulltext_bytes", 60_000_000)),
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_crossref_literature_audit_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_aedes_crossref_literature_audit import ingest_aedes_crossref_literature_audit

    max_results = int(payload.get("max_results", 500))
    page_size = int(payload.get("page_size", 100))
    response = ingest_aedes_crossref_literature_audit(
        artifact_dir=artifact_dir,
        max_results=max_results,
        page_size=page_size,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_mosquito_repellent_literature_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_mosquito_repellent_literature import ingest_mosquito_repellent_literature

    pubmed_max_results = int(payload.get("pubmed_max_results", 1000))
    crossref_max_results = int(payload.get("crossref_max_results", 1000))
    page_size = int(payload.get("page_size", 100))
    response = ingest_mosquito_repellent_literature(
        artifact_dir=artifact_dir,
        pubmed_max_results=pubmed_max_results,
        crossref_max_results=crossref_max_results,
        page_size=page_size,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response


def ingest_mosquito_repellent_external_discovery_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_mosquito_repellent_external_discovery import ingest_mosquito_repellent_external_discovery

    max_results_per_source = int(payload.get("max_results_per_source", 50))
    response = ingest_mosquito_repellent_external_discovery(
        artifact_dir=artifact_dir,
        max_results_per_source=max_results_per_source,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
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
    fetch_who_malaria_threats_resistance_records_fn: Callable[..., object] = fetch_who_malaria_threats_resistance_records,
    fetch_harvard_dataverse_suitability_records_fn: Callable[..., object] = fetch_harvard_dataverse_suitability_records,
    fetch_mendeley_behavior_media_records_fn: Callable[..., object] = fetch_mendeley_behavior_media_records,
    fetch_mosquito_alert_records_fn: Callable[..., object] = fetch_mosquito_alert_records,
    fetch_ncbi_biosample_records_fn: Callable[..., object] = fetch_ncbi_biosample_records,
    fetch_ncbi_snp_variation_records_fn: Callable[..., object] = fetch_ncbi_snp_variation_records,
    fetch_osf_flighttrackai_video_records_fn: Callable[..., object] = fetch_osf_flighttrackai_video_records,
    fetch_pmc_video_records_fn: Callable[..., object] = fetch_pmc_video_records,
    fetch_pathogen_taxonomy_records_fn: Callable[..., object] = fetch_pathogen_taxonomy_records,
    fetch_public_health_guidance_records_fn: Callable[..., object] = fetch_public_health_guidance_records,
    fetch_paho_dengue_surveillance_records_fn: Callable[..., object] = fetch_paho_dengue_surveillance_records,
    fetch_who_dengue_surveillance_records_fn: Callable[..., object] = fetch_who_dengue_surveillance_records,
    fetch_cdc_dengue_surveillance_records_fn: Callable[..., object] = fetch_cdc_dengue_surveillance_records,
    fetch_ncvbdc_dengue_surveillance_records_fn: Callable[..., object] = fetch_ncvbdc_dengue_surveillance_records,
    fetch_opendatasus_dengue_surveillance_records_fn: Callable[..., object] = fetch_opendatasus_dengue_surveillance_records,
    fetch_vectorbase_genomics_records_fn: Callable[..., object] = fetch_vectorbase_genomics_records,
    fetch_vectornet_surveillance_records_fn: Callable[..., object] = fetch_vectornet_surveillance_records,
    fetch_zenodo_aedes_video_records_fn: Callable[..., object] = fetch_zenodo_aedes_video_records,
    fetch_figshare_aedes_video_records_fn: Callable[..., object] = fetch_figshare_aedes_video_records,
    fetch_aedes_deep_source_records_fn: Callable[..., object] = fetch_aedes_deep_source_records,
) -> Response:
    if not is_authorized(headers, token):
        return json_response(401, {"ok": False, "error": "unauthorized"})

    index = SourceIndex(artifact_dir / "source_index.sqlite")
    try:
        if method == "GET" and path == "/health":
            return json_response(200, health_payload(artifact_dir))
        if method in {"GET", "POST"} and path in {"/summary", "/ask", "/search", "/sql"}:
            ready, reason = source_index_readiness(artifact_dir)
            if not ready:
                return source_index_unavailable_response(artifact_dir, reason)
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
        if method == "POST" and path == "/ingest/who-malaria-threats-resistance":
            result = ingest_who_malaria_threats_resistance(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_who_malaria_threats_resistance_records_fn=fetch_who_malaria_threats_resistance_records_fn,
            )
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/harvard-dataverse-suitability":
            result = ingest_harvard_dataverse_suitability(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_harvard_dataverse_suitability_records_fn=fetch_harvard_dataverse_suitability_records_fn,
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
        if method == "POST" and path == "/ingest/who-dengue-surveillance":
            result = ingest_who_dengue_surveillance(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_who_dengue_surveillance_records_fn=fetch_who_dengue_surveillance_records_fn,
            )
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/cdc-dengue-surveillance":
            result = ingest_cdc_dengue_surveillance(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_cdc_dengue_surveillance_records_fn=fetch_cdc_dengue_surveillance_records_fn,
            )
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/ncvbdc-dengue-surveillance":
            result = ingest_ncvbdc_dengue_surveillance(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_ncvbdc_dengue_surveillance_records_fn=fetch_ncvbdc_dengue_surveillance_records_fn,
            )
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/opendatasus-dengue-surveillance":
            result = ingest_opendatasus_dengue_surveillance(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_opendatasus_dengue_surveillance_records_fn=fetch_opendatasus_dengue_surveillance_records_fn,
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
        if method == "POST" and path == "/ingest/expression-omics":
            result = ingest_expression_omics_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/uniprot-proteins":
            result = ingest_uniprot_proteins_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/wolbachia-interventions":
            result = ingest_wolbachia_interventions_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/vectorbyte-traits":
            result = ingest_vectorbyte_traits_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/vectorbyte-abundance":
            result = ingest_vectorbyte_abundance_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/aedes-deep-sources":
            result = ingest_aedes_deep_sources_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii":
            result = ingest_drosophila_suzukii_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-deep-sources":
            result = ingest_drosophila_suzukii_deep_sources_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-genome-files":
            result = ingest_drosophila_suzukii_genome_files_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-literature-fulltext":
            result = ingest_drosophila_suzukii_literature_fulltext_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-pubmed-literature":
            result = ingest_drosophila_suzukii_pubmed_literature_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-neurobiology":
            result = ingest_drosophila_suzukii_neurobiology_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-olfaction-literature":
            result = ingest_drosophila_suzukii_olfaction_literature_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-traits":
            result = ingest_drosophila_suzukii_traits_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-ncbi-nucleotide":
            result = ingest_drosophila_suzukii_ncbi_nucleotide_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-ncbi-marker-review":
            result = ingest_drosophila_suzukii_ncbi_marker_review_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-ncbi-snp-variation":
            result = ingest_drosophila_suzukii_ncbi_snp_variation_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-ncbi-gene-orthologs":
            result = ingest_drosophila_suzukii_ncbi_gene_orthologs_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-ensembl-metazoa-orthology":
            result = ingest_drosophila_suzukii_ensembl_metazoa_orthology_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-geo-expression-matrices":
            result = ingest_drosophila_suzukii_geo_expression_matrices_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-figshare-mk-selection":
            result = ingest_drosophila_suzukii_figshare_mk_selection_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-population-genomics":
            result = ingest_drosophila_suzukii_population_genomics_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-dryad-population-variants":
            result = ingest_drosophila_suzukii_dryad_population_variants_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-extension-guidance":
            result = ingest_drosophila_suzukii_extension_guidance_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-jki-drosomon-trap-captures":
            result = ingest_drosophila_suzukii_jki_drosomon_trap_captures_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-plos-climate-suitability":
            result = ingest_drosophila_suzukii_plos_climate_suitability_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-osu-trap-reports":
            result = ingest_drosophila_suzukii_osu_trap_reports_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-dryad-landscape-monitoring":
            result = ingest_drosophila_suzukii_dryad_landscape_monitoring_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-umn-flight-assay-rows":
            result = ingest_drosophila_suzukii_umn_flight_assay_rows_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-susceptibility-assay-rows":
            result = ingest_drosophila_suzukii_susceptibility_assay_rows_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-biocontrol-outcome-rows":
            result = ingest_drosophila_suzukii_biocontrol_outcome_rows_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-extracted-facts":
            result = ingest_drosophila_suzukii_extracted_facts_staged(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-video-atoms":
            result = ingest_drosophila_suzukii_video_atoms_staged(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-dryad-table-rows":
            result = ingest_drosophila_suzukii_dryad_table_rows_staged(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/aedes-olfaction-literature":
            result = ingest_aedes_olfaction_literature_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/crossref-literature-audit":
            result = ingest_crossref_literature_audit_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/mosquito-repellent-literature":
            result = ingest_mosquito_repellent_literature_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/mosquito-repellent-external-discovery":
            result = ingest_mosquito_repellent_external_discovery_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/vectornet-surveillance":
            result = ingest_vectornet_surveillance(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_vectornet_surveillance_records_fn=fetch_vectornet_surveillance_records_fn,
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
        if method == "POST" and path == "/ingest/pmc-videos":
            result = ingest_pmc_videos(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_pmc_video_records_fn=fetch_pmc_video_records_fn,
            )
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/zenodo-aedes-videos":
            result = ingest_zenodo_aedes_videos(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_zenodo_aedes_video_records_fn=fetch_zenodo_aedes_video_records_fn,
            )
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/figshare-aedes-videos":
            result = ingest_figshare_aedes_videos(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_figshare_aedes_video_records_fn=fetch_figshare_aedes_video_records_fn,
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
        if method == "POST" and path == "/ingest/ncbi-snp-variation":
            result = ingest_ncbi_snp_variation_staged(
                payload or {},
                artifact_dir=artifact_dir,
                fetch_ncbi_snp_variation_records_fn=fetch_ncbi_snp_variation_records_fn,
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
        if method == "POST" and path == "/ingest/resistance-table-rows":
            result = ingest_resistance_table_rows(payload or {}, artifact_dir=artifact_dir)
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
        if method == "POST" and path == "/ingest/image-atoms":
            result = ingest_image_atoms_staged(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/source-coverage":
            result = ingest_source_coverage_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/occurrence-ecology":
            result = ingest_occurrence_ecology(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path == "/ingest/drosophila-suzukii-occurrence-ecology":
            result = ingest_drosophila_suzukii_occurrence_ecology(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
        if method == "POST" and path in {"/ingest/observation-climate", "/ingest/observation-climate-join"}:
            result = ingest_observation_climate(payload or {}, artifact_dir=artifact_dir)
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
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
        self.close_connection = True

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
        except Exception as exc:
            # Any other error (e.g. a SQLite lock or upstream failure inside an
            # ingest) must still return a response, not kill the worker thread
            # and leave the client hanging with no reply.
            response = json_response(500, {"ok": False, "error": str(exc)})
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
