from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
import hashlib
import json
from pathlib import Path
import re
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


ZENODO_AEDES_VIDEO_SOURCE_ID = "zenodo_aedes_videos"
ZENODO_API_BASE = "https://zenodo.org/api/records"
DEFAULT_ZENODO_SIZE = 25
USER_AGENT = "AskInsects/0.1 source-plane"
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".m4v", ".webm", ".mpg", ".mpeg")
AEDES_PATTERN = re.compile(r"\b(?:aedes|ae\.?|a\.)\s*aegypti\b", re.I)


@dataclass(frozen=True)
class ZenodoAedesVideoResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    query: str
    search_result_count: int
    material_record_count: int
    file_count: int
    media_file_count: int


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fetch_json(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Zenodo endpoint returned non-object JSON for {url}")
    return payload


def _write_raw_json(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _clean_text(value: object) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _safe_id(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value)).strip("_").lower() or "zenodo"


def _digest(*parts: object) -> str:
    return hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:12]


def _hits(payload: dict[str, object]) -> list[dict[str, object]]:
    hits = payload.get("hits")
    records = hits.get("hits") if isinstance(hits, dict) else []
    return [record for record in records if isinstance(record, dict)] if isinstance(records, list) else []


def _metadata(record: dict[str, object]) -> dict[str, object]:
    metadata = record.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _links(payload: dict[str, object]) -> dict[str, object]:
    links = payload.get("links")
    return links if isinstance(links, dict) else {}


def _files(record: dict[str, object]) -> list[dict[str, object]]:
    files = record.get("files")
    return [file_payload for file_payload in files if isinstance(file_payload, dict)] if isinstance(files, list) else []


def _license(metadata: dict[str, object]) -> str:
    license_payload = metadata.get("license")
    if isinstance(license_payload, dict):
        return str(license_payload.get("id") or license_payload.get("title") or "Zenodo license not supplied")
    return str(license_payload or "Zenodo license not supplied")


def _material_text(record: dict[str, object]) -> str:
    metadata = _metadata(record)
    keywords = metadata.get("keywords")
    keyword_text = " ".join(str(keyword) for keyword in keywords) if isinstance(keywords, list) else ""
    return " ".join(
        [
            _clean_text(metadata.get("title")),
            _clean_text(metadata.get("description")),
            keyword_text,
            _clean_text(metadata.get("notes")),
        ]
    )


def _has_aedes_scope(record: dict[str, object]) -> bool:
    return bool(AEDES_PATTERN.search(_material_text(record)))


def _is_video_file(file_payload: dict[str, object]) -> bool:
    filename = str(file_payload.get("key") or file_payload.get("filename") or "")
    content_type = str(file_payload.get("type") or file_payload.get("mimetype") or "")
    lower = filename.lower()
    return lower.endswith(VIDEO_EXTENSIONS) or content_type.lower().startswith("video/")


def _download_url(file_payload: dict[str, object]) -> str | None:
    links = _links(file_payload)
    value = links.get("self") or links.get("download")
    return str(value) if value else None


def _source_hashes(file_payload: dict[str, object]) -> dict[str, str]:
    checksum = file_payload.get("checksum")
    if isinstance(checksum, str) and ":" in checksum:
        key, value = checksum.split(":", 1)
        return {key: value}
    if isinstance(checksum, str) and checksum:
        return {"checksum": checksum}
    return {}


def _source_url(record: dict[str, object]) -> str | None:
    links = _links(record)
    value = links.get("html") or record.get("doi_url")
    return str(value) if value else None


def _media_record(
    *,
    record: dict[str, object],
    file_payload: dict[str, object],
    raw_path: Path,
    hit_index: int,
    file_index: int,
    retrieved_at: str,
) -> EvidenceRecord:
    metadata = _metadata(record)
    zenodo_id = str(record.get("id") or _digest(metadata.get("title"), file_payload.get("key")))
    filename = str(file_payload.get("key") or file_payload.get("filename") or f"file-{file_index}")
    title = _clean_text(metadata.get("title")) or f"Zenodo Aedes aegypti video record {zenodo_id}"
    description = _clean_text(metadata.get("description"))
    download_url = _download_url(file_payload)
    size = file_payload.get("size")
    hashes = _source_hashes(file_payload)
    payload = {
        "zenodo_record_id": zenodo_id,
        "filename": filename,
        "source_byte_size": size,
        "source_hashes": hashes,
        "download_url": download_url,
        "source_url": _source_url(record),
        "raw_record": record,
        "raw_file": file_payload,
    }
    payload = {key: value for key, value in payload.items() if value not in (None, "", {})}
    text = f"Zenodo Aedes aegypti video file {filename} from {title}."
    if description:
        text += f" Description: {description[:700]}"
    return EvidenceRecord(
        record_id=f"zenodo:aedes-video:{_safe_id(zenodo_id)}:{_safe_id(filename)}",
        lane="media",
        source=ZENODO_AEDES_VIDEO_SOURCE_ID,
        title=f"Aedes aegypti Zenodo video file {filename}",
        text=text,
        species="Aedes aegypti",
        url=_source_url(record),
        media_url=download_url,
        provenance=Provenance(
            source_id=ZENODO_AEDES_VIDEO_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#hits/{hit_index}/files/{file_index}",
            retrieved_at=retrieved_at,
            license=_license(metadata),
            source_url=download_url or _source_url(record),
        ),
        payload=payload,
    )


def _gap_record(gap: dict[str, object], *, retrieved_at: str, index: int) -> EvidenceRecord:
    reason = str(gap.get("reason") or "zenodo_video_gap")
    source_record_id = str(gap.get("record_id") or gap.get("source_url") or f"gap-{index}")
    source_url = gap.get("source_url") or gap.get("url")
    url = str(source_url) if isinstance(source_url, str) and source_url else None
    locator = str(gap.get("locator") or f"gaps.json#{ZENODO_AEDES_VIDEO_SOURCE_ID}/{index}")
    title = f"Aedes aegypti Zenodo video gap {reason}"
    text = f"Zenodo Aedes aegypti video source gap: {reason}. Source record: {source_record_id}."
    if gap.get("query"):
        text += f" Query: {gap.get('query')}."
    if url:
        text += f" Source URL: {url}."
    if gap.get("error"):
        text += f" Error: {gap.get('error')}."
    return EvidenceRecord(
        record_id=f"zenodo:aedes-video-gap:{_safe_id(source_record_id)}:{_digest(reason, source_record_id, locator, index)}",
        lane="media",
        source=ZENODO_AEDES_VIDEO_SOURCE_ID,
        title=title,
        text=text,
        species="Aedes aegypti",
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=ZENODO_AEDES_VIDEO_SOURCE_ID,
            locator=locator,
            retrieved_at=retrieved_at,
            source_url=url,
        ),
        payload={"atom_type": "video_gap", "gap_type": "zenodo_manifest_gap", **gap},
    )


def fetch_zenodo_aedes_video_records(
    *,
    raw_dir: Path,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
    query: str = '"Aedes aegypti" (video OR movie OR mp4 OR tracking)',
    size: int = DEFAULT_ZENODO_SIZE,
) -> ZenodoAedesVideoResult:
    retrieved = retrieved_at or utc_now()
    if size < 1 or size > 100:
        raise ValueError("size must be between 1 and 100")
    fetcher = fetch_json or _fetch_json
    url = f"{ZENODO_API_BASE}?{urlencode({'q': query, 'size': size})}"
    gaps: list[dict[str, object]] = []
    records: list[EvidenceRecord] = []
    raw_artifacts: list[str] = []
    try:
        payload = fetcher(url)
    except Exception as exc:
        gap = {"source": ZENODO_AEDES_VIDEO_SOURCE_ID, "reason": "zenodo_search_fetch_failed", "query": query, "url": url, "error": str(exc)}
        return ZenodoAedesVideoResult(
            source_id=ZENODO_AEDES_VIDEO_SOURCE_ID,
            records=[_gap_record(gap, retrieved_at=retrieved, index=1)],
            gaps=[gap],
            raw_artifacts=[],
            query=query,
            search_result_count=0,
            material_record_count=0,
            file_count=0,
            media_file_count=0,
        )
    raw_path = _write_raw_json(raw_dir, f"search_{_digest(query, size)}.json", payload)
    raw_artifacts.append(raw_path.as_posix())
    hits = _hits(payload)
    if not hits:
        gaps.append({"source": ZENODO_AEDES_VIDEO_SOURCE_ID, "reason": "zenodo_video_search_no_candidates", "query": query, "url": url, "retrieved_at": retrieved})
    material_count = 0
    file_count = 0
    media_count = 0
    for hit_index, record in enumerate(hits, start=1):
        if not _has_aedes_scope(record):
            gaps.append(
                {
                    "source": ZENODO_AEDES_VIDEO_SOURCE_ID,
                    "reason": "zenodo_record_not_aedes_scope",
                    "query": query,
                    "record_id": record.get("id"),
                    "source_url": _source_url(record),
                    "locator": f"{raw_path.as_posix()}#hits/{hit_index}",
                }
            )
            continue
        material_count += 1
        video_found = False
        for file_index, file_payload in enumerate(_files(record), start=1):
            file_count += 1
            if not _is_video_file(file_payload):
                continue
            media_count += 1
            video_found = True
            records.append(
                _media_record(
                    record=record,
                    file_payload=file_payload,
                    raw_path=raw_path,
                    hit_index=hit_index,
                    file_index=file_index,
                    retrieved_at=retrieved,
                )
            )
        if not video_found:
            gaps.append(
                {
                    "source": ZENODO_AEDES_VIDEO_SOURCE_ID,
                    "reason": "zenodo_material_record_no_video_files",
                    "query": query,
                    "record_id": record.get("id"),
                    "source_url": _source_url(record),
                    "locator": f"{raw_path.as_posix()}#hits/{hit_index}",
                }
            )
    records.extend(_gap_record(gap, retrieved_at=retrieved, index=index) for index, gap in enumerate(gaps, start=1))
    return ZenodoAedesVideoResult(
        source_id=ZENODO_AEDES_VIDEO_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        query=query,
        search_result_count=len(hits),
        material_record_count=material_count,
        file_count=file_count,
        media_file_count=media_count,
    )
