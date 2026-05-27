from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
import json
from pathlib import Path
import re
from typing import Callable
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


DRYAD_BEHAVIOR_VIDEO_SOURCE_ID = "dryad_aedes_behavior_videos"
DRYAD_API_BASE = "https://datadryad.org"
USER_AGENT = "AskInsects/0.1 source-plane"
MEDIA_EXTENSIONS = (".zip", ".mp4", ".mov", ".avi", ".webm", ".m4v")


@dataclass(frozen=True)
class DryadDatasetSpec:
    doi: str
    behavior_labels: tuple[str, ...]


DEFAULT_DRYAD_DATASETS = (
    DryadDatasetSpec(
        doi="10.5061/dryad.547d7wmh3",
        behavior_labels=("host seeking", "thermal infrared", "human odor", "CO2", "navigation"),
    ),
    DryadDatasetSpec(
        doi="10.5061/dryad.j6q573nr3",
        behavior_labels=("host seeking", "visual threat avoidance", "shadow response", "escape"),
    ),
    DryadDatasetSpec(
        doi="10.5061/dryad.ttdz08m09",
        behavior_labels=("flight", "looming threat escape", "light condition", "evasive maneuver"),
    ),
    DryadDatasetSpec(
        doi="10.5061/dryad.qz612jmrb",
        behavior_labels=("mating", "courtship", "hearing", "wingbeat", "flight"),
    ),
    DryadDatasetSpec(
        doi="10.5061/dryad.tb2rbp04x",
        behavior_labels=("male host attraction", "female host attraction", "landing", "human preference", "repellent response"),
    ),
    DryadDatasetSpec(
        doi="10.5061/dryad.z8w9ghxfv",
        behavior_labels=("tethered flight", "visual tracking", "CO2", "blood feeding", "oviposition state"),
    ),
)


@dataclass(frozen=True)
class DryadBehaviorVideoResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_dois: list[str]
    dataset_count: int
    file_count: int
    media_file_count: int


class DryadClient:
    def __init__(self, fetch_json: Callable[[str], dict[str, object]] | None = None):
        self.fetch_json = fetch_json or self._fetch_json

    def dataset(self, doi: str) -> tuple[str, dict[str, object]]:
        url = f"{DRYAD_API_BASE}/api/v2/datasets/{quote(f'doi:{doi}', safe='')}"
        return url, self.fetch_json(url)

    def linked(self, href: str) -> tuple[str, dict[str, object]]:
        url = urljoin(DRYAD_API_BASE, href)
        return url, self.fetch_json(url)

    @staticmethod
    def _fetch_json(url: str) -> dict[str, object]:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Dryad endpoint returned non-object JSON for {url}")
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
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower() or "dryad"


def _link(payload: dict[str, object], rel: str) -> str | None:
    links = payload.get("_links")
    if not isinstance(links, dict):
        return None
    link = links.get(rel)
    if not isinstance(link, dict):
        return None
    href = link.get("href")
    return str(href) if href else None


def _file_rows(files_payload: dict[str, object]) -> list[dict[str, object]]:
    embedded = files_payload.get("_embedded")
    if not isinstance(embedded, dict):
        return []
    files = embedded.get("stash:files")
    if not isinstance(files, list):
        return []
    return [item for item in files if isinstance(item, dict)]


def _is_media_file(path: str, mime_type: str) -> bool:
    lower = path.lower()
    return lower.endswith(MEDIA_EXTENSIONS) or "zip" in mime_type.lower() or mime_type.lower().startswith("video/")


def _authors(dataset_payload: dict[str, object]) -> str:
    authors = dataset_payload.get("authors")
    if not isinstance(authors, list):
        return ""
    names = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        name = " ".join(part for part in (author.get("firstName"), author.get("lastName")) if part)
        if name:
            names.append(name)
    return ", ".join(names[:8])


def _doi_from_identifier(dataset_payload: dict[str, object], fallback: str) -> str:
    identifier = str(dataset_payload.get("identifier") or "")
    if identifier.startswith("doi:"):
        return identifier.removeprefix("doi:")
    return fallback


def _dataset_web_url(doi: str) -> str:
    return f"{DRYAD_API_BASE}/dataset/{quote(f'doi:{doi}', safe='')}"


def _dataset_record(
    *,
    spec: DryadDatasetSpec,
    dataset_url: str,
    dataset_payload: dict[str, object],
    version_url: str,
    files_url: str,
    raw_path: Path,
    file_count: int,
    media_file_count: int,
    retrieved_at: str,
) -> EvidenceRecord:
    doi = _doi_from_identifier(dataset_payload, spec.doi)
    title = _clean_text(dataset_payload.get("title")) or f"Dryad Aedes aegypti behavior dataset {doi}"
    labels = ", ".join(spec.behavior_labels)
    authors = _authors(dataset_payload)
    abstract = _clean_text(dataset_payload.get("abstract"))
    text_parts = [
        f"Dryad dataset for Aedes aegypti behavior/video evidence: {title}.",
        f"Behavior labels: {labels}.",
        f"File manifest: {file_count} file(s), including {media_file_count} media/archive file(s).",
    ]
    if authors:
        text_parts.append(f"Authors: {authors}.")
    if abstract:
        text_parts.append(f"Abstract: {abstract[:700]}")
    return EvidenceRecord(
        record_id=f"dryad:dataset:{_safe_id(doi)}",
        lane="behavior",
        source=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
        title=f"Aedes aegypti Dryad behavior dataset {title}",
        text=" ".join(text_parts),
        species="Aedes aegypti",
        url=_dataset_web_url(doi),
        media_url=None,
        provenance=Provenance(
            source_id=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#dataset",
            retrieved_at=retrieved_at,
            license=str(dataset_payload.get("license") or "Dryad dataset license not supplied"),
            source_url=dataset_url,
        ),
        payload={
            "doi": doi,
            "dataset_api_url": dataset_url,
            "version_api_url": version_url,
            "files_api_url": files_url,
            "behavior_labels": list(spec.behavior_labels),
            "raw_dataset": dataset_payload,
        },
    )


def _file_record(
    *,
    spec: DryadDatasetSpec,
    dataset_payload: dict[str, object],
    file_payload: dict[str, object],
    raw_path: Path,
    file_index: int,
    retrieved_at: str,
) -> EvidenceRecord:
    doi = _doi_from_identifier(dataset_payload, spec.doi)
    dataset_title = _clean_text(dataset_payload.get("title")) or doi
    file_path = str(file_payload.get("path") or f"file-{file_index}")
    mime_type = str(file_payload.get("mimeType") or "")
    media = _is_media_file(file_path, mime_type)
    download_href = _link(file_payload, "stash:download")
    download_url = urljoin(DRYAD_API_BASE, download_href) if download_href else _dataset_web_url(doi)
    size = file_payload.get("size")
    digest = file_payload.get("digest")
    digest_type = file_payload.get("digestType")
    labels = ", ".join(spec.behavior_labels)
    title_kind = "video/archive file" if media else "behavior data file"
    text_parts = [
        f"Dryad {title_kind} for Aedes aegypti behavior dataset {dataset_title}.",
        f"File path: {file_path}.",
        f"Behavior labels: {labels}.",
    ]
    if size is not None:
        text_parts.append(f"Size bytes: {size}.")
    if mime_type:
        text_parts.append(f"MIME type: {mime_type}.")
    if digest and digest_type:
        text_parts.append(f"Checksum: {digest_type} {digest}.")
    return EvidenceRecord(
        record_id=f"dryad:file:{_safe_id(doi)}:{_safe_id(file_path)}",
        lane="media" if media else "behavior",
        source=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
        title=f"Aedes aegypti Dryad {title_kind} {file_path}",
        text=" ".join(text_parts),
        species="Aedes aegypti",
        url=_dataset_web_url(doi),
        media_url=download_url if media else None,
        provenance=Provenance(
            source_id=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#file/{file_index}",
            retrieved_at=retrieved_at,
            license=str(dataset_payload.get("license") or "Dryad dataset license not supplied"),
            source_url=download_url,
        ),
        payload={
            "doi": doi,
            "dataset_title": dataset_title,
            "behavior_labels": list(spec.behavior_labels),
            "raw_file": file_payload,
            "download_url": download_url,
        },
    )


def _archive_decode_gap_record(
    *,
    spec: DryadDatasetSpec,
    dataset_payload: dict[str, object],
    file_payload: dict[str, object],
    raw_path: Path,
    file_index: int,
    retrieved_at: str,
) -> EvidenceRecord:
    doi = _doi_from_identifier(dataset_payload, spec.doi)
    dataset_title = _clean_text(dataset_payload.get("title")) or doi
    file_path = str(file_payload.get("path") or f"file-{file_index}")
    mime_type = str(file_payload.get("mimeType") or "")
    download_href = _link(file_payload, "stash:download")
    download_url = urljoin(DRYAD_API_BASE, download_href) if download_href else _dataset_web_url(doi)
    size = file_payload.get("size")
    digest = file_payload.get("digest")
    digest_type = file_payload.get("digestType")
    labels = ", ".join(spec.behavior_labels)
    source_video_record_id = f"dryad:file:{_safe_id(doi)}:{_safe_id(file_path)}"
    text_parts = [
        "Aedes aegypti Dryad video source gap: dryad_archive_contents_not_decoded.",
        f"Source dataset: {dataset_title}.",
        f"Source file: {file_path}.",
        f"Behavior labels: {labels}.",
        "The downloadable file is manifest-indexed, but its archive contents are not yet expanded into per-video assets, keyframes, previews, frame manifests, or motion rows.",
    ]
    if size is not None:
        text_parts.append(f"Size bytes: {size}.")
    if mime_type:
        text_parts.append(f"MIME type: {mime_type}.")
    if digest and digest_type:
        text_parts.append(f"Checksum: {digest_type} {digest}.")
    return EvidenceRecord(
        record_id=f"dryad:gap:{_safe_id(doi)}:{_safe_id(file_path)}:archive_contents_not_decoded",
        lane="media",
        source=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
        title=f"Aedes aegypti Dryad video gap archive contents not decoded {file_path}",
        text=" ".join(text_parts),
        species="Aedes aegypti",
        url=_dataset_web_url(doi),
        media_url=None,
        provenance=Provenance(
            source_id=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#file/{file_index}/gap/archive_contents_not_decoded",
            retrieved_at=retrieved_at,
            license=str(dataset_payload.get("license") or "Dryad dataset license not supplied"),
            source_url=download_url,
        ),
        payload={
            "atom_type": "video_gap",
            "reason": "dryad_archive_contents_not_decoded",
            "repository": "dryad",
            "doi": doi,
            "dataset_title": dataset_title,
            "file_path": file_path,
            "mime_type": mime_type,
            "byte_size": size,
            "source_hash": digest,
            "source_hash_type": digest_type,
            "download_url": download_url,
            "source_video_record_id": source_video_record_id,
            "behavior_labels": list(spec.behavior_labels),
            "required_next_artifacts": [
                "archive_member_manifest",
                "per_video_asset_rows",
                "duration_fps_resolution_codec_probe_rows",
                "thumbnail_keyframe_preview_frame_manifest_rows",
                "source_table_or_motion_tracking_rows_when_available",
            ],
        },
    )


def fetch_dryad_behavior_video_records(
    dataset_specs: list[DryadDatasetSpec] | tuple[DryadDatasetSpec, ...] = DEFAULT_DRYAD_DATASETS,
    *,
    raw_dir: Path,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
) -> DryadBehaviorVideoResult:
    retrieved = retrieved_at or utc_now()
    client = DryadClient(fetch_json)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    file_count = 0
    media_file_count = 0

    for spec in dataset_specs:
        safe_doi = _safe_id(spec.doi)
        try:
            dataset_url, dataset_payload = client.dataset(spec.doi)
            dataset_raw_path = write_raw_json(raw_dir, f"{safe_doi}_dataset.json", dataset_payload)
            raw_artifacts.append(dataset_raw_path.as_posix())
            version_href = _link(dataset_payload, "stash:version")
            if not version_href:
                raise ValueError("Dryad dataset payload did not include a stash:version link")
            version_url, version_payload = client.linked(version_href)
            version_raw_path = write_raw_json(raw_dir, f"{safe_doi}_version.json", version_payload)
            raw_artifacts.append(version_raw_path.as_posix())
            files_href = _link(version_payload, "stash:files")
            if not files_href:
                raise ValueError("Dryad version payload did not include a stash:files link")
            files_url, files_payload = client.linked(files_href)
            files_raw_path = write_raw_json(raw_dir, f"{safe_doi}_files.json", files_payload)
            raw_artifacts.append(files_raw_path.as_posix())
            files = _file_rows(files_payload)
        except Exception as exc:
            gaps.append(
                {
                    "source": DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
                    "lane": "media",
                    "doi": spec.doi,
                    "reason": "dryad_dataset_fetch_failed",
                    "error": str(exc),
                    "retrieved_at": retrieved,
                }
            )
            continue

        dataset_media_count = sum(
            1 for row in files if _is_media_file(str(row.get("path") or ""), str(row.get("mimeType") or ""))
        )
        records.append(
            _dataset_record(
                spec=spec,
                dataset_url=dataset_url,
                dataset_payload=dataset_payload,
                version_url=version_url,
                files_url=files_url,
                raw_path=dataset_raw_path,
                file_count=len(files),
                media_file_count=dataset_media_count,
                retrieved_at=retrieved,
            )
        )
        if not files:
            gaps.append(
                {
                    "source": DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
                    "lane": "media",
                    "doi": spec.doi,
                    "reason": "dryad_file_manifest_empty",
                    "retrieved_at": retrieved,
                }
            )
        for index, file_payload in enumerate(files, start=1):
            file_count += 1
            is_media = _is_media_file(str(file_payload.get("path") or ""), str(file_payload.get("mimeType") or ""))
            if is_media:
                media_file_count += 1
            records.append(
                _file_record(
                    spec=spec,
                    dataset_payload=dataset_payload,
                    file_payload=file_payload,
                    raw_path=files_raw_path,
                    file_index=index,
                    retrieved_at=retrieved,
                )
            )
            if is_media:
                records.append(
                    _archive_decode_gap_record(
                        spec=spec,
                        dataset_payload=dataset_payload,
                        file_payload=file_payload,
                        raw_path=files_raw_path,
                        file_index=index,
                        retrieved_at=retrieved,
                    )
                )

    return DryadBehaviorVideoResult(
        source_id=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_dois=[spec.doi for spec in dataset_specs],
        dataset_count=len([record for record in records if record.record_id.startswith("dryad:dataset:")]),
        file_count=file_count,
        media_file_count=media_file_count,
    )
