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


FIGSHARE_AEDES_VIDEO_SOURCE_ID = "figshare_aedes_videos"
FIGSHARE_API_BASE = "https://api.figshare.com/v2"
DEFAULT_FIGSHARE_PAGE_SIZE = 100
USER_AGENT = "AskInsects/0.1 source-plane"
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".m4v", ".webm", ".mpg", ".mpeg")
AEDES_PATTERN = re.compile(r"\b(?:aedes|ae\.?|a\.)\s*aegypti\b", re.I)


@dataclass(frozen=True)
class FigshareAedesVideoResult:
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


def _fetch_json(url: str) -> object:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _write_raw_json(raw_dir: Path, filename: str, payload: object) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _clean_text(value: object) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _safe_id(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value)).strip("_").lower() or "figshare"


def _digest(*parts: object) -> str:
    return hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:12]


def _search_rows(payload: object) -> list[dict[str, object]]:
    return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []


def _files(article: dict[str, object]) -> list[dict[str, object]]:
    files = article.get("files")
    return [file_payload for file_payload in files if isinstance(file_payload, dict)] if isinstance(files, list) else []


def _license(article: dict[str, object]) -> str:
    license_payload = article.get("license")
    if isinstance(license_payload, dict):
        return str(license_payload.get("name") or license_payload.get("url") or "Figshare license not supplied")
    return str(license_payload or "Figshare license not supplied")


def _tag_text(article: dict[str, object]) -> str:
    tags = article.get("tags")
    if isinstance(tags, list):
        return " ".join(str(tag) for tag in tags)
    categories = article.get("categories")
    if isinstance(categories, list):
        names = []
        for category in categories:
            if isinstance(category, dict):
                names.append(str(category.get("title") or category.get("name") or ""))
            else:
                names.append(str(category))
        return " ".join(names)
    return ""


def _material_text(article: dict[str, object]) -> str:
    return " ".join(
        [
            _clean_text(article.get("title")),
            _clean_text(article.get("description")),
            _tag_text(article),
            _clean_text(article.get("doi")),
        ]
    )


def _has_aedes_scope(article: dict[str, object]) -> bool:
    return bool(AEDES_PATTERN.search(_material_text(article)))


def _is_video_file(file_payload: dict[str, object]) -> bool:
    filename = str(file_payload.get("name") or file_payload.get("filename") or "")
    content_type = str(file_payload.get("mimetype") or file_payload.get("mime_type") or "")
    lower = filename.lower()
    return lower.endswith(VIDEO_EXTENSIONS) or content_type.lower().startswith("video/")


def _source_url(article: dict[str, object]) -> str | None:
    for key in ("url_public_html", "figshare_url", "url"):
        value = article.get(key)
        if isinstance(value, str) and value:
            return value
    article_id = article.get("id")
    return f"https://figshare.com/articles/{article_id}" if article_id else None


def _download_url(file_payload: dict[str, object]) -> str | None:
    value = file_payload.get("download_url") or file_payload.get("downloadUrl")
    return str(value) if value else None


def _source_hashes(file_payload: dict[str, object]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for key in ("computed_md5", "md5", "sha256", "checksum"):
        value = file_payload.get(key)
        if isinstance(value, str) and value.strip():
            hash_key = "md5" if key == "computed_md5" else key
            hashes[hash_key] = value.strip()
    return hashes


def _media_record(
    *,
    article: dict[str, object],
    file_payload: dict[str, object],
    raw_path: Path,
    file_index: int,
    retrieved_at: str,
) -> EvidenceRecord:
    article_id = str(article.get("id") or _digest(article.get("title"), file_payload.get("name")))
    filename = str(file_payload.get("name") or file_payload.get("filename") or f"file-{file_index}")
    title = _clean_text(article.get("title")) or f"Figshare Aedes aegypti video article {article_id}"
    description = _clean_text(article.get("description"))
    download_url = _download_url(file_payload)
    payload = {
        "figshare_article_id": article_id,
        "figshare_file_id": file_payload.get("id"),
        "filename": filename,
        "doi": article.get("doi"),
        "source_byte_size": file_payload.get("size"),
        "source_hashes": _source_hashes(file_payload),
        "download_url": download_url,
        "source_url": _source_url(article),
        "raw_article": article,
        "raw_file": file_payload,
    }
    payload = {key: value for key, value in payload.items() if value not in (None, "", {})}
    text = f"Figshare Aedes aegypti video file {filename} from {title}."
    if description:
        text += f" Description: {description[:700]}"
    return EvidenceRecord(
        record_id=f"figshare:aedes-video:{_safe_id(article_id)}:{_safe_id(filename)}",
        lane="media",
        source=FIGSHARE_AEDES_VIDEO_SOURCE_ID,
        title=f"Aedes aegypti Figshare video file {filename}",
        text=text,
        species="Aedes aegypti",
        url=_source_url(article),
        media_url=download_url,
        provenance=Provenance(
            source_id=FIGSHARE_AEDES_VIDEO_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#files/{file_index}",
            retrieved_at=retrieved_at,
            license=_license(article),
            source_url=download_url or _source_url(article),
        ),
        payload=payload,
    )


def _gap_record(gap: dict[str, object], *, retrieved_at: str, index: int) -> EvidenceRecord:
    reason = str(gap.get("reason") or "figshare_video_gap")
    source_record_id = str(gap.get("article_id") or gap.get("file_id") or gap.get("source_url") or f"gap-{index}")
    source_url = gap.get("source_url") or gap.get("url")
    url = str(source_url) if isinstance(source_url, str) and source_url else None
    locator = str(gap.get("locator") or f"gaps.json#{FIGSHARE_AEDES_VIDEO_SOURCE_ID}/{index}")
    title = f"Aedes aegypti Figshare video gap {reason}"
    text = f"Figshare Aedes aegypti video source gap: {reason}. Source record: {source_record_id}."
    if gap.get("query"):
        text += f" Query: {gap.get('query')}."
    if url:
        text += f" Source URL: {url}."
    if gap.get("error"):
        text += f" Error: {gap.get('error')}."
    return EvidenceRecord(
        record_id=f"figshare:aedes-video-gap:{_safe_id(source_record_id)}:{_digest(reason, source_record_id, locator, index)}",
        lane="media",
        source=FIGSHARE_AEDES_VIDEO_SOURCE_ID,
        title=title,
        text=text,
        species="Aedes aegypti",
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=FIGSHARE_AEDES_VIDEO_SOURCE_ID,
            locator=locator,
            retrieved_at=retrieved_at,
            source_url=url,
        ),
        payload={"atom_type": "video_gap", "gap_type": "figshare_manifest_gap", **gap},
    )


def fetch_figshare_aedes_video_records(
    *,
    raw_dir: Path,
    fetch_json: Callable[[str], object] | None = None,
    retrieved_at: str | None = None,
    query: str = "Aedes aegypti video",
    page_size: int = DEFAULT_FIGSHARE_PAGE_SIZE,
) -> FigshareAedesVideoResult:
    retrieved = retrieved_at or utc_now()
    if page_size < 1 or page_size > 100:
        raise ValueError("page_size must be between 1 and 100")
    fetcher = fetch_json or _fetch_json
    search_url = f"{FIGSHARE_API_BASE}/articles?{urlencode({'search_for': query, 'page_size': page_size})}"
    gaps: list[dict[str, object]] = []
    records: list[EvidenceRecord] = []
    raw_artifacts: list[str] = []
    try:
        search_payload = fetcher(search_url)
    except Exception as exc:
        gap = {"source": FIGSHARE_AEDES_VIDEO_SOURCE_ID, "reason": "figshare_search_fetch_failed", "query": query, "url": search_url, "error": str(exc)}
        return FigshareAedesVideoResult(
            source_id=FIGSHARE_AEDES_VIDEO_SOURCE_ID,
            records=[_gap_record(gap, retrieved_at=retrieved, index=1)],
            gaps=[gap],
            raw_artifacts=[],
            query=query,
            search_result_count=0,
            material_record_count=0,
            file_count=0,
            media_file_count=0,
        )
    search_path = _write_raw_json(raw_dir, f"search_{_digest(query, page_size)}.json", search_payload)
    raw_artifacts.append(search_path.as_posix())
    rows = _search_rows(search_payload)
    if not rows:
        gaps.append({"source": FIGSHARE_AEDES_VIDEO_SOURCE_ID, "reason": "figshare_video_search_no_candidates", "query": query, "url": search_url, "retrieved_at": retrieved})
    material_count = 0
    file_count = 0
    media_count = 0
    for row_index, row in enumerate(rows, start=1):
        article_id = row.get("id")
        if not article_id:
            gaps.append({"source": FIGSHARE_AEDES_VIDEO_SOURCE_ID, "reason": "figshare_search_result_missing_id", "query": query, "locator": f"{search_path.as_posix()}#rows/{row_index}"})
            continue
        detail_url = f"{FIGSHARE_API_BASE}/articles/{article_id}"
        try:
            article = fetcher(detail_url)
        except Exception as exc:
            gaps.append({"source": FIGSHARE_AEDES_VIDEO_SOURCE_ID, "reason": "figshare_article_fetch_failed", "query": query, "article_id": article_id, "url": detail_url, "error": str(exc), "locator": f"{search_path.as_posix()}#rows/{row_index}"})
            continue
        if not isinstance(article, dict):
            gaps.append({"source": FIGSHARE_AEDES_VIDEO_SOURCE_ID, "reason": "figshare_article_detail_not_object", "query": query, "article_id": article_id, "url": detail_url, "locator": f"{search_path.as_posix()}#rows/{row_index}"})
            continue
        detail_path = _write_raw_json(raw_dir, f"article_{_safe_id(article_id)}.json", article)
        raw_artifacts.append(detail_path.as_posix())
        if not _has_aedes_scope(article):
            gaps.append(
                {
                    "source": FIGSHARE_AEDES_VIDEO_SOURCE_ID,
                    "reason": "figshare_article_not_aedes_scope",
                    "query": query,
                    "article_id": article_id,
                    "source_url": _source_url(article),
                    "locator": f"{detail_path.as_posix()}#article",
                }
            )
            continue
        material_count += 1
        video_found = False
        for file_index, file_payload in enumerate(_files(article), start=1):
            file_count += 1
            if not _is_video_file(file_payload):
                continue
            media_count += 1
            video_found = True
            records.append(
                _media_record(
                    article=article,
                    file_payload=file_payload,
                    raw_path=detail_path,
                    file_index=file_index,
                    retrieved_at=retrieved,
                )
            )
        if not video_found:
            gaps.append(
                {
                    "source": FIGSHARE_AEDES_VIDEO_SOURCE_ID,
                    "reason": "figshare_material_article_no_video_files",
                    "query": query,
                    "article_id": article_id,
                    "source_url": _source_url(article),
                    "locator": f"{detail_path.as_posix()}#article",
                }
            )
    records.extend(_gap_record(gap, retrieved_at=retrieved, index=index) for index, gap in enumerate(gaps, start=1))
    return FigshareAedesVideoResult(
        source_id=FIGSHARE_AEDES_VIDEO_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        query=query,
        search_result_count=len(rows),
        material_record_count=material_count,
        file_count=file_count,
        media_file_count=media_count,
    )
