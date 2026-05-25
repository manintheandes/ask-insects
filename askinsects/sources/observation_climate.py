from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from askinsects.records import EvidenceRecord, Provenance

from .aedes_deep_sources import (
    DEFAULT_WORLDCLIM_BIOCLIM_10M_URL,
    _worldclim_raster_values,
    _worldclim_rasters,
)
from .occurrence_ecology import OBSERVATION_SOURCE_IDS, _country_from_place, _date_prefix, _parse_float


OBSERVATION_CLIMATE_SOURCE_ID = "aedes_observation_climate_join"
DEFAULT_WORLDCLIM_ZIP_RELATIVE_PATH = Path("raw/aedes_deep_sources/worldclim/wc2.1_10m_bio.zip")


@dataclass(frozen=True)
class ClimateObservation:
    record_id: str
    source: str
    title: str
    text: str
    species: str | None
    url: str | None
    latitude: float
    longitude: float
    country: str | None
    observed_date: str | None
    dataset: str | None
    place: str | None
    quality_grade: str | None
    payload: dict[str, Any]
    provenance: dict[str, Any]


@dataclass(frozen=True)
class ObservationClimateResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    observation_count: int
    sampled_count: int
    skipped_no_coordinate_count: int
    input_source_counts: dict[str, int]
    raw_artifacts: list[str]
    limit: int


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_id(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value or "")).strip("_")[:140] or "unknown"


def _digest(*parts: object) -> str:
    return hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:12]


def _clean(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _valid_lat_lon(latitude: float | None, longitude: float | None) -> tuple[float, float] | None:
    if latitude is None or longitude is None:
        return None
    if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
        return None
    return latitude, longitude


def _gbif_observation(row: sqlite3.Row, payload: dict[str, Any], provenance: dict[str, Any]) -> ClimateObservation | None:
    raw = payload.get("raw_occurrence")
    if not isinstance(raw, dict):
        raw = payload
    coords = _valid_lat_lon(_parse_float(raw.get("decimalLatitude")), _parse_float(raw.get("decimalLongitude")))
    if coords is None:
        return None
    latitude, longitude = coords
    country = _clean(raw.get("country")) or None
    return ClimateObservation(
        record_id=str(row["record_id"]),
        source=str(row["source"]),
        title=str(row["title"]),
        text=str(row["text"]),
        species=row["species"],
        url=row["url"],
        latitude=latitude,
        longitude=longitude,
        country=country,
        observed_date=_date_prefix(raw.get("eventDate") or raw.get("dateIdentified")),
        dataset=_clean(raw.get("datasetName") or raw.get("datasetKey")) or None,
        place=_clean(raw.get("locality") or raw.get("stateProvince")) or None,
        quality_grade=None,
        payload=payload,
        provenance=provenance,
    )


def _inat_observation(row: sqlite3.Row, payload: dict[str, Any], provenance: dict[str, Any]) -> ClimateObservation | None:
    raw = payload.get("raw_observation")
    if not isinstance(raw, dict):
        raw = payload
    geojson = raw.get("geojson")
    coordinates = geojson.get("coordinates") if isinstance(geojson, dict) else None
    longitude: float | None = None
    latitude: float | None = None
    if isinstance(coordinates, list) and len(coordinates) >= 2:
        longitude = _parse_float(coordinates[0])
        latitude = _parse_float(coordinates[1])
    coords = _valid_lat_lon(latitude, longitude)
    if coords is None:
        return None
    latitude, longitude = coords
    place = _clean(raw.get("place_guess")) or None
    return ClimateObservation(
        record_id=str(row["record_id"]),
        source=str(row["source"]),
        title=str(row["title"]),
        text=str(row["text"]),
        species=row["species"],
        url=row["url"],
        latitude=latitude,
        longitude=longitude,
        country=_country_from_place(place) if place else None,
        observed_date=_date_prefix(raw.get("observed_on") or raw.get("time_observed_at")),
        dataset="iNaturalist public observations",
        place=place,
        quality_grade=_clean(raw.get("quality_grade")) or None,
        payload=payload,
        provenance=provenance,
    )


def _observation_from_row(row: sqlite3.Row) -> ClimateObservation | None:
    payload = json.loads(str(row["payload_json"] or "{}"))
    provenance = json.loads(str(row["provenance_json"] or "{}"))
    source = str(row["source"])
    if source in {"gbif_api", "mosquito_alert_gbif"}:
        return _gbif_observation(row, payload, provenance)
    if source == "inaturalist_api":
        return _inat_observation(row, payload, provenance)
    return None


def _observation_rows(conn: sqlite3.Connection, input_sources: tuple[str, ...]) -> tuple[list[ClimateObservation], int, int]:
    placeholders = ",".join("?" for _ in input_sources)
    rows = conn.execute(
        f"""
        SELECT r.record_id, r.source, r.title, r.text, r.species, r.url, r.provenance_json, p.payload_json
        FROM records r
        JOIN record_payloads p ON p.record_id = r.record_id
        WHERE r.lane='observations'
          AND r.source IN ({placeholders})
        ORDER BY r.source, r.record_id
        """,
        input_sources,
    ).fetchall()
    observations: list[ClimateObservation] = []
    skipped = 0
    for row in rows:
        observation = _observation_from_row(row)
        if observation is None:
            skipped += 1
            continue
        observations.append(observation)
    return observations, len(rows), skipped


def _gap_record(gap: dict[str, object], *, retrieved_at: str, index: int) -> EvidenceRecord:
    reason = _clean(gap.get("reason")) or "observation_climate_gap"
    locator = _clean(gap.get("locator")) or f"gaps.json#{OBSERVATION_CLIMATE_SOURCE_ID}/{index}"
    text = f"Aedes aegypti observation climate-join source gap: {reason}."
    if gap.get("detail"):
        text += f" {gap['detail']}."
    if gap.get("source_url"):
        text += f" Source URL: {gap['source_url']}."
    return EvidenceRecord(
        record_id=f"ecology:observation_climate:gap:{_normalize_id(reason)}:{_digest(json.dumps(gap, sort_keys=True, default=str), index)}",
        lane="ecology",
        source=OBSERVATION_CLIMATE_SOURCE_ID,
        title=f"Aedes aegypti observation climate source gap: {reason}",
        text=text,
        species="Aedes aegypti",
        url=_clean(gap.get("source_url")) or None,
        media_url=None,
        provenance=Provenance(
            source_id=OBSERVATION_CLIMATE_SOURCE_ID,
            locator=locator,
            retrieved_at=retrieved_at,
            license=_clean(gap.get("license")) or "derived source gap; upstream terms apply",
            source_url=_clean(gap.get("source_url")) or None,
        ),
        payload={"gap": gap},
    )


def _sample_record(
    observation: ClimateObservation,
    values: dict[str, float],
    *,
    raw_zip_path: Path,
    retrieved_at: str,
    sample_index: int,
) -> EvidenceRecord:
    temp = values.get("bio1_annual_mean_temperature_c")
    precip = values.get("bio12_annual_precipitation_mm")
    country = observation.country or "unknown"
    text = (
        "WorldClim v2.1 10-minute bioclim raster values joined to an indexed Aedes aegypti observation. "
        f"Input source: {observation.source}. Observation: {observation.record_id}. "
        f"Country/place: {country}; {observation.place or 'place not supplied'}. "
        f"Observed date: {observation.observed_date or 'unknown'}. "
        f"Coordinates: {observation.latitude}, {observation.longitude}. "
        f"Annual mean temperature: {temp if temp is not None else 'not sampled'} deg C. "
        f"Annual precipitation: {precip if precip is not None else 'not sampled'} mm."
    )
    payload = {
        "record_type": "observation_climate_sample",
        "source_observation_record_id": observation.record_id,
        "source_observation_source": observation.source,
        "source_observation_url": observation.url,
        "country": observation.country,
        "place": observation.place,
        "observed_date": observation.observed_date,
        "dataset": observation.dataset,
        "quality_grade": observation.quality_grade,
        "latitude": observation.latitude,
        "longitude": observation.longitude,
        "variables": values,
        "bio1_annual_mean_temperature_c": temp,
        "bio12_annual_precipitation_mm": precip,
        "raster": "WorldClim v2.1 10-minute bioclimatic variables",
        "raster_url": DEFAULT_WORLDCLIM_BIOCLIM_10M_URL,
        "raw_zip_path": raw_zip_path.as_posix(),
        "source_observation_provenance": observation.provenance,
        "sample_index": sample_index,
    }
    return EvidenceRecord(
        record_id=f"ecology:observation_climate:{observation.source}:{_normalize_id(observation.record_id)}",
        lane="ecology",
        source=OBSERVATION_CLIMATE_SOURCE_ID,
        title=f"Aedes aegypti observation climate sample: {observation.record_id}",
        text=text,
        species="Aedes aegypti",
        url=observation.url or DEFAULT_WORLDCLIM_BIOCLIM_10M_URL,
        media_url=None,
        provenance=Provenance(
            source_id=OBSERVATION_CLIMATE_SOURCE_ID,
            locator=f"{raw_zip_path.as_posix()}#observation/{observation.record_id}",
            retrieved_at=retrieved_at,
            license="derived from indexed public observation records and WorldClim public climate data; upstream source terms apply",
            source_url=observation.url or DEFAULT_WORLDCLIM_BIOCLIM_10M_URL,
        ),
        payload=payload,
    )


def build_observation_climate_records(
    artifact_dir: Path,
    *,
    worldclim_zip_path: Path | None = None,
    limit: int = 1000,
    input_sources: tuple[str, ...] = OBSERVATION_SOURCE_IDS,
    retrieved_at: str | None = None,
) -> ObservationClimateResult:
    if limit < 1:
        raise ValueError("limit must be positive")
    if not input_sources:
        raise ValueError("input_sources must not be empty")
    db_path = artifact_dir / "source_index.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"missing source index: {db_path}")
    retrieved = retrieved_at or utc_now()
    zip_path = worldclim_zip_path or artifact_dir / DEFAULT_WORLDCLIM_ZIP_RELATIVE_PATH
    raw_artifacts: list[str] = []
    gaps: list[dict[str, object]] = []
    records: list[EvidenceRecord] = []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        observations, observation_count, skipped_no_coordinate_count = _observation_rows(conn, input_sources)

    if not zip_path.exists():
        gaps.append(
            {
                "source": OBSERVATION_CLIMATE_SOURCE_ID,
                "lane": "ecology",
                "reason": "observation_climate_worldclim_zip_missing",
                "worldclim_zip_path": zip_path.as_posix(),
                "source_url": DEFAULT_WORLDCLIM_BIOCLIM_10M_URL,
                "retrieved_at": retrieved,
            }
        )
        records.extend(_gap_record(gap, retrieved_at=retrieved, index=index) for index, gap in enumerate(gaps, start=1))
        return ObservationClimateResult(
            source_id=OBSERVATION_CLIMATE_SOURCE_ID,
            records=records,
            gaps=gaps,
            observation_count=observation_count,
            sampled_count=0,
            skipped_no_coordinate_count=skipped_no_coordinate_count,
            input_source_counts=dict(sorted(Counter(obs.source for obs in observations).items())),
            raw_artifacts=raw_artifacts,
            limit=limit,
        )

    raw_artifacts.append(zip_path.as_posix())
    if not observations:
        gaps.append(
            {
                "source": OBSERVATION_CLIMATE_SOURCE_ID,
                "lane": "ecology",
                "reason": "observation_climate_no_coordinate_observations",
                "input_sources": list(input_sources),
                "skipped_no_coordinate_count": skipped_no_coordinate_count,
                "retrieved_at": retrieved,
            }
        )

    try:
        rasters = _worldclim_rasters(zip_path.read_bytes())
    except Exception as exc:  # noqa: BLE001
        rasters = {}
        gaps.append(
            {
                "source": OBSERVATION_CLIMATE_SOURCE_ID,
                "lane": "ecology",
                "reason": "observation_climate_raster_sampling_failed",
                "worldclim_zip_path": zip_path.as_posix(),
                "source_url": DEFAULT_WORLDCLIM_BIOCLIM_10M_URL,
                "error": str(exc),
                "retrieved_at": retrieved,
            }
        )

    for observation in observations:
        if len(records) >= limit:
            break
        values = _worldclim_raster_values(rasters, observation.longitude, observation.latitude) if rasters else {}
        if not values:
            continue
        records.append(
            _sample_record(
                observation,
                values,
                raw_zip_path=zip_path,
                retrieved_at=retrieved,
                sample_index=len(records) + 1,
            )
        )

    if len(observations) > limit:
        gaps.append(
            {
                "source": OBSERVATION_CLIMATE_SOURCE_ID,
                "lane": "ecology",
                "reason": "observation_climate_limit_applied",
                "limit": limit,
                "coordinate_observation_count": len(observations),
                "retrieved_at": retrieved,
            }
        )
    if observations and not records and not any(gap.get("reason") == "observation_climate_raster_sampling_failed" for gap in gaps):
        gaps.append(
            {
                "source": OBSERVATION_CLIMATE_SOURCE_ID,
                "lane": "ecology",
                "reason": "observation_climate_no_raster_values_sampled",
                "coordinate_observation_count": len(observations),
                "worldclim_zip_path": zip_path.as_posix(),
                "retrieved_at": retrieved,
            }
        )

    records.extend(_gap_record(gap, retrieved_at=retrieved, index=index) for index, gap in enumerate(gaps, start=1))
    return ObservationClimateResult(
        source_id=OBSERVATION_CLIMATE_SOURCE_ID,
        records=records,
        gaps=gaps,
        observation_count=observation_count,
        sampled_count=len([record for record in records if record.payload and record.payload.get("record_type") == "observation_climate_sample"]),
        skipped_no_coordinate_count=skipped_no_coordinate_count,
        input_source_counts=dict(sorted(Counter(obs.source for obs in observations).items())),
        raw_artifacts=raw_artifacts,
        limit=limit,
    )
