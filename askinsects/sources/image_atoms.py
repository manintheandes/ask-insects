from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import re
from pathlib import Path
import struct
from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

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
    mirrored_image_count: int = 0
    verified_image_count: int = 0


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


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_json(raw: object) -> dict[str, object]:
    if not raw:
        return {}
    try:
        payload = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _license_is_unclear(license_value: object) -> bool:
    text = str(license_value or "").strip().lower()
    return not text or any(marker in text for marker in ("unknown", "unclear", "not supplied", "missing", "none"))


def _is_allowed_license(license_value: object, allowed_licenses: tuple[str, ...] | None) -> bool:
    if _license_is_unclear(license_value):
        return False
    if not allowed_licenses:
        return True
    text = str(license_value).lower()
    normalized_text = re.sub(r"[^a-z0-9]+", "", text)
    return any(
        allowed.lower() in text or re.sub(r"[^a-z0-9]+", "", allowed.lower()) in normalized_text
        for allowed in allowed_licenses
    )


def _image_extension(url: str, content_type: str | None = None) -> str:
    content = str(content_type or "").lower()
    if "png" in content:
        return ".png"
    if "gif" in content:
        return ".gif"
    if "webp" in content:
        return ".webp"
    if "jpeg" in content or "jpg" in content:
        return ".jpg"
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp"} else ".jpg"


def _default_fetch_image_bytes(url: str, max_bytes: int) -> tuple[bytes, str | None]:
    request = Request(url, headers={"User-Agent": "AskInsects/0.1 image-atoms"})
    with urlopen(request, timeout=60) as response:
        content_type = str(response.headers.get("content-type") or "").lower()
        if "text/html" in content_type or "application/xhtml" in content_type:
            raise ValueError(f"download content-type is not an image: {content_type}")
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > max_bytes:
            raise ValueError(f"image exceeds max bytes: {content_length} > {max_bytes}")
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"image exceeds max bytes: {len(data)} > {max_bytes}")
    prefix = data[:512].lstrip().lower()
    if prefix.startswith((b"<!doctype html", b"<html", b"<?xml")):
        raise ValueError("download payload is HTML/XML, not image bytes")
    return data, content_type or None


def _jpeg_dimensions_and_exif(data: bytes) -> dict[str, object]:
    if not data.startswith(b"\xff\xd8"):
        return {}
    offset = 2
    result: dict[str, object] = {"image_format": "image/jpeg"}
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        offset += 2
        if marker in (0xD8, 0xD9):
            continue
        if offset + 2 > len(data):
            break
        segment_length = int.from_bytes(data[offset : offset + 2], "big")
        segment_start = offset + 2
        segment_end = offset + segment_length
        if segment_end > len(data) or segment_length < 2:
            break
        segment = data[segment_start:segment_end]
        if marker == 0xE1 and segment.startswith(b"Exif\x00\x00"):
            result["exif_present"] = True
            result["exif_byte_size"] = len(segment)
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF} and len(segment) >= 5:
            result["height"] = int.from_bytes(segment[1:3], "big")
            result["width"] = int.from_bytes(segment[3:5], "big")
            return result
        offset = segment_end
    return result


def _image_metadata(data: bytes, content_type: str | None = None) -> dict[str, object]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return {
            "image_format": "image/png",
            "width": struct.unpack(">I", data[16:20])[0],
            "height": struct.unpack(">I", data[20:24])[0],
        }
    if data.startswith((b"GIF87a", b"GIF89a")) and len(data) >= 10:
        return {
            "image_format": "image/gif",
            "width": struct.unpack("<H", data[6:8])[0],
            "height": struct.unpack("<H", data[8:10])[0],
        }
    jpeg = _jpeg_dimensions_and_exif(data)
    if jpeg:
        return jpeg
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return {"image_format": "image/webp"}
    return {"image_format": content_type} if content_type else {}


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


def _gap_payload(candidate: ImageCandidate, reason: str, **extra: object) -> dict[str, object]:
    payload = {
        "source": IMAGE_ATOMS_SOURCE_ID,
        "lane": "media",
        "reason": reason,
        "upstream_source": candidate.source,
        "record_id": candidate.source_record_id,
        "image_url": candidate.media_url,
        "source_url": candidate.url,
        "license": candidate.provenance.get("license"),
        "locator": candidate.provenance.get("locator"),
        **extra,
    }
    return {key: value for key, value in payload.items() if value not in (None, "", {})}


def _existing_mirror_path(candidate: ImageCandidate, artifact_dir: Path) -> Path | None:
    assets_dir = artifact_dir / "raw" / "image_atoms" / "assets"
    if not assets_dir.exists():
        return None
    prefix = _safe_id(candidate.source_record_id)
    matches = [
        path
        for path in assets_dir.glob(f"{prefix}_*")
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    ]
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def _mirror_payload_for_existing(candidate: ImageCandidate, path: Path, artifact_dir: Path) -> dict[str, object]:
    data = path.read_bytes()
    metadata = _image_metadata(data)
    return {
        "verification_status": "verified" if metadata.get("width") and metadata.get("height") else "mirrored_unverified",
        "sha256": _sha256(data),
        "byte_size": len(data),
        "raw_asset_path": path.relative_to(artifact_dir).as_posix(),
        **metadata,
    }


def _mirror_candidate(
    candidate: ImageCandidate,
    *,
    artifact_dir: Path,
    max_image_bytes: int,
    allowed_licenses: tuple[str, ...] | None,
    allow_unclear_license: bool,
    fetch_image_bytes_fn: Callable[[str, int], tuple[bytes, str | None]],
    gaps: list[dict[str, object]],
) -> dict[str, object]:
    if not allow_unclear_license and not _is_allowed_license(candidate.provenance.get("license"), allowed_licenses):
        gaps.append(_gap_payload(candidate, "image_license_unclear"))
        return {"verification_status": "gapped_license_unclear"}
    try:
        data, content_type = fetch_image_bytes_fn(candidate.media_url, max_image_bytes)
    except Exception as exc:
        gaps.append(_gap_payload(candidate, "image_download_failed", error=str(exc)))
        return {"verification_status": "gapped_download_failed"}
    if len(data) > max_image_bytes:
        gaps.append(_gap_payload(candidate, "image_too_large", byte_size=len(data), max_image_bytes=max_image_bytes))
        return {"verification_status": "gapped_too_large"}
    metadata = _image_metadata(data, content_type)
    digest = _sha256(data)
    raw_dir = artifact_dir / "raw" / "image_atoms" / "assets"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{_safe_id(candidate.source_record_id)}_{digest[:12]}{_image_extension(candidate.media_url, str(metadata.get('image_format') or content_type or ''))}"
    raw_path.write_bytes(data)
    status = "verified" if metadata.get("width") and metadata.get("height") else "mirrored_unverified"
    if status != "verified":
        gaps.append(_gap_payload(candidate, "image_probe_incomplete", raw_asset_path=raw_path.relative_to(artifact_dir).as_posix()))
    return {
        "verification_status": status,
        "sha256": digest,
        "byte_size": len(data),
        "raw_asset_path": raw_path.relative_to(artifact_dir).as_posix(),
        **metadata,
    }


def _asset_record(candidate: ImageCandidate, payload: dict[str, object], *, retrieved_at: str) -> EvidenceRecord:
    details = []
    for key, label in (
        ("place", "place"),
        ("country", "country"),
        ("observed_on", "observed on"),
        ("event_date", "event date"),
        ("quality_grade", "quality"),
        ("media_format", "format"),
        ("verification_status", "verification"),
        ("byte_size", "byte size"),
    ):
        value = payload.get(key)
        if value:
            details.append(f"{label}: {value}")
    width = payload.get("width")
    height = payload.get("height")
    if width and height:
        details.append(f"dimensions: {width}x{height}")
    if payload.get("sha256"):
        details.append(f"sha256: {payload['sha256']}")
    if payload.get("exif_present") is not None:
        details.append(f"exif present: {payload['exif_present']}")
    if payload.get("raw_asset_path"):
        details.append(f"raw asset: {payload['raw_asset_path']}")
    detail_text = f" ({'; '.join(details)})" if details else ""
    return EvidenceRecord(
        record_id=f"image_atom:asset:{_safe_id(candidate.source_record_id)}",
        lane="media",
        source=IMAGE_ATOMS_SOURCE_ID,
        title=f"Aedes aegypti image asset from {candidate.source}",
        text=f"Aedes aegypti source image asset derived from {candidate.source} media record {candidate.source_record_id}.{detail_text}",
        species="Aedes aegypti",
        url=candidate.url,
        media_url=str(payload.get("raw_asset_path") or candidate.media_url),
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


def _gap_record(gap: dict[str, object], *, retrieved_at: str, index: int) -> EvidenceRecord:
    reason = str(gap.get("reason") or "image_gap")
    upstream_source = str(gap.get("upstream_source") or gap.get("source") or "unknown")
    label_type = gap.get("label_type")
    record_key = str(gap.get("record_id") or label_type or f"gap-{index}")
    title_detail = f" missing {label_type}" if label_type else f" {reason}"
    if reason == "image_label_missing" and label_type:
        text = (
            f"Aedes aegypti image label gap: {upstream_source} has {gap.get('missing_count')} image asset(s) "
            f"without source-provided {label_type} metadata."
        )
    else:
        text = f"Aedes aegypti image source gap: {reason}. Upstream source: {upstream_source}."
        if gap.get("record_id"):
            text += f" Source record: {gap.get('record_id')}."
        if gap.get("image_url"):
            text += f" Image URL: {gap.get('image_url')}."
        if gap.get("license"):
            text += f" License: {gap.get('license')}."
        if gap.get("error"):
            text += f" Error: {gap.get('error')}."
    return EvidenceRecord(
        record_id=f"image_atom:gap:{_safe_id(upstream_source)}:{_safe_id(record_key)}:{_digest(reason, record_key, index)}",
        lane="media",
        source=IMAGE_ATOMS_SOURCE_ID,
        title=f"Aedes aegypti image gap{title_detail}",
        text=text,
        species="Aedes aegypti",
        url=gap.get("source_url") if isinstance(gap.get("source_url"), str) else None,
        media_url=None,
        provenance=Provenance(
            source_id=IMAGE_ATOMS_SOURCE_ID,
            locator=str(gap.get("locator") or f"gaps.json#aedes_image_atoms/{index}"),
            retrieved_at=retrieved_at,
            license=gap.get("license") if isinstance(gap.get("license"), str) else None,
            source_url=gap.get("source_url") if isinstance(gap.get("source_url"), str) else None,
        ),
        payload={"atom_type": "image_gap", **gap},
    )


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
        records.append(_gap_record(gap, retrieved_at=retrieved_at, index=index))
    return records, gaps


def build_image_atom_records(
    artifact_dir: Path,
    *,
    retrieved_at: str | None = None,
    mirror_images: bool = False,
    max_image_bytes: int = 5_000_000,
    max_image_mirrors: int = 250,
    allow_unclear_license: bool = False,
    allowed_licenses: tuple[str, ...] | None = None,
    fetch_image_bytes_fn: Callable[[str, int], tuple[bytes, str | None]] | None = None,
) -> AedesImageAtomsResult:
    retrieved = retrieved_at or utc_now()
    if max_image_bytes < 1:
        raise ValueError("max_image_bytes must be positive")
    if max_image_mirrors < 0:
        raise ValueError("max_image_mirrors must be non-negative")
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    candidates = _candidate_rows(index)
    records: list[EvidenceRecord] = []
    mirror_gaps: list[dict[str, object]] = []
    label_records_by_id: dict[str, list[EvidenceRecord]] = {}
    mirrored_image_count = 0
    verified_image_count = 0
    fetcher = fetch_image_bytes_fn or _default_fetch_image_bytes
    for candidate in candidates:
        asset_payload = _asset_payload(candidate)
        existing_mirror = _existing_mirror_path(candidate, artifact_dir)
        if existing_mirror is not None:
            asset_payload.update(_mirror_payload_for_existing(candidate, existing_mirror, artifact_dir))
            mirrored_image_count += 1
            if asset_payload.get("verification_status") == "verified":
                verified_image_count += 1
        elif mirror_images and mirrored_image_count < max_image_mirrors:
            mirror_payload = _mirror_candidate(
                candidate,
                artifact_dir=artifact_dir,
                max_image_bytes=max_image_bytes,
                allowed_licenses=allowed_licenses,
                allow_unclear_license=allow_unclear_license,
                fetch_image_bytes_fn=fetcher,
                gaps=mirror_gaps,
            )
            asset_payload.update(mirror_payload)
            if asset_payload.get("raw_asset_path"):
                mirrored_image_count += 1
            if asset_payload.get("verification_status") == "verified":
                verified_image_count += 1
        records.append(_asset_record(candidate, asset_payload, retrieved_at=retrieved))
        labels = _label_records(candidate, asset_payload, retrieved_at=retrieved)
        label_records_by_id[candidate.source_record_id] = labels
        records.extend(labels)
    if mirror_images and mirrored_image_count >= max_image_mirrors:
        omitted = max(len(candidates) - mirrored_image_count, 0)
        if omitted:
            mirror_gaps.append(
                {
                    "source": IMAGE_ATOMS_SOURCE_ID,
                    "lane": "media",
                    "reason": "image_mirror_limit_applied",
                    "upstream_source": "aedes_image_atoms",
                    "mirror_limit": max_image_mirrors,
                    "omitted_count": omitted,
                    "locator": f"gaps.json#aedes_image_atoms/mirror-limit",
                }
            )
    gap_records, gaps = _gap_records_and_payloads(candidates, label_records_by_id, retrieved_at=retrieved)
    for index, gap in enumerate(mirror_gaps, start=len(gaps) + 1):
        gaps.append(gap)
        gap_records.append(_gap_record(gap, retrieved_at=retrieved, index=index))
    records.extend(gap_records)
    return AedesImageAtomsResult(
        source_id=IMAGE_ATOMS_SOURCE_ID,
        records=records,
        gaps=gaps,
        image_asset_count=len(candidates),
        image_label_count=sum(1 for record in records if record.payload and record.payload.get("atom_type") == "image_label"),
        image_gap_count=len(gap_records),
        mirrored_image_count=mirrored_image_count,
        verified_image_count=verified_image_count,
    )
