from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
import json
from pathlib import Path
import re
from typing import Callable
from urllib.parse import quote
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID = "mendeley_aedes_behavior_media"
MENDELEY_DATA_BASE = "https://data.mendeley.com"
MENDELEY_PUBLIC_API_BASE = f"{MENDELEY_DATA_BASE}/public-api"
USER_AGENT = "AskInsects/0.1 source-plane"
MEDIA_EXTENSIONS = (
    ".7z",
    ".avi",
    ".m4a",
    ".m4v",
    ".mov",
    ".mp3",
    ".mp4",
    ".wav",
    ".webm",
    ".zip",
)


@dataclass(frozen=True)
class MendeleyDatasetSpec:
    dataset_id: str
    version: int
    behavior_labels: tuple[str, ...]


DEFAULT_MENDELEY_DATASETS = (
    MendeleyDatasetSpec(
        dataset_id="6gvs94p6r2",
        version=1,
        behavior_labels=("mating", "mate recognition", "wing flash", "wingbeat", "acoustic signal", "high-speed video"),
    ),
    MendeleyDatasetSpec(
        dataset_id="g79w8wxpr7",
        version=2,
        behavior_labels=("hearing", "flight tones", "mate recognition", "wingbeat", "auditory system"),
    ),
    MendeleyDatasetSpec(
        dataset_id="sg5rrvdzvg",
        version=1,
        behavior_labels=("locomotory behavior", "temperature regime", "video analysis", "flight", "thermal response"),
    ),
)


@dataclass(frozen=True)
class MendeleyBehaviorMediaResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_datasets: list[str]
    dataset_count: int
    folder_count: int
    file_count: int
    media_file_count: int


class MendeleyClient:
    def __init__(self, fetch_json: Callable[[str], object] | None = None):
        self.fetch_json = fetch_json or self._fetch_json

    def snapshot(self, dataset_id: str, version: int) -> tuple[str, dict[str, object]]:
        url = f"{MENDELEY_PUBLIC_API_BASE}/datasets/{quote(dataset_id)}/snapshot/{version}"
        payload = self.fetch_json(url)
        if not isinstance(payload, dict):
            raise ValueError(f"Mendeley snapshot returned non-object JSON for {url}")
        return url, payload

    def folders(self, dataset_id: str, version: int) -> tuple[str, list[dict[str, object]]]:
        url = f"{MENDELEY_PUBLIC_API_BASE}/datasets/{quote(dataset_id)}/folders/{version}"
        payload = self.fetch_json(url)
        if not isinstance(payload, list):
            raise ValueError(f"Mendeley folders returned non-list JSON for {url}")
        return url, [item for item in payload if isinstance(item, dict)]

    def files(self, dataset_id: str, version: int, folder_id: str) -> tuple[str, list[dict[str, object]]]:
        url = f"{MENDELEY_PUBLIC_API_BASE}/datasets/{quote(dataset_id)}/files?folder_id={quote(folder_id)}&version={version}"
        payload = self.fetch_json(url)
        if not isinstance(payload, list):
            raise ValueError(f"Mendeley files returned non-list JSON for {url}")
        return url, [item for item in payload if isinstance(item, dict)]

    @staticmethod
    def _fetch_json(url: str) -> object:
        request = Request(
            url,
            headers={
                "Accept": "application/vnd.mendeley-public-dataset.1+json",
                "User-Agent": USER_AGENT,
            },
        )
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_raw_json(raw_dir: Path, filename: str, payload: object) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _clean_text(value: object) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower() or "mendeley"


def _dataset_label(spec: MendeleyDatasetSpec) -> str:
    return f"{spec.dataset_id}:v{spec.version}"


def _dataset_web_url(snapshot: dict[str, object], spec: MendeleyDatasetSpec) -> str:
    dataset_id = str(snapshot.get("id") or spec.dataset_id)
    version = int(snapshot.get("version") or spec.version)
    return f"{MENDELEY_DATA_BASE}/datasets/{quote(dataset_id)}/{version}"


def _doi(snapshot: dict[str, object], spec: MendeleyDatasetSpec) -> str:
    doi = str(snapshot.get("doi") or "").strip()
    return doi or f"10.17632/{spec.dataset_id}.{spec.version}"


def _license(snapshot: dict[str, object]) -> str:
    licence = snapshot.get("licence")
    if isinstance(licence, dict):
        parts = [str(licence.get("short_name") or licence.get("full_name") or "").strip(), str(licence.get("url") or "").strip()]
        text = " ".join(part for part in parts if part)
        if text:
            return text
    license_value = snapshot.get("license")
    return str(license_value or "Mendeley Data license not supplied")


def _contributors(snapshot: dict[str, object]) -> str:
    contributors = snapshot.get("contributors")
    if not isinstance(contributors, list):
        return ""
    names = []
    for contributor in contributors:
        if not isinstance(contributor, dict):
            continue
        name = " ".join(part for part in (contributor.get("first_name"), contributor.get("last_name")) if part)
        if name:
            names.append(name)
    return ", ".join(names[:8])


def _category_labels(snapshot: dict[str, object]) -> list[str]:
    categories = snapshot.get("categories")
    if not isinstance(categories, list):
        return []
    labels = []
    for category in categories:
        if isinstance(category, dict) and category.get("label"):
            labels.append(str(category["label"]))
    return labels


def _folder_path(folder: dict[str, object], folder_by_id: dict[str, dict[str, object]]) -> str:
    names = []
    seen: set[str] = set()
    current: dict[str, object] | None = folder
    while current:
        folder_id = str(current.get("id") or "")
        if folder_id in seen:
            break
        seen.add(folder_id)
        name = str(current.get("name") or folder_id or "folder")
        if name:
            names.append(name)
        parent_id = current.get("parent_id")
        current = folder_by_id.get(str(parent_id)) if parent_id else None
    return "/".join(reversed(names))


def _file_folder_path(file_payload: dict[str, object], folder_paths: dict[str, str]) -> str:
    folder_id = file_payload.get("folder_id")
    if folder_id and str(folder_id) in folder_paths:
        return folder_paths[str(folder_id)]
    return "root"


def _content_details(file_payload: dict[str, object]) -> dict[str, object]:
    details = file_payload.get("content_details")
    return details if isinstance(details, dict) else {}


def _is_media_file(filename: str, content_type: str) -> bool:
    lower = filename.lower()
    ctype = content_type.lower()
    return lower.endswith(MEDIA_EXTENSIONS) or ctype.startswith("video/") or ctype.startswith("audio/") or "zip" in ctype


def _dataset_record(
    *,
    spec: MendeleyDatasetSpec,
    snapshot_url: str,
    folders_url: str,
    snapshot: dict[str, object],
    raw_path: Path,
    folder_count: int,
    file_count: int,
    media_file_count: int,
    retrieved_at: str,
) -> EvidenceRecord:
    title = _clean_text(snapshot.get("name")) or f"Mendeley Aedes aegypti behavior dataset {spec.dataset_id}"
    description = _clean_text(snapshot.get("description"))
    labels = ", ".join(spec.behavior_labels)
    contributors = _contributors(snapshot)
    categories = ", ".join(_category_labels(snapshot))
    text_parts = [
        f"Mendeley Data dataset for Aedes aegypti behavior/media evidence: {title}.",
        f"Behavior labels: {labels}.",
        f"Manifest: {folder_count} folder(s), {file_count} file(s), including {media_file_count} video/audio/archive file(s).",
    ]
    if contributors:
        text_parts.append(f"Contributors: {contributors}.")
    if categories:
        text_parts.append(f"Categories: {categories}.")
    if description:
        text_parts.append(f"Description: {description[:700]}")
    return EvidenceRecord(
        record_id=f"mendeley:dataset:{_safe_id(spec.dataset_id)}:v{spec.version}",
        lane="behavior",
        source=MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
        title=f"Aedes aegypti Mendeley behavior dataset {title}",
        text=" ".join(text_parts),
        species="Aedes aegypti",
        url=_dataset_web_url(snapshot, spec),
        media_url=None,
        provenance=Provenance(
            source_id=MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#snapshot",
            retrieved_at=retrieved_at,
            license=_license(snapshot),
            source_url=snapshot_url,
        ),
        payload={
            "dataset_id": spec.dataset_id,
            "version": spec.version,
            "doi": _doi(snapshot, spec),
            "snapshot_api_url": snapshot_url,
            "folders_api_url": folders_url,
            "behavior_labels": list(spec.behavior_labels),
            "raw_snapshot": snapshot,
        },
    )


def _folder_record(
    *,
    spec: MendeleyDatasetSpec,
    snapshot: dict[str, object],
    folder: dict[str, object],
    folder_path: str,
    raw_path: Path,
    folder_index: int,
    retrieved_at: str,
) -> EvidenceRecord:
    title = _clean_text(snapshot.get("name")) or _doi(snapshot, spec)
    folder_name = str(folder.get("name") or folder.get("id") or "folder")
    labels = ", ".join(spec.behavior_labels)
    return EvidenceRecord(
        record_id=f"mendeley:folder:{_safe_id(spec.dataset_id)}:v{spec.version}:{_safe_id(str(folder.get('id') or folder_index))}",
        lane="behavior",
        source=MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
        title=f"Aedes aegypti Mendeley dataset folder {folder_path}",
        text=(
            f"Mendeley Data folder for Aedes aegypti behavior/media dataset {title}. "
            f"Folder: {folder_name}. Path: {folder_path}. Behavior labels: {labels}."
        ),
        species="Aedes aegypti",
        url=_dataset_web_url(snapshot, spec),
        media_url=None,
        provenance=Provenance(
            source_id=MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#folders/{folder_index}",
            retrieved_at=retrieved_at,
            license=_license(snapshot),
            source_url=_dataset_web_url(snapshot, spec),
        ),
        payload={
            "dataset_id": spec.dataset_id,
            "version": spec.version,
            "doi": _doi(snapshot, spec),
            "folder_id": folder.get("id"),
            "folder_path": folder_path,
            "parent_id": folder.get("parent_id"),
            "behavior_labels": list(spec.behavior_labels),
            "raw_folder": folder,
        },
    )


def _file_record(
    *,
    spec: MendeleyDatasetSpec,
    snapshot: dict[str, object],
    file_payload: dict[str, object],
    folder_path: str,
    raw_path: Path,
    folder_id: str,
    file_index: int,
    retrieved_at: str,
) -> EvidenceRecord:
    dataset_title = _clean_text(snapshot.get("name")) or _doi(snapshot, spec)
    filename = str(file_payload.get("filename") or f"file-{file_index}")
    details = _content_details(file_payload)
    content_type = str(details.get("content_type") or "")
    media = _is_media_file(filename, content_type)
    download_url = str(details.get("download_url") or "")
    view_url = str(details.get("view_url") or "")
    source_url = download_url or view_url or _dataset_web_url(snapshot, spec)
    size = details.get("size") if details.get("size") is not None else file_payload.get("size")
    sha256_hash = str(details.get("sha256_hash") or "")
    labels = ", ".join(spec.behavior_labels)
    title_kind = "video/audio/archive file" if media else "behavior data file"
    text_parts = [
        f"Mendeley {title_kind} for Aedes aegypti behavior/media dataset {dataset_title}.",
        f"File: {filename}.",
        f"Folder path: {folder_path}.",
        f"Behavior labels: {labels}.",
    ]
    if size is not None:
        text_parts.append(f"Size bytes: {size}.")
    if content_type:
        text_parts.append(f"Content type: {content_type}.")
    if sha256_hash:
        text_parts.append(f"SHA-256: {sha256_hash}.")
    return EvidenceRecord(
        record_id=f"mendeley:file:{_safe_id(spec.dataset_id)}:v{spec.version}:{_safe_id(str(file_payload.get('id') or filename))}",
        lane="media" if media else "behavior",
        source=MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
        title=f"Aedes aegypti Mendeley {title_kind} {filename}",
        text=" ".join(text_parts),
        species="Aedes aegypti",
        url=_dataset_web_url(snapshot, spec),
        media_url=download_url if media and download_url else None,
        provenance=Provenance(
            source_id=MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#files/{folder_id}/{file_index}",
            retrieved_at=retrieved_at,
            license=_license(snapshot),
            source_url=source_url,
        ),
        payload={
            "dataset_id": spec.dataset_id,
            "version": spec.version,
            "doi": _doi(snapshot, spec),
            "dataset_title": dataset_title,
            "file_id": file_payload.get("id"),
            "filename": filename,
            "folder_id": file_payload.get("folder_id"),
            "folder_path": folder_path,
            "content_type": content_type,
            "size": size,
            "sha256_hash": sha256_hash,
            "download_url": download_url,
            "view_url": view_url,
            "behavior_labels": list(spec.behavior_labels),
            "raw_file": file_payload,
        },
    )


def fetch_mendeley_behavior_media_records(
    dataset_specs: list[MendeleyDatasetSpec] | tuple[MendeleyDatasetSpec, ...] = DEFAULT_MENDELEY_DATASETS,
    *,
    raw_dir: Path,
    fetch_json: Callable[[str], object] | None = None,
    retrieved_at: str | None = None,
) -> MendeleyBehaviorMediaResult:
    retrieved = retrieved_at or utc_now()
    client = MendeleyClient(fetch_json)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    total_folders = 0
    total_files = 0
    total_media_files = 0

    for spec in dataset_specs:
        safe_dataset = f"{_safe_id(spec.dataset_id)}_v{spec.version}"
        try:
            snapshot_url, snapshot = client.snapshot(spec.dataset_id, spec.version)
            snapshot_raw_path = write_raw_json(raw_dir, f"{safe_dataset}_snapshot.json", snapshot)
            raw_artifacts.append(snapshot_raw_path.as_posix())
            folders_url, folders = client.folders(spec.dataset_id, spec.version)
            folders_raw_path = write_raw_json(raw_dir, f"{safe_dataset}_folders.json", folders)
            raw_artifacts.append(folders_raw_path.as_posix())
        except Exception as exc:
            gaps.append(
                {
                    "source": MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
                    "lane": "behavior",
                    "dataset_id": spec.dataset_id,
                    "version": spec.version,
                    "reason": "mendeley_dataset_fetch_failed",
                    "error": str(exc),
                    "retrieved_at": retrieved,
                }
            )
            continue

        folder_by_id = {str(folder.get("id")): folder for folder in folders if folder.get("id")}
        folder_paths = {folder_id: _folder_path(folder, folder_by_id) for folder_id, folder in folder_by_id.items()}
        files_payloads: list[dict[str, object]] = []
        for folder_id in ("root", *folder_by_id):
            try:
                files_url, files = client.files(spec.dataset_id, spec.version, folder_id)
            except Exception as exc:
                gaps.append(
                    {
                        "source": MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
                        "lane": "media",
                        "dataset_id": spec.dataset_id,
                        "version": spec.version,
                        "folder_id": folder_id,
                        "reason": "mendeley_file_manifest_fetch_failed",
                        "error": str(exc),
                        "retrieved_at": retrieved,
                    }
                )
                files = []
                files_url = f"{MENDELEY_PUBLIC_API_BASE}/datasets/{spec.dataset_id}/files?folder_id={folder_id}&version={spec.version}"
            files_payloads.append({"folder_id": folder_id, "url": files_url, "files": files})

        files_raw_path = write_raw_json(raw_dir, f"{safe_dataset}_files.json", files_payloads)
        raw_artifacts.append(files_raw_path.as_posix())
        files_flat = [
            (str(item["folder_id"]), index, file_payload)
            for item in files_payloads
            for index, file_payload in enumerate(item["files"], start=1)
            if isinstance(file_payload, dict)
        ]
        media_file_count = sum(
            1
            for _, _, file_payload in files_flat
            if _is_media_file(str(file_payload.get("filename") or ""), str(_content_details(file_payload).get("content_type") or ""))
        )
        total_folders += len(folders)
        total_files += len(files_flat)
        total_media_files += media_file_count
        records.append(
            _dataset_record(
                spec=spec,
                snapshot_url=snapshot_url,
                folders_url=folders_url,
                snapshot=snapshot,
                raw_path=snapshot_raw_path,
                folder_count=len(folders),
                file_count=len(files_flat),
                media_file_count=media_file_count,
                retrieved_at=retrieved,
            )
        )
        for index, folder in enumerate(folders, start=1):
            folder_id = str(folder.get("id") or index)
            records.append(
                _folder_record(
                    spec=spec,
                    snapshot=snapshot,
                    folder=folder,
                    folder_path=folder_paths.get(folder_id, str(folder.get("name") or folder_id)),
                    raw_path=folders_raw_path,
                    folder_index=index,
                    retrieved_at=retrieved,
                )
            )
        for folder_id, file_index, file_payload in files_flat:
            records.append(
                _file_record(
                    spec=spec,
                    snapshot=snapshot,
                    file_payload=file_payload,
                    folder_path=_file_folder_path(file_payload, folder_paths) if folder_id == "root" else folder_paths.get(folder_id, folder_id),
                    raw_path=files_raw_path,
                    folder_id=folder_id,
                    file_index=file_index,
                    retrieved_at=retrieved,
                )
            )

    return MendeleyBehaviorMediaResult(
        source_id=MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_datasets=[_dataset_label(spec) for spec in dataset_specs],
        dataset_count=len([record for record in records if record.record_id.startswith("mendeley:dataset:")]),
        folder_count=total_folders,
        file_count=total_files,
        media_file_count=total_media_files,
    )
