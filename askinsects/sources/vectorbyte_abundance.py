from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from math import ceil
from pathlib import Path
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..records import EvidenceRecord, Provenance


VECTORBYTE_ABUNDANCE_SOURCE_ID = "aedes_vectorbyte_abundance"
USER_AGENT = "AskInsects/0.1 source-plane"
VECDYN_API_BASE = "https://vectorbyte.crc.nd.edu/portal/api"
DEFAULT_QUERY = "Aedes aegypti"
DEFAULT_PAGE_SIZE = 50
MAX_SEARCH_LIMIT = 50


@dataclass(frozen=True)
class VectorByteAbundanceResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]


def _default_fetch_json(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _write_raw(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _clean(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _num(value: object) -> object:
    if isinstance(value, (int, float)):
        return value
    text = _clean(value)
    if not text:
        return None
    try:
        return int(text) if re.fullmatch(r"-?\d+", text) else float(text)
    except ValueError:
        return text


def _search_url(query: str, *, page: int = 1) -> str:
    return f"{VECDYN_API_BASE}/vecdynbyprovider?{urlencode({'format': 'json', 'keywords': query, 'page': page})}"


def _dataset_page_url(dataset_id: str, *, page: int = 1) -> str:
    return f"{VECDYN_API_BASE}/vecdyncsv?{urlencode({'format': 'json', 'page': page, 'piids': dataset_id})}"


def _metadata_results(payload: dict[str, object]) -> list[dict[str, object]]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    rows = data.get("results")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _metadata_count(payload: dict[str, object]) -> int:
    data = payload.get("data")
    if not isinstance(data, dict):
        return 0
    count = _num(data.get("count"))
    return int(count) if isinstance(count, (int, float)) else 0


def _species_names(metadata: dict[str, object]) -> list[str]:
    value = metadata.get("SpeciesName")
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    text = _clean(value)
    return [part.strip() for part in text.split(",") if part.strip()]


def _metadata_is_aedes(metadata: dict[str, object]) -> bool:
    names = {name.lower() for name in _species_names(metadata)}
    if "aedes aegypti" in names:
        return True
    material = " ".join(_clean(metadata.get(key)) for key in ("Title", "description", "citation", "doi"))
    return "aedes aegypti" in material.lower()


def _row_species(row: dict[str, object], consistent: dict[str, object]) -> str:
    return _clean(row.get("species")) or _clean(consistent.get("species"))


def _row_is_aedes(row: dict[str, object], consistent: dict[str, object]) -> bool:
    return _row_species(row, consistent).lower() in {"aedes aegypti", "ae. aegypti"}


def _stable_row_id(dataset_id: str, page: int, index: int, row: dict[str, object]) -> str:
    digest = sha1(json.dumps(row, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]
    return f"p{page}-r{index}-{digest}"


def _dataset_record(
    metadata: dict[str, object],
    *,
    raw_path: Path,
    source_url: str,
    retrieved_at: str,
) -> EvidenceRecord:
    dataset_id = _clean(metadata.get("Id"))
    title = _clean(metadata.get("Title")) or f"VectorByte VecDyn dataset {dataset_id}"
    species = ", ".join(_species_names(metadata))
    years = ", ".join(str(item) for item in metadata.get("Years", []) if item) if isinstance(metadata.get("Years"), list) else _clean(metadata.get("Years"))
    methods = ", ".join(str(item) for item in metadata.get("CollectionMethods", []) if item) if isinstance(metadata.get("CollectionMethods"), list) else _clean(metadata.get("CollectionMethods"))
    row_count = _num(metadata.get("row_count"))
    collections = _num(metadata.get("Collections"))
    doi = _clean(metadata.get("doi"))
    citation = _clean(metadata.get("citation"))
    contact = _clean(metadata.get("ContactName")) or _clean(metadata.get("contact_name"))
    text = " ".join(
        part
        for part in (
            f"VectorByte VecDyn Aedes aegypti abundance dataset: {title}.",
            f"Species listed: {species}." if species else "",
            f"Years: {years}." if years else "",
            f"Collection methods: {methods}." if methods else "",
            f"Collections: {collections}." if collections is not None else "",
            f"Rows exposed by VecDyn metadata: {row_count}." if row_count is not None else "",
            f"Contact: {contact}." if contact else "",
            f"Citation: {citation}." if citation else "",
            f"DOI: {doi}." if doi else "",
        )
        if part
    )
    return EvidenceRecord(
        record_id=f"vectorbyte:abundance-dataset:{dataset_id}",
        lane="ecology",
        source=VECTORBYTE_ABUNDANCE_SOURCE_ID,
        title=f"VectorByte VecDyn abundance dataset {dataset_id}: {title}",
        text=text,
        species="Aedes aegypti",
        url=f"https://doi.org/{doi}" if doi else source_url,
        media_url=None,
        provenance=Provenance(
            source_id=VECTORBYTE_ABUNDANCE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#data/results/{dataset_id}",
            retrieved_at=retrieved_at,
            license="VectorByte/VecDyn public data; source terms apply",
            source_url=source_url,
        ),
        payload={
            "atom_type": "vecdyn_dataset",
            "dataset_id": dataset_id,
            "title": title,
            "species_names": _species_names(metadata),
            "years": metadata.get("Years"),
            "collection_methods": metadata.get("CollectionMethods"),
            "collections": collections,
            "row_count": row_count,
            "doi": doi,
            "citation": citation,
            "contact_name": contact,
            "raw_json_path": raw_path.as_posix(),
        },
    )


def _abundance_record(
    row: dict[str, object],
    consistent: dict[str, object],
    *,
    dataset_id: str,
    row_id: str,
    raw_path: Path,
    source_url: str,
    retrieved_at: str,
) -> EvidenceRecord:
    title = _clean(consistent.get("title")) or f"VectorByte VecDyn dataset {dataset_id}"
    doi = _clean(consistent.get("doi"))
    citation = _clean(consistent.get("citation"))
    value = _num(row.get("sample_value"))
    unit = _clean(consistent.get("sample_unit")) or _clean(row.get("sample_unit"))
    start_date = _clean(row.get("sample_start_date"))
    start_time = _clean(row.get("sample_start_time"))
    end_date = _clean(row.get("sample_end_date"))
    species = _row_species(row, consistent) or "Aedes aegypti"
    stage = _clean(row.get("sample_stage")) or _clean(consistent.get("sample_stage"))
    sex = _clean(row.get("sample_sex")) or _clean(consistent.get("sample_sex"))
    method = _clean(row.get("sampling_method")) or _clean(consistent.get("sampling_method"))
    sample_name = _clean(row.get("sample_name"))
    latitude = _num(row.get("sample_lat_dd"))
    longitude = _num(row.get("sample_long_dd"))
    location = _clean(row.get("location_description")) or _clean(consistent.get("location_description")) or _clean(consistent.get("sample_location"))
    assay_id = _clean(row.get("linked_assay_id"))
    value_text = f"{value} {unit}".strip() if value is not None else ""
    text = " ".join(
        part
        for part in (
            f"VectorByte VecDyn Aedes aegypti abundance sample from dataset {dataset_id}.",
            f"Sample value: {value_text}." if value_text else "",
            f"Sample date: {start_date}." if start_date else "",
            f"Sample time: {start_time}." if start_time else "",
            f"Sample end date: {end_date}." if end_date and end_date != start_date else "",
            f"Sampling method: {method}." if method else "",
            f"Life stage: {stage}." if stage else "",
            f"Sex: {sex}." if sex else "",
            f"Coordinates: {latitude}, {longitude}." if latitude is not None and longitude is not None else "",
            f"Location: {location}." if location else "",
            f"Sample name: {sample_name}." if sample_name else "",
            f"Linked assay ID: {assay_id}." if assay_id else "",
            f"Dataset title: {title}.",
            f"Citation: {citation}." if citation else "",
            f"DOI: {doi}." if doi else "",
        )
        if part
    )
    return EvidenceRecord(
        record_id=f"vectorbyte:abundance:{dataset_id}:{row_id}",
        lane="observations",
        source=VECTORBYTE_ABUNDANCE_SOURCE_ID,
        title=f"VectorByte VecDyn abundance sample {dataset_id} {row_id}",
        text=text,
        species="Aedes aegypti",
        url=f"https://doi.org/{doi}" if doi else source_url,
        media_url=None,
        provenance=Provenance(
            source_id=VECTORBYTE_ABUNDANCE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#results/{row_id}",
            retrieved_at=retrieved_at,
            license="VectorByte/VecDyn public data; source terms apply",
            source_url=source_url,
        ),
        payload={
            "atom_type": "vecdyn_abundance_sample",
            "dataset_id": dataset_id,
            "row_id": row_id,
            "species": species,
            "sample_value": value,
            "sample_unit": unit,
            "sample_start_date": start_date,
            "sample_start_time": start_time,
            "sample_end_date": end_date,
            "sample_stage": stage,
            "sample_sex": sex,
            "sampling_method": method,
            "sample_name": sample_name,
            "latitude": latitude,
            "longitude": longitude,
            "location_description": location,
            "linked_assay_id": assay_id,
            "dataset_title": title,
            "doi": doi,
            "citation": citation,
            "raw_json_path": raw_path.as_posix(),
        },
    )


def fetch_vectorbyte_abundance_records(
    *,
    raw_dir: Path,
    fetch_json=None,
    retrieved_at: str,
    query: str = DEFAULT_QUERY,
    dataset_limit: int = 5,
    row_limit: int = 5000,
    search_page_limit: int = 3,
    dataset_page_limit: int = 100,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> VectorByteAbundanceResult:
    fetch = fetch_json or _default_fetch_json
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []
    dataset_metadata: list[tuple[dict[str, object], Path, str]] = []
    seen_ids: set[str] = set()

    for page in range(1, max(1, search_page_limit) + 1):
        url = _search_url(query, page=page)
        requested_urls.append(url)
        try:
            payload = fetch(url)
        except Exception as exc:  # noqa: BLE001
            gaps.append(
                {
                    "source": VECTORBYTE_ABUNDANCE_SOURCE_ID,
                    "reason": "vectorbyte_abundance_search_failed",
                    "url": url,
                    "page": page,
                    "error": str(exc),
                    "retrieved_at": retrieved_at,
                }
            )
            break
        raw_path = _write_raw(raw_dir, f"vecdyn_search_aedes_aegypti_page_{page}.json", payload)
        raw_artifacts.append(raw_path.as_posix())
        for item in _metadata_results(payload):
            dataset_id = _clean(item.get("Id"))
            if not dataset_id or dataset_id in seen_ids or not _metadata_is_aedes(item):
                continue
            dataset_metadata.append((item, raw_path, url))
            seen_ids.add(dataset_id)
            if len(dataset_metadata) >= dataset_limit:
                break
        if len(dataset_metadata) >= dataset_limit:
            break
        if page * MAX_SEARCH_LIMIT >= _metadata_count(payload):
            break

    if not dataset_metadata:
        gaps.append(
            {
                "source": VECTORBYTE_ABUNDANCE_SOURCE_ID,
                "reason": "vectorbyte_abundance_no_aedes_datasets",
                "query": query,
                "retrieved_at": retrieved_at,
            }
        )

    for metadata, metadata_path, metadata_url in dataset_metadata:
        dataset_id = _clean(metadata.get("Id"))
        records.append(_dataset_record(metadata, raw_path=metadata_path, source_url=metadata_url, retrieved_at=retrieved_at))
        row_count = _num(metadata.get("row_count"))
        expected_pages = ceil(float(row_count) / page_size) if isinstance(row_count, (int, float)) and row_count > 0 else dataset_page_limit
        max_pages = max(1, min(dataset_page_limit, expected_pages))
        matched = 0
        for page in range(1, max_pages + 1):
            url = _dataset_page_url(dataset_id, page=page)
            requested_urls.append(url)
            try:
                payload = fetch(url)
            except Exception as exc:  # noqa: BLE001
                gaps.append(
                    {
                        "source": VECTORBYTE_ABUNDANCE_SOURCE_ID,
                        "reason": "vectorbyte_abundance_dataset_page_fetch_failed",
                        "dataset_id": dataset_id,
                        "url": url,
                        "page": page,
                        "error": str(exc),
                        "retrieved_at": retrieved_at,
                    }
                )
                break
            raw_path = _write_raw(raw_dir, f"vecdyn_dataset_{dataset_id}_page_{page}.json", payload)
            raw_artifacts.append(raw_path.as_posix())
            rows = payload.get("results")
            if not isinstance(rows, list) or not rows:
                break
            consistent = payload.get("consistent_data") if isinstance(payload.get("consistent_data"), dict) else {}
            for index, row in enumerate(rows):
                if not isinstance(row, dict) or not _row_is_aedes(row, consistent):
                    continue
                row_id = _stable_row_id(dataset_id, page, index, row)
                records.append(
                    _abundance_record(
                        row,
                        consistent,
                        dataset_id=dataset_id,
                        row_id=row_id,
                        raw_path=raw_path,
                        source_url=url,
                        retrieved_at=retrieved_at,
                    )
                )
                matched += 1
                if len(records) >= row_limit:
                    gaps.append(
                        {
                            "source": VECTORBYTE_ABUNDANCE_SOURCE_ID,
                            "reason": "vectorbyte_abundance_row_limit_applied",
                            "row_limit": row_limit,
                            "retrieved_at": retrieved_at,
                        }
                    )
                    return VectorByteAbundanceResult(VECTORBYTE_ABUNDANCE_SOURCE_ID, records, gaps, raw_artifacts, requested_urls)
        if matched == 0:
            gaps.append(
                {
                    "source": VECTORBYTE_ABUNDANCE_SOURCE_ID,
                    "reason": "vectorbyte_abundance_no_aedes_rows",
                    "dataset_id": dataset_id,
                    "retrieved_at": retrieved_at,
                }
            )
        if max_pages < expected_pages:
            gaps.append(
                {
                    "source": VECTORBYTE_ABUNDANCE_SOURCE_ID,
                    "reason": "vectorbyte_abundance_dataset_page_limit_applied",
                    "dataset_id": dataset_id,
                    "page_limit": dataset_page_limit,
                    "expected_pages": expected_pages,
                    "retrieved_at": retrieved_at,
                }
            )

    return VectorByteAbundanceResult(VECTORBYTE_ABUNDANCE_SOURCE_ID, records, gaps, raw_artifacts, requested_urls)
