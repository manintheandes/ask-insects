from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from posixpath import normpath
import re
import shutil
import subprocess
import tarfile
from typing import Callable, Iterable
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen
import zipfile

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.mendeley_behavior_media import _parse_table, _row_values, _safe_id as _mendeley_safe_id, _table_layout


VIDEO_ATOMS_SOURCE_ID = "aedes_video_atoms"

VIDEO_LOCATOR_SCAN_SOURCES = (
    "aedes_literature_openalex",
    "aedes_extracted_facts",
    "pmc_open_access_videos",
    "dryad_aedes_behavior_videos",
    "mendeley_aedes_behavior_media",
    "osf_flighttrackai_aedes_videos",
    "zenodo_aedes_videos",
    "figshare_aedes_videos",
)
INSTITUTIONAL_VIDEO_LOCATOR_SCAN_SOURCES = tuple(
    source
    for source in VIDEO_LOCATOR_SCAN_SOURCES
    if source not in {"aedes_literature_openalex", "aedes_extracted_facts"}
)
VIDEO_SOURCE_IDS = {
    "pmc_open_access_videos",
    "dryad_aedes_behavior_videos",
    "mendeley_aedes_behavior_media",
    "osf_flighttrackai_aedes_videos",
    "zenodo_aedes_videos",
    "figshare_aedes_videos",
}
REPOSITORY_SOURCE_IDS = {
    "pmc_oa": "pmc_open_access_videos",
    "dryad": "dryad_aedes_behavior_videos",
    "mendeley": "mendeley_aedes_behavior_media",
    "osf": "osf_flighttrackai_aedes_videos",
    "zenodo": "zenodo_aedes_videos",
    "figshare": "figshare_aedes_videos",
}
UPSTREAM_VIDEO_MANIFEST_GAP_SOURCES = {
    "zenodo_aedes_videos",
    "figshare_aedes_videos",
}
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".m4v", ".webm", ".mpg", ".mpeg")
ARCHIVE_EXTENSIONS = (".zip", ".tar", ".tar.gz", ".tgz", ".7z")
NON_VIDEO_MEDIA_EXTENSIONS = (
    ".aac",
    ".csv",
    ".doc",
    ".docx",
    ".flac",
    ".gif",
    ".h5",
    ".hdf5",
    ".html",
    ".ipynb",
    ".jpeg",
    ".jpg",
    ".json",
    ".mat",
    ".nc",
    ".npy",
    ".npz",
    ".parquet",
    ".mp3",
    ".pkl",
    ".pickle",
    ".png",
    ".pdf",
    ".py",
    ".r",
    ".rdata",
    ".rds",
    ".svg",
    ".tif",
    ".tiff",
    ".tsv",
    ".txt",
    ".wav",
    ".xls",
    ".xlsx",
    ".yaml",
    ".yml",
)
VIDEO_TERMS = ("video", "movie", "flight", "tracking", "high-speed", "wingbeat")
UNCLEAR_LICENSE_MARKERS = ("not supplied", "unknown", "unclear", "not parsed", "missing")
AEDES_SCOPE_PATTERN = re.compile(r"\b(?:aedes|ae\.?|a\.)\s*aegypti\b", re.I)
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
    "subject": "track_id",
    "unique_subject": "track_id",
    "zone": "arena",
    "feeding_status": "feeding_status",
    "velocity_center_point_mean_cm_s": "velocity_mean_cm_s",
    "angular_velocity_absolute_center_point_absolute_mean_deg_s": "angular_velocity_absolute_mean_deg_s",
    "angular_velocity_center_point_relative_mean_deg_s": "angular_velocity_relative_mean_deg_s",
    "distance_moved_center_point_total_cm": "distance_moved_total_cm",
    "in_zone_arena_center_point_mean_s": "zone_mean_seconds",
    "in_zone_arena_center_point_frequency": "zone_frequency",
    "in_zone_arena_center_point_cumulative_duration_s": "zone_cumulative_duration_seconds",
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
FIGSHARE_DISCOVERY_PAGE_SIZE = 100


class VideoDownloadNotVideoError(ValueError):
    """Raised when a video URL returns HTML or another clearly non-video payload."""


class VideoDownloadAccessRestrictedError(PermissionError):
    """Raised when a video URL exists but denies unauthenticated download."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


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
    discovery_sweep_receipts: list[dict[str, object]]


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


@dataclass(frozen=True)
class DiscoverySweepResult:
    items: list[dict[str, object]]
    receipt: dict[str, object]


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


def _raw_file_values(payload: dict[str, object]) -> tuple[object, ...]:
    raw_file = payload.get("raw_file")
    if not isinstance(raw_file, dict):
        return ()
    values: list[object] = []
    for key in ("path", "filename", "name", "download_url", "url"):
        value = raw_file.get(key)
        if value:
            values.append(value)
    attrs = raw_file.get("attributes")
    if isinstance(attrs, dict):
        for key in ("path", "filename", "name", "download_url", "url"):
            value = attrs.get(key)
            if value:
                values.append(value)
    return tuple(values)


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


def _looks_like_archive(*values: object) -> bool:
    text = " ".join(str(value or "").lower() for value in values)
    return any(re.search(rf"{re.escape(extension)}(?:\b|$|[?#])", text) for extension in ARCHIVE_EXTENSIONS)


def _looks_like_video(*values: object) -> bool:
    text = " ".join(str(value or "").lower() for value in values)
    if any(extension in text for extension in VIDEO_EXTENSIONS):
        return True
    if _contains_non_video_media_file(*values):
        return False
    return any(term in text for term in VIDEO_TERMS)


def _has_aedes_scope(*values: object) -> bool:
    return any(AEDES_SCOPE_PATTERN.search(str(value or "")) for value in values)


def _has_discovery_aedes_scope(raw: dict[str, object]) -> bool:
    if _has_aedes_scope(raw.get("species")):
        return True
    material_fields = (
        "title",
        "description",
        "filename",
        "name",
        "path",
        "dataset_name",
        "dataset_citation",
        "source_title",
        "source_dataset",
    )
    if _has_aedes_scope(*(raw.get(field) for field in material_fields)):
        return True
    if not any(raw.get(field) for field in material_fields):
        return _has_aedes_scope(raw.get("species_scope"))
    return False


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
    return {source_id: repository for repository, source_id in REPOSITORY_SOURCE_IDS.items()}.get(source)


def _source_ids_for_repositories(repositories: Iterable[str]) -> tuple[str, ...]:
    return tuple(REPOSITORY_SOURCE_IDS[repository] for repository in repositories if repository in REPOSITORY_SOURCE_IDS)


def _size_from_candidate(candidate: VideoCandidate) -> int | None:
    for key in ("size", "size_bytes", "byte_size", "source_byte_size"):
        value = candidate.payload.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    match = re.search(r"size bytes:\s*(\d+)", candidate.text, re.I)
    return int(match.group(1)) if match else None


def _source_hashes_from_candidate(candidate: VideoCandidate) -> dict[str, str]:
    hashes: dict[str, str] = {}
    source_hashes = candidate.payload.get("source_hashes")
    if isinstance(source_hashes, dict):
        for key, value in source_hashes.items():
            if isinstance(value, str) and value.strip():
                hashes[str(key)] = value.strip()
    for key in ("sha256", "md5", "checksum", "digest"):
        value = candidate.payload.get(key)
        if isinstance(value, str) and value.strip():
            hashes[key] = value.strip()
    raw_file = candidate.payload.get("raw_file")
    if isinstance(raw_file, dict):
        attrs = raw_file.get("attributes")
        if isinstance(attrs, dict):
            extra = attrs.get("extra")
            if isinstance(extra, dict):
                    raw_hashes = extra.get("hashes")
                    if isinstance(raw_hashes, dict):
                        for key, value in raw_hashes.items():
                            if isinstance(value, str) and value.strip():
                                hashes[str(key)] = value.strip()
    return hashes


def _source_hashes_from_raw(raw: dict[str, object]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for key in ("sha256", "md5", "checksum", "digest"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            hashes[key] = value.strip()
    return hashes


def _size_from_raw(raw: dict[str, object]) -> int | None:
    for key in ("size", "size_bytes", "byte_size", "source_byte_size"):
        value = raw.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _candidate_source_payload(candidate: VideoCandidate) -> dict[str, object]:
    payload: dict[str, object] = {}
    size = _size_from_candidate(candidate)
    if size is not None:
        payload["source_byte_size"] = size
    hashes = _source_hashes_from_candidate(candidate)
    if hashes:
        payload["source_hashes"] = hashes
    repository = candidate.discovery_repository or _repository_for_source(candidate.source)
    if repository:
        payload["repository"] = repository
    return payload


def _gap_context(candidate: VideoCandidate, reason: str, **extra: object) -> dict[str, object]:
    context = {
        "source": VIDEO_ATOMS_SOURCE_ID,
        "lane": "media",
        "reason": reason,
        "record_id": candidate.source_record_id,
        "title": candidate.title,
        "download_url": candidate.media_url,
        "source_url": candidate.url,
        "license": candidate.provenance.get("license"),
        "source_dataset": candidate.payload.get("source_dataset") or candidate.title,
        "locator": candidate.provenance.get("locator"),
        **_candidate_source_payload(candidate),
        **extra,
    }
    return {key: value for key, value in context.items() if value not in (None, "", {})}


def _discovery_gap(raw: dict[str, object], reason: str, repository: str, title: str) -> dict[str, object]:
    download_url = raw.get("download_url") or raw.get("media_url")
    source_url = raw.get("source_url") or raw.get("url")
    locator = raw.get("locator") or f"raw/video_atoms/discovery_sweeps.json#{repository}/{_digest(title, download_url, source_url, reason)}"
    context: dict[str, object] = {
        "source": VIDEO_ATOMS_SOURCE_ID,
        "lane": "media",
        "reason": reason,
        "repository": repository,
        "title": title,
        "filename": raw.get("filename") or raw.get("name") or raw.get("path"),
        "download_url": download_url,
        "source_url": source_url,
        "license": raw.get("license"),
        "source_dataset": raw.get("source_dataset") or raw.get("dataset_name") or title,
        "locator": locator,
    }
    size = _size_from_raw(raw)
    if size is not None:
        context["source_byte_size"] = size
    hashes = _source_hashes_from_raw(raw)
    if hashes:
        context["source_hashes"] = hashes
    return {key: value for key, value in context.items() if value not in (None, "", {})}


def _candidate_rows(index: SourceIndex, source_ids: Iterable[str] | None = None) -> list[VideoCandidate]:
    source_ids = tuple(source_ids) if source_ids is not None else tuple(VIDEO_SOURCE_IDS)
    if not source_ids:
        return []
    source_placeholders = ", ".join(repr(source) for source in source_ids)
    rows = index.sql(
        f"""
        SELECT r.*, p.payload_json
        FROM records r
        LEFT JOIN record_payloads p ON p.record_id = r.record_id
        WHERE r.source IN ({source_placeholders})
          AND lower(coalesce(r.species, '')) = 'aedes aegypti'
          AND r.lane = 'media'
        ORDER BY r.record_id
        """,
        limit=100000,
    )
    candidates: list[VideoCandidate] = []
    for row in rows:
        payload = _safe_json(row.get("payload_json"))
        if payload.get("atom_type") in {"video_gap", "source_gap"} or payload.get("gap_type"):
            continue
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
            *_raw_file_values(payload),
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
        **_candidate_source_payload(candidate),
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
            locator=str(candidate.provenance.get("locator") or f"records#{candidate.source_record_id}") if candidate.discovery_repository else f"records#{candidate.source_record_id}",
            retrieved_at=retrieved_at,
            license=candidate.provenance.get("license") if isinstance(candidate.provenance.get("license"), str) else None,
            source_url=candidate.provenance.get("source_url") if isinstance(candidate.provenance.get("source_url"), str) else candidate.url,
        ),
        payload=payload,
    )


def _default_fetch_video_bytes(url: str, max_bytes: int) -> bytes:
    request = Request(url, headers={"User-Agent": "AskInsects/0.1 video-atoms"})
    try:
        with urlopen(request, timeout=120) as response:
            content_type = str(response.headers.get("content-type") or "").lower()
            if "text/html" in content_type or "application/xhtml" in content_type:
                raise VideoDownloadNotVideoError(f"download content-type is not video: {content_type}")
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > max_bytes:
                raise ValueError(f"video exceeds max bytes: {content_length} > {max_bytes}")
            data = response.read(max_bytes + 1)
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise VideoDownloadAccessRestrictedError(str(exc), status_code=exc.code) from exc
        raise
    if len(data) > max_bytes:
        raise ValueError(f"video exceeds max bytes: {len(data)} > {max_bytes}")
    prefix = data[:512].lstrip().lower()
    if prefix.startswith((b"<!doctype html", b"<html", b"<?xml")):
        raise VideoDownloadNotVideoError("download payload is HTML/XML, not video bytes")
    return data


def _fetch_json(url: str) -> object:
    request = Request(url, headers={"User-Agent": "AskInsects/0.1 video-discovery"})
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "AskInsects/0.1 video-discovery"})
    with urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8", "replace")


def _default_zenodo_discovery_client() -> DiscoverySweepResult:
    search_string = '"Aedes aegypti" (video OR movie OR mp4 OR tracking)'
    page_size = 25
    query = urlencode({"q": search_string, "size": str(page_size)})
    request_url = f"https://zenodo.org/api/records?{query}"
    payload = _fetch_json(request_url)
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
    return DiscoverySweepResult(
        items=discovered,
        receipt={
            "coverage_method": "api_search",
            "queries": [search_string],
            "request_urls": [request_url],
            "page_size": page_size,
            "page_count": 1,
            "cursor_or_page_complete": True,
            "candidate_limit": page_size,
        },
    )


def _default_figshare_discovery_client() -> DiscoverySweepResult:
    search_string = "Aedes aegypti video"
    query = urlencode({"search_for": search_string, "page_size": str(FIGSHARE_DISCOVERY_PAGE_SIZE)})
    search_url = f"https://api.figshare.com/v2/articles?{query}"
    request_urls = [search_url]
    payload = _fetch_json(search_url)
    summaries = payload if isinstance(payload, list) else []
    discovered: list[dict[str, object]] = []
    for summary in summaries:
        if not isinstance(summary, dict):
            continue
        article_id = summary.get("id")
        if not article_id:
            continue
        detail_url = f"https://api.figshare.com/v2/articles/{article_id}"
        request_urls.append(detail_url)
        try:
            detail = _fetch_json(detail_url)
        except Exception as exc:
            title = str(summary.get("title") or "Figshare Aedes video candidate")
            source_url = summary.get("url_public_html") if isinstance(summary.get("url_public_html"), str) else detail_url
            discovered.append(
                {
                    "repository": "figshare",
                    "title": title,
                    "description": str(summary.get("description") or ""),
                    "source_url": source_url,
                    "license": "unclear",
                    "species_scope": title,
                    "retrieved_at": utc_now(),
                    "fetch_error": str(exc),
                    "locator": f"raw/video_atoms/discovery_sweeps.json#figshare/articles/{article_id}",
                }
            )
            continue
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
    return DiscoverySweepResult(
        items=discovered,
        receipt={
            "coverage_method": "api_search",
            "queries": [search_string],
            "request_urls": request_urls,
            "page_size": FIGSHARE_DISCOVERY_PAGE_SIZE,
            "page_count": 1,
            "cursor_or_page_complete": True,
            "candidate_limit": FIGSHARE_DISCOVERY_PAGE_SIZE,
        },
    )


def _default_dryad_discovery_client() -> DiscoverySweepResult:
    from askinsects.sources.dryad_behavior_videos import DRYAD_API_BASE, DryadClient, _file_rows, _link

    client = DryadClient()
    queries = (
        '"Aedes aegypti" video',
        '"Aedes aegypti" flight',
        '"Aedes aegypti" tracking',
        '"Aedes aegypti" wingbeat',
    )
    discovered: list[dict[str, object]] = []
    seen_dois: set[str] = set()
    request_urls: list[str] = []
    for query in queries:
        search_url = f"{DRYAD_API_BASE}/api/v2/search?{urlencode({'q': query, 'page': 1, 'per_page': 10})}"
        request_urls.append(search_url)
        search_payload = _fetch_json(search_url)
        search_payload = search_payload if isinstance(search_payload, dict) else {}
        embedded = search_payload.get("_embedded") if isinstance(search_payload.get("_embedded"), dict) else {}
        datasets = embedded.get("stash:datasets") if isinstance(embedded.get("stash:datasets"), list) else []
        for dataset in datasets:
            if not isinstance(dataset, dict):
                continue
            identifier = str(dataset.get("identifier") or "")
            doi = identifier.removeprefix("doi:") if identifier.startswith("doi:") else identifier
            if not doi or doi in seen_dois:
                continue
            seen_dois.add(doi)
            version_href = _link(dataset, "stash:version")
            if not version_href:
                continue
            version_url, version_payload = client.linked(version_href)
            request_urls.append(version_url)
            files_href = _link(version_payload, "stash:files")
            if not files_href:
                continue
            files_url, files_payload = client.linked(files_href)
            request_urls.append(files_url)
            for file_index, file_payload in enumerate(_file_rows(files_payload), start=1):
                path = str(file_payload.get("path") or f"file-{file_index}")
                mime_type = str(file_payload.get("mimeType") or "")
                download_href = _link(file_payload, "stash:download")
                download_url = urljoin(DRYAD_API_BASE, download_href) if download_href else ""
                if not download_url:
                    continue
                discovered.append(
                    {
                        "repository": "dryad",
                        "title": str(dataset.get("title") or f"Dryad Aedes dataset {doi}"),
                        "description": str(dataset.get("abstract") or dataset.get("title") or ""),
                        "filename": path,
                        "download_url": download_url,
                        "source_url": f"{DRYAD_API_BASE}/dataset/{quote(f'doi:{doi}', safe='')}",
                        "license": dataset.get("license"),
                        "species_scope": f"{dataset.get('title') or ''} {dataset.get('abstract') or ''} {dataset.get('keywords') or ''}",
                        "search_query": query,
                        "retrieved_at": utc_now(),
                        "locator": f"{files_url}#file/{file_index}",
                        "doi": doi,
                        "size": file_payload.get("size"),
                        "mime_type": mime_type,
                        "digest": file_payload.get("digest"),
                        "digest_type": file_payload.get("digestType"),
                    }
                )
    return DiscoverySweepResult(
        items=discovered,
        receipt={
            "coverage_method": "api_search",
            "queries": list(queries),
            "request_urls": request_urls,
            "page_size": 10,
            "page_count": len(queries),
            "cursor_or_page_complete": True,
            "candidate_limit": len(queries) * 10,
        },
    )


def _default_osf_discovery_client() -> DiscoverySweepResult:
    from askinsects.sources.osf_flighttrackai_videos import OSF_API_BASE, _attrs, _data, _links, _next_href, _related_href

    search_query = '"Aedes aegypti" video'
    search_url = f"{OSF_API_BASE}/search/?{urlencode({'q': search_query, 'page[size]': 5})}"
    request_urls = [search_url]
    search_payload = _fetch_json(search_url)
    search_payload = search_payload if isinstance(search_payload, dict) else {}
    discovered: list[dict[str, object]] = []
    for node in _data(search_payload):
        attrs = _attrs(node)
        node_id = str(node.get("id") or "")
        if not node_id:
            continue
        title = str(attrs.get("title") or f"OSF Aedes video project {node_id}")
        description = str(attrs.get("description") or "")
        links = _links(node)
        source_url = str(links.get("html") or f"https://osf.io/{node_id}/")
        license_payload = attrs.get("node_license") if isinstance(attrs.get("node_license"), dict) else {}
        license_value = license_payload.get("name") or license_payload.get("id") if isinstance(license_payload, dict) else None
        queue = [f"{OSF_API_BASE}/nodes/{node_id}/files/osfstorage/"]
        seen_urls: set[str] = set()
        file_index = 0
        while queue:
            url = queue.pop(0)
            if url in seen_urls:
                continue
            seen_urls.add(url)
            request_urls.append(url)
            payload = _fetch_json(url)
            payload = payload if isinstance(payload, dict) else {}
            for item in _data(payload):
                item_attrs = _attrs(item)
                if item_attrs.get("kind") == "folder":
                    href = _related_href(item, "files")
                    if href:
                        queue.append(href)
                    continue
                if item_attrs.get("kind") != "file":
                    continue
                file_index += 1
                name = str(item_attrs.get("name") or item.get("id") or f"file-{file_index}")
                download_url = _links(item).get("download")
                if not isinstance(download_url, str) or not download_url:
                    continue
                discovered.append(
                    {
                        "repository": "osf",
                        "title": title,
                        "description": f"{description} OSF file: {name}.",
                        "filename": name,
                        "download_url": download_url,
                        "source_url": source_url,
                        "license": license_value,
                        "species_scope": f"{title} {description}",
                        "search_query": search_query,
                        "retrieved_at": utc_now(),
                        "locator": f"{url}#file/{file_index}",
                        "project_id": node_id,
                        "file_id": item.get("id"),
                        "materialized_path": item_attrs.get("materialized_path"),
                        "size": item_attrs.get("size"),
                    }
                )
            next_url = _next_href(payload)
            if next_url:
                queue.append(next_url)
    return DiscoverySweepResult(
        items=discovered,
        receipt={
            "coverage_method": "api_search",
            "queries": [search_query],
            "request_urls": request_urls,
            "page_size": 5,
            "page_count": len(request_urls),
            "cursor_or_page_complete": True,
            "candidate_limit": 5,
        },
    )


def _default_mendeley_discovery_client() -> DiscoverySweepResult:
    from askinsects.sources.mendeley_behavior_media import (
        DEFAULT_MENDELEY_DATASETS,
        MendeleyClient,
        _content_details,
        _dataset_web_url,
        _file_folder_path,
        _folder_path,
        _is_media_file,
        _license,
    )

    client = MendeleyClient()
    discovered: list[dict[str, object]] = []
    request_urls: list[str] = []
    dataset_ids: list[str] = []
    for spec in DEFAULT_MENDELEY_DATASETS:
        dataset_ids.append(spec.dataset_id)
        snapshot_url, snapshot = client.snapshot(spec.dataset_id, spec.version)
        request_urls.append(snapshot_url)
        folders_url, folders = client.folders(spec.dataset_id, spec.version)
        request_urls.append(folders_url)
        folder_by_id = {str(folder.get("id")): folder for folder in folders if folder.get("id")}
        folder_paths = {folder_id: _folder_path(folder, folder_by_id) for folder_id, folder in folder_by_id.items()}
        for folder in folders:
            folder_id = str(folder.get("id") or "")
            if not folder_id:
                continue
            files_url, file_groups = client.files(spec.dataset_id, spec.version, folder_id)
            request_urls.append(files_url)
            for group in file_groups:
                files = group.get("files") if isinstance(group.get("files"), list) else [group]
                for file_payload in files:
                    if not isinstance(file_payload, dict):
                        continue
                    filename = str(file_payload.get("filename") or file_payload.get("name") or "")
                    details = _content_details(file_payload)
                    content_type = str(details.get("content_type") or "")
                    if not _is_media_file(filename, content_type):
                        continue
                    download_url = details.get("download_url")
                    if not isinstance(download_url, str) or not download_url:
                        continue
                    folder_path = _file_folder_path(file_payload, folder_paths)
                    discovered.append(
                        {
                            "repository": "mendeley",
                            "title": str(snapshot.get("name") or f"Mendeley Aedes dataset {spec.dataset_id}"),
                            "description": (
                                f"Mendeley Data Aedes aegypti media file {filename}. "
                                f"Folder path: {folder_path}. Dataset API: {snapshot_url}. Files API: {files_url}."
                            ),
                            "filename": filename,
                            "download_url": download_url,
                            "source_url": _dataset_web_url(snapshot, spec),
                            "license": _license(snapshot),
                            "species_scope": f"Aedes aegypti {' '.join(spec.behavior_labels)} {snapshot.get('description') or ''}",
                            "retrieved_at": utc_now(),
                            "locator": f"{files_url}#file/{file_payload.get('id') or filename}",
                            "size": details.get("size") if details.get("size") is not None else file_payload.get("size"),
                            "sha256": details.get("sha256_hash"),
                        }
                    )
    return DiscoverySweepResult(
        items=discovered,
        receipt={
            "coverage_method": "seed_plus_api",
            "queries": [f"mendeley_dataset:{dataset_id}" for dataset_id in dataset_ids],
            "request_urls": request_urls,
            "page_size": None,
            "page_count": len(request_urls),
            "cursor_or_page_complete": True,
            "input_sources": ["DEFAULT_MENDELEY_DATASETS"],
            "candidate_limit": len(dataset_ids),
        },
    )


def _default_pmc_oa_discovery_client() -> DiscoverySweepResult:
    from askinsects.sources.pmc_videos import DEFAULT_PMC_VIDEO_ARTICLES, _license_text, _meta, _pmcid, _video_links

    article_urls: list[str] = list(DEFAULT_PMC_VIDEO_ARTICLES)
    search_string = '"Aedes aegypti" video OPEN_ACCESS:y'
    query = urlencode(
        {
            "query": search_string,
            "format": "json",
            "pageSize": "10",
            "resultType": "lite",
        }
    )
    search_url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?{query}"
    request_urls = [search_url]
    payload = _fetch_json(search_url)
    payload = payload if isinstance(payload, dict) else {}
    result_list = payload.get("resultList") if isinstance(payload.get("resultList"), dict) else {}
    results = result_list.get("result") if isinstance(result_list.get("result"), list) else []
    discovered: list[dict[str, object]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        pmcid = result.get("pmcid")
        if not isinstance(pmcid, str) or not pmcid:
            fulltext_ids = result.get("fullTextIdList") if isinstance(result.get("fullTextIdList"), dict) else {}
            ids = fulltext_ids.get("fullTextId") if isinstance(fulltext_ids.get("fullTextId"), list) else []
            pmcid = next((str(value) for value in ids if str(value).startswith("PMC")), "")
        if not pmcid:
            continue
        article_urls.append(f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/")
    seen_articles: set[str] = set()
    for article_url in article_urls:
        if article_url in seen_articles:
            continue
        seen_articles.add(article_url)
        try:
            request_urls.append(article_url)
            html = _fetch_text(article_url)
        except Exception:
            continue
        article_title = _meta(html, "citation_title") or article_url
        doi = _meta(html, "citation_doi")
        license_text = _license_text(html)
        normalized_pmcid = _pmcid(article_url, html)
        for index, video_url in enumerate(_video_links(article_url, html), start=1):
            discovered.append(
                {
                    "repository": "pmc_oa",
                    "title": article_title,
                    "description": f"PMC OA supplementary video candidate from {article_title}. DOI: {doi}.",
                    "filename": Path(urlparse(video_url).path).name,
                    "download_url": video_url,
                    "source_url": article_url,
                    "license": license_text,
                    "species_scope": f"Aedes aegypti {article_title}",
                    "retrieved_at": utc_now(),
                    "locator": f"{article_url}#video/{index}",
                    "pmcid": normalized_pmcid,
                    "doi": doi,
                }
            )
    return DiscoverySweepResult(
        items=discovered,
        receipt={
            "coverage_method": "seed_plus_api",
            "queries": [search_string, "DEFAULT_PMC_VIDEO_ARTICLES"],
            "request_urls": request_urls,
            "page_size": 10,
            "page_count": 1,
            "cursor_or_page_complete": True,
            "input_sources": ["DEFAULT_PMC_VIDEO_ARTICLES"],
            "candidate_limit": 10 + len(DEFAULT_PMC_VIDEO_ARTICLES),
        },
    )


def _default_paper_supplements_discovery_client(artifact_dir: Path) -> DiscoverySweepResult:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    rows = index.sql(
        """
        SELECT r.record_id, r.title, r.text, r.url, r.provenance_json, p.payload_json
        FROM records r
        LEFT JOIN record_payloads p ON p.record_id = r.record_id
        WHERE r.source IN ('aedes_literature_openalex', 'aedes_extracted_facts')
          AND (lower(coalesce(r.text, '')) LIKE '%.mp4%'
               OR lower(coalesce(r.text, '')) LIKE '%.mov%'
               OR lower(coalesce(p.payload_json, '')) LIKE '%.mp4%'
               OR lower(coalesce(p.payload_json, '')) LIKE '%.mov%')
        ORDER BY r.record_id
        """,
        limit=250,
    )
    discovered: list[dict[str, object]] = []
    for row in rows:
        payload_text = str(row.get("payload_json") or "")
        text = f"{row.get('title') or ''} {row.get('text') or ''} {payload_text}"
        urls = re.findall(r"https?://[^\s\"'<>]+?\.(?:mp4|mov|avi|webm|m4v)(?:\?[^\s\"'<>]+)?", text, flags=re.I)
        provenance = _safe_json(row.get("provenance_json"))
        for index, url in enumerate(dict.fromkeys(urls), start=1):
            discovered.append(
                {
                    "repository": "paper_supplements",
                    "title": str(row.get("title") or "Aedes aegypti paper supplement video"),
                    "description": str(row.get("text") or row.get("title") or ""),
                    "filename": Path(urlparse(url).path).name,
                    "download_url": url,
                    "source_url": str(row.get("url") or provenance.get("source_url") or ""),
                    "license": provenance.get("license") or "paper supplement license not supplied",
                    "species_scope": text,
                    "retrieved_at": provenance.get("retrieved_at") or utc_now(),
                    "locator": f"records#{row.get('record_id')}/supplement-video/{index}",
                    "source_record_id": row.get("record_id"),
                }
            )
    return DiscoverySweepResult(
        items=discovered,
        receipt={
            "coverage_method": "sqlite_scan",
            "queries": ["paper_supplement_video_url_scan"],
            "input_sources": ["aedes_literature_openalex", "aedes_extracted_facts"],
            "raw_artifacts": ["source_index.sqlite"],
            "page_size": 250,
            "page_count": 1,
            "cursor_or_page_complete": True,
            "candidate_limit": 250,
        },
    )


def _default_institutional_discovery_client(artifact_dir: Path) -> DiscoverySweepResult:
    dataverse_result = _dataverse_institutional_discovery_candidates()
    discovered = list(dataverse_result.items)
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    source_placeholders = ", ".join(repr(source) for source in INSTITUTIONAL_VIDEO_LOCATOR_SCAN_SOURCES)
    rows = index.sql(
        f"""
        SELECT r.record_id, r.title, r.text, r.url, r.media_url, r.provenance_json
        FROM records r
        WHERE r.source IN ({source_placeholders})
          AND lower(coalesce(r.species, '') || ' ' || coalesce(r.title, '') || ' ' || coalesce(r.text, '')) LIKE '%aedes aegypti%'
          AND (lower(coalesce(r.url, '')) LIKE '%.mp4%'
               OR lower(coalesce(r.media_url, '')) LIKE '%.mp4%'
               OR lower(coalesce(r.media_url, '')) LIKE '%.mov%'
               OR lower(coalesce(r.text, '')) LIKE '%.mp4%'
               OR lower(coalesce(r.text, '')) LIKE '%.mov%')
        ORDER BY r.record_id
        """,
        limit=250,
    )
    known_hosts = ("zenodo.org", "figshare.com", "mendeley.com", "datadryad.org", "osf.io", "pmc.ncbi.nlm.nih.gov")
    for row in rows:
        provenance = _safe_json(row.get("provenance_json"))
        text = f"{row.get('url') or ''} {row.get('media_url') or ''} {row.get('text') or ''}"
        urls = re.findall(r"https?://[^\s\"'<>]+?\.(?:mp4|mov|avi|webm|m4v)(?:\?[^\s\"'<>]+)?", text, flags=re.I)
        for index, url in enumerate(dict.fromkeys(urls), start=1):
            host = urlparse(url).netloc.lower()
            if any(known in host for known in known_hosts):
                continue
            discovered.append(
                {
                    "repository": "institutional",
                    "title": str(row.get("title") or "Aedes aegypti institutional video candidate"),
                    "description": str(row.get("text") or row.get("title") or ""),
                    "filename": Path(urlparse(url).path).name,
                    "download_url": url,
                    "source_url": str(row.get("url") or provenance.get("source_url") or ""),
                    "license": provenance.get("license") or "institutional repository license not supplied",
                    "species_scope": text,
                    "retrieved_at": provenance.get("retrieved_at") or utc_now(),
                    "locator": f"records#{row.get('record_id')}/institutional-video/{index}",
                    "source_record_id": row.get("record_id"),
                }
            )
    receipt = {
        **dataverse_result.receipt,
        "coverage_method": "api_plus_sqlite_scan",
        "queries": [*dataverse_result.receipt.get("queries", []), "institutional_indexed_video_url_scan"],
        "input_sources": [
            *dataverse_result.receipt.get("input_sources", []),
            *INSTITUTIONAL_VIDEO_LOCATOR_SCAN_SOURCES,
        ],
        "raw_artifacts": ["source_index.sqlite"],
    }
    return DiscoverySweepResult(items=discovered, receipt=receipt)


def _dataverse_institutional_discovery_candidates() -> DiscoverySweepResult:
    queries = (
        '"Aedes aegypti" mp4',
        '"Aedes aegypti" video',
        '"Aedes aegypti" movie',
    )
    discovered: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    request_urls: list[str] = []
    search_result_count = 0
    source_material_aedes_candidate_count = 0
    filtered_search_false_positive_count = 0
    for query in queries:
        url = f"https://dataverse.harvard.edu/api/search?{urlencode({'q': query, 'type': 'file', 'per_page': 50})}"
        request_urls.append(url)
        payload = _fetch_json(url)
        payload = payload if isinstance(payload, dict) else {}
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        items = data.get("items") if isinstance(data.get("items"), list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            search_result_count += 1
            filename = str(item.get("name") or "")
            content_type = str(item.get("file_content_type") or item.get("file_type") or "")
            download_url = item.get("url")
            if not isinstance(download_url, str) or not download_url:
                continue
            if not _looks_like_video(filename, content_type, item.get("dataset_name"), item.get("description")):
                continue
            raw_scope = {
                "title": item.get("dataset_name") or item.get("name"),
                "description": item.get("description"),
                "filename": filename,
                "name": item.get("name"),
                "dataset_name": item.get("dataset_name"),
                "dataset_citation": item.get("dataset_citation"),
            }
            if not _has_discovery_aedes_scope(raw_scope):
                filtered_search_false_positive_count += 1
                continue
            source_material_aedes_candidate_count += 1
            if download_url in seen_urls:
                continue
            seen_urls.add(download_url)
            discovered.append(
                {
                    "repository": "institutional",
                    "title": str(item.get("dataset_name") or item.get("name") or "Aedes aegypti Dataverse video candidate"),
                    "description": str(item.get("description") or item.get("dataset_citation") or item.get("name") or ""),
                    "filename": filename,
                    "download_url": download_url,
                    "source_url": str(item.get("url") or item.get("dataset_persistent_id") or ""),
                    "license": item.get("license") or item.get("termsOfUse"),
                    "species_scope": (
                        f"{item.get('dataset_name') or ''} "
                        f"{item.get('description') or ''} "
                        f"{item.get('dataset_citation') or ''} "
                        f"{filename}"
                    ),
                    "search_query": query,
                    "retrieved_at": utc_now(),
                    "locator": f"{url}#file/{item.get('file_id') or filename}",
                    "file_id": item.get("file_id"),
                    "dataset_persistent_id": item.get("dataset_persistent_id"),
                    "size": item.get("size_in_bytes"),
                    "checksum": item.get("checksum"),
                    "content_type": content_type,
                }
            )
    return DiscoverySweepResult(
        items=discovered,
        receipt={
            "coverage_method": "api_search",
            "queries": list(queries),
            "request_urls": request_urls,
            "page_size": 50,
            "page_count": len(queries),
            "cursor_or_page_complete": True,
            "input_sources": ["Harvard Dataverse API"],
            "candidate_limit": len(queries) * 50,
            "search_result_count": search_result_count,
            "source_material_aedes_candidate_count": source_material_aedes_candidate_count,
            "filtered_search_false_positive_count": filtered_search_false_positive_count,
        },
    )


def default_discovery_clients(artifact_dir: Path | None = None) -> dict[str, Callable[[], list[dict[str, object]] | DiscoverySweepResult]]:
    artifact_dir = Path(artifact_dir) if artifact_dir is not None else Path(".")
    return {
        "pmc_oa": _default_pmc_oa_discovery_client,
        "dryad": _default_dryad_discovery_client,
        "mendeley": _default_mendeley_discovery_client,
        "osf": _default_osf_discovery_client,
        "zenodo": _default_zenodo_discovery_client,
        "figshare": _default_figshare_discovery_client,
        "institutional": lambda: _default_institutional_discovery_client(artifact_dir),
        "paper_supplements": lambda: _default_paper_supplements_discovery_client(artifact_dir),
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


def _existing_mirror_path(candidate: VideoCandidate, artifact_dir: Path) -> Path | None:
    assets_dir = artifact_dir / "raw" / "video_atoms" / "assets"
    if not assets_dir.exists():
        return None
    prefix = _safe_id(candidate.source_record_id)
    paths = [
        path
        for path in assets_dir.glob(f"{prefix}_*")
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    ]
    if not paths:
        return None
    return max(paths, key=lambda path: path.stat().st_mtime)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _archive_extension(candidate: VideoCandidate) -> str:
    for value in (
        candidate.payload.get("filename"),
        candidate.payload.get("name"),
        candidate.payload.get("materialized_path"),
        candidate.media_url,
        candidate.url,
        *_raw_file_values(candidate.payload),
    ):
        parsed = urlparse(str(value or ""))
        path = parsed.path.lower()
        for suffix in (".tar.gz", ".tgz", ".zip", ".tar", ".7z"):
            if path.endswith(suffix):
                return suffix
    return ""


def _safe_archive_member_name(name: str) -> str | None:
    normalized = normpath(name.replace("\\", "/"))
    if normalized.startswith("../") or normalized == ".." or normalized.startswith("/"):
        return None
    return normalized


def _archive_manifest_record(
    candidate: VideoCandidate,
    *,
    retrieved_at: str,
    archive_sha256: str,
    archive_byte_size: int,
    raw_archive_path: str,
    members: list[dict[str, object]],
) -> EvidenceRecord:
    digest = _digest(candidate.source_record_id, archive_sha256, "archive_manifest")
    video_member_count = sum(1 for member in members if member.get("is_video"))
    return EvidenceRecord(
        record_id=f"video_atom:archive_manifest:{_safe_id(candidate.source_record_id)}:{digest}",
        lane="media",
        source=VIDEO_ATOMS_SOURCE_ID,
        title=f"Aedes aegypti video archive manifest {candidate.title}",
        text=(
            f"Aedes aegypti video archive manifest for {candidate.title}. "
            f"Archive members: {len(members)}. Video members: {video_member_count}. "
            f"Archive SHA-256: {archive_sha256}."
        ),
        species=candidate.species or "Aedes aegypti",
        url=candidate.url,
        media_url=raw_archive_path,
        provenance=Provenance(
            source_id=VIDEO_ATOMS_SOURCE_ID,
            locator=str(candidate.provenance.get("locator") or f"records#{candidate.source_record_id}"),
            retrieved_at=retrieved_at,
            license=candidate.provenance.get("license") if isinstance(candidate.provenance.get("license"), str) else None,
            source_url=candidate.media_url or candidate.url,
        ),
        payload={
            "atom_type": "video_archive_manifest",
            "source_video_record_id": candidate.source_record_id,
            "source_dataset": candidate.payload.get("source_dataset") or candidate.title,
            "download_url": candidate.media_url,
            "sha256": archive_sha256,
            "byte_size": archive_byte_size,
            "raw_archive_path": raw_archive_path,
            "member_count": len(members),
            "video_member_count": video_member_count,
            "members": members[:250],
            "source_video_provenance": candidate.provenance,
        },
    )


def _archive_member_record(
    candidate: VideoCandidate,
    asset: EvidenceRecord,
    *,
    retrieved_at: str,
    archive_sha256: str,
    raw_archive_path: str,
    member_name: str,
    member_sha256: str,
    member_byte_size: int,
    raw_asset_path: str,
) -> EvidenceRecord:
    digest = _digest(candidate.source_record_id, member_name, member_sha256, "archive_member")
    return EvidenceRecord(
        record_id=f"video_atom:archive_member:{_safe_id(candidate.source_record_id)}:{digest}",
        lane="media",
        source=VIDEO_ATOMS_SOURCE_ID,
        title=f"Aedes aegypti video archive member {member_name}",
        text=(
            f"Aedes aegypti video archive member {member_name} extracted from {candidate.title}. "
            f"Member byte size: {member_byte_size}. Member SHA-256: {member_sha256}."
        ),
        species=candidate.species or "Aedes aegypti",
        url=candidate.url,
        media_url=raw_asset_path,
        provenance=Provenance(
            source_id=VIDEO_ATOMS_SOURCE_ID,
            locator=f"{raw_archive_path}#{member_name}",
            retrieved_at=retrieved_at,
            license=candidate.provenance.get("license") if isinstance(candidate.provenance.get("license"), str) else None,
            source_url=candidate.media_url or candidate.url,
        ),
        payload={
            "atom_type": "video_archive_member",
            "source_video_asset_id": asset.record_id,
            "source_video_record_id": asset.payload["source_video_record_id"],
            "archive_source_video_record_id": candidate.source_record_id,
            "archive_url": candidate.media_url,
            "archive_sha256": archive_sha256,
            "raw_archive_path": raw_archive_path,
            "member_name": member_name,
            "member_sha256": member_sha256,
            "byte_size": member_byte_size,
            "raw_asset_path": raw_asset_path,
        },
    )


def _asset_probe_payload(
    path: Path,
    candidate: VideoCandidate,
    *,
    probe_video_file_fn: Callable[[Path], dict[str, object]],
    gaps: list[dict[str, object]],
    gap_reason_prefix: str,
) -> tuple[dict[str, object], str]:
    probe_payload: dict[str, object] = {}
    try:
        probe_payload = probe_video_file_fn(path)
    except FileNotFoundError as exc:
        gaps.append(
            {
                "source": VIDEO_ATOMS_SOURCE_ID,
                "reason": f"{gap_reason_prefix}_tool_missing",
                "record_id": candidate.source_record_id,
                "path": path.as_posix(),
                "error": str(exc),
            }
        )
    except Exception as exc:
        gaps.append(
            {
                "source": VIDEO_ATOMS_SOURCE_ID,
                "reason": f"{gap_reason_prefix}_failed",
                "record_id": candidate.source_record_id,
                "path": path.as_posix(),
                "error": str(exc),
            }
        )
    probe_verified = any(probe_payload.get(key) is not None for key in ("duration_seconds", "fps", "width", "height", "codec"))
    return probe_payload, "verified" if probe_verified else "mirrored_unverified"


def _record_for_existing_mirror(
    candidate: VideoCandidate,
    path: Path,
    *,
    artifact_dir: Path,
    retrieved_at: str,
    probe_video_file_fn: Callable[[Path], dict[str, object]],
    gaps: list[dict[str, object]],
) -> tuple[EvidenceRecord, Path]:
    digest = _sha256_file(path)
    probe_payload, verification_status = _asset_probe_payload(
        path,
        candidate,
        probe_video_file_fn=probe_video_file_fn,
        gaps=gaps,
        gap_reason_prefix="video_existing_probe",
    )
    extra_payload = {
        "sha256": digest,
        "byte_size": path.stat().st_size,
        "raw_asset_path": path.relative_to(artifact_dir).as_posix(),
        **{key: value for key, value in probe_payload.items() if value is not None},
    }
    return (
        _record_for_asset(
            candidate,
            retrieved_at=retrieved_at,
            verification_status=verification_status,
            extra_payload=extra_payload,
        ),
        path,
    )


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
        gaps.append(_gap_context(candidate, "video_download_url_missing"))
        return _record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="gapped_download_url_missing"), None
    if _looks_like_archive(
        candidate.media_url,
        candidate.url,
        candidate.title,
        candidate.payload.get("filename"),
        candidate.payload.get("name"),
        candidate.payload.get("materialized_path"),
    ):
        gaps.append(_gap_context(candidate, "video_archive_not_expanded"))
        return _record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="gapped_archive_not_expanded"), None
    if not allow_unclear_license and not _is_allowed_license(candidate.provenance.get("license"), allowed_licenses):
        gaps.append(_gap_context(candidate, "video_license_unclear"))
        size = _size_from_candidate(candidate)
        if size is not None and size > max_video_bytes:
            gaps.append(
                _gap_context(candidate, "video_too_large", byte_size=size, max_video_bytes=max_video_bytes)
            )
        return _record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="gapped_license_unclear"), None
    size = _size_from_candidate(candidate)
    if size is not None and size > max_video_bytes:
        gaps.append(
            _gap_context(candidate, "video_too_large", byte_size=size, max_video_bytes=max_video_bytes)
        )
        return _record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="gapped_too_large"), None
    try:
        data = fetch_video_bytes_fn(candidate.media_url, max_video_bytes)
    except VideoDownloadAccessRestrictedError as exc:
        gaps.append(_gap_context(candidate, "video_download_access_restricted", error=str(exc), status_code=exc.status_code))
        return _record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="gapped_download_access_restricted"), None
    except VideoDownloadNotVideoError as exc:
        gaps.append(_gap_context(candidate, "video_download_not_video", error=str(exc)))
        return _record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="gapped_download_not_video"), None
    except Exception as exc:
        gaps.append(_gap_context(candidate, "video_download_failed", error=str(exc)))
        return _record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="gapped_download_failed"), None
    if len(data) > max_video_bytes:
        gaps.append(
            _gap_context(candidate, "video_too_large", byte_size=len(data), max_video_bytes=max_video_bytes)
        )
        return _record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="gapped_too_large"), None
    digest = hashlib.sha256(data).hexdigest()
    raw_dir = artifact_dir / "raw" / "video_atoms" / "assets"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{_safe_id(candidate.source_record_id)}_{digest[:12]}{_asset_extension(candidate)}"
    raw_path.write_bytes(data)
    probe_payload, verification_status = _asset_probe_payload(
        raw_path,
        candidate,
        probe_video_file_fn=probe_video_file_fn,
        gaps=gaps,
        gap_reason_prefix="video_probe",
    )
    extra_payload = {
        "sha256": digest,
        "byte_size": len(data),
        "raw_asset_path": raw_path.relative_to(artifact_dir).as_posix(),
        **{key: value for key, value in probe_payload.items() if value is not None},
    }
    return _record_for_asset(candidate, retrieved_at=retrieved_at, verification_status=verification_status, extra_payload=extra_payload), raw_path


def _mirror_archive_candidate(
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
) -> tuple[list[EvidenceRecord], list[tuple[EvidenceRecord, Path | None]]]:
    if not candidate.media_url:
        gaps.append(_gap_context(candidate, "video_download_url_missing"))
        return [], [(_record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="gapped_download_url_missing"), None)]
    if not allow_unclear_license and not _is_allowed_license(candidate.provenance.get("license"), allowed_licenses):
        gaps.append(_gap_context(candidate, "video_license_unclear"))
        return [], [(_record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="gapped_license_unclear"), None)]
    size = _size_from_candidate(candidate)
    if size is not None and size > max_video_bytes:
        gaps.append(_gap_context(candidate, "video_archive_too_large", byte_size=size, max_video_bytes=max_video_bytes))
        return [], [(_record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="gapped_archive_too_large"), None)]
    archive_extension = _archive_extension(candidate)
    supported_archive_extensions = {".zip", ".tar", ".tar.gz", ".tgz"}
    if archive_extension not in supported_archive_extensions:
        gaps.append(_gap_context(candidate, "video_archive_unsupported_format", archive_format=archive_extension or "unknown"))
        return [], [(_record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="gapped_archive_unsupported_format"), None)]
    try:
        data = fetch_video_bytes_fn(candidate.media_url, max_video_bytes)
    except VideoDownloadAccessRestrictedError as exc:
        gaps.append(_gap_context(candidate, "video_download_access_restricted", error=str(exc), status_code=exc.status_code))
        return [], [(_record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="gapped_download_access_restricted"), None)]
    except VideoDownloadNotVideoError as exc:
        gaps.append(_gap_context(candidate, "video_download_not_video", error=str(exc)))
        return [], [(_record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="gapped_download_not_video"), None)]
    except Exception as exc:
        gaps.append(_gap_context(candidate, "video_download_failed", error=str(exc)))
        return [], [(_record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="gapped_download_failed"), None)]
    if len(data) > max_video_bytes:
        gaps.append(_gap_context(candidate, "video_archive_too_large", byte_size=len(data), max_video_bytes=max_video_bytes))
        return [], [(_record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="gapped_archive_too_large"), None)]

    archive_sha256 = hashlib.sha256(data).hexdigest()
    archive_dir = artifact_dir / "raw" / "video_atoms" / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    raw_archive_path = archive_dir / f"{_safe_id(candidate.source_record_id)}_{archive_sha256[:12]}{archive_extension}"
    raw_archive_path.write_bytes(data)
    relative_archive_path = raw_archive_path.relative_to(artifact_dir).as_posix()

    members: list[dict[str, object]] = []
    extra_records: list[EvidenceRecord] = []
    asset_entries: list[tuple[EvidenceRecord, Path | None]] = []

    def process_member(member_name_raw: str, member_size: int, read_member_fn: Callable[[], bytes]) -> None:
        member_name = _safe_archive_member_name(member_name_raw)
        if not member_name:
            return
        suffix = Path(member_name).suffix.lower()
        is_video = suffix in VIDEO_EXTENSIONS
        member_context = {
            "member_name": member_name,
            "byte_size": member_size,
            "is_video": is_video,
        }
        if is_video and member_size > max_video_bytes:
            gaps.append(
                _gap_context(
                    candidate,
                    "video_archive_member_too_large",
                    member_name=member_name,
                    byte_size=member_size,
                    max_video_bytes=max_video_bytes,
                )
            )
            members.append(member_context)
            return
        if is_video:
            member_data = read_member_fn()
            if len(member_data) > max_video_bytes:
                gaps.append(
                    _gap_context(
                        candidate,
                        "video_archive_member_too_large",
                        member_name=member_name,
                        byte_size=len(member_data),
                        max_video_bytes=max_video_bytes,
                    )
                )
                members.append(member_context)
                return
            member_sha256 = hashlib.sha256(member_data).hexdigest()
            member_safe = _safe_id(member_name)
            asset_dir = artifact_dir / "raw" / "video_atoms" / "assets"
            asset_dir.mkdir(parents=True, exist_ok=True)
            raw_asset_path = asset_dir / f"{_safe_id(candidate.source_record_id)}_{member_safe}_{member_sha256[:12]}{suffix}"
            raw_asset_path.write_bytes(member_data)
            relative_asset_path = raw_asset_path.relative_to(artifact_dir).as_posix()
            member_candidate = VideoCandidate(
                source_record_id=f"{candidate.source_record_id}:{member_name}",
                title=f"{candidate.title} member {Path(member_name).name}",
                text=f"{candidate.text} Archive member: {member_name}.",
                species=candidate.species,
                url=candidate.url,
                media_url=f"{candidate.media_url}#{quote(member_name)}",
                source=candidate.source,
                provenance=candidate.provenance,
                payload={
                    **candidate.payload,
                    "filename": Path(member_name).name,
                    "source_dataset": candidate.payload.get("source_dataset") or candidate.title,
                    "archive_source_video_record_id": candidate.source_record_id,
                },
                discovery_repository=candidate.discovery_repository,
            )
            probe_payload, verification_status = _asset_probe_payload(
                raw_asset_path,
                member_candidate,
                probe_video_file_fn=probe_video_file_fn,
                gaps=gaps,
                gap_reason_prefix="video_archive_member_probe",
            )
            extra_payload = {
                "archive_source_video_record_id": candidate.source_record_id,
                "archive_url": candidate.media_url,
                "archive_sha256": archive_sha256,
                "raw_archive_path": relative_archive_path,
                "member_name": member_name,
                "member_sha256": member_sha256,
                "byte_size": len(member_data),
                "raw_asset_path": relative_asset_path,
                **{key: value for key, value in probe_payload.items() if value is not None},
            }
            asset = _record_for_asset(
                member_candidate,
                retrieved_at=retrieved_at,
                verification_status=verification_status,
                extra_payload=extra_payload,
            )
            extra_records.append(
                _archive_member_record(
                    candidate,
                    asset,
                    retrieved_at=retrieved_at,
                    archive_sha256=archive_sha256,
                    raw_archive_path=relative_archive_path,
                    member_name=member_name,
                    member_sha256=member_sha256,
                    member_byte_size=len(member_data),
                    raw_asset_path=relative_asset_path,
                )
            )
            asset_entries.append((asset, raw_asset_path))
            member_context.update({"sha256": member_sha256, "raw_asset_path": relative_asset_path})
        elif suffix in {".csv", ".tsv", ".xlsx"} and member_size <= max_video_bytes:
            table_dir = artifact_dir / "raw" / "video_atoms" / "archive_tables" / _safe_id(candidate.source_record_id)
            table_dir.mkdir(parents=True, exist_ok=True)
            table_path = table_dir / _safe_id(member_name)
            table_path.write_bytes(read_member_fn())
            member_context["raw_table_path"] = table_path.relative_to(artifact_dir).as_posix()
        members.append(member_context)

    try:
        if archive_extension == ".zip":
            with zipfile.ZipFile(raw_archive_path) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue

                    def read_zip_member(info: zipfile.ZipInfo = info) -> bytes:
                        with archive.open(info) as handle:
                            return handle.read(max_video_bytes + 1)

                    process_member(
                        info.filename,
                        info.file_size,
                        read_zip_member,
                    )
        else:
            with tarfile.open(raw_archive_path, "r:*") as archive:
                for info in archive.getmembers():
                    if info.isdir() or not info.isfile():
                        continue

                    def read_tar_member(info: tarfile.TarInfo = info) -> bytes:
                        handle = archive.extractfile(info)
                        if handle is None:
                            return b""
                        with handle:
                            return handle.read(max_video_bytes + 1)

                    process_member(info.name, int(info.size), read_tar_member)
    except (zipfile.BadZipFile, tarfile.TarError, EOFError) as exc:
        gaps.append(_gap_context(candidate, "video_archive_read_failed", error=str(exc)))
        return [], [(_record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="gapped_archive_read_failed"), None)]

    extra_records.insert(
        0,
        _archive_manifest_record(
            candidate,
            retrieved_at=retrieved_at,
            archive_sha256=archive_sha256,
            archive_byte_size=len(data),
            raw_archive_path=relative_archive_path,
            members=members,
        ),
    )
    if not any(member.get("is_video") for member in members):
        gaps.append(_gap_context(candidate, "video_archive_no_video_members"))
        asset_entries.append((_record_for_asset(candidate, retrieved_at=retrieved_at, verification_status="gapped_archive_no_video_members"), None))
    return extra_records, asset_entries


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


def _existing_artifact_payload(source_asset: EvidenceRecord, artifact_dir: Path, *, allow_thumbnail_keyframe: bool = True) -> dict[str, object] | None:
    output_dir = artifact_dir / "raw" / "video_atoms" / "artifacts" / _safe_id(source_asset.record_id)
    if not output_dir.exists():
        return None
    thumbnail = output_dir / "thumbnail.jpg"
    preview = output_dir / "preview.mp4"
    frames = output_dir / "frames.json"
    keyframes = sorted(output_dir.glob("keyframe*.jpg"))
    if not keyframes and allow_thumbnail_keyframe and thumbnail.exists():
        keyframes = [thumbnail]
    payload: dict[str, object] = {}
    if thumbnail.exists():
        payload["thumbnail_path"] = thumbnail.relative_to(artifact_dir).as_posix()
    if keyframes:
        payload["keyframe_paths"] = [path.relative_to(artifact_dir).as_posix() for path in keyframes]
    if preview.exists():
        payload["preview_clip_path"] = preview.relative_to(artifact_dir).as_posix()
    if frames.exists():
        payload["frame_manifest_path"] = frames.relative_to(artifact_dir).as_posix()
    return payload or None


def _gap_record(gap: dict[str, object], *, retrieved_at: str, index: int) -> EvidenceRecord:
    reason = str(gap.get("reason") or "video_gap")
    source_record_id = str(gap.get("record_id") or gap.get("title") or gap.get("repository") or f"gap-{index}")
    locator = str(gap.get("locator") or f"gaps.json#aedes_video_atoms/{index}")
    digest = _digest(
        str(gap.get("source") or VIDEO_ATOMS_SOURCE_ID),
        str(gap.get("lane") or "media"),
        reason,
        source_record_id,
        locator,
    )
    source_url = gap.get("source_url")
    url = source_url if isinstance(source_url, str) and source_url else None
    license_value = gap.get("license")
    title = f"Aedes aegypti video gap {reason}"
    text = f"Aedes aegypti video source gap: {reason}. Source record: {source_record_id}."
    if gap.get("original_source"):
        text += f" Original source: {gap.get('original_source')}."
    if gap.get("original_reason"):
        text += f" Original reason: {gap.get('original_reason')}."
    if gap.get("repository"):
        text += f" Repository: {gap.get('repository')}."
    if gap.get("source_dataset"):
        text += f" Source dataset: {gap.get('source_dataset')}."
    if gap.get("download_url"):
        text += f" Download URL: {gap.get('download_url')}."
    byte_size = gap.get("source_byte_size") or gap.get("byte_size")
    if byte_size is not None:
        text += f" Source byte size: {byte_size}."
    source_hashes = gap.get("source_hashes")
    if isinstance(source_hashes, dict):
        sha256 = source_hashes.get("sha256")
        if sha256:
            text += f" Source SHA-256: {sha256}."
    if gap.get("license"):
        text += f" License: {gap.get('license')}."
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


def _sweep_record(receipt: dict[str, object], *, retrieved_at: str) -> EvidenceRecord:
    repository = str(receipt.get("repository") or "unknown")
    status = str(receipt.get("status") or "unknown")
    raw_count = int(receipt.get("raw_candidate_count") or 0)
    accepted_count = int(receipt.get("accepted_candidate_count") or 0)
    gap_count = int(receipt.get("gap_count") or 0)
    locator = str(receipt.get("locator") or f"raw/video_atoms/discovery_sweeps.json#{repository}")
    title = f"Aedes aegypti video discovery sweep: {repository}"
    text = (
        f"Aedes aegypti video discovery sweep for {repository}: status {status}; "
        f"raw candidates {raw_count}; accepted video assets {accepted_count}; structured gaps {gap_count}."
    )
    if receipt.get("limit_applied"):
        text += f" Limit applied at {receipt.get('max_discovery_results')} discovery candidates."
    return EvidenceRecord(
        record_id=f"video_atom:sweep:{_safe_id(repository)}",
        lane="media",
        source=VIDEO_ATOMS_SOURCE_ID,
        title=title,
        text=text,
        species="Aedes aegypti",
        url=str(receipt.get("source_url") or "") or None,
        media_url=None,
        provenance=Provenance(
            source_id=VIDEO_ATOMS_SOURCE_ID,
            locator=locator,
            retrieved_at=retrieved_at,
            license="Ask Insects source boundary audit",
            source_url=str(receipt.get("source_url") or "") or None,
        ),
        payload={"atom_type": "video_sweep", **receipt},
    )


def _load_upstream_manifest_gap_contexts(artifact_dir: Path) -> list[dict[str, object]]:
    gaps_path = artifact_dir / "gaps.json"
    if not gaps_path.exists():
        return []
    try:
        payload = json.loads(gaps_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    contexts: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    repository_for_source = {
        "zenodo_aedes_videos": "zenodo",
        "figshare_aedes_videos": "figshare",
    }
    for index, raw_gap in enumerate(payload, start=1):
        if not isinstance(raw_gap, dict):
            continue
        original_source = raw_gap.get("source")
        if original_source not in UPSTREAM_VIDEO_MANIFEST_GAP_SOURCES:
            continue
        original_reason = str(raw_gap.get("reason") or "manifest_gap")
        raw_record_id = raw_gap.get("record_id") or raw_gap.get("article_id") or raw_gap.get("file_id") or raw_gap.get("source_url") or f"gap-{index}"
        key = (original_source, original_reason, raw_record_id, raw_gap.get("locator"))
        if key in seen:
            continue
        seen.add(key)
        context: dict[str, object] = {
            "source": VIDEO_ATOMS_SOURCE_ID,
            "lane": "media",
            "reason": "video_manifest_gap",
            "original_source": original_source,
            "original_reason": original_reason,
            "repository": repository_for_source.get(str(original_source)),
            "record_id": f"{original_source}:{raw_record_id}",
            "title": f"{original_source} manifest gap {original_reason}",
            "query": raw_gap.get("query"),
            "source_url": raw_gap.get("source_url") or raw_gap.get("url"),
            "download_url": raw_gap.get("download_url") or raw_gap.get("media_url"),
            "license": raw_gap.get("license"),
            "locator": raw_gap.get("locator") or f"gaps.json#{index}",
            "article_id": raw_gap.get("article_id"),
            "file_id": raw_gap.get("file_id"),
            "source_byte_size": raw_gap.get("source_byte_size") or raw_gap.get("byte_size") or raw_gap.get("size"),
            "source_hashes": raw_gap.get("source_hashes"),
            "manifest_gap": raw_gap,
        }
        contexts.append({key: value for key, value in context.items() if value not in (None, "", {})})
    return contexts


def _keyframe_timestamps(probe: dict[str, object], *, max_keyframes: int = 6) -> list[float]:
    raw_duration = probe.get("duration_seconds")
    try:
        duration = float(raw_duration) if raw_duration is not None else 0.0
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        return [1.0]
    if duration <= 1:
        return [round(max(duration / 2, 0.0), 3)]
    count = min(max_keyframes, max(2, int(duration // 2) + 1))
    if count == 1:
        return [round(min(1.0, duration / 2), 3)]
    step = duration / (count + 1)
    return [round(step * index, 3) for index in range(1, count + 1)]


def generate_video_artifacts(
    asset_path: Path,
    output_dir: Path,
    probe: dict[str, object],
    *,
    max_keyframes: int = 6,
    preview_seconds: int = 8,
) -> dict[str, object]:
    if shutil.which("ffmpeg") is None:
        raise FileNotFoundError("ffmpeg not found")
    output_dir.mkdir(parents=True, exist_ok=True)
    thumbnail = output_dir / "thumbnail.jpg"
    preview = output_dir / "preview.mp4"
    frames = output_dir / "frames.json"
    timestamps = _keyframe_timestamps(probe, max_keyframes=max_keyframes)
    thumbnail_time = timestamps[0] if timestamps else 1.0
    subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-ss", str(thumbnail_time), "-i", str(asset_path), "-frames:v", "1", "-update", "1", str(thumbnail)])
    keyframe_paths: list[Path] = []
    for index, timestamp in enumerate(timestamps, start=1):
        keyframe_path = output_dir / f"keyframe_{index:06d}.jpg"
        subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-ss", str(timestamp), "-i", str(asset_path), "-frames:v", "1", "-update", "1", str(keyframe_path)])
        keyframe_paths.append(keyframe_path)
    raw_duration = probe.get("duration_seconds")
    try:
        duration = float(raw_duration) if raw_duration is not None else float(preview_seconds)
    except (TypeError, ValueError):
        duration = float(preview_seconds)
    preview_length = max(1.0, min(float(preview_seconds), duration if duration > 0 else float(preview_seconds)))
    subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-i", str(asset_path), "-t", str(preview_length), "-c", "copy", str(preview)])
    frames.write_text(
        json.dumps(
            {
                "source": asset_path.as_posix(),
                "probe": probe,
                "thumbnail_path": thumbnail.as_posix(),
                "preview_clip_path": preview.as_posix(),
                "keyframes": [
                    {
                        "frame_index": index,
                        "time_seconds": timestamp,
                        "artifact_path": keyframe_path.as_posix(),
                    }
                    for index, (timestamp, keyframe_path) in enumerate(zip(timestamps, keyframe_paths), start=1)
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "thumbnail_path": thumbnail.as_posix(),
        "keyframe_paths": [path.as_posix() for path in keyframe_paths],
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


def _motion_explicit_video_id(row: dict[str, str]) -> str | None:
    return row.get("video_id") or row.get("video") or row.get("source_video_record_id")


def _motion_video_id(row: dict[str, str], table_path: Path) -> str:
    return _motion_explicit_video_id(row) or table_path.stem


def _motion_source_video_lookup_id(filename: str) -> str | None:
    stem = Path(filename).stem
    match = re.match(r"(.+?)\s*-\s*Spot Statistics$", stem, flags=re.I)
    if match:
        return match.group(1).strip()
    return None


def _motion_lookup_keys(value: object) -> set[str]:
    text = str(value or "").strip()
    if not text:
        return set()
    keys = {text.lower()}
    spot_match = re.match(r"(.+?)\s*-\s*spot statistics$", text, flags=re.I)
    if spot_match:
        keys.add(spot_match.group(1).strip().lower())
    parsed = urlparse(text)
    if parsed.fragment:
        fragment = unquote(parsed.fragment).strip()
        if fragment:
            keys.add(fragment.lower())
            keys.add(Path(fragment).name.lower())
            fragment_spot_match = re.match(r"(.+?)\s*-\s*spot statistics$", Path(fragment).stem, flags=re.I)
            if fragment_spot_match:
                keys.add(fragment_spot_match.group(1).strip().lower())
    path = unquote(parsed.path or text).strip()
    if path:
        keys.add(path.lower())
        keys.add(Path(path).name.lower())
        stem = Path(path).stem.lower()
        if stem:
            keys.add(stem)
            path_spot_match = re.match(r"(.+?)\s*-\s*spot statistics$", stem, flags=re.I)
            if path_spot_match:
                keys.add(path_spot_match.group(1).strip().lower())
    return {key for key in keys if key}


def _build_motion_asset_lookup(records: Iterable[EvidenceRecord]) -> dict[str, EvidenceRecord]:
    lookup: dict[str, EvidenceRecord] = {}
    for record in records:
        if not record.payload or record.payload.get("atom_type") != "video_asset":
            continue
        payload = record.payload
        values: list[object] = [
            record.record_id,
            record.media_url,
            record.url,
            payload.get("source_video_record_id"),
            payload.get("member_name"),
            payload.get("raw_asset_path"),
            payload.get("download_url"),
            payload.get("archive_source_video_record_id"),
        ]
        source_payload = payload.get("source_video_payload")
        if isinstance(source_payload, dict):
            values.extend(
                source_payload.get(key)
                for key in (
                    "filename",
                    "name",
                    "materialized_path",
                    "download_url",
                    "video_url",
                    "media_url",
                )
            )
        for value in values:
            for key in _motion_lookup_keys(value):
                lookup.setdefault(key, record)
    return lookup


def _motion_asset_for_video_id(video_id: str, asset_lookup: dict[str, EvidenceRecord]) -> EvidenceRecord | None:
    for key in _motion_lookup_keys(video_id):
        asset = asset_lookup.get(key)
        if asset is not None:
            return asset
    return None


def _mendeley_motion_table_contexts(artifact_dir: Path) -> dict[str, dict[str, object]]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    try:
        rows = index.sql(
            """
            select payload_json
            from record_payloads
            where source='mendeley_aedes_behavior_media'
              and record_id like 'mendeley:file:%'
            """,
            limit=100000,
        )
    except Exception:
        return {}
    contexts: dict[str, dict[str, object]] = {}
    for row in rows:
        payload = _safe_json(row.get("payload_json"))
        filename = str(payload.get("filename") or "")
        suffix = Path(filename).suffix.lower()
        if suffix not in {".csv", ".tsv", ".xlsx"}:
            continue
        dataset_id = str(payload.get("dataset_id") or "")
        version = payload.get("version")
        file_id = str(payload.get("file_id") or "")
        if not dataset_id or not version or not file_id:
            continue
        rel_path = (
            Path("raw")
            / "mendeley_behavior_media"
            / "table_files"
            / f"{_mendeley_safe_id(dataset_id)}_v{version}_{_mendeley_safe_id(file_id)}{suffix}"
        ).as_posix()
        context: dict[str, object] = {
            "source_table_filename": filename,
            "source_table_file_id": file_id,
        }
        lookup_id = _motion_source_video_lookup_id(filename)
        if lookup_id:
            context["source_video_lookup_id"] = lookup_id
        contexts[rel_path] = context
    return contexts


def _list_text_values(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _motion_asset_behavior_labels(asset: EvidenceRecord | None) -> list[str]:
    if asset is None or not asset.payload:
        return []
    labels: list[str] = []
    payload = asset.payload
    labels.extend(_list_text_values(payload.get("behavior_labels")))
    source_payload = payload.get("source_video_payload")
    if isinstance(source_payload, dict):
        labels.extend(_list_text_values(source_payload.get("behavior_labels")))
    seen: set[str] = set()
    unique: list[str] = []
    for label in labels:
        key = label.lower()
        if key not in seen:
            seen.add(key)
            unique.append(label)
    return unique


def _motion_asset_payload(asset: EvidenceRecord | None) -> dict[str, object]:
    if asset is None or not asset.payload:
        return {}
    payload = asset.payload
    behavior_labels = _motion_asset_behavior_labels(asset)
    return {
        key: value
        for key, value in {
            "source_video_asset_id": asset.record_id,
            "source_video_asset_status": payload.get("verification_status"),
            "source_dataset": payload.get("source_dataset"),
            "repository": payload.get("repository") or payload.get("discovery_repository"),
            "download_url": payload.get("download_url") or asset.media_url,
            "source_video_asset_media_url": asset.media_url,
            "source_behavior_labels": behavior_labels,
        }.items()
        if value not in (None, "", {}, [])
    }


def _motion_dataset_payload(
    video_id: str,
    table_path: Path,
    asset_lookup: dict[str, EvidenceRecord] | None,
) -> dict[str, object]:
    if not asset_lookup:
        return {}
    haystack = " ".join(
        value.lower()
        for value in (
            video_id,
            table_path.name,
            table_path.stem,
            table_path.as_posix(),
        )
        if value
    )
    seen_assets: set[str] = set()
    for asset in asset_lookup.values():
        if asset.record_id in seen_assets or not asset.payload:
            continue
        seen_assets.add(asset.record_id)
        source_payload = asset.payload.get("source_video_payload")
        source_payload = source_payload if isinstance(source_payload, dict) else {}
        match_values = (
            source_payload.get("dataset_id"),
            source_payload.get("doi"),
            source_payload.get("dataset_title"),
            asset.payload.get("source_dataset"),
        )
        if not any(str(value or "").lower() in haystack for value in match_values if str(value or "").strip()):
            continue
        behavior_labels = _motion_asset_behavior_labels(asset)
        context = {
            "source_dataset": asset.payload.get("source_dataset"),
            "repository": asset.payload.get("repository") or asset.payload.get("discovery_repository"),
            "source_behavior_labels": behavior_labels,
        }
        return {key: value for key, value in context.items() if value not in (None, "", {}, [])}
    return {}


def _motion_behavior_from_labels(labels: object) -> str | None:
    values = _list_text_values(labels)
    if not values:
        return None
    return ", ".join(values[:3])


def _motion_record(
    row: dict[str, str],
    *,
    table_path: Path,
    artifact_dir: Path,
    row_index: int,
    retrieved_at: str,
    locator_suffix: str | None = None,
    source_video_asset: EvidenceRecord | None = None,
    source_motion_context: dict[str, object] | None = None,
) -> EvidenceRecord:
    video_id = _motion_video_id(row, table_path)
    source_payload = {
        **(source_motion_context or {}),
        **_motion_asset_payload(source_video_asset),
    }
    behavior = row.get("behavior") or row.get("behavior_type") or _motion_behavior_from_labels(source_payload.get("source_behavior_labels")) or "video motion"
    trial = row.get("trial")
    arena = row.get("arena")
    temperature = row.get("temperature")
    rel_path = table_path.relative_to(artifact_dir).as_posix()
    locator = f"{rel_path}#{locator_suffix or f'row/{row_index}'}"
    payload = {
        "atom_type": "video_motion_row",
        "source_video_record_id": video_id,
        "source_table": rel_path,
        "source_table_locator": locator,
        "track_id": row.get("track_id") or row.get("track"),
        "frame": _parse_number(row.get("frame")),
        "time_seconds": _parse_number(row.get("time_seconds") or row.get("time")),
        "x": _parse_number(row.get("x")),
        "y": _parse_number(row.get("y")),
        "behavior_type": behavior,
        "sex": row.get("sex"),
        "life_stage": row.get("life_stage") or row.get("life stage"),
        "assay": row.get("assay") or ("locomotory video analysis" if any(key in row for key in ("velocity_mean_cm_s", "distance_moved_total_cm", "zone_mean_seconds")) else None),
        "stimulus": row.get("stimulus"),
        "arena": arena,
        "confidence": row.get("confidence") or "source_table",
        "trial": trial,
        "temperature": temperature,
        "feeding_status": row.get("feeding_status"),
        "age": _parse_number(row.get("age")),
        "zone_mean_seconds": _parse_number(row.get("zone_mean_seconds")),
        "zone_frequency": _parse_number(row.get("zone_frequency")),
        "zone_cumulative_duration_seconds": _parse_number(row.get("zone_cumulative_duration_seconds")),
        "velocity_mean_cm_s": _parse_number(row.get("velocity_mean_cm_s")),
        "angular_velocity_absolute_mean_deg_s": _parse_number(row.get("angular_velocity_absolute_mean_deg_s")),
        "angular_velocity_relative_mean_deg_s": _parse_number(row.get("angular_velocity_relative_mean_deg_s")),
        "distance_moved_total_cm": _parse_number(row.get("distance_moved_total_cm")),
        "source_table_row": row,
        **source_payload,
    }
    payload = {key: value for key, value in payload.items() if value is not None}
    digest = _digest(video_id, rel_path, row_index)
    metrics = []
    if payload.get("velocity_mean_cm_s") is not None:
        metrics.append(f"mean velocity {payload.get('velocity_mean_cm_s')} cm/s")
    if payload.get("distance_moved_total_cm") is not None:
        metrics.append(f"distance moved {payload.get('distance_moved_total_cm')} cm")
    if temperature:
        metrics.append(f"temperature {temperature}")
    metric_text = f" Metrics: {', '.join(metrics)}." if metrics else ""
    label_text = _motion_behavior_from_labels(payload.get("source_behavior_labels"))
    source_label_text = f" Source behavior labels: {label_text}." if label_text else ""
    source_video_label_text = f" Source video label: {payload.get('source_video_lookup_id')}." if payload.get("source_video_lookup_id") else ""
    return EvidenceRecord(
        record_id=f"video_atom:motion:{_safe_id(video_id)}:{digest}",
        lane="behavior",
        source=VIDEO_ATOMS_SOURCE_ID,
        title=f"Aedes aegypti video motion row {behavior}",
        text=(
            f"Aedes aegypti video motion row for {behavior}. "
            f"Video: {video_id}. Track: {payload.get('track_id')}. Frame: {payload.get('frame')}. "
            f"Time seconds: {payload.get('time_seconds')}. Coordinates: {payload.get('x')}, {payload.get('y')}.{metric_text}{source_video_label_text}{source_label_text}"
        ),
        species="Aedes aegypti",
        url=source_video_asset.url if source_video_asset else None,
        media_url=source_video_asset.media_url if source_video_asset else None,
        provenance=Provenance(
            source_id=VIDEO_ATOMS_SOURCE_ID,
            locator=locator,
            retrieved_at=retrieved_at,
            source_url=source_video_asset.media_url if source_video_asset and source_video_asset.media_url else rel_path,
        ),
        payload=payload,
    )


def _parse_delimited_motion_table(table_path: Path) -> list[tuple[int, dict[str, str], str]]:
    with table_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter="\t" if table_path.suffix.lower() == ".tsv" else ",")
        headers = {_normalize_motion_header(header) for header in (reader.fieldnames or [])}
        if not headers & MOTION_HEADERS:
            return []
        rows = []
        for row_index, row in enumerate(reader, start=1):
            cleaned = _normalize_motion_row(row)
            if cleaned:
                rows.append((row_index, cleaned, f"row/{row_index}"))
        return rows


def _parse_xlsx_motion_table(table_path: Path) -> list[tuple[int, dict[str, str], str]]:
    rows = []
    for sheet_index, sheet in enumerate(_parse_table(table_path, table_path.name), start=1):
        headers, data_rows = _table_layout(sheet.rows)
        normalized_headers = {_normalize_motion_header(header) for header in headers}
        if not normalized_headers & MOTION_HEADERS:
            continue
        for row_number, row in data_rows:
            cleaned = _normalize_motion_row(_row_values(headers, row))
            if cleaned:
                rows.append((row_number, cleaned, f"sheet/{sheet_index}/row/{row_number}"))
    return rows


def _repository_for_motion_table_path(table_path: Path) -> str | None:
    text = table_path.as_posix()
    path_repositories = (
        ("raw/pmc_videos/", "pmc_oa"),
        ("raw/dryad_behavior_videos/", "dryad"),
        ("raw/mendeley_behavior_media/", "mendeley"),
        ("raw/osf_flighttrackai_videos/", "osf"),
        ("raw/zenodo_aedes_videos/", "zenodo"),
        ("raw/figshare_aedes_videos/", "figshare"),
    )
    for marker, repository in path_repositories:
        if marker in text:
            return repository
    return None


def _parse_motion_tables(
    motion_table_paths: Iterable[Path],
    *,
    artifact_dir: Path,
    retrieved_at: str,
    gaps: list[dict[str, object]],
    asset_lookup: dict[str, EvidenceRecord] | None = None,
    table_contexts: dict[str, dict[str, object]] | None = None,
) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    unmatched: set[tuple[str, str]] = set()
    for table_path in motion_table_paths:
        try:
            path = Path(table_path)
            if path.name.startswith("._"):
                continue
            rel_path = path.relative_to(artifact_dir).as_posix()
            table_context = (table_contexts or {}).get(rel_path, {})
            parsed_rows = _parse_xlsx_motion_table(path) if path.suffix.lower() == ".xlsx" else _parse_delimited_motion_table(path)
            for row_index, cleaned, locator_suffix in parsed_rows:
                video_id = _motion_video_id(cleaned, path)
                lookup_video_id = str(table_context.get("source_video_lookup_id") or video_id)
                source_video_asset = _motion_asset_for_video_id(lookup_video_id, asset_lookup or {})
                source_motion_context = {
                    **_motion_dataset_payload(lookup_video_id, path, asset_lookup),
                    **table_context,
                }
                if asset_lookup and source_video_asset is None and _motion_explicit_video_id(cleaned):
                    key = (rel_path, video_id)
                    if key not in unmatched:
                        unmatched.add(key)
                        gaps.append(
                            {
                                "source": VIDEO_ATOMS_SOURCE_ID,
                                "lane": "behavior",
                                "reason": "video_motion_unmatched_source_video",
                                "record_id": video_id,
                                "source_video_record_id": video_id,
                                "source_table": rel_path,
                                "locator": f"{rel_path}#{locator_suffix}",
                            }
                        )
                records.append(
                    _motion_record(
                        cleaned,
                        table_path=path,
                        artifact_dir=artifact_dir,
                        row_index=row_index,
                        retrieved_at=retrieved_at,
                        locator_suffix=locator_suffix,
                        source_video_asset=source_video_asset,
                        source_motion_context=source_motion_context,
                    )
                )
        except Exception as exc:
            path = Path(table_path)
            try:
                rel_path = path.relative_to(artifact_dir).as_posix()
            except ValueError:
                rel_path = path.as_posix()
            gap = {
                "source": VIDEO_ATOMS_SOURCE_ID,
                "lane": "behavior",
                "reason": "video_motion_table_parse_failed",
                "record_id": path.name,
                "path": path.as_posix(),
                "locator": rel_path,
                "error": str(exc),
            }
            repository = _repository_for_motion_table_path(path)
            if repository:
                gap["repository"] = repository
            gaps.append(gap)
    return records


def _default_motion_table_paths(artifact_dir: Path) -> list[Path]:
    search_roots = (
        artifact_dir / "raw" / "pmc_videos",
        artifact_dir / "raw" / "dryad_behavior_videos",
        artifact_dir / "raw" / "mendeley_behavior_media" / "table_files",
        artifact_dir / "raw" / "mendeley_behavior_media",
        artifact_dir / "raw" / "osf_flighttrackai_videos",
        artifact_dir / "raw" / "zenodo_aedes_videos",
        artifact_dir / "raw" / "figshare_aedes_videos",
        artifact_dir / "raw" / "video_atoms",
    )
    paths: list[Path] = []
    seen: set[Path] = set()
    for root in search_roots:
        if not root.exists():
            continue
        for path in sorted([*root.rglob("*.csv"), *root.rglob("*.tsv"), *root.rglob("*.xlsx")]):
            if path.name.startswith("._"):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            paths.append(path)
    return paths


def _candidate_from_discovery(raw: dict[str, object]) -> VideoCandidate | dict[str, object]:
    repository = str(raw.get("repository") or "unknown")
    title = str(raw.get("title") or "")
    if not _has_discovery_aedes_scope(raw):
        return _discovery_gap(raw, "video_discovery_not_aedes_scope", repository, title)
    download_url = raw.get("download_url") or raw.get("media_url")
    if not isinstance(download_url, str) or not download_url:
        return _discovery_gap(raw, "video_discovery_no_download_url", repository, title)
    filename = raw.get("filename") or raw.get("name") or raw.get("path")
    if not _looks_like_video(filename, download_url, title, raw.get("description")):
        return _discovery_gap(raw, "video_discovery_not_video_media", repository, title)
    license_value = raw.get("license")
    if _license_is_unclear(license_value):
        return _discovery_gap(raw, "video_discovery_license_unclear", repository, title)
    record_id = f"discovery:{repository}:{_digest(title, download_url)}"
    provenance = {
        "source_id": f"video_discovery_{repository}",
        "locator": raw.get("locator") or f"discovery#{repository}:{_digest(title, download_url)}",
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


def _normalize_discovery_result(
    repository: str,
    result: list[dict[str, object]] | DiscoverySweepResult,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    if isinstance(result, DiscoverySweepResult):
        return result.items, dict(result.receipt)
    return result, {
        "coverage_method": "custom_client",
        "queries": [f"custom_discovery_client:{repository}"],
        "page_size": len(result),
        "page_count": 1,
        "cursor_or_page_complete": True,
        "candidate_limit": len(result),
    }


def _discover_candidates(
    discovery_clients: dict[str, Callable[[], list[dict[str, object]] | DiscoverySweepResult]],
    *,
    max_discovery_results: int,
    gaps: list[dict[str, object]],
    known_download_urls: set[str] | None = None,
    repositories: Iterable[str] | None = None,
) -> tuple[list[VideoCandidate], int, list[dict[str, object]]]:
    candidates: list[VideoCandidate] = []
    sweep_receipts: list[dict[str, object]] = []
    known_download_urls = known_download_urls or set()
    repository_order = tuple(repositories) if repositories is not None else DISCOVERY_REPOSITORIES
    count = 0
    for repository in repository_order:
        receipt: dict[str, object] = {
            "repository": repository,
            "status": "not_started",
            "raw_candidate_count": 0,
            "accepted_candidate_count": 0,
            "gap_count": 0,
            "locator": f"raw/video_atoms/discovery_sweeps.json#{repository}",
        }
        client = discovery_clients.get(repository)
        if client is None:
            gaps.append(
                {
                    "source": VIDEO_ATOMS_SOURCE_ID,
                    "lane": "media",
                    "reason": "video_discovery_client_missing",
                    "repository": repository,
                    "locator": receipt["locator"],
                }
            )
            receipt.update({"status": "client_missing", "gap_count": 1})
            sweep_receipts.append(receipt)
            continue
        try:
            raw_items, receipt_metadata = _normalize_discovery_result(repository, client())
            receipt.update({key: value for key, value in receipt_metadata.items() if value is not None})
        except Exception as exc:
            gaps.append(
                {
                    "source": VIDEO_ATOMS_SOURCE_ID,
                    "lane": "media",
                    "reason": "video_discovery_fetch_failed",
                    "repository": repository,
                    "error": str(exc),
                    "locator": receipt["locator"],
                }
            )
            receipt.update({"status": "fetch_failed", "gap_count": 1, "error": str(exc)})
            sweep_receipts.append(receipt)
            continue
        if not raw_items:
            gaps.append(
                {
                    "source": VIDEO_ATOMS_SOURCE_ID,
                    "lane": "media",
                    "reason": "video_discovery_no_candidates",
                    "repository": repository,
                    "locator": receipt["locator"],
                }
            )
            receipt.update({"status": "no_candidates", "gap_count": 1})
            sweep_receipts.append(receipt)
            continue
        receipt["raw_candidate_count"] = len(raw_items)
        for raw in raw_items:
            if count >= max_discovery_results:
                gaps.append(
                    {
                        "source": VIDEO_ATOMS_SOURCE_ID,
                        "lane": "media",
                        "reason": "video_discovery_limit_applied",
                        "repository": repository,
                        "max_discovery_results": max_discovery_results,
                        "locator": receipt["locator"],
                    }
                )
                receipt.update(
                    {
                        "status": "limit_applied",
                        "limit_applied": True,
                        "max_discovery_results": max_discovery_results,
                    }
                )
                sweep_receipts.append(receipt)
                return candidates, count, sweep_receipts
            count += 1
            normalized = _candidate_from_discovery({**raw, "repository": raw.get("repository") or repository})
            if isinstance(normalized, VideoCandidate):
                candidates.append(normalized)
                receipt["accepted_candidate_count"] = int(receipt.get("accepted_candidate_count") or 0) + 1
            else:
                download_url = raw.get("download_url") or raw.get("media_url")
                if normalized.get("reason") == "video_discovery_not_aedes_scope" and isinstance(download_url, str) and download_url in known_download_urls:
                    continue
                gaps.append(normalized)
                receipt["gap_count"] = int(receipt.get("gap_count") or 0) + 1
        if int(receipt.get("accepted_candidate_count") or 0):
            receipt["status"] = "accepted_candidates"
        elif int(receipt.get("gap_count") or 0):
            receipt["status"] = "all_candidates_gapped"
        else:
            receipt["status"] = "all_candidates_deduped"
        sweep_receipts.append(receipt)
    return candidates, count, sweep_receipts


def _dedupe_candidates(candidates: Iterable[VideoCandidate]) -> list[VideoCandidate]:
    deduped: list[VideoCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.media_url or candidate.source_record_id or "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


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
    discovery_clients: dict[str, Callable[[], list[dict[str, object]] | DiscoverySweepResult]] | None = None,
    discovery_repositories: Iterable[str] | None = None,
    max_discovery_results: int = 1000,
    motion_table_paths: Iterable[Path] | None = None,
    parse_motion_rows: bool = True,
) -> AedesVideoAtomsResult:
    artifact_dir = Path(artifact_dir)
    retrieved_at = retrieved_at or utc_now()
    if max_video_bytes < 1:
        raise ValueError("max_video_bytes must be positive")
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    gaps: list[dict[str, object]] = []
    records: list[EvidenceRecord] = []
    repository_scope = set(discovery_repositories or ())
    source_scope = _source_ids_for_repositories(repository_scope) if repository_scope else None
    if repository_scope:
        candidates = _candidate_rows(index, source_scope) if source_scope else []
    else:
        candidates = _candidate_rows(index)
    if repository_scope and source_scope:
        candidates = [
            candidate
            for candidate in candidates
            if _repository_for_source(candidate.source) in repository_scope
        ]
    discovery_candidate_count = 0
    discovery_sweep_receipts: list[dict[str, object]] = []
    if discover_sources:
        discovery_clients = discovery_clients if discovery_clients is not None else default_discovery_clients(artifact_dir)
        known_download_urls = {candidate.media_url for candidate in candidates if candidate.media_url}
        discovered, discovery_candidate_count, discovery_sweep_receipts = _discover_candidates(
            discovery_clients,
            max_discovery_results=max_discovery_results,
            gaps=gaps,
            known_download_urls=known_download_urls,
            repositories=discovery_repositories,
        )
        candidates.extend(discovered)
        if discovery_sweep_receipts:
            sweep_path = artifact_dir / "raw" / "video_atoms" / "discovery_sweeps.json"
            sweep_path.parent.mkdir(parents=True, exist_ok=True)
            sweep_path.write_text(json.dumps(discovery_sweep_receipts, indent=2, sort_keys=True), encoding="utf-8")
    candidates = _dedupe_candidates(candidates)

    mirrored_video_count = 0
    verified_video_count = 0
    artifact_count = 0
    fetcher = fetch_video_bytes_fn or _default_fetch_video_bytes
    probe_fn = probe_video_file_fn or probe_video_file
    artifact_fn = artifact_generator_fn or generate_video_artifacts
    for candidate in candidates:
        asset_entries: list[tuple[EvidenceRecord, Path | None]] = []
        existing_asset_path = _existing_mirror_path(candidate, artifact_dir)
        if existing_asset_path is not None:
            asset, asset_path = _record_for_existing_mirror(
                candidate,
                existing_asset_path,
                artifact_dir=artifact_dir,
                retrieved_at=retrieved_at,
                probe_video_file_fn=probe_fn,
                gaps=gaps,
            )
            mirrored_video_count += 1
            if asset.payload.get("verification_status") == "verified":
                verified_video_count += 1
            asset_entries.append((asset, asset_path))
        elif mirror_videos and _looks_like_archive(
            candidate.media_url,
            candidate.url,
            candidate.title,
            candidate.payload.get("filename"),
            candidate.payload.get("name"),
            candidate.payload.get("materialized_path"),
            *_raw_file_values(candidate.payload),
        ):
            archive_records, asset_entries = _mirror_archive_candidate(
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
            records.extend(archive_records)
            mirrored_video_count += sum(1 for _, path in asset_entries if path is not None)
            verified_video_count += sum(1 for asset, _ in asset_entries if asset.payload.get("verification_status") == "verified")
        elif mirror_videos:
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
            asset_entries.append((asset, asset_path))
        else:
            asset = _record_for_asset(candidate, retrieved_at=retrieved_at)
            asset_entries.append((asset, None))
        for asset, asset_path in asset_entries:
            records.append(asset)
            existing_artifacts = _existing_artifact_payload(asset, artifact_dir, allow_thumbnail_keyframe=not generate_artifacts)
            if existing_artifacts and (not generate_artifacts or existing_artifacts.get("keyframe_paths")):
                artifact_records = _artifact_records(asset, existing_artifacts, retrieved_at=retrieved_at)
                artifact_count += len(artifact_records)
                records.extend(artifact_records)
            elif generate_artifacts and asset_path is not None and asset.payload.get("verification_status") == "verified":
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
                    gaps.append({"source": VIDEO_ATOMS_SOURCE_ID, "reason": "video_artifact_tool_missing", "record_id": asset.payload.get("source_video_record_id") or candidate.source_record_id, "error": str(exc)})
                except Exception as exc:
                    gaps.append({"source": VIDEO_ATOMS_SOURCE_ID, "reason": "video_artifact_generation_failed", "record_id": asset.payload.get("source_video_record_id") or candidate.source_record_id, "error": str(exc)})

    if parse_motion_rows:
        if motion_table_paths is None:
            motion_table_paths = _default_motion_table_paths(artifact_dir)
        motion_records = _parse_motion_tables(
            motion_table_paths,
            artifact_dir=artifact_dir,
            retrieved_at=retrieved_at,
            gaps=gaps,
            asset_lookup=_build_motion_asset_lookup(records),
            table_contexts=_mendeley_motion_table_contexts(artifact_dir),
        )
    else:
        motion_records = []
    records.extend(motion_records)
    upstream_gaps = _load_upstream_manifest_gap_contexts(artifact_dir)
    if repository_scope:
        upstream_gaps = [gap for gap in upstream_gaps if gap.get("repository") in repository_scope]
    gaps.extend(upstream_gaps)
    records.extend(_sweep_record(receipt, retrieved_at=retrieved_at) for receipt in discovery_sweep_receipts)
    records.extend(_gap_record(gap, retrieved_at=retrieved_at, index=index) for index, gap in enumerate(gaps, start=1))
    return AedesVideoAtomsResult(
        source_id=VIDEO_ATOMS_SOURCE_ID,
        records=records,
        gaps=gaps,
        video_asset_count=sum(1 for record in records if record.payload and record.payload.get("atom_type") == "video_asset"),
        mirrored_video_count=mirrored_video_count,
        verified_video_count=verified_video_count,
        artifact_count=artifact_count,
        motion_row_count=len(motion_records),
        discovery_candidate_count=discovery_candidate_count,
        discovery_sweep_receipts=discovery_sweep_receipts,
    )
