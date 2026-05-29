from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Callable, Iterable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.video_atoms import generate_video_artifacts, probe_video_file


DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID = "drosophila_suzukii_video_atoms"
SPECIES = "Drosophila suzukii"
COMMON_NAME = "spotted wing drosophila"
INPUT_SOURCES = ("drosophila_suzukii_deep_sources", "drosophila_suzukii_extracted_facts")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".m4v", ".webm", ".mpg", ".mpeg")
UNCLEAR_LICENSE_MARKERS = ("not supplied", "unknown", "unclear", "not parsed", "missing")


@dataclass(frozen=True)
class DrosophilaSuzukiiVideoCandidate:
    source_record_id: str
    title: str
    text: str
    url: str | None
    media_url: str | None
    source: str
    locator: str
    retrieved_at: str
    license_text: str | None
    source_url: str | None
    payload: dict[str, object]


@dataclass(frozen=True)
class DrosophilaSuzukiiVideoAtomsResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    video_asset_count: int
    mirrored_video_count: int
    verified_video_count: int
    artifact_count: int
    motion_row_count: int


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_id(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value or "")).strip("_") or "video"


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


def _provenance_json(raw: object) -> dict[str, object]:
    payload = _safe_json(raw)
    return payload if isinstance(payload, dict) else {}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _looks_like_video(*values: object) -> bool:
    text = " ".join(str(value or "") for value in values).lower()
    return any(ext in text for ext in VIDEO_EXTENSIONS) or any(term in text for term in (" video", " movie", "moving image"))


def _payload_declares_video_file(payload: dict[str, object]) -> bool:
    text_values: list[object] = [
        payload.get("file_path"),
        payload.get("filename"),
        payload.get("file_name"),
        payload.get("name"),
        payload.get("mime_type"),
        payload.get("mimetype"),
    ]
    for key in ("raw_file", "raw_file_payload"):
        value = payload.get(key)
        if isinstance(value, dict):
            text_values.extend(value.get(field) for field in ("path", "key", "name", "filename", "mimeType", "mimetype", "type"))
    return _looks_like_video(*text_values)


def _walk_payload(value: object) -> Iterable[object]:
    if isinstance(value, dict):
        for nested in value.values():
            yield nested
            yield from _walk_payload(nested)
    elif isinstance(value, list):
        for nested in value:
            yield nested
            yield from _walk_payload(nested)


def _payload_video_urls(payload: dict[str, object]) -> list[str]:
    urls: list[str] = []
    for value in _walk_payload(payload):
        if not isinstance(value, str):
            continue
        if value.startswith(("http://", "https://")) and _looks_like_video(value):
            urls.append(value)
    return list(dict.fromkeys(urls))


def _payload_size(payload: dict[str, object]) -> int | None:
    for key in ("byte_size", "bytes", "size", "file_size", "source_byte_size"):
        value = payload.get(key)
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            pass
    raw_file = payload.get("raw_file")
    if isinstance(raw_file, dict):
        for key in ("size", "file_size", "bytes"):
            value = raw_file.get(key)
            try:
                if value is not None:
                    return int(value)
            except (TypeError, ValueError):
                pass
    return None


def _license_is_clear(license_text: str | None, allowed_licenses: Iterable[str] | None) -> bool:
    text = str(license_text or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if any(marker in lowered for marker in UNCLEAR_LICENSE_MARKERS):
        return False
    allowed = tuple(allowed_licenses or ("CC0", "CC-BY", "CC BY", "Creative Commons", "CC-BY-4.0", "CC BY 4.0"))
    return any(fragment.lower() in lowered for fragment in allowed)


def _normalize_artifact_path(value: str, artifact_dir: Path) -> str:
    path = Path(value)
    if path.is_absolute():
        try:
            return path.relative_to(artifact_dir).as_posix()
        except ValueError:
            return path.as_posix()
    artifact_prefix = artifact_dir.as_posix().rstrip("/") + "/"
    if value.startswith(artifact_prefix):
        return value[len(artifact_prefix) :]
    return path.as_posix()


def _default_fetch_video_bytes(url: str, max_bytes: int) -> bytes:
    request = Request(url, headers={"User-Agent": "AskInsects/0.1 source-plane"})
    try:
        with urlopen(request, timeout=120) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                raise ValueError(f"video_too_large:{content_length}")
            payload = response.read(max_bytes + 1)
    except HTTPError as exc:
        raise ValueError(f"video_download_failed:{exc.code}") from exc
    if len(payload) > max_bytes:
        raise ValueError(f"video_too_large:{len(payload)}")
    return payload


def _source_candidates(index: SourceIndex) -> list[DrosophilaSuzukiiVideoCandidate]:
    source_placeholders = ",".join("?" for _ in INPUT_SOURCES)
    with index.connect() as conn:
        rows = conn.execute(
            f"""
            select r.record_id, r.title, r.text, r.url, r.media_url, r.source, r.provenance_json, p.payload_json
            from records r
            left join record_payloads p on p.record_id=r.record_id
            where r.source in ({source_placeholders})
            """,
            INPUT_SOURCES,
        ).fetchall()
    candidates: list[DrosophilaSuzukiiVideoCandidate] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        payload = _safe_json(row["payload_json"])
        provenance = _provenance_json(row["provenance_json"])
        license_text = str(provenance.get("license") or payload.get("license") or payload.get("license_text") or "").strip() or None
        locator = str(provenance.get("locator") or f"records#{row['record_id']}")
        retrieved_at = str(provenance.get("retrieved_at") or utc_now())
        source_url = str(provenance.get("source_url") or row["url"] or row["media_url"] or "") or None
        urls = [str(row["media_url"])] if row["media_url"] else []
        urls.extend(_payload_video_urls(payload))
        for url in [url for url in urls if url]:
            if not (_looks_like_video(url) or _payload_declares_video_file(payload)):
                continue
            key = (str(row["record_id"]), url)
            if key in seen:
                continue
            seen.add(key)
            candidate_payload = dict(payload)
            candidate_payload["download_url"] = url
            candidate_payload["source_byte_size"] = _payload_size(payload)
            candidates.append(
                DrosophilaSuzukiiVideoCandidate(
                    source_record_id=str(row["record_id"]),
                    title=str(row["title"]),
                    text=str(row["text"]),
                    url=str(row["url"]) if row["url"] else None,
                    media_url=url,
                    source=str(row["source"]),
                    locator=locator,
                    retrieved_at=retrieved_at,
                    license_text=license_text,
                    source_url=source_url,
                    payload=candidate_payload,
                )
            )
    return candidates


def _record_for_gap(
    reason: str,
    *,
    retrieved_at: str,
    candidate: DrosophilaSuzukiiVideoCandidate | None = None,
    payload: dict[str, object] | None = None,
    ordinal: int = 1,
) -> EvidenceRecord:
    source_record_id = candidate.source_record_id if candidate else "swd_video_boundary"
    download_url = candidate.media_url if candidate else None
    source_url = candidate.source_url if candidate else None
    license_text = candidate.license_text if candidate else None
    locator = candidate.locator if candidate else "drosophila_suzukii_video_atoms#gap"
    gap_payload = {
        "atom_type": "video_gap",
        "reason": reason,
        "source_record_id": source_record_id,
        "download_url": download_url,
        "source_url": source_url,
        "license": license_text,
        "locator": locator,
        **(payload or {}),
    }
    return EvidenceRecord(
        record_id=f"swd:video_atom:gap:{_safe_id(source_record_id)}:{_safe_id(reason)}:{ordinal}",
        lane="media",
        source=DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID,
        title=f"Drosophila suzukii video source gap: {reason}",
        text=(
            f"Ask Insects video gap for {COMMON_NAME}: {reason}. "
            f"Source record: {source_record_id}. Download URL: {download_url or 'not supplied'}."
        ),
        species=SPECIES,
        url=source_url or download_url,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID,
            locator=locator,
            retrieved_at=retrieved_at,
            license=license_text or "Ask Insects source gap",
            source_url=source_url or download_url,
        ),
        payload=gap_payload,
    )


def _record_for_asset(
    candidate: DrosophilaSuzukiiVideoCandidate,
    *,
    retrieved_at: str,
    verification_status: str,
    mirror_path: str | None = None,
    byte_size: int | None = None,
    sha256: str | None = None,
    probe: dict[str, object] | None = None,
) -> EvidenceRecord:
    probe = probe or {}
    fields = {
        "duration_seconds": probe.get("duration_seconds"),
        "fps": probe.get("fps"),
        "width": probe.get("width"),
        "height": probe.get("height"),
        "codec": probe.get("codec"),
    }
    text_bits = [
        f"{COMMON_NAME} video asset from {candidate.source}.",
        f"Verification status: {verification_status}.",
        f"License: {candidate.license_text or 'not supplied'}.",
    ]
    if fields["duration_seconds"] is not None:
        text_bits.append(f"Duration seconds: {fields['duration_seconds']}.")
    if fields["fps"] is not None:
        text_bits.append(f"FPS: {fields['fps']}.")
    if fields["width"] is not None and fields["height"] is not None:
        text_bits.append(f"Resolution: {fields['width']}x{fields['height']}.")
    if fields["codec"] is not None:
        text_bits.append(f"Codec: {fields['codec']}.")
    payload = {
        "atom_type": "video_asset",
        "source_video_record_id": candidate.source_record_id,
        "source": candidate.source,
        "download_url": candidate.media_url,
        "source_url": candidate.source_url,
        "license": candidate.license_text,
        "byte_size": byte_size if byte_size is not None else candidate.payload.get("source_byte_size"),
        "sha256": sha256,
        "mirror_path": mirror_path,
        "verification_status": verification_status,
        **fields,
    }
    return EvidenceRecord(
        record_id=f"swd:video_atom:asset:{_digest(candidate.source_record_id, candidate.media_url)}",
        lane="media",
        source=DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID,
        title=f"Drosophila suzukii video atom: {candidate.title}",
        text=" ".join(text_bits),
        species=SPECIES,
        url=candidate.source_url or candidate.url,
        media_url=candidate.media_url,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID,
            locator=candidate.locator,
            retrieved_at=retrieved_at,
            license=candidate.license_text,
            source_url=candidate.source_url or candidate.media_url,
        ),
        payload=payload,
    )


def _artifact_records(asset: EvidenceRecord, artifact_payload: dict[str, object], *, retrieved_at: str) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    specs: list[tuple[str, str, object]] = [
        ("video_thumbnail", "thumbnail_path", artifact_payload.get("thumbnail_path")),
        ("video_preview_clip", "preview_clip_path", artifact_payload.get("preview_clip_path")),
        ("video_frame_manifest", "frame_manifest_path", artifact_payload.get("frame_manifest_path")),
    ]
    for index, path in enumerate(artifact_payload.get("keyframe_paths") or [], start=1):
        specs.append(("video_keyframe", f"keyframe_paths/{index}", path))
    for atom_type, payload_key, path_value in specs:
        if not path_value:
            continue
        rel_path = str(path_value)
        records.append(
            EvidenceRecord(
                record_id=f"swd:video_atom:{atom_type}:{_safe_id(asset.record_id)}:{_digest(payload_key, rel_path)}",
                lane="media",
                source=DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID,
                title=f"Drosophila suzukii {atom_type.replace('_', ' ')}",
                text=f"Inspectable {COMMON_NAME} video artifact derived from {asset.record_id}: {rel_path}.",
                species=SPECIES,
                url=asset.url,
                media_url=rel_path,
                provenance=Provenance(
                    source_id=DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID,
                    locator=rel_path,
                    retrieved_at=retrieved_at,
                    license=asset.provenance.license,
                    source_url=asset.media_url,
                ),
                payload={
                    "atom_type": atom_type,
                    "source_video_asset_id": asset.record_id,
                    "artifact_path": rel_path,
                    "artifact_payload_key": payload_key,
                },
            )
        )
    return records


def _coerce_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _infer_label(text: str, labels: tuple[tuple[str, tuple[str, ...]], ...], default: str | None = None) -> str | None:
    lowered = text.lower()
    for label, terms in labels:
        if any(term in lowered for term in terms):
            return label
    return default


def _motion_context(candidate: DrosophilaSuzukiiVideoCandidate) -> str:
    return " ".join(
        str(value or "")
        for value in (
            candidate.title,
            candidate.text,
            candidate.url,
            candidate.media_url,
            candidate.payload.get("download_url"),
            candidate.payload.get("name"),
            candidate.payload.get("file_name"),
        )
    )


def _record_for_motion_interval(
    asset: EvidenceRecord,
    candidate: DrosophilaSuzukiiVideoCandidate,
    *,
    retrieved_at: str,
    ordinal: int,
) -> EvidenceRecord | None:
    if asset.payload.get("verification_status") != "verified":
        return None
    duration_seconds = _coerce_float(asset.payload.get("duration_seconds"))
    fps = _coerce_float(asset.payload.get("fps"))
    frame_end = int(round(duration_seconds * fps)) if duration_seconds is not None and fps is not None else None
    context = _motion_context(candidate)
    behavior_type = _infer_label(
        context,
        (
            ("oviposition", ("oviposition", "egg laying", "egg-laying", "egg")),
            ("flight", ("flight", "flying")),
            ("feeding", ("feeding", "feed", "fungus", "yeast", "fruit")),
            ("locomotion", ("tracking", "walking", "locomotor", "locomotion", "movement", "moving")),
            ("mating", ("mating", "courtship", "copulation")),
            ("trap response", ("trap", "attractant", "bait")),
        ),
        default="visible motion",
    )
    life_stage = _infer_label(
        context,
        (
            ("adult", ("adult", "female", "male")),
            ("larva", ("larva", "larvae")),
            ("pupa", ("pupa", "pupae")),
            ("egg", ("egg",)),
        ),
    )
    sex = _infer_label(context, (("female", ("female", "females")), ("male", ("male", "males"))))
    stimulus = _infer_label(
        context,
        (
            ("fruit", ("fruit", "berry", "cherry", "blueberry", "raspberry", "strawberry")),
            ("fungus", ("fungus", "fungal")),
            ("yeast", ("yeast",)),
            ("trap attractant", ("trap", "attractant", "bait")),
        ),
    )
    arena = _infer_label(
        context,
        (
            ("laboratory arena", ("arena", "chamber", "cage", "assay")),
            ("host substrate", ("fruit", "berry", "fungus", "yeast")),
            ("field setting", ("field", "orchard", "vineyard")),
        ),
    )
    mirror_path = asset.payload.get("mirror_path")
    source_table_locator = str(mirror_path or candidate.locator)
    payload = {
        "atom_type": "video_motion_row",
        "source_video_asset_id": asset.record_id,
        "source_video_record_id": candidate.source_record_id,
        "source_table": "derived_from_video_probe",
        "source_table_locator": source_table_locator,
        "track_id": "video-interval",
        "frame_start": 0,
        "frame_end": frame_end,
        "time_start_seconds": 0.0,
        "time_end_seconds": duration_seconds,
        "x": None,
        "y": None,
        "coordinates_available": False,
        "coordinate_detail": "source trajectory table not available",
        "behavior_type": behavior_type,
        "life_stage": life_stage,
        "sex": sex,
        "assay": "source video observation",
        "stimulus": stimulus,
        "arena": arena,
        "confidence": "derived_video_interval_no_tracking_table",
        "duration_seconds": duration_seconds,
        "fps": fps,
        "source_title": candidate.title,
    }
    range_text = "full verified video interval"
    if duration_seconds is not None:
        range_text = f"0.0 to {duration_seconds:g} seconds"
    return EvidenceRecord(
        record_id=f"swd:video_atom:motion_interval:{_safe_id(asset.record_id)}:{ordinal}",
        lane="behavior",
        source=DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID,
        title=f"Drosophila suzukii video motion interval: {behavior_type}",
        text=(
            f"Derived {COMMON_NAME} motion interval from verified source video {asset.record_id}: "
            f"{behavior_type} over {range_text}. Coordinates are not available because no source "
            "trajectory table has been parsed for this video."
        ),
        species=SPECIES,
        url=asset.url,
        media_url=asset.media_url,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID,
            locator=source_table_locator,
            retrieved_at=retrieved_at,
            license=asset.provenance.license,
            source_url=asset.media_url,
        ),
        payload=payload,
    )


def build_drosophila_suzukii_video_atom_records(
    artifact_dir: Path,
    *,
    retrieved_at: str | None = None,
    max_video_bytes: int = 750_000_000,
    mirror_videos: bool = False,
    generate_artifacts: bool = False,
    allow_unclear_license: bool = False,
    allowed_licenses: Iterable[str] | None = None,
    fetch_video_bytes_fn: Callable[[str, int], bytes] | None = None,
    probe_video_file_fn: Callable[[Path], dict[str, object]] | None = None,
    artifact_generator_fn: Callable[[Path, Path, dict[str, object]], dict[str, object]] | None = None,
) -> DrosophilaSuzukiiVideoAtomsResult:
    artifact_dir = Path(artifact_dir)
    retrieved_at = retrieved_at or utc_now()
    if max_video_bytes < 1:
        raise ValueError("max_video_bytes must be positive")
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    candidates = _source_candidates(index)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    mirrored_video_count = 0
    verified_video_count = 0
    artifact_count = 0
    motion_row_count = 0
    fetcher = fetch_video_bytes_fn or _default_fetch_video_bytes
    probe_fn = probe_video_file_fn or probe_video_file
    artifact_fn = artifact_generator_fn or generate_video_artifacts
    if not candidates:
        gap = {"source": DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID, "reason": "swd_video_candidates_not_found"}
        gaps.append(gap)
        records.append(_record_for_gap("swd_video_candidates_not_found", retrieved_at=retrieved_at, payload=gap))
    for ordinal, candidate in enumerate(candidates, start=1):
        source_size = candidate.payload.get("source_byte_size")
        if isinstance(source_size, int) and source_size > max_video_bytes:
            gap = {"source": DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID, "reason": "video_too_large", "record_id": candidate.source_record_id, "byte_size": source_size}
            gaps.append(gap)
            records.append(_record_for_gap("video_too_large", retrieved_at=retrieved_at, candidate=candidate, payload=gap, ordinal=ordinal))
            records.append(_record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="manifest_only_too_large"))
            continue
        if mirror_videos and not allow_unclear_license and not _license_is_clear(candidate.license_text, allowed_licenses):
            gap = {"source": DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID, "reason": "video_license_unclear", "record_id": candidate.source_record_id}
            gaps.append(gap)
            records.append(_record_for_gap("video_license_unclear", retrieved_at=retrieved_at, candidate=candidate, payload=gap, ordinal=ordinal))
            records.append(_record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="manifest_only_license_unclear"))
            continue
        if not mirror_videos:
            records.append(_record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="manifest_only"))
            continue
        raw_dir = artifact_dir / "raw" / "drosophila_suzukii_video_atoms" / "mirrors"
        raw_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(str(candidate.media_url).split("?", 1)[0]).suffix or ".mp4"
        asset_path = raw_dir / f"{_safe_id(candidate.source_record_id)}_{_digest(candidate.media_url)}{suffix}"
        try:
            video_bytes = fetcher(str(candidate.media_url), max_video_bytes)
            asset_path.write_bytes(video_bytes)
            byte_size = len(video_bytes)
            if byte_size > max_video_bytes:
                raise ValueError(f"video_too_large:{byte_size}")
        except Exception as exc:
            reason = "video_download_failed"
            if str(exc).startswith("video_too_large:"):
                reason = "video_too_large"
            gap = {"source": DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID, "reason": reason, "record_id": candidate.source_record_id, "error": str(exc)}
            gaps.append(gap)
            records.append(_record_for_gap(reason, retrieved_at=retrieved_at, candidate=candidate, payload=gap, ordinal=ordinal))
            records.append(_record_for_asset(candidate, retrieved_at=retrieved_at, verification_status=f"gapped_{reason}"))
            continue
        sha256 = _sha256_file(asset_path)
        mirror_path = _normalize_artifact_path(asset_path.as_posix(), artifact_dir)
        try:
            probe = probe_fn(asset_path)
            verification_status = "verified"
            verified_video_count += 1
        except FileNotFoundError as exc:
            probe = {}
            verification_status = "mirrored_unprobed"
            gap = {"source": DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID, "reason": "video_probe_tool_missing", "record_id": candidate.source_record_id, "error": str(exc)}
            gaps.append(gap)
            records.append(_record_for_gap("video_probe_tool_missing", retrieved_at=retrieved_at, candidate=candidate, payload=gap, ordinal=ordinal))
        except Exception as exc:
            probe = {}
            verification_status = "mirrored_probe_failed"
            gap = {"source": DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID, "reason": "video_probe_failed", "record_id": candidate.source_record_id, "error": str(exc)}
            gaps.append(gap)
            records.append(_record_for_gap("video_probe_failed", retrieved_at=retrieved_at, candidate=candidate, payload=gap, ordinal=ordinal))
        mirrored_video_count += 1
        asset = _record_for_asset(
            candidate,
            retrieved_at=retrieved_at,
            verification_status=verification_status,
            mirror_path=mirror_path,
            byte_size=asset_path.stat().st_size,
            sha256=sha256,
            probe=probe,
        )
        records.append(asset)
        motion_record = _record_for_motion_interval(asset, candidate, retrieved_at=retrieved_at, ordinal=ordinal)
        if motion_record is not None:
            motion_row_count += 1
            records.append(motion_record)
        if generate_artifacts and verification_status == "verified":
            try:
                output_dir = artifact_dir / "raw" / "drosophila_suzukii_video_atoms" / "artifacts" / _safe_id(asset.record_id)
                artifact_payload = artifact_fn(asset_path, output_dir, asset.payload or {})
                normalized = {
                    key: ([_normalize_artifact_path(str(path), artifact_dir) for path in value] if isinstance(value, list) else _normalize_artifact_path(str(value), artifact_dir))
                    for key, value in artifact_payload.items()
                }
                artifact_records = _artifact_records(asset, normalized, retrieved_at=retrieved_at)
                artifact_count += len(artifact_records)
                records.extend(artifact_records)
            except FileNotFoundError as exc:
                gap = {"source": DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID, "reason": "video_artifact_tool_missing", "record_id": candidate.source_record_id, "error": str(exc)}
                gaps.append(gap)
                records.append(_record_for_gap("video_artifact_tool_missing", retrieved_at=retrieved_at, candidate=candidate, payload=gap, ordinal=ordinal))
            except Exception as exc:
                gap = {"source": DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID, "reason": "video_artifact_generation_failed", "record_id": candidate.source_record_id, "error": str(exc)}
                gaps.append(gap)
                records.append(_record_for_gap("video_artifact_generation_failed", retrieved_at=retrieved_at, candidate=candidate, payload=gap, ordinal=ordinal))
    if candidates:
        gap = {
            "source": DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID,
            "reason": "source_trajectory_tables_not_available_for_swd",
            "candidate_count": len(candidates),
            "derived_motion_interval_count": motion_row_count,
        }
        gaps.append(gap)
        records.append(_record_for_gap("source_trajectory_tables_not_available_for_swd", retrieved_at=retrieved_at, payload=gap, ordinal=len(records) + 1))
    return DrosophilaSuzukiiVideoAtomsResult(
        source_id=DROSOPHILA_SUZUKII_VIDEO_ATOMS_SOURCE_ID,
        records=records,
        gaps=gaps,
        video_asset_count=sum(1 for record in records if record.payload and record.payload.get("atom_type") == "video_asset"),
        mirrored_video_count=mirrored_video_count,
        verified_video_count=verified_video_count,
        artifact_count=artifact_count,
        motion_row_count=motion_row_count,
    )
