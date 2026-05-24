from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable, Iterable
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance


VIDEO_ATOMS_SOURCE_ID = "aedes_video_atoms"
VIDEO_SOURCE_IDS = {
    "pmc_open_access_videos",
    "dryad_aedes_behavior_videos",
    "mendeley_aedes_behavior_media",
    "osf_flighttrackai_aedes_videos",
}
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".m4v", ".webm", ".mpg", ".mpeg")
NON_VIDEO_MEDIA_EXTENSIONS = (
    ".aac",
    ".csv",
    ".doc",
    ".docx",
    ".flac",
    ".html",
    ".json",
    ".mp3",
    ".pdf",
    ".tsv",
    ".txt",
    ".wav",
    ".xls",
    ".xlsx",
)
VIDEO_TERMS = ("video", "movie", "flight", "tracking", "high-speed", "wingbeat")
UNCLEAR_LICENSE_MARKERS = ("not supplied", "unknown", "unclear", "not parsed", "missing")
MOTION_HEADERS = {
    "video",
    "video_id",
    "track",
    "track_id",
    "frame",
    "time",
    "time_seconds",
    "position_t",
    "x",
    "position_x",
    "y",
    "position_y",
    "behavior",
}
MOTION_HEADER_ALIASES = {
    "source_video_record_id": "video_id",
    "track": "track_id",
    "trackid": "track_id",
    "tracking_id": "track_id",
    "position_t": "time_seconds",
    "timestamp": "time_seconds",
    "t": "time_seconds",
    "position_x": "x",
    "x_position": "x",
    "pos_x": "x",
    "center_x": "x",
    "position_y": "y",
    "y_position": "y",
    "pos_y": "y",
    "center_y": "y",
    "behavioral_activity": "behavior",
    "behavioural_activity": "behavior",
    "behavior_type": "behavior",
    "life stage": "life_stage",
}
DISCOVERY_REPOSITORIES = (
    "pmc_oa",
    "dryad",
    "mendeley",
    "osf",
    "zenodo",
    "figshare",
    "institutional",
    "paper_supplements",
)


@dataclass(frozen=True)
class AedesVideoAtomsResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    video_asset_count: int
    mirrored_video_count: int
    verified_video_count: int
    artifact_count: int
    motion_row_count: int
    discovery_candidate_count: int


@dataclass(frozen=True)
class VideoCandidate:
    source_record_id: str
    title: str
    text: str
    species: str | None
    url: str | None
    media_url: str | None
    source: str
    provenance: dict[str, object]
    payload: dict[str, object]
    discovery_repository: str | None = None


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_id(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value)).strip("_") or "video"


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


def _license_is_unclear(license_value: object) -> bool:
    text = str(license_value or "").strip().lower()
    return not text or any(marker in text for marker in UNCLEAR_LICENSE_MARKERS)


def _is_allowed_license(license_value: object, allowed_licenses: Iterable[str] | None) -> bool:
    if _license_is_unclear(license_value):
        return False
    if not allowed_licenses:
        return True
    normalized = str(license_value).lower()
    return any(str(license_name).lower() in normalized for license_name in allowed_licenses)


def _contains_non_video_media_file(*values: object) -> bool:
    text = " ".join(str(value or "").lower() for value in values)
    return any(re.search(rf"{re.escape(extension)}(?:\b|$|[?#])", text) for extension in NON_VIDEO_MEDIA_EXTENSIONS)


def _looks_like_video(*values: object) -> bool:
    text = " ".join(str(value or "").lower() for value in values)
    if any(extension in text for extension in VIDEO_EXTENSIONS):
        return True
    if _contains_non_video_media_file(*values):
        return False
    return any(term in text for term in VIDEO_TERMS)


def _download_url(row: dict[str, object], payload: dict[str, object]) -> str | None:
    for key in ("download_url", "video_url", "media_url", "url", "source_url"):
        value = payload.get(key) if key in payload else row.get(key)
        if isinstance(value, str) and value:
            return value
    media_url = row.get("media_url")
    return str(media_url) if media_url else None


def _source_dataset(row: dict[str, object], payload: dict[str, object]) -> str:
    for key in ("article_title", "dataset_title", "project_title", "title", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    title = str(row.get("title") or "")
    if " from " in title:
        return title.split(" from ", 1)[1].strip()
    return title or str(row.get("source") or "Aedes video source")


def _repository_for_source(source: str) -> str | None:
    return {
        "pmc_open_access_videos": "pmc_oa",
        "dryad_aedes_behavior_videos": "dryad",
        "mendeley_aedes_behavior_media": "mendeley",
        "osf_flighttrackai_aedes_videos": "osf",
    }.get(source)


def _size_from_candidate(candidate: VideoCandidate) -> int | None:
    for key in ("size", "size_bytes", "byte_size"):
        value = candidate.payload.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    match = re.search(r"size bytes:\s*(\d+)", candidate.text, re.I)
    return int(match.group(1)) if match else None


def _candidate_rows(index: SourceIndex) -> list[VideoCandidate]:
    rows = index.sql(
        """
        SELECT r.*, p.payload_json
        FROM records r
        LEFT JOIN record_payloads p ON p.record_id = r.record_id
        WHERE r.source IN ('pmc_open_access_videos', 'dryad_aedes_behavior_videos', 'mendeley_aedes_behavior_media', 'osf_flighttrackai_aedes_videos')
          AND lower(coalesce(r.species, '')) = 'aedes aegypti'
          AND r.lane = 'media'
        ORDER BY r.record_id
        """,
        limit=100000,
    )
    candidates: list[VideoCandidate] = []
    for row in rows:
        payload = _safe_json(row.get("payload_json"))
        download_url = _download_url(row, payload)
        if not _looks_like_video(
            row.get("title"),
            row.get("text"),
            row.get("media_url"),
            row.get("url"),
            download_url,
            payload.get("filename"),
            payload.get("name"),
            payload.get("materialized_path"),
        ):
            continue
        provenance = _safe_json(row.get("provenance_json"))
        candidates.append(
            VideoCandidate(
                source_record_id=str(row["record_id"]),
                title=str(row["title"]),
                text=str(row["text"]),
                species=row.get("species") if isinstance(row.get("species"), str) else None,
                url=row.get("url") if isinstance(row.get("url"), str) else None,
                media_url=download_url,
                source=str(row["source"]),
                provenance=provenance,
                payload={**payload, "download_url": download_url, "source_dataset": _source_dataset(row, payload)},
            )
        )
    return candidates


def _record_for_asset(
    candidate: VideoCandidate,
    *,
    retrieved_at: str,
    verification_status: str = "candidate",
    extra_payload: dict[str, object] | None = None,
) -> EvidenceRecord:
    payload = {
        "atom_type": "video_asset",
        "source_video_record_id": candidate.source_record_id,
        "source_dataset": candidate.payload.get("source_dataset") or candidate.title,
        "download_url": candidate.media_url,
        "license": candidate.provenance.get("license"),
        "verification_status": verification_status,
        "source_video_provenance": candidate.provenance,
        "source_video_payload": candidate.payload,
    }
    if candidate.discovery_repository:
        payload["discovery_repository"] = candidate.discovery_repository
        payload["repository"] = candidate.discovery_repository
    else:
        repository = _repository_for_source(candidate.source)
        if repository:
            payload["repository"] = repository
    if extra_payload:
        payload.update(extra_payload)
    digest = _digest(candidate.source_record_id, candidate.media_url, verification_status)
    text_parts = [
        f"Aedes aegypti video asset from {payload['source_dataset']}.",
        f"Source record: {candidate.source_video_record_id if hasattr(candidate, 'source_video_record_id') else candidate.source_record_id}.",
    ]
    if candidate.media_url:
        text_parts.append(f"Download URL: {candidate.media_url}.")
    if payload.get("duration_seconds") is not None:
        text_parts.append(
            f"Duration {payload.get('duration_seconds')} seconds, {payload.get('fps')} fps, "
            f"{payload.get('width')}x{payload.get('height')}, codec {payload.get('codec')}."
        )
    return EvidenceRecord(
        record_id=f"video_atom:asset:{_safe_id(candidate.source_record_id)}:{digest}",
        lane="media",
        source=VIDEO_ATOMS_SOURCE_ID,
        title=f"Aedes aegypti video asset {candidate.title}",
        text=" ".join(text_parts),
        species=candidate.species or "Aedes aegypti",
        url=candidate.url,
        media_url=candidate.media_url,
        provenance=Provenance(
            source_id=VIDEO_ATOMS_SOURCE_ID,
            locator=f"records#{candidate.source_record_id}",
            retrieved_at=retrieved_at,
            license=candidate.provenance.get("license") if isinstance(candidate.provenance.get("license"), str) else None,
            source_url=candidate.provenance.get("source_url") if isinstance(candidate.provenance.get("source_url"), str) else candidate.url,
        ),
        payload=payload,
    )


def _default_fetch_video_bytes(url: str, max_bytes: int) -> bytes:
    request = Request(url, headers={"User-Agent": "AskInsects/0.1 video-atoms"})
    with urlopen(request, timeout=120) as response:
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > max_bytes:
            raise ValueError(f"video exceeds max bytes: {content_length} > {max_bytes}")
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"video exceeds max bytes: {len(data)} > {max_bytes}")
    return data


def _fetch_json(url: str) -> object:
    request = Request(url, headers={"User-Agent": "AskInsects/0.1 video-discovery"})
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _default_zenodo_discovery_client() -> list[dict[str, object]]:
    query = urlencode({"q": '"Aedes aegypti" (video OR movie OR mp4 OR tracking)', "size": "25"})
    payload = _fetch_json(f"https://zenodo.org/api/records?{query}")
    payload = payload if isinstance(payload, dict) else {}
    hits = payload.get("hits")
    records = hits.get("hits") if isinstance(hits, dict) else []
    discovered: list[dict[str, object]] = []
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        files = record.get("files") if isinstance(record.get("files"), list) else []
        title = str(metadata.get("title") or record.get("title") or "Zenodo Aedes video candidate")
        description = str(metadata.get("description") or "")
        license_payload = metadata.get("license") if isinstance(metadata.get("license"), dict) else {}
        license_value = license_payload.get("id") or license_payload.get("title") or metadata.get("license")
        source_url = None
        links = record.get("links") if isinstance(record.get("links"), dict) else {}
        if isinstance(links.get("html"), str):
            source_url = links["html"]
        elif isinstance(record.get("doi_url"), str):
            source_url = record["doi_url"]
        for file_payload in files:
            if not isinstance(file_payload, dict):
                continue
            filename = str(file_payload.get("key") or file_payload.get("filename") or "")
            file_links = file_payload.get("links") if isinstance(file_payload.get("links"), dict) else {}
            download_url = file_links.get("self") or file_links.get("download")
            if not isinstance(download_url, str) or not _looks_like_video(filename, download_url, title, description):
                continue
            discovered.append(
                {
                    "repository": "zenodo",
                    "title": title,
                    "description": description,
                    "filename": filename,
                    "download_url": download_url,
                    "source_url": source_url,
                    "license": license_value,
                    "species_scope": f"{title} {description}",
                    "retrieved_at": utc_now(),
                }
            )
    return discovered


def _default_figshare_discovery_client() -> list[dict[str, object]]:
    query = urlencode({"search_for": "Aedes aegypti video", "page_size": "25"})
    payload = _fetch_json(f"https://api.figshare.com/v2/articles/search?{query}")
    summaries = payload if isinstance(payload, list) else []
    discovered: list[dict[str, object]] = []
    for summary in summaries:
        if not isinstance(summary, dict):
            continue
        article_id = summary.get("id")
        if not article_id:
            continue
        detail = _fetch_json(f"https://api.figshare.com/v2/articles/{article_id}")
        title = str(detail.get("title") or summary.get("title") or "Figshare Aedes video candidate")
        description = str(detail.get("description") or "")
        license_payload = detail.get("license") if isinstance(detail.get("license"), dict) else {}
        license_value = license_payload.get("name") or license_payload.get("url")
        source_url = detail.get("url_public_html") if isinstance(detail.get("url_public_html"), str) else summary.get("url_public_html")
        files = detail.get("files") if isinstance(detail.get("files"), list) else []
        for file_payload in files:
            if not isinstance(file_payload, dict):
                continue
            filename = str(file_payload.get("name") or "")
            download_url = file_payload.get("download_url")
            if not isinstance(download_url, str) or not _looks_like_video(filename, download_url, title, description):
                continue
            discovered.append(
                {
                    "repository": "figshare",
                    "title": title,
                    "description": description,
                    "filename": filename,
                    "download_url": download_url,
                    "source_url": source_url,
                    "license": license_value,
                    "species_scope": f"{title} {description}",
                    "retrieved_at": utc_now(),
                }
            )
    return discovered


def default_discovery_clients() -> dict[str, Callable[[], list[dict[str, object]]]]:
    return {
        "zenodo": _default_zenodo_discovery_client,
        "figshare": _default_figshare_discovery_client,
    }


def probe_video_file(path: Path) -> dict[str, object]:
    if shutil.which("ffprobe") is None:
        raise FileNotFoundError("ffprobe not found")
    output = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        text=True,
    )
    payload = json.loads(output)
    streams = payload.get("streams") if isinstance(payload, dict) else []
    video_stream = next((stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"), {})
    fmt = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    rate = str(video_stream.get("avg_frame_rate") or "0/1")
    fps = None
    if "/" in rate:
        numerator, denominator = rate.split("/", 1)
        try:
            fps = float(numerator) / float(denominator)
        except (ValueError, ZeroDivisionError):
            fps = None
    return {
        "duration_seconds": float(fmt["duration"]) if fmt.get("duration") else None,
        "fps": fps,
        "width": int(video_stream["width"]) if video_stream.get("width") else None,
        "height": int(video_stream["height"]) if video_stream.get("height") else None,
        "codec": video_stream.get("codec_name"),
    }


def _asset_extension(candidate: VideoCandidate) -> str:
    parsed = urlparse(candidate.media_url or "")
    suffix = Path(parsed.path).suffix.lower()
    return suffix if suffix in VIDEO_EXTENSIONS else ".mp4"


def _mirror_candidate(
    candidate: VideoCandidate,
    *,
    artifact_dir: Path,
    retrieved_at: str,
    max_video_bytes: int,
    fetch_video_bytes_fn: Callable[[str, int], bytes],
    probe_video_file_fn: Callable[[Path], dict[str, object]],
    allowed_licenses: Iterable[str] | None,
    allow_unclear_license: bool,
    gaps: list[dict[str, object]],
) -> tuple[EvidenceRecord, Path | None]:
    if not candidate.media_url:
        gaps.append({"source": VIDEO_ATOMS_SOURCE_ID, "reason": "video_download_url_missing", "record_id": candidate.source_record_id})
        return _record_for_asset(candidate, retrieved_at=retrieved_at), None
    if not allow_unclear_license and not _is_allowed_license(candidate.provenance.get("license"), allowed_licenses):
        gaps.append(
            {
                "source": VIDEO_ATOMS_SOURCE_ID,
                "reason": "video_license_unclear",
                "record_id": candidate.source_record_id,
                "license": candidate.provenance.get("license"),
            }
        )
        size = _size_from_candidate(candidate)
        if size is not None and size > max_video_bytes:
            gaps.append(
                {
                    "source": VIDEO_ATOMS_SOURCE_ID,
                    "reason": "video_too_large",
                    "record_id": candidate.source_record_id,
                    "byte_size": size,
                    "max_video_bytes": max_video_bytes,
                }
            )
        return _record_for_asset(candidate, retrieved_at=retrieved_at), None
    size = _size_from_candidate(candidate)
    if size is not None and size > max_video_bytes:
        gaps.append(
            {
                "source": VIDEO_ATOMS_SOURCE_ID,
                "reason": "video_too_large",
                "record_id": candidate.source_record_id,
                "byte_size": size,
                "max_video_bytes": max_video_bytes,
            }
        )
        return _record_for_asset(candidate, retrieved_at=retrieved_at), None
    try:
        data = fetch_video_bytes_fn(candidate.media_url, max_video_bytes)
    except Exception as exc:
        gaps.append({"source": VIDEO_ATOMS_SOURCE_ID, "reason": "video_download_failed", "record_id": candidate.source_record_id, "error": str(exc)})
        return _record_for_asset(candidate, retrieved_at=retrieved_at), None
    if len(data) > max_video_bytes:
        gaps.append(
            {
                "source": VIDEO_ATOMS_SOURCE_ID,
                "reason": "video_too_large",
                "record_id": candidate.source_record_id,
                "byte_size": len(data),
                "max_video_bytes": max_video_bytes,
            }
        )
        return _record_for_asset(candidate, retrieved_at=retrieved_at), None
    digest = hashlib.sha256(data).hexdigest()
    raw_dir = artifact_dir / "raw" / "video_atoms" / "assets"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{_safe_id(candidate.source_record_id)}_{digest[:12]}{_asset_extension(candidate)}"
    raw_path.write_bytes(data)
    probe_payload: dict[str, object] = {}
    try:
        probe_payload = probe_video_file_fn(raw_path)
    except FileNotFoundError as exc:
        gaps.append({"source": VIDEO_ATOMS_SOURCE_ID, "reason": "video_probe_tool_missing", "record_id": candidate.source_record_id, "error": str(exc)})
    except Exception as exc:
        gaps.append({"source": VIDEO_ATOMS_SOURCE_ID, "reason": "video_probe_failed", "record_id": candidate.source_record_id, "error": str(exc)})
    probe_verified = any(probe_payload.get(key) is not None for key in ("duration_seconds", "fps", "width", "height", "codec"))
    extra_payload = {
        "sha256": digest,
        "byte_size": len(data),
        "raw_asset_path": raw_path.relative_to(artifact_dir).as_posix(),
        **{key: value for key, value in probe_payload.items() if value is not None},
    }
    verification_status = "verified" if probe_verified else "mirrored_unverified"
    return _record_for_asset(candidate, retrieved_at=retrieved_at, verification_status=verification_status, extra_payload=extra_payload), raw_path


def _artifact_records(
    source_asset: EvidenceRecord,
    artifact_payload: dict[str, object],
    *,
    retrieved_at: str,
) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    source_video_record_id = str(source_asset.payload["source_video_record_id"])
    source_dataset = str(source_asset.payload.get("source_dataset") or source_asset.title)

    def add_record(atom_type: str, path: str, index: int = 0) -> None:
        digest = _digest(source_asset.record_id, atom_type, path, index)
        records.append(
            EvidenceRecord(
                record_id=f"video_atom:{atom_type}:{_safe_id(source_video_record_id)}:{digest}",
                lane="media",
                source=VIDEO_ATOMS_SOURCE_ID,
                title=f"Aedes aegypti {atom_type.replace('_', ' ')} for {source_dataset}",
                text=f"Inspectable {atom_type.replace('_', ' ')} derived from Aedes aegypti video {source_dataset}. Artifact path: {path}.",
                species=source_asset.species,
                url=source_asset.url,
                media_url=path,
                provenance=Provenance(
                    source_id=VIDEO_ATOMS_SOURCE_ID,
                    locator=f"{source_asset.provenance.locator};{path}",
                    retrieved_at=retrieved_at,
                    license=source_asset.provenance.license,
                    source_url=source_asset.media_url or source_asset.url,
                ),
                payload={
                    "atom_type": atom_type,
                    "source_video_asset_id": source_asset.record_id,
                    "source_video_record_id": source_video_record_id,
                    "artifact_path": path,
                },
            )
        )

    thumbnail = artifact_payload.get("thumbnail_path")
    if isinstance(thumbnail, str):
        add_record("video_thumbnail", thumbnail)
    for index, keyframe_path in enumerate(artifact_payload.get("keyframe_paths") or [], start=1):
        if isinstance(keyframe_path, str):
            add_record("video_keyframe", keyframe_path, index)
    preview = artifact_payload.get("preview_clip_path")
    if isinstance(preview, str):
        add_record("video_preview_clip", preview)
    frame_manifest = artifact_payload.get("frame_manifest_path")
    if isinstance(frame_manifest, str):
        add_record("video_frame_manifest", frame_manifest)
    return records


def _gap_record(gap: dict[str, object], *, retrieved_at: str, index: int) -> EvidenceRecord:
    reason = str(gap.get("reason") or "video_gap")
    source_record_id = str(gap.get("record_id") or gap.get("title") or gap.get("repository") or f"gap-{index}")
    digest = _digest(reason, source_record_id, json.dumps(gap, sort_keys=True, default=str), index)
    locator = str(gap.get("locator") or f"gaps.json#aedes_video_atoms/{index}")
    source_url = gap.get("source_url")
    url = source_url if isinstance(source_url, str) and source_url else None
    license_value = gap.get("license")
    title = f"Aedes aegypti video gap {reason}"
    text = f"Aedes aegypti video source gap: {reason}. Source record: {source_record_id}."
    if gap.get("repository"):
        text += f" Repository: {gap.get('repository')}."
    if gap.get("error"):
        text += f" Error: {gap.get('error')}."
    return EvidenceRecord(
        record_id=f"video_atom:gap:{_safe_id(source_record_id)}:{digest}",
        lane="media",
        source=VIDEO_ATOMS_SOURCE_ID,
        title=title,
        text=text,
        species="Aedes aegypti",
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=VIDEO_ATOMS_SOURCE_ID,
            locator=locator,
            retrieved_at=retrieved_at,
            license=license_value if isinstance(license_value, str) else None,
            source_url=url,
        ),
        payload={"atom_type": "video_gap", **gap},
    )


def generate_video_artifacts(asset_path: Path, output_dir: Path, probe: dict[str, object]) -> dict[str, object]:
    if shutil.which("ffmpeg") is None:
        raise FileNotFoundError("ffmpeg not found")
    output_dir.mkdir(parents=True, exist_ok=True)
    thumbnail = output_dir / "thumbnail.jpg"
    preview = output_dir / "preview.mp4"
    frames = output_dir / "frames.json"
    subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(asset_path), "-frames:v", "1", "-update", "1", str(thumbnail)])
    subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-i", str(asset_path), "-t", "8", "-c", "copy", str(preview)])
    frames.write_text(json.dumps({"source": asset_path.as_posix(), "probe": probe}, indent=2), encoding="utf-8")
    return {
        "thumbnail_path": thumbnail.as_posix(),
        "keyframe_paths": [thumbnail.as_posix()],
        "preview_clip_path": preview.as_posix(),
        "frame_manifest_path": frames.as_posix(),
    }


def _normalize_artifact_path(path: str, artifact_dir: Path) -> str:
    try:
        return Path(path).relative_to(artifact_dir).as_posix()
    except ValueError:
        return path


def _parse_number(value: str | None) -> int | float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def _normalize_motion_header(header: object) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(header or "").strip().lower()).strip("_")
    return MOTION_HEADER_ALIASES.get(normalized, normalized)


def _normalize_motion_row(row: dict[object, object]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in row.items():
        if key is None or value is None:
            continue
        raw_key = str(key).strip()
        raw_value = str(value).strip()
        if not raw_key or raw_value == "":
            continue
        cleaned[raw_key] = raw_value
        normalized_key = _normalize_motion_header(raw_key)
        cleaned.setdefault(normalized_key, raw_value)
    return cleaned


def _motion_record(row: dict[str, str], *, table_path: Path, artifact_dir: Path, row_index: int, retrieved_at: str) -> EvidenceRecord:
    video_id = row.get("video_id") or row.get("video") or row.get("source_video_record_id") or table_path.stem
    behavior = row.get("behavior") or row.get("behavior_type") or "video motion"
    payload = {
        "atom_type": "video_motion_row",
        "source_video_record_id": video_id,
        "track_id": row.get("track_id") or row.get("track"),
        "frame": _parse_number(row.get("frame")),
        "time_seconds": _parse_number(row.get("time_seconds") or row.get("time")),
        "x": _parse_number(row.get("x")),
        "y": _parse_number(row.get("y")),
        "behavior_type": behavior,
        "sex": row.get("sex"),
        "life_stage": row.get("life_stage") or row.get("life stage"),
        "assay": row.get("assay"),
        "stimulus": row.get("stimulus"),
        "arena": row.get("arena"),
        "confidence": row.get("confidence") or "source_table",
        "source_table_row": row,
    }
    rel_path = table_path.relative_to(artifact_dir).as_posix()
    digest = _digest(video_id, rel_path, row_index)
    return EvidenceRecord(
        record_id=f"video_atom:motion:{_safe_id(video_id)}:{digest}",
        lane="behavior",
        source=VIDEO_ATOMS_SOURCE_ID,
        title=f"Aedes aegypti video motion row {behavior}",
        text=(
            f"Aedes aegypti video motion row for {behavior}. "
            f"Video: {video_id}. Track: {payload.get('track_id')}. Frame: {payload.get('frame')}. "
            f"Time seconds: {payload.get('time_seconds')}. Coordinates: {payload.get('x')}, {payload.get('y')}."
        ),
        species="Aedes aegypti",
        url=None,
        media_url=None,
        provenance=Provenance(
            source_id=VIDEO_ATOMS_SOURCE_ID,
            locator=f"{rel_path}#row/{row_index}",
            retrieved_at=retrieved_at,
            source_url=rel_path,
        ),
        payload=payload,
    )


def _parse_motion_tables(
    motion_table_paths: Iterable[Path],
    *,
    artifact_dir: Path,
    retrieved_at: str,
    gaps: list[dict[str, object]],
) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    for table_path in motion_table_paths:
        try:
            with Path(table_path).open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                headers = {_normalize_motion_header(header) for header in (reader.fieldnames or [])}
                if not headers & MOTION_HEADERS:
                    continue
                for row_index, row in enumerate(reader, start=1):
                    cleaned = _normalize_motion_row(row)
                    if cleaned:
                        records.append(_motion_record(cleaned, table_path=Path(table_path), artifact_dir=artifact_dir, row_index=row_index, retrieved_at=retrieved_at))
        except Exception as exc:
            gaps.append({"source": VIDEO_ATOMS_SOURCE_ID, "reason": "video_motion_table_parse_failed", "path": Path(table_path).as_posix(), "error": str(exc)})
    return records


def _default_motion_table_paths(artifact_dir: Path) -> list[Path]:
    search_roots = (
        artifact_dir / "raw" / "mendeley_behavior_media" / "table_files",
        artifact_dir / "raw" / "mendeley_behavior_media",
        artifact_dir / "raw" / "video_atoms",
    )
    paths: list[Path] = []
    seen: set[Path] = set()
    for root in search_roots:
        if not root.exists():
            continue
        for path in sorted(root.glob("*.csv")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            paths.append(path)
    return paths


def _candidate_from_discovery(raw: dict[str, object]) -> VideoCandidate | dict[str, object]:
    repository = str(raw.get("repository") or "unknown")
    title = str(raw.get("title") or "")
    species_scope = str(raw.get("species_scope") or raw.get("species") or "")
    if "aedes aegypti" not in species_scope.lower() and "a. aegypti" not in species_scope.lower():
        return {"source": VIDEO_ATOMS_SOURCE_ID, "reason": "video_discovery_not_aedes_scope", "repository": repository, "title": title}
    download_url = raw.get("download_url") or raw.get("media_url")
    if not isinstance(download_url, str) or not download_url:
        return {"source": VIDEO_ATOMS_SOURCE_ID, "reason": "video_discovery_no_download_url", "repository": repository, "title": title}
    filename = raw.get("filename") or raw.get("name") or raw.get("path")
    if not _looks_like_video(filename, download_url, title, raw.get("description")):
        return {"source": VIDEO_ATOMS_SOURCE_ID, "reason": "video_discovery_not_video_media", "repository": repository, "title": title}
    license_value = raw.get("license")
    if _license_is_unclear(license_value):
        return {"source": VIDEO_ATOMS_SOURCE_ID, "reason": "video_discovery_license_unclear", "repository": repository, "title": title}
    record_id = f"discovery:{repository}:{_digest(title, download_url)}"
    provenance = {
        "source_id": f"video_discovery_{repository}",
        "locator": f"discovery#{repository}:{_digest(title, download_url)}",
        "retrieved_at": raw.get("retrieved_at") or utc_now(),
        "license": license_value,
        "source_url": raw.get("source_url"),
    }
    return VideoCandidate(
        source_record_id=record_id,
        title=title,
        text=str(raw.get("description") or title),
        species="Aedes aegypti",
        url=str(raw.get("source_url") or ""),
        media_url=download_url,
        source=f"video_discovery_{repository}",
        provenance=provenance,
        payload={"download_url": download_url, "source_dataset": title, **raw},
        discovery_repository=repository,
    )


def _discover_candidates(
    discovery_clients: dict[str, Callable[[], list[dict[str, object]]]],
    *,
    max_discovery_results: int,
    gaps: list[dict[str, object]],
) -> tuple[list[VideoCandidate], int]:
    candidates: list[VideoCandidate] = []
    count = 0
    for repository in DISCOVERY_REPOSITORIES:
        client = discovery_clients.get(repository)
        if client is None:
            gaps.append({"source": VIDEO_ATOMS_SOURCE_ID, "reason": "video_discovery_client_missing", "repository": repository})
            continue
        try:
            raw_items = client()
        except Exception as exc:
            gaps.append({"source": VIDEO_ATOMS_SOURCE_ID, "reason": "video_discovery_fetch_failed", "repository": repository, "error": str(exc)})
            continue
        if not raw_items:
            gaps.append({"source": VIDEO_ATOMS_SOURCE_ID, "reason": "video_discovery_no_candidates", "repository": repository})
            continue
        for raw in raw_items:
            if count >= max_discovery_results:
                gaps.append({"source": VIDEO_ATOMS_SOURCE_ID, "reason": "video_discovery_limit_applied", "max_discovery_results": max_discovery_results})
                return candidates, count
            count += 1
            normalized = _candidate_from_discovery({**raw, "repository": raw.get("repository") or repository})
            if isinstance(normalized, VideoCandidate):
                candidates.append(normalized)
            else:
                gaps.append(normalized)
    return candidates, count


def build_video_atom_records(
    artifact_dir: Path,
    *,
    retrieved_at: str | None = None,
    max_video_bytes: int = 750_000_000,
    mirror_videos: bool = False,
    generate_artifacts: bool = False,
    discover_sources: bool = False,
    allow_unclear_license: bool = False,
    allowed_licenses: Iterable[str] | None = None,
    fetch_video_bytes_fn: Callable[[str, int], bytes] | None = None,
    probe_video_file_fn: Callable[[Path], dict[str, object]] | None = None,
    artifact_generator_fn: Callable[[Path, Path, dict[str, object]], dict[str, object]] | None = None,
    discovery_clients: dict[str, Callable[[], list[dict[str, object]]]] | None = None,
    max_discovery_results: int = 1000,
    motion_table_paths: Iterable[Path] | None = None,
) -> AedesVideoAtomsResult:
    artifact_dir = Path(artifact_dir)
    retrieved_at = retrieved_at or utc_now()
    if max_video_bytes < 1:
        raise ValueError("max_video_bytes must be positive")
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    gaps: list[dict[str, object]] = []
    records: list[EvidenceRecord] = []
    candidates = _candidate_rows(index)
    discovery_candidate_count = 0
    if discover_sources:
        discovery_clients = discovery_clients if discovery_clients is not None else default_discovery_clients()
        discovered, discovery_candidate_count = _discover_candidates(discovery_clients, max_discovery_results=max_discovery_results, gaps=gaps)
        candidates.extend(discovered)

    mirrored_video_count = 0
    verified_video_count = 0
    artifact_count = 0
    fetcher = fetch_video_bytes_fn or _default_fetch_video_bytes
    probe_fn = probe_video_file_fn or probe_video_file
    artifact_fn = artifact_generator_fn or generate_video_artifacts
    for candidate in candidates:
        asset_path: Path | None = None
        if mirror_videos:
            asset, asset_path = _mirror_candidate(
                candidate,
                artifact_dir=artifact_dir,
                retrieved_at=retrieved_at,
                max_video_bytes=max_video_bytes,
                fetch_video_bytes_fn=fetcher,
                probe_video_file_fn=probe_fn,
                allowed_licenses=allowed_licenses,
                allow_unclear_license=allow_unclear_license,
                gaps=gaps,
            )
            if asset_path is not None:
                mirrored_video_count += 1
                if asset.payload.get("verification_status") == "verified":
                    verified_video_count += 1
        else:
            asset = _record_for_asset(candidate, retrieved_at=retrieved_at)
        records.append(asset)
        if generate_artifacts and asset_path is not None and asset.payload.get("verification_status") == "verified":
            try:
                output_dir = artifact_dir / "raw" / "video_atoms" / "artifacts" / _safe_id(asset.record_id)
                artifact_payload = artifact_fn(asset_path, output_dir, asset.payload)
                normalized = {
                    key: ([_normalize_artifact_path(str(path), artifact_dir) for path in value] if isinstance(value, list) else _normalize_artifact_path(str(value), artifact_dir))
                    for key, value in artifact_payload.items()
                }
                artifact_records = _artifact_records(asset, normalized, retrieved_at=retrieved_at)
                artifact_count += len(artifact_records)
                records.extend(artifact_records)
            except FileNotFoundError as exc:
                gaps.append({"source": VIDEO_ATOMS_SOURCE_ID, "reason": "video_artifact_tool_missing", "record_id": candidate.source_record_id, "error": str(exc)})
            except Exception as exc:
                gaps.append({"source": VIDEO_ATOMS_SOURCE_ID, "reason": "video_artifact_generation_failed", "record_id": candidate.source_record_id, "error": str(exc)})

    if motion_table_paths is None:
        motion_table_paths = _default_motion_table_paths(artifact_dir)
    motion_records = _parse_motion_tables(motion_table_paths, artifact_dir=artifact_dir, retrieved_at=retrieved_at, gaps=gaps)
    records.extend(motion_records)
    records.extend(_gap_record(gap, retrieved_at=retrieved_at, index=index) for index, gap in enumerate(gaps, start=1))
    return AedesVideoAtomsResult(
        source_id=VIDEO_ATOMS_SOURCE_ID,
        records=records,
        gaps=gaps,
        video_asset_count=len(candidates),
        mirrored_video_count=mirrored_video_count,
        verified_video_count=verified_video_count,
        artifact_count=artifact_count,
        motion_row_count=len(motion_records),
        discovery_candidate_count=discovery_candidate_count,
    )
