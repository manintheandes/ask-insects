from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
import json
from pathlib import Path
import re
from typing import Callable
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


OSF_FLIGHTTRACKAI_SOURCE_ID = "osf_flighttrackai_aedes_videos"
OSF_API_BASE = "https://api.osf.io/v2"
OSF_PROJECT_ID = "cx762"
OSF_PROJECT_URL = "https://osf.io/cx762/"
USER_AGENT = "AskInsects/0.1 source-plane"
MEDIA_EXTENSIONS = (".mp4", ".mov", ".avi", ".webm", ".m4v")


@dataclass(frozen=True)
class OSFFlightTrackAIResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    project_id: str
    folder_count: int
    file_count: int
    media_file_count: int
    software_file_count: int


class OSFClient:
    def __init__(self, fetch_json: Callable[[str], dict[str, object]] | None = None):
        self.fetch_json = fetch_json or self._fetch_json

    def project(self, project_id: str) -> tuple[str, dict[str, object]]:
        url = f"{OSF_API_BASE}/nodes/{project_id}/"
        return url, self.fetch_json(url)

    def providers(self, project_id: str) -> tuple[str, dict[str, object]]:
        url = f"{OSF_API_BASE}/nodes/{project_id}/files/"
        return url, self.fetch_json(url)

    def osfstorage(self, project_id: str, folder_id: str | None = None) -> tuple[str, dict[str, object]]:
        suffix = f"osfstorage/{folder_id}/" if folder_id else "osfstorage/"
        url = f"{OSF_API_BASE}/nodes/{project_id}/files/{suffix}"
        return url, self.fetch_json(url)

    def linked(self, url: str) -> tuple[str, dict[str, object]]:
        return url, self.fetch_json(url)

    @staticmethod
    def _fetch_json(url: str) -> dict[str, object]:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"OSF endpoint returned non-object JSON for {url}")
        return payload


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_raw_json(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _clean_text(value: object) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower() or "osf"


def _data(payload: dict[str, object]) -> list[dict[str, object]]:
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _attrs(item: dict[str, object]) -> dict[str, object]:
    attrs = item.get("attributes")
    return attrs if isinstance(attrs, dict) else {}


def _relationships(item: dict[str, object]) -> dict[str, object]:
    rel = item.get("relationships")
    return rel if isinstance(rel, dict) else {}


def _links(item: dict[str, object]) -> dict[str, object]:
    links = item.get("links")
    return links if isinstance(links, dict) else {}


def _related_href(item: dict[str, object], relationship: str) -> str | None:
    rel = _relationships(item).get(relationship)
    if not isinstance(rel, dict):
        return None
    links = rel.get("links")
    if not isinstance(links, dict):
        return None
    related = links.get("related")
    if not isinstance(related, dict):
        return None
    href = related.get("href")
    return str(href) if href else None


def _next_href(payload: dict[str, object]) -> str | None:
    links = payload.get("links")
    if not isinstance(links, dict):
        return None
    href = links.get("next")
    return str(href) if href else None


def _is_media_file(name: str) -> bool:
    return name.lower().endswith(MEDIA_EXTENSIONS)


def _is_software_file(name: str) -> bool:
    lower = name.lower()
    return lower.endswith((".exe", ".bin", ".pt")) or "model" in lower or "instruction" in lower


def _license(project_payload: dict[str, object]) -> str:
    attrs = _attrs(project_payload.get("data", {}) if isinstance(project_payload.get("data"), dict) else {})
    license_payload = attrs.get("node_license")
    if isinstance(license_payload, dict):
        return str(license_payload.get("name") or license_payload.get("id") or "OSF license not supplied")
    return "OSF project license not supplied"


def _project_record(
    *,
    project_url: str,
    providers_url: str,
    project_payload: dict[str, object],
    raw_path: Path,
    folder_count: int,
    file_count: int,
    media_file_count: int,
    retrieved_at: str,
) -> EvidenceRecord:
    data = project_payload.get("data") if isinstance(project_payload.get("data"), dict) else {}
    attrs = _attrs(data)
    title = _clean_text(attrs.get("title")) or "FlightTrackAI Aedes aegypti OSF project"
    description = _clean_text(attrs.get("description"))
    text = (
        f"OSF project for Aedes aegypti FlightTrackAI behavior/video evidence: {title}. "
        f"File manifest: {folder_count} folder(s), {file_count} file(s), including {media_file_count} video file(s). "
        f"Description: {description[:900]}"
    )
    return EvidenceRecord(
        record_id=f"osf:flighttrackai:project:{OSF_PROJECT_ID}",
        lane="behavior",
        source=OSF_FLIGHTTRACKAI_SOURCE_ID,
        title=f"Aedes aegypti OSF FlightTrackAI project {title}",
        text=text,
        species="Aedes aegypti",
        url=OSF_PROJECT_URL,
        media_url=None,
        provenance=Provenance(
            source_id=OSF_FLIGHTTRACKAI_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#project",
            retrieved_at=retrieved_at,
            license=_license(project_payload),
            source_url=project_url,
        ),
        payload={
            "project_id": OSF_PROJECT_ID,
            "project_api_url": project_url,
            "providers_api_url": providers_url,
            "raw_project": project_payload,
        },
    )


def _folder_record(
    *,
    item: dict[str, object],
    raw_path: Path,
    folder_index: int,
    retrieved_at: str,
) -> EvidenceRecord:
    attrs = _attrs(item)
    folder_id = str(item.get("id") or attrs.get("path") or folder_index)
    name = str(attrs.get("name") or folder_id)
    materialized_path = str(attrs.get("materialized_path") or attrs.get("path") or name)
    return EvidenceRecord(
        record_id=f"osf:flighttrackai:folder:{_safe_id(folder_id)}",
        lane="behavior",
        source=OSF_FLIGHTTRACKAI_SOURCE_ID,
        title=f"Aedes aegypti OSF FlightTrackAI folder {materialized_path}",
        text=(
            "OSF folder in the FlightTrackAI Aedes aegypti behavior/video project. "
            f"Folder: {name}. Path: {materialized_path}."
        ),
        species="Aedes aegypti",
        url=OSF_PROJECT_URL,
        media_url=None,
        provenance=Provenance(
            source_id=OSF_FLIGHTTRACKAI_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#folders/{folder_index}",
            retrieved_at=retrieved_at,
            license="OSF project license not supplied",
            source_url=str(_links(item).get("self") or OSF_PROJECT_URL),
        ),
        payload={
            "project_id": OSF_PROJECT_ID,
            "folder_id": folder_id,
            "name": name,
            "materialized_path": materialized_path,
            "files_api_url": _related_href(item, "files"),
            "raw_folder": item,
        },
    )


def _file_record(
    *,
    item: dict[str, object],
    raw_path: Path,
    file_index: int,
    retrieved_at: str,
) -> EvidenceRecord:
    attrs = _attrs(item)
    file_id = str(item.get("id") or attrs.get("path") or file_index)
    name = str(attrs.get("name") or file_id)
    materialized_path = str(attrs.get("materialized_path") or attrs.get("path") or name)
    size = attrs.get("size")
    download_url = str(_links(item).get("download") or "")
    info_url = str(_links(item).get("info") or _links(item).get("self") or "")
    media = _is_media_file(name)
    software = _is_software_file(name)
    kind = "video file" if media else "software/model/instruction file" if software else "project file"
    text_parts = [
        f"OSF FlightTrackAI {kind} for Aedes aegypti flight-behavior tracking.",
        f"File: {name}.",
        f"Path: {materialized_path}.",
    ]
    if size is not None:
        text_parts.append(f"Size bytes: {size}.")
    if download_url:
        text_parts.append(f"Download URL: {download_url}.")
    return EvidenceRecord(
        record_id=f"osf:flighttrackai:file:{_safe_id(file_id)}",
        lane="media" if media else "behavior",
        source=OSF_FLIGHTTRACKAI_SOURCE_ID,
        title=f"Aedes aegypti OSF FlightTrackAI {kind} {name}",
        text=" ".join(text_parts),
        species="Aedes aegypti",
        url=OSF_PROJECT_URL,
        media_url=download_url if media else None,
        provenance=Provenance(
            source_id=OSF_FLIGHTTRACKAI_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#files/{file_index}",
            retrieved_at=retrieved_at,
            license="OSF project license not supplied",
            source_url=info_url or download_url or OSF_PROJECT_URL,
        ),
        payload={
            "project_id": OSF_PROJECT_ID,
            "file_id": file_id,
            "name": name,
            "materialized_path": materialized_path,
            "size": size,
            "download_url": download_url,
            "info_url": info_url,
            "is_media": media,
            "is_software": software,
            "raw_file": item,
        },
    )


def fetch_osf_flighttrackai_video_records(
    *,
    raw_dir: Path,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
) -> OSFFlightTrackAIResult:
    retrieved = retrieved_at or utc_now()
    client = OSFClient(fetch_json)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []

    try:
        project_url, project_payload = client.project(OSF_PROJECT_ID)
        project_raw_path = write_raw_json(raw_dir, f"{OSF_PROJECT_ID}_project.json", project_payload)
        raw_artifacts.append(project_raw_path.as_posix())
        providers_url, providers_payload = client.providers(OSF_PROJECT_ID)
        providers_raw_path = write_raw_json(raw_dir, f"{OSF_PROJECT_ID}_providers.json", providers_payload)
        raw_artifacts.append(providers_raw_path.as_posix())
    except Exception as exc:
        gaps.append(
            {
                "source": OSF_FLIGHTTRACKAI_SOURCE_ID,
                "lane": "media",
                "project_id": OSF_PROJECT_ID,
                "reason": "osf_project_fetch_failed",
                "error": str(exc),
                "retrieved_at": retrieved,
            }
        )
        return OSFFlightTrackAIResult(
            source_id=OSF_FLIGHTTRACKAI_SOURCE_ID,
            records=[],
            gaps=gaps,
            raw_artifacts=raw_artifacts,
            project_id=OSF_PROJECT_ID,
            folder_count=0,
            file_count=0,
            media_file_count=0,
            software_file_count=0,
        )

    folder_items: list[tuple[Path, int, dict[str, object]]] = []
    file_items: list[tuple[Path, int, dict[str, object]]] = []
    queue: list[tuple[str, str]] = [(f"{OSF_PROJECT_ID}_osfstorage_root.json", f"{OSF_API_BASE}/nodes/{OSF_PROJECT_ID}/files/osfstorage/")]
    seen_urls: set[str] = set()
    while queue:
        raw_name, url = queue.pop(0)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        try:
            current_url, payload = client.linked(url)
            raw_path = write_raw_json(raw_dir, raw_name, payload)
            raw_artifacts.append(raw_path.as_posix())
        except Exception as exc:
            gaps.append(
                {
                    "source": OSF_FLIGHTTRACKAI_SOURCE_ID,
                    "lane": "media",
                    "project_id": OSF_PROJECT_ID,
                    "url": url,
                    "reason": "osf_file_manifest_fetch_failed",
                    "error": str(exc),
                    "retrieved_at": retrieved,
                }
            )
            continue
        for item_index, item in enumerate(_data(payload), start=1):
            attrs = _attrs(item)
            if attrs.get("kind") == "folder":
                folder_items.append((raw_path, len(folder_items) + 1, item))
                href = _related_href(item, "files")
                if href:
                    queue.append((f"{OSF_PROJECT_ID}_folder_{_safe_id(str(item.get('id') or item_index))}.json", href))
            elif attrs.get("kind") == "file":
                file_items.append((raw_path, len(file_items) + 1, item))
        next_url = _next_href(payload)
        if next_url:
            queue.append((f"{raw_name.removesuffix('.json')}_next_{len(seen_urls)}.json", next_url))

    media_file_count = sum(1 for _, _, item in file_items if _is_media_file(str(_attrs(item).get("name") or "")))
    software_file_count = sum(1 for _, _, item in file_items if _is_software_file(str(_attrs(item).get("name") or "")))
    records.append(
        _project_record(
            project_url=project_url,
            providers_url=providers_url,
            project_payload=project_payload,
            raw_path=project_raw_path,
            folder_count=len(folder_items),
            file_count=len(file_items),
            media_file_count=media_file_count,
            retrieved_at=retrieved,
        )
    )
    records.extend(
        _folder_record(item=item, raw_path=raw_path, folder_index=folder_index, retrieved_at=retrieved)
        for raw_path, folder_index, item in folder_items
    )
    records.extend(
        _file_record(item=item, raw_path=raw_path, file_index=file_index, retrieved_at=retrieved)
        for raw_path, file_index, item in file_items
    )
    return OSFFlightTrackAIResult(
        source_id=OSF_FLIGHTTRACKAI_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        project_id=OSF_PROJECT_ID,
        folder_count=len(folder_items),
        file_count=len(file_items),
        media_file_count=media_file_count,
        software_file_count=software_file_count,
    )
