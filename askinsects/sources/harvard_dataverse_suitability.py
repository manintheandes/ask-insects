from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Callable
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID = "harvard_dataverse_aedes_suitability"
DATAVERSE_API_BASE = "https://dataverse.harvard.edu/api"
DEFAULT_QUERIES = (
    '"Aedes aegypti" suitability',
    '"Aedes aegypti" "dengue transmission"',
    '"Aedes aegypti" "transmission risk"',
)
USER_AGENT = "AskInsects/0.1 source-plane"


@dataclass(frozen=True)
class HarvardDataverseSuitabilityResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    query_count: int
    search_item_count: int
    dataset_count: int
    file_record_count: int


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_fetch_json(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    return payload if isinstance(payload, dict) else {}


def _write_json(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _safe_name(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value or "")).strip("_")[:120] or "dataverse"


def _digest(*parts: object) -> str:
    return hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:12]


def _clean(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _search_url(query: str, *, per_page: int) -> str:
    return f"{DATAVERSE_API_BASE}/search?{urlencode({'q': query, 'type': 'file', 'per_page': per_page})}"


def _dataset_detail_url(dataset_pid: str) -> str:
    return f"{DATAVERSE_API_BASE}/datasets/:persistentId/?{urlencode({'persistentId': dataset_pid})}"


def _items(payload: dict[str, object]) -> list[dict[str, object]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    return [item for item in items if isinstance(item, dict)]


def _has_aedes_scope(item: dict[str, object]) -> bool:
    text = " ".join(
        _clean(item.get(key))
        for key in ("name", "description", "dataset_name", "dataset_citation", "file_persistent_id")
    )
    return bool(re.search(r"\b(?:Aedes|Ae\.?)\s+aegypti\b", text, re.I))


def _is_suitability_raster(item: dict[str, object]) -> bool:
    name = _clean(item.get("name")).lower()
    content_type = _clean(item.get("file_content_type")).lower()
    file_type = _clean(item.get("file_type")).lower()
    scope = " ".join(_clean(item.get(key)).lower() for key in ("dataset_name", "description", "dataset_citation"))
    rasterish = name.endswith((".tif", ".tiff", ".geotiff")) or "tiff" in content_type or "tiff" in file_type
    suitabilityish = any(term in scope for term in ("suitability", "transmission", "risk", "climate", "rcp", "current", "2050", "2080"))
    return rasterish and suitabilityish


def _license_from_detail(detail: dict[str, object]) -> str:
    data = detail.get("data") if isinstance(detail.get("data"), dict) else {}
    version = data.get("latestVersion") if isinstance(data.get("latestVersion"), dict) else {}
    license_payload = version.get("license") if isinstance(version.get("license"), dict) else {}
    name = _clean(license_payload.get("name"))
    uri = _clean(license_payload.get("uri"))
    rights = _clean(license_payload.get("rightsIdentifier"))
    return " ".join(part for part in (name, rights, uri) if part) or "Dataverse dataset license not supplied"


def _description_from_detail(detail: dict[str, object]) -> str:
    data = detail.get("data") if isinstance(detail.get("data"), dict) else {}
    version = data.get("latestVersion") if isinstance(data.get("latestVersion"), dict) else {}
    blocks = version.get("metadataBlocks") if isinstance(version.get("metadataBlocks"), dict) else {}
    citation = blocks.get("citation") if isinstance(blocks.get("citation"), dict) else {}
    fields = citation.get("fields") if isinstance(citation.get("fields"), list) else []
    pieces: list[str] = []
    for field in fields:
        if not isinstance(field, dict):
            continue
        if field.get("typeName") == "dsDescription" and isinstance(field.get("value"), list):
            for item in field["value"]:
                if isinstance(item, dict):
                    desc = item.get("dsDescriptionValue")
                    if isinstance(desc, dict):
                        pieces.append(_clean(desc.get("value")))
        if field.get("typeName") == "publication" and isinstance(field.get("value"), list):
            for item in field["value"]:
                if isinstance(item, dict):
                    citation_value = item.get("publicationCitation")
                    if isinstance(citation_value, dict):
                        pieces.append(_clean(citation_value.get("value")))
    return " ".join(piece for piece in pieces if piece)


def _dataset_url(item: dict[str, object]) -> str:
    dataset_pid = _clean(item.get("dataset_persistent_id"))
    if dataset_pid.startswith("doi:"):
        return f"https://doi.org/{dataset_pid.removeprefix('doi:')}"
    return _clean(item.get("url"))


def _file_url(item: dict[str, object]) -> str:
    file_pid = _clean(item.get("file_persistent_id"))
    if file_pid.startswith("doi:"):
        return f"https://doi.org/{file_pid.removeprefix('doi:')}"
    return _clean(item.get("url"))


def _checksum_payload(item: dict[str, object]) -> dict[str, str]:
    checksum = item.get("checksum")
    if isinstance(checksum, dict):
        ctype = _clean(checksum.get("type")).lower()
        value = _clean(checksum.get("value"))
        if ctype and value:
            return {ctype: value}
    md5 = _clean(item.get("md5"))
    return {"md5": md5} if md5 else {}


def _scenario_terms(item: dict[str, object]) -> list[str]:
    text = " ".join(_clean(item.get(key)) for key in ("name", "description", "dataset_name", "dataset_citation"))
    terms: list[str] = []
    for pattern in ("current", "baseline", "2050", "2080", "rcp 2.6", "rcp 8.5", "hadgem2-es", "97.5% ci", "5 arc minutes"):
        if pattern.lower() in text.lower():
            terms.append(pattern)
    return terms


def _record_for_file(
    item: dict[str, object],
    *,
    detail: dict[str, object],
    detail_path: Path | None,
    search_path: Path,
    search_index: int,
    retrieved_at: str,
) -> EvidenceRecord:
    file_id = _clean(item.get("file_id")) or _digest(item.get("url"), item.get("name"))
    dataset_name = _clean(item.get("dataset_name")) or "Harvard Dataverse Aedes suitability dataset"
    filename = _clean(item.get("name")) or f"datafile-{file_id}"
    license_value = _license_from_detail(detail) if detail else "Dataverse dataset license not fetched"
    checksum = _checksum_payload(item)
    byte_size = item.get("size_in_bytes")
    terms = _scenario_terms(item)
    description = _clean(item.get("description")) or _description_from_detail(detail)
    access_url = _clean(item.get("url"))
    access_status = "downloadable" if item.get("canDownloadFile") is True and item.get("restricted") is False else "metadata_only_or_not_public"
    text = (
        f"Harvard Dataverse Aedes aegypti suitability raster manifest. Dataset: {dataset_name}. "
        f"File: {filename}. Content type: {_clean(item.get('file_content_type')) or _clean(item.get('file_type'))}. "
        f"Byte size: {byte_size}. Checksum: {checksum}. Scenario terms: {', '.join(terms) if terms else 'not parsed'}. "
        f"Access status: {access_status}. {description[:500]}"
    )
    payload = {
        "dataset_name": dataset_name,
        "dataset_id": item.get("dataset_id"),
        "dataset_persistent_id": item.get("dataset_persistent_id"),
        "file_id": item.get("file_id"),
        "file_persistent_id": item.get("file_persistent_id"),
        "filename": filename,
        "content_type": item.get("file_content_type") or item.get("file_type"),
        "byte_size": byte_size,
        "checksum": checksum,
        "download_url": access_url,
        "dataset_url": _dataset_url(item),
        "file_url": _file_url(item),
        "restricted": item.get("restricted"),
        "can_download_file": item.get("canDownloadFile"),
        "publication_statuses": item.get("publicationStatuses"),
        "published_at": item.get("published_at") or item.get("releaseOrCreateDate"),
        "license": license_value,
        "scenario_terms": terms,
        "raw_search_locator": f"{search_path.as_posix()}#data/items/{search_index}",
        "raw_dataset_detail_path": detail_path.as_posix() if detail_path else None,
    }
    return EvidenceRecord(
        record_id=f"ecology:dataverse_suitability:{_safe_name(file_id)}",
        lane="ecology",
        source=HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID,
        title=f"Aedes aegypti Dataverse suitability raster {filename}",
        text=text,
        species="Aedes aegypti",
        url=_dataset_url(item) or _file_url(item) or access_url,
        media_url=access_url or None,
        provenance=Provenance(
            source_id=HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID,
            locator=f"{search_path.as_posix()}#data/items/{search_index}",
            retrieved_at=retrieved_at,
            license=license_value,
            source_url=access_url or _dataset_url(item),
        ),
        payload=payload,
    )


def _gap_record(gap: dict[str, object], *, retrieved_at: str, index: int) -> EvidenceRecord:
    reason = _clean(gap.get("reason")) or "harvard_dataverse_suitability_gap"
    title = _clean(gap.get("title")) or _clean(gap.get("filename")) or reason
    locator = _clean(gap.get("locator")) or f"gaps.json#{HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID}/{index}"
    text = f"Harvard Dataverse Aedes suitability source gap: {reason}. {title}."
    if gap.get("download_url"):
        text += f" Download URL: {gap.get('download_url')}."
    if gap.get("error"):
        text += f" Error: {gap.get('error')}."
    return EvidenceRecord(
        record_id=f"ecology:dataverse_suitability:gap:{_safe_name(reason)}:{_digest(json.dumps(gap, sort_keys=True, default=str), index)}",
        lane="ecology",
        source=HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID,
        title=f"Aedes aegypti Dataverse suitability source gap: {reason}",
        text=text,
        species="Aedes aegypti",
        url=_clean(gap.get("source_url")) or None,
        media_url=None,
        provenance=Provenance(
            source_id=HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID,
            locator=locator,
            retrieved_at=retrieved_at,
            license=_clean(gap.get("license")) or None,
            source_url=_clean(gap.get("source_url")) or None,
        ),
        payload={"gap": gap},
    )


def fetch_harvard_dataverse_suitability_records(
    *,
    raw_dir: Path,
    queries: tuple[str, ...] = DEFAULT_QUERIES,
    per_page: int = 25,
    dataset_limit: int = 12,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
) -> HarvardDataverseSuitabilityResult:
    if per_page < 1:
        raise ValueError("per_page must be positive")
    if dataset_limit < 1:
        raise ValueError("dataset_limit must be positive")
    retrieved = retrieved_at or utc_now()
    fetch = fetch_json or _default_fetch_json
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    seen_files: set[str] = set()
    dataset_details: dict[str, tuple[dict[str, object], Path | None]] = {}
    search_item_count = 0

    for query_index, query in enumerate(queries, start=1):
        url = _search_url(query, per_page=per_page)
        try:
            payload = fetch(url)
        except Exception as exc:
            gap = {
                "source": HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID,
                "lane": "ecology",
                "reason": "dataverse_suitability_search_failed",
                "query": query,
                "source_url": url,
                "error": str(exc),
            }
            gaps.append(gap)
            continue
        search_path = _write_json(raw_dir, f"search_{query_index}_{_safe_name(query)}.json", payload)
        raw_artifacts.append(search_path.as_posix())
        for item_index, item in enumerate(_items(payload), start=1):
            search_item_count += 1
            if not _has_aedes_scope(item) or not _is_suitability_raster(item):
                continue
            file_key = _clean(item.get("file_id")) or _clean(item.get("file_persistent_id")) or _clean(item.get("url"))
            if file_key in seen_files:
                continue
            seen_files.add(file_key)
            dataset_pid = _clean(item.get("dataset_persistent_id"))
            detail: dict[str, object] = {}
            detail_path: Path | None = None
            if dataset_pid:
                if dataset_pid not in dataset_details and len(dataset_details) < dataset_limit:
                    detail_url = _dataset_detail_url(dataset_pid)
                    try:
                        detail = fetch(detail_url)
                        detail_path = _write_json(raw_dir, f"dataset_{_safe_name(dataset_pid)}.json", detail)
                        raw_artifacts.append(detail_path.as_posix())
                        dataset_details[dataset_pid] = (detail, detail_path)
                    except Exception as exc:
                        gap = {
                            "source": HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID,
                            "lane": "ecology",
                            "reason": "dataverse_dataset_detail_fetch_failed",
                            "dataset_persistent_id": dataset_pid,
                            "source_url": detail_url,
                            "error": str(exc),
                            "locator": f"{search_path.as_posix()}#data/items/{item_index}",
                        }
                        gaps.append(gap)
                        dataset_details[dataset_pid] = ({}, None)
                detail, detail_path = dataset_details.get(dataset_pid, ({}, None))
            record = _record_for_file(
                item,
                detail=detail,
                detail_path=detail_path,
                search_path=search_path,
                search_index=item_index,
                retrieved_at=retrieved,
            )
            records.append(record)
            if item.get("canDownloadFile") is not True or item.get("restricted") is not False:
                gaps.append(
                    {
                        "source": HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID,
                        "lane": "ecology",
                        "reason": "dataverse_file_download_not_public",
                        "title": record.title,
                        "filename": item.get("name"),
                        "dataset_persistent_id": dataset_pid,
                        "file_persistent_id": item.get("file_persistent_id"),
                        "download_url": item.get("url"),
                        "source_url": _dataset_url(item),
                        "license": record.provenance.license,
                        "locator": f"{search_path.as_posix()}#data/items/{item_index}",
                        "restricted": item.get("restricted"),
                        "can_download_file": item.get("canDownloadFile"),
                    }
                )
            if len(dataset_details) >= dataset_limit and dataset_pid not in dataset_details:
                gaps.append(
                    {
                        "source": HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID,
                        "lane": "ecology",
                        "reason": "dataverse_dataset_limit_applied",
                        "dataset_limit": dataset_limit,
                        "dataset_persistent_id": dataset_pid,
                        "locator": f"{search_path.as_posix()}#data/items/{item_index}",
                    }
                )

    if not records:
        gaps.append(
            {
                "source": HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID,
                "lane": "ecology",
                "reason": "dataverse_suitability_no_aedes_raster_files",
                "queries": list(queries),
                "search_item_count": search_item_count,
            }
        )
    records.extend(_gap_record(gap, retrieved_at=retrieved, index=index) for index, gap in enumerate(gaps, start=1))
    return HarvardDataverseSuitabilityResult(
        source_id=HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        query_count=len(queries),
        search_item_count=search_item_count,
        dataset_count=len(dataset_details),
        file_record_count=len([record for record in records if record.payload and not record.payload.get("gap")]),
    )
