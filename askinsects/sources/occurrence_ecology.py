from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from askinsects.records import EvidenceRecord, Provenance


OCCURRENCE_ECOLOGY_SOURCE_ID = "aedes_occurrence_ecology"
OBSERVATION_SOURCE_IDS = ("gbif_api", "inaturalist_api", "mosquito_alert_gbif")

MONTH_NAMES = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


@dataclass(frozen=True)
class OccurrenceObservation:
    record_id: str
    source: str
    title: str
    text: str
    species: str | None
    url: str | None
    country: str
    observed_date: str | None
    month: int | None
    latitude: float | None
    longitude: float | None
    dataset: str | None
    quality_grade: str | None
    place: str | None
    habitat_values: tuple[str, ...]
    provenance: dict[str, Any]


@dataclass(frozen=True)
class OccurrenceEcologyResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    observation_count: int
    country_count: int
    country_month_count: int
    habitat_count: int
    input_source_counts: dict[str, int]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", value).strip("_") or "unknown"


def _parse_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date_prefix(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    match = re.match(r"^\d{4}-\d{2}-\d{2}", value)
    if match:
        return match.group(0)
    year_month = re.match(r"^\d{4}-\d{2}", value)
    if year_month:
        return year_month.group(0)
    year = re.match(r"^\d{4}", value)
    return year.group(0) if year else None


def _month_from_date(value: str | None) -> int | None:
    if not value:
        return None
    match = re.match(r"^\d{4}-(\d{2})", value)
    if not match:
        return None
    month = int(match.group(1))
    return month if 1 <= month <= 12 else None


def _country_from_place(place: object) -> str | None:
    if not isinstance(place, str) or not place.strip():
        return None
    parts = [part.strip() for part in place.split(",") if part.strip()]
    if not parts:
        return None
    last = parts[-1]
    aliases = {
        "US": "United States of America",
        "USA": "United States of America",
        "United States": "United States of America",
        "U.S.A.": "United States of America",
        "Suid-Afrika": "South Africa",
    }
    return aliases.get(last, last)


def _habitat_values(raw_observation: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    ofvs = raw_observation.get("ofvs")
    if not isinstance(ofvs, list):
        return ()
    for field in ofvs:
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or field.get("name_ci") or "").lower()
        if "habitat" not in name:
            continue
        value = str(field.get("value") or field.get("value_ci") or "").strip()
        if value:
            values.append(value)
    return tuple(dict.fromkeys(values))


def _observation_from_row(row: sqlite3.Row) -> OccurrenceObservation | None:
    payload = json.loads(str(row["payload_json"] or "{}"))
    provenance = json.loads(str(row["provenance_json"] or "{}"))
    source = str(row["source"])
    country: str | None = None
    observed_date: str | None = None
    month: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    dataset: str | None = None
    quality_grade: str | None = None
    place: str | None = None
    habitats: tuple[str, ...] = ()

    if source in {"gbif_api", "mosquito_alert_gbif"}:
        raw = payload.get("raw_occurrence")
        if not isinstance(raw, dict):
            raw = payload
        country = str(raw.get("country") or "").strip() or None
        observed_date = _date_prefix(raw.get("eventDate") or raw.get("dateIdentified"))
        month = _month_from_date(observed_date)
        latitude = _parse_float(raw.get("decimalLatitude"))
        longitude = _parse_float(raw.get("decimalLongitude"))
        dataset = str(raw.get("datasetName") or raw.get("datasetKey") or "").strip() or None
    elif source == "inaturalist_api":
        raw = payload.get("raw_observation")
        if not isinstance(raw, dict):
            raw = payload
        place_value = raw.get("place_guess")
        place = str(place_value).strip() if isinstance(place_value, str) and place_value.strip() else None
        country = _country_from_place(place)
        observed_date = _date_prefix(raw.get("observed_on") or raw.get("time_observed_at"))
        details = raw.get("observed_on_details")
        if isinstance(details, dict) and details.get("month"):
            try:
                month = int(details["month"])
            except (TypeError, ValueError):
                month = None
        if month is None:
            month = _month_from_date(observed_date)
        geojson = raw.get("geojson")
        coordinates = geojson.get("coordinates") if isinstance(geojson, dict) else None
        if isinstance(coordinates, list) and len(coordinates) >= 2:
            longitude = _parse_float(coordinates[0])
            latitude = _parse_float(coordinates[1])
        dataset = "iNaturalist public observations"
        quality_grade = str(raw.get("quality_grade") or "").strip() or None
        habitats = _habitat_values(raw)
    else:
        return None

    if not country:
        country = "unknown"
    if month is not None and not 1 <= month <= 12:
        month = None

    return OccurrenceObservation(
        record_id=str(row["record_id"]),
        source=source,
        title=str(row["title"]),
        text=str(row["text"]),
        species=row["species"],
        url=row["url"],
        country=country,
        observed_date=observed_date,
        month=month,
        latitude=latitude,
        longitude=longitude,
        dataset=dataset,
        quality_grade=quality_grade,
        place=place,
        habitat_values=habitats,
        provenance=provenance,
    )


def _observation_rows(conn: sqlite3.Connection) -> list[OccurrenceObservation]:
    placeholders = ",".join("?" for _ in OBSERVATION_SOURCE_IDS)
    rows = conn.execute(
        f"""
        SELECT r.record_id, r.source, r.title, r.text, r.species, r.url, r.provenance_json, p.payload_json
        FROM records r
        JOIN record_payloads p ON p.record_id = r.record_id
        WHERE r.lane='observations'
          AND r.source IN ({placeholders})
        ORDER BY r.source, r.record_id
        """,
        OBSERVATION_SOURCE_IDS,
    ).fetchall()
    observations: list[OccurrenceObservation] = []
    for row in rows:
        observation = _observation_from_row(row)
        if observation is not None:
            observations.append(observation)
    return observations


def _sample_values(values: list[str], *, limit: int = 8) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))[:limit]


def _date_range(observations: list[OccurrenceObservation]) -> tuple[str | None, str | None]:
    dates = sorted(obs.observed_date for obs in observations if obs.observed_date)
    if not dates:
        return None, None
    return dates[0], dates[-1]


def _bbox(observations: list[OccurrenceObservation]) -> dict[str, float] | None:
    lats = [obs.latitude for obs in observations if obs.latitude is not None]
    lons = [obs.longitude for obs in observations if obs.longitude is not None]
    if not lats or not lons:
        return None
    return {
        "min_latitude": min(lats),
        "max_latitude": max(lats),
        "min_longitude": min(lons),
        "max_longitude": max(lons),
    }


def _record(
    *,
    record_id: str,
    title: str,
    text: str,
    locator: str,
    observations: list[OccurrenceObservation],
    payload: dict[str, Any],
    retrieved_at: str,
) -> EvidenceRecord:
    source_urls = _sample_values([obs.url or str(obs.provenance.get("source_url") or "") for obs in observations], limit=5)
    source_url = source_urls[0] if source_urls else None
    payload = {
        **payload,
        "observation_count": len(observations),
        "input_source_counts": dict(sorted(Counter(obs.source for obs in observations).items())),
        "sample_record_ids": [obs.record_id for obs in observations[:10]],
        "sample_source_urls": source_urls,
        "coordinate_count": sum(1 for obs in observations if obs.latitude is not None and obs.longitude is not None),
        "bbox": _bbox(observations),
    }
    first_date, last_date = _date_range(observations)
    payload["first_observed"] = first_date
    payload["last_observed"] = last_date
    return EvidenceRecord(
        record_id=record_id,
        lane="ecology",
        source=OCCURRENCE_ECOLOGY_SOURCE_ID,
        title=title,
        text=text,
        species="Aedes aegypti",
        url=source_url,
        media_url=None,
        provenance=Provenance(
            source_id=OCCURRENCE_ECOLOGY_SOURCE_ID,
            locator=locator,
            retrieved_at=retrieved_at,
            license="derived from indexed public GBIF, iNaturalist, and Mosquito Alert observation records",
            source_url=source_url,
        ),
        payload=payload,
    )


def _country_records(observations: list[OccurrenceObservation], *, retrieved_at: str) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    by_country: dict[str, list[OccurrenceObservation]] = {}
    for observation in observations:
        by_country.setdefault(observation.country, []).append(observation)
    for country, country_observations in sorted(by_country.items(), key=lambda item: (-len(item[1]), item[0])):
        first_date, last_date = _date_range(country_observations)
        source_counts = Counter(obs.source for obs in country_observations)
        months = sorted({obs.month for obs in country_observations if obs.month})
        month_names = [MONTH_NAMES[month] for month in months]
        text = (
            f"Aedes aegypti occurrence ecology range summary for {country}. "
            f"{len(country_observations)} indexed observation record(s) across {len(source_counts)} source(s): "
            f"{', '.join(f'{source}={count}' for source, count in sorted(source_counts.items()))}. "
            f"Observed date range: {first_date or 'unknown'} to {last_date or 'unknown'}. "
            f"Seasonality months represented: {', '.join(month_names) if month_names else 'unknown'}. "
            f"Coordinate-bearing observations: {sum(1 for obs in country_observations if obs.latitude is not None and obs.longitude is not None)}."
        )
        records.append(
            _record(
                record_id=f"occurrence_ecology:country:{_normalize_id(country)}",
                title=f"Aedes aegypti occurrence ecology in {country}",
                text=text,
                locator=f"source_index.sqlite#observation-ecology/country/{_normalize_id(country)}",
                observations=country_observations,
                payload={
                    "aggregation_type": "country_summary",
                    "country": country,
                    "months": months,
                    "month_names": month_names,
                },
                retrieved_at=retrieved_at,
            )
        )
    return records


def _country_month_records(observations: list[OccurrenceObservation], *, retrieved_at: str) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    by_key: dict[tuple[str, int], list[OccurrenceObservation]] = {}
    for observation in observations:
        if observation.month is None:
            continue
        by_key.setdefault((observation.country, observation.month), []).append(observation)
    for (country, month), month_observations in sorted(by_key.items(), key=lambda item: (item[0][0], item[0][1])):
        first_date, last_date = _date_range(month_observations)
        month_name = MONTH_NAMES[month]
        source_counts = Counter(obs.source for obs in month_observations)
        text = (
            f"Aedes aegypti occurrence ecology seasonality record for {country} in {month_name}. "
            f"{len(month_observations)} indexed observation record(s) are dated to month {month} "
            f"from {', '.join(f'{source}={count}' for source, count in sorted(source_counts.items()))}. "
            f"Observed date range in this month bucket: {first_date or 'unknown'} to {last_date or 'unknown'}."
        )
        records.append(
            _record(
                record_id=f"occurrence_ecology:country_month:{_normalize_id(country)}:{month:02d}",
                title=f"Aedes aegypti seasonality in {country}: {month_name}",
                text=text,
                locator=f"source_index.sqlite#observation-ecology/country-month/{_normalize_id(country)}/{month:02d}",
                observations=month_observations,
                payload={
                    "aggregation_type": "country_month_summary",
                    "country": country,
                    "month": month,
                    "month_name": month_name,
                },
                retrieved_at=retrieved_at,
            )
        )
    return records


def _habitat_records(observations: list[OccurrenceObservation], *, retrieved_at: str) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    by_key: dict[tuple[str, str], list[OccurrenceObservation]] = {}
    for observation in observations:
        for habitat in observation.habitat_values:
            by_key.setdefault((observation.country, habitat), []).append(observation)
    for (country, habitat), habitat_observations in sorted(by_key.items(), key=lambda item: (-len(item[1]), item[0][0], item[0][1])):
        text = (
            f"Aedes aegypti occurrence ecology habitat annotation for {country}. "
            f"Habitat value: {habitat}. "
            f"{len(habitat_observations)} iNaturalist observation record(s) include this public observation-field value."
        )
        records.append(
            _record(
                record_id=f"occurrence_ecology:habitat:{_normalize_id(country)}:{_normalize_id(habitat)}",
                title=f"Aedes aegypti habitat annotation in {country}: {habitat}",
                text=text,
                locator=f"source_index.sqlite#observation-ecology/habitat/{_normalize_id(country)}/{_normalize_id(habitat)}",
                observations=habitat_observations,
                payload={
                    "aggregation_type": "habitat_summary",
                    "country": country,
                    "habitat": habitat,
                    "habitat_source": "iNaturalist observation field value containing habitat",
                },
                retrieved_at=retrieved_at,
            )
        )
    return records


def _deduplicate_record_ids(records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    seen: set[str] = set()
    deduplicated: list[EvidenceRecord] = []
    for record in records:
        if record.record_id not in seen:
            seen.add(record.record_id)
            deduplicated.append(record)
            continue
        digest = hashlib.sha1(f"{record.record_id}|{record.title}|{record.text}".encode("utf-8")).hexdigest()[:10]
        record_id = f"{record.record_id}:{digest}"
        provenance = replace(record.provenance, locator=f"{record.provenance.locator};record_id_dedup={digest}")
        while record_id in seen:
            digest = hashlib.sha1(f"{record_id}|{len(seen)}".encode("utf-8")).hexdigest()[:10]
            record_id = f"{record.record_id}:{digest}"
            provenance = replace(record.provenance, locator=f"{record.provenance.locator};record_id_dedup={digest}")
        seen.add(record_id)
        deduplicated.append(replace(record, record_id=record_id, provenance=provenance))
    return deduplicated


def build_occurrence_ecology_records(artifact_dir: Path, *, retrieved_at: str | None = None) -> OccurrenceEcologyResult:
    db_path = artifact_dir / "source_index.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"missing source index: {db_path}")
    retrieved = retrieved_at or utc_now()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        observations = _observation_rows(conn)

    records: list[EvidenceRecord] = []
    records.extend(_country_records(observations, retrieved_at=retrieved))
    country_record_count = len(records)
    records.extend(_country_month_records(observations, retrieved_at=retrieved))
    country_month_count = len(records) - country_record_count
    records.extend(_habitat_records(observations, retrieved_at=retrieved))
    habitat_count = len(records) - country_record_count - country_month_count
    records = _deduplicate_record_ids(records)

    gaps: list[dict[str, object]] = []
    if not observations:
        gaps.append(
            {
                "source": OCCURRENCE_ECOLOGY_SOURCE_ID,
                "lane": "ecology",
                "reason": "no_indexed_aedes_observation_records",
                "input_sources": list(OBSERVATION_SOURCE_IDS),
                "retrieved_at": retrieved,
            }
        )

    return OccurrenceEcologyResult(
        source_id=OCCURRENCE_ECOLOGY_SOURCE_ID,
        records=records,
        gaps=gaps,
        observation_count=len(observations),
        country_count=country_record_count,
        country_month_count=country_month_count,
        habitat_count=habitat_count,
        input_source_counts=dict(sorted(Counter(obs.source for obs in observations).items())),
    )
