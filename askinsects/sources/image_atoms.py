from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import re
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance


IMAGE_ATOMS_SOURCE_ID = "aedes_image_atoms"
IMAGE_SOURCE_IDS = {"inaturalist_api", "mosquito_alert_gbif"}
IMAGE_LABEL_GAP_TYPES = ("life_stage", "sex", "anatomy", "body_part")
INATURALIST_ANNOTATION_MAP = {
    (1, 2): ("life_stage", "adult"),
    (1, 3): ("life_stage", "teneral"),
    (1, 4): ("life_stage", "pupa"),
    (1, 5): ("life_stage", "nymph"),
    (1, 6): ("life_stage", "larva"),
    (1, 7): ("life_stage", "egg"),
    (1, 8): ("life_stage", "juvenile"),
    (9, 10): ("sex", "female"),
    (9, 11): ("sex", "male"),
}


@dataclass(frozen=True)
class AedesImageAtomsResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    image_asset_count: int
    image_label_count: int
    image_gap_count: int


@dataclass(frozen=True)
class ImageCandidate:
    source_record_id: str
    title: str
    text: str
    species: str | None
    url: str | None
    media_url: str
    source: str
    provenance: dict[str, object]
    payload: dict[str, object]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_id(value: object) -> str:
    text = str(value or "")
    safe = re.sub(r"[^A-Za-z0-9_.:-]+", "_", text).strip("_")
    return safe or hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _digest(*parts: object) -> str:
    return hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:12]


def _safe_json(raw: object) -> dict[str, object]:
    if not raw:
        return {}
    try:
        payload = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _candidate_rows(index: SourceIndex) -> list[ImageCandidate]:
    source_placeholders = ",".join("?" for _ in IMAGE_SOURCE_IDS)
    with index.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT r.*, p.payload_json
            FROM records r
            LEFT JOIN record_payloads p ON p.record_id = r.record_id
            WHERE r.source IN ({source_placeholders})
              AND r.lane = 'media'
              AND r.media_url IS NOT NULL
              AND lower(coalesce(r.species, '')) LIKE 'aedes aegypti%'
            ORDER BY r.record_id
            """,
            sorted(IMAGE_SOURCE_IDS),
        ).fetchall()
    candidates: list[ImageCandidate] = []
    for raw_row in rows:
        row = dict(raw_row)
        payload = _safe_json(row.get("payload_json"))
        media_url = row.get("media_url")
        if not isinstance(media_url, str) or not media_url:
            continue
        candidates.append(
            ImageCandidate(
                source_record_id=str(row["record_id"]),
                title=str(row["title"]),
                text=str(row["text"]),
                species=row.get("species") if isinstance(row.get("species"), str) else None,
                url=row.get("url") if isinstance(row.get("url"), str) else None,
                media_url=media_url,
                source=str(row["source"]),
                provenance=_safe_json(row.get("provenance_json")),
                payload=payload,
            )
        )
    return candidates


def _coordinates(raw_observation: dict[str, object] | None, raw_occurrence: dict[str, object] | None) -> dict[str, object]:
    if raw_observation:
        geojson = raw_observation.get("geojson")
        if isinstance(geojson, dict):
            coords = geojson.get("coordinates")
            if isinstance(coords, list) and len(coords) >= 2:
                return {"longitude": coords[0], "latitude": coords[1]}
    if raw_occurrence:
        latitude = raw_occurrence.get("decimalLatitude")
        longitude = raw_occurrence.get("decimalLongitude")
        if latitude is not None or longitude is not None:
            return {"latitude": latitude, "longitude": longitude}
    return {}


def _asset_payload(candidate: ImageCandidate) -> dict[str, object]:
    raw_observation = candidate.payload.get("raw_observation")
    raw_photo = candidate.payload.get("raw_photo")
    raw_occurrence = candidate.payload.get("raw_occurrence")
    raw_media = candidate.payload.get("raw_media")
    raw_observation = raw_observation if isinstance(raw_observation, dict) else None
    raw_photo = raw_photo if isinstance(raw_photo, dict) else None
    raw_occurrence = raw_occurrence if isinstance(raw_occurrence, dict) else None
    raw_media = raw_media if isinstance(raw_media, dict) else None
    coordinates = _coordinates(raw_observation, raw_occurrence)
    payload: dict[str, object] = {
        "atom_type": "image_asset",
        "source_record_id": candidate.source_record_id,
        "source_image_record_id": candidate.source_record_id,
        "source": candidate.source,
        "input_source": candidate.source,
        "image_url": candidate.media_url,
        "source_url": candidate.url,
        "source_locator": candidate.provenance.get("locator"),
        "license": candidate.provenance.get("license"),
        "retrieved_at": candidate.provenance.get("retrieved_at"),
    }
    if raw_observation:
        payload.update(
            {
                "observation_id": raw_observation.get("id"),
                "source_observation_record_id": f"inat:observation:{raw_observation.get('id')}" if raw_observation.get("id") else None,
                "observed_on": raw_observation.get("observed_on"),
                "observed_time": raw_observation.get("time_observed_at"),
                "place": raw_observation.get("place_guess"),
                "place_guess": raw_observation.get("place_guess"),
                "quality_grade": raw_observation.get("quality_grade"),
                "captive": raw_observation.get("captive"),
                "geoprivacy": raw_observation.get("geoprivacy"),
                "coordinate_privacy_status": raw_observation.get("geoprivacy"),
            }
        )
    if raw_photo:
        payload.update(
            {
                "photo_id": raw_photo.get("id"),
                "attribution": raw_photo.get("attribution"),
                "photo_license": raw_photo.get("license_code"),
                "original_dimensions": raw_photo.get("original_dimensions"),
                "width": (raw_photo.get("original_dimensions") or {}).get("width") if isinstance(raw_photo.get("original_dimensions"), dict) else None,
                "height": (raw_photo.get("original_dimensions") or {}).get("height") if isinstance(raw_photo.get("original_dimensions"), dict) else None,
            }
        )
    if raw_occurrence:
        payload.update(
            {
                "occurrence_id": raw_occurrence.get("key"),
                "gbif_key": raw_occurrence.get("key"),
                "source_observation_record_id": f"mosquito_alert:observation:{raw_occurrence.get('key')}" if raw_occurrence.get("key") else None,
                "event_date": raw_occurrence.get("eventDate"),
                "observed_time": raw_occurrence.get("eventTime"),
                "country": raw_occurrence.get("country") or raw_occurrence.get("countryCode"),
                "country_code": raw_occurrence.get("countryCode"),
                "basis_of_record": raw_occurrence.get("basisOfRecord"),
                "identified_by": raw_occurrence.get("identifiedBy"),
                "occurrence_status": raw_occurrence.get("occurrenceStatus"),
                "taxon_key": raw_occurrence.get("taxonKey"),
            }
        )
    if raw_media:
        payload.update(
            {
                "media_format": raw_media.get("format"),
                "image_format": raw_media.get("format"),
                "media_type": raw_media.get("type"),
                "creator": raw_media.get("creator"),
                "rights_holder": raw_media.get("rightsHolder"),
                "media_license": raw_media.get("license"),
            }
        )
    payload.update({key: value for key, value in coordinates.items() if value is not None})
    return {key: value for key, value in payload.items() if value is not None}


def _asset_record(candidate: ImageCandidate, payload: dict[str, object], *, retrieved_at: str) -> EvidenceRecord:
    details = []
    for key, label in (
        ("place", "place"),
        ("country", "country"),
        ("observed_on", "observed on"),
        ("event_date", "event date"),
        ("quality_grade", "quality"),
        ("media_format", "format"),
    ):
        value = payload.get(key)
        if value:
            details.append(f"{label}: {value}")
    detail_text = f" ({'; '.join(details)})" if details else ""
    return EvidenceRecord(
        record_id=f"image_atom:asset:{_safe_id(candidate.source_record_id)}",
        lane="media",
        source=IMAGE_ATOMS_SOURCE_ID,
        title=f"Aedes aegypti image asset from {candidate.source}",
        text=f"Aedes aegypti source image asset derived from {candidate.source} media record {candidate.source_record_id}.{detail_text}",
        species="Aedes aegypti",
        url=candidate.url,
        media_url=candidate.media_url,
        provenance=Provenance(
            source_id=IMAGE_ATOMS_SOURCE_ID,
            locator=f"records#{candidate.source_record_id}",
            retrieved_at=retrieved_at,
            license=candidate.provenance.get("license") if isinstance(candidate.provenance.get("license"), str) else None,
            source_url=candidate.url or candidate.media_url,
        ),
        payload=payload,
    )


def _label_records(candidate: ImageCandidate, asset_payload: dict[str, object], *, retrieved_at: str) -> list[EvidenceRecord]:
    labels: list[tuple[str, object, str]] = []
    for key in ("quality_grade", "basis_of_record", "occurrence_status", "media_format", "media_type"):
        if asset_payload.get(key):
            labels.append((key, asset_payload[key], "source_metadata"))
    raw_occurrence = candidate.payload.get("raw_occurrence")
    if isinstance(raw_occurrence, dict):
        for key, label_type in (("lifeStage", "life_stage"), ("sex", "sex")):
            value = raw_occurrence.get(key)
            if value:
                labels.append((label_type, value, "source_metadata"))
    raw_observation = candidate.payload.get("raw_observation")
    if isinstance(raw_observation, dict):
        annotations = raw_observation.get("annotations")
        if isinstance(annotations, list):
            for annotation in annotations:
                if not isinstance(annotation, dict):
                    continue
                attr = annotation.get("controlled_attribute_id")
                value = annotation.get("controlled_value_id")
                label_type, label_value = INATURALIST_ANNOTATION_MAP.get(
                    (attr, value),
                    (f"inaturalist_annotation_{attr}", value or annotation.get("concatenated_attr_val")),
                )
                if label_value:
                    labels.append((str(label_type), label_value, "inaturalist_annotation"))
    records: list[EvidenceRecord] = []
    seen: set[tuple[str, str]] = set()
    for label_type, label_value, confidence in labels:
        normalized_value = str(label_value).strip()
        if not normalized_value:
            continue
        key = (str(label_type), normalized_value.lower())
        if key in seen:
            continue
        seen.add(key)
        digest = _digest(candidate.source_record_id, label_type, normalized_value)
        records.append(
            EvidenceRecord(
                record_id=f"image_atom:label:{_safe_id(candidate.source_record_id)}:{digest}",
                lane="media",
                source=IMAGE_ATOMS_SOURCE_ID,
                title=f"Aedes aegypti image label {label_type}: {normalized_value}",
                text=(
                    f"Aedes aegypti image label from source metadata: {label_type} = {normalized_value}. "
                    f"Source image record: {candidate.source_record_id}. Confidence: {confidence}."
                ),
                species="Aedes aegypti",
                url=candidate.url,
                media_url=candidate.media_url,
                provenance=Provenance(
                    source_id=IMAGE_ATOMS_SOURCE_ID,
                    locator=f"records#{candidate.source_record_id};label/{label_type}",
                    retrieved_at=retrieved_at,
                    license=candidate.provenance.get("license") if isinstance(candidate.provenance.get("license"), str) else None,
                    source_url=candidate.url or candidate.media_url,
                ),
                payload={
                    "atom_type": "image_label",
                    "source_record_id": candidate.source_record_id,
                    "source_image_record_id": candidate.source_record_id,
                    "source": candidate.source,
                    "input_source": candidate.source,
                    "label_type": label_type,
                    "label_value": normalized_value,
                    "confidence": confidence,
                    "image_url": candidate.media_url,
                },
            )
        )
    return records


def _label_types(records: list[EvidenceRecord]) -> set[str]:
    types = set()
    for record in records:
        if record.payload and record.payload.get("atom_type") == "image_label" and record.payload.get("label_type"):
            types.add(str(record.payload["label_type"]))
    return types


def _gap_records_and_payloads(candidates: list[ImageCandidate], label_records_by_id: dict[str, list[EvidenceRecord]], *, retrieved_at: str) -> tuple[list[EvidenceRecord], list[dict[str, object]]]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for candidate in candidates:
        present = _label_types(label_records_by_id.get(candidate.source_record_id, []))
        for label_type in IMAGE_LABEL_GAP_TYPES:
            if label_type not in present:
                grouped.setdefault((candidate.source, label_type), []).append(candidate.source_record_id)
    gaps: list[dict[str, object]] = []
    records: list[EvidenceRecord] = []
    for index, ((source, label_type), record_ids) in enumerate(sorted(grouped.items()), start=1):
        gap = {
            "source": IMAGE_ATOMS_SOURCE_ID,
            "lane": "media",
            "reason": "image_label_missing",
            "upstream_source": source,
            "label_type": label_type,
            "missing_count": len(record_ids),
            "sample_source_record_ids": record_ids[:10],
            "locator": f"gaps.json#aedes_image_atoms/{index}",
        }
        gaps.append(gap)
        records.append(
            EvidenceRecord(
                record_id=f"image_atom:gap:{_safe_id(source)}:{_safe_id(label_type)}",
                lane="media",
                source=IMAGE_ATOMS_SOURCE_ID,
                title=f"Aedes aegypti image gap missing {label_type}",
                text=(
                    f"Aedes aegypti image label gap: {source} has {len(record_ids)} image asset(s) "
                    f"without source-provided {label_type} metadata."
                ),
                species="Aedes aegypti",
                url=None,
                media_url=None,
                provenance=Provenance(
                    source_id=IMAGE_ATOMS_SOURCE_ID,
                    locator=str(gap["locator"]),
                    retrieved_at=retrieved_at,
                ),
                payload={"atom_type": "image_gap", **gap},
            )
        )
    return records, gaps


def build_image_atom_records(artifact_dir: Path, *, retrieved_at: str | None = None) -> AedesImageAtomsResult:
    retrieved = retrieved_at or utc_now()
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    candidates = _candidate_rows(index)
    records: list[EvidenceRecord] = []
    label_records_by_id: dict[str, list[EvidenceRecord]] = {}
    for candidate in candidates:
        asset_payload = _asset_payload(candidate)
        records.append(_asset_record(candidate, asset_payload, retrieved_at=retrieved))
        labels = _label_records(candidate, asset_payload, retrieved_at=retrieved)
        label_records_by_id[candidate.source_record_id] = labels
        records.extend(labels)
    gap_records, gaps = _gap_records_and_payloads(candidates, label_records_by_id, retrieved_at=retrieved)
    records.extend(gap_records)
    return AedesImageAtomsResult(
        source_id=IMAGE_ATOMS_SOURCE_ID,
        records=records,
        gaps=gaps,
        image_asset_count=len(candidates),
        image_label_count=sum(1 for record in records if record.payload and record.payload.get("atom_type") == "image_label"),
        image_gap_count=len(gap_records),
    )
