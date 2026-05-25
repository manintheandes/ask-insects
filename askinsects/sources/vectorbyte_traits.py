from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..records import EvidenceRecord, Provenance


VECTORBYTE_TRAITS_SOURCE_ID = "aedes_vectorbyte_traits"
USER_AGENT = "AskInsects/0.1 source-plane"
HUB_SEARCH_BASE = "https://api.vbdhub.org/search"
VECTRAITS_DATASET_BASE = "https://vectorbyte.crc.nd.edu/portal/api/vectraits-dataset"
DEFAULT_QUERY = "Aedes aegypti"
MAX_SEARCH_LIMIT = 50


@dataclass(frozen=True)
class VectorByteTraitResult:
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


def _search_url(query: str, *, search_limit: int) -> str:
    capped_limit = max(1, min(search_limit, MAX_SEARCH_LIMIT))
    return f"{HUB_SEARCH_BASE}?{urlencode({'query': query, 'database': 'vt', 'limit': capped_limit, 'page': 1, 'withoutPublished': 'true'})}"


def _dataset_url(dataset_id: str) -> str:
    return f"{VECTRAITS_DATASET_BASE}/{dataset_id}/?format=json"


def _search_hits(payload: dict[str, object]) -> list[dict[str, object]]:
    hits = payload.get("hits")
    if not isinstance(hits, list):
        return []
    return [hit for hit in hits if isinstance(hit, dict)]


def _dataset_ids(payload: dict[str, object], *, dataset_limit: int) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for hit in _search_hits(payload):
        if _clean(hit.get("db")) != "vt":
            continue
        dataset_id = _clean(hit.get("id"))
        if not dataset_id or dataset_id in seen:
            continue
        ids.append(dataset_id)
        seen.add(dataset_id)
        if len(ids) >= dataset_limit:
            break
    return ids


def _dataset_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    rows = payload.get("results")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _is_aedes_aegypti(row: dict[str, object]) -> bool:
    interactor = _clean(row.get("Interactor1")).lower()
    genus = _clean(row.get("Interactor1Genus")).lower()
    species = _clean(row.get("Interactor1Species")).lower()
    return interactor == "aedes aegypti" or (genus == "aedes" and species == "aegypti")


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


def _trait_record(row: dict[str, object], *, raw_path: Path, source_url: str, retrieved_at: str) -> EvidenceRecord:
    dataset_id = _clean(row.get("DatasetID"))
    row_id = _clean(row.get("Id")) or _clean(row.get("OriginalID")) or f"row-{len(json.dumps(row, sort_keys=True))}"
    trait = _clean(row.get("OriginalTraitName")) or _clean(row.get("StandardisedTraitName")) or "trait observation"
    trait_def = _clean(row.get("OriginalTraitDef")) or _clean(row.get("StandardisedTraitDef"))
    value = _num(row.get("OriginalTraitValue"))
    unit = _clean(row.get("OriginalTraitUnit"))
    temperature = _num(row.get("Interactor1Temp"))
    temperature_unit = _clean(row.get("Interactor1TempUnit"))
    location = _clean(row.get("Location"))
    stage = _clean(row.get("Interactor1Stage"))
    sex = _clean(row.get("Interactor1Sex"))
    habitat = _clean(row.get("Habitat"))
    lab_field = _clean(row.get("LabField"))
    latitude = _num(row.get("Latitude"))
    longitude = _num(row.get("Longitude"))
    citation = _clean(row.get("Citation"))
    doi = _clean(row.get("DOI"))
    figure_table = _clean(row.get("FigureTable"))
    value_text = f"{value} {unit}".strip() if value is not None else ""
    temp_text = f"{temperature} {temperature_unit}".strip() if temperature is not None else ""
    text = " ".join(
        part
        for part in (
            f"VectorByte VecTraits Aedes aegypti observation for {trait}.",
            f"Definition: {trait_def}." if trait_def else "",
            f"Value: {value_text}." if value_text else "",
            f"Temperature: {temp_text}." if temp_text else "",
            f"Life stage: {stage}." if stage else "",
            f"Sex: {sex}." if sex else "",
            f"Habitat: {habitat}." if habitat else "",
            f"Environment: {lab_field}." if lab_field else "",
            f"Location: {location}." if location else "",
            f"Coordinates: {latitude}, {longitude}." if latitude is not None and longitude is not None else "",
            f"Figure or table: {figure_table}." if figure_table else "",
            f"Citation: {citation}." if citation else "",
            f"DOI: {doi}." if doi else "",
        )
        if part
    )
    return EvidenceRecord(
        record_id=f"vectorbyte:trait:{dataset_id}:{row_id}",
        lane="traits",
        source=VECTORBYTE_TRAITS_SOURCE_ID,
        title=f"VectorByte trait {trait}: dataset {dataset_id} row {row_id}",
        text=text,
        species="Aedes aegypti",
        url=f"https://doi.org/{doi}" if doi else source_url,
        media_url=None,
        provenance=Provenance(
            source_id=VECTORBYTE_TRAITS_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#results/{row_id}",
            retrieved_at=retrieved_at,
            license="VectorByte/VBD Hub public data; source terms apply",
            source_url=source_url,
        ),
        payload={
            "dataset_id": dataset_id,
            "row_id": row_id,
            "trait_name": trait,
            "trait_definition": trait_def,
            "trait_value": value,
            "trait_unit": unit,
            "temperature": temperature,
            "temperature_unit": temperature_unit,
            "location": location,
            "stage": stage,
            "sex": sex,
            "habitat": habitat,
            "lab_field": lab_field,
            "latitude": latitude,
            "longitude": longitude,
            "citation": citation,
            "doi": doi,
            "figure_table": figure_table,
            "raw_json_path": raw_path.as_posix(),
        },
    )


def fetch_vectorbyte_trait_records(
    *,
    raw_dir: Path,
    fetch_json=None,
    retrieved_at: str,
    query: str = DEFAULT_QUERY,
    dataset_limit: int = 20,
    row_limit: int = 5000,
    search_limit: int = MAX_SEARCH_LIMIT,
) -> VectorByteTraitResult:
    fetch = fetch_json or _default_fetch_json
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []

    search_url = _search_url(query, search_limit=search_limit)
    requested_urls.append(search_url)
    try:
        search_payload = fetch(search_url)
        search_path = _write_raw(raw_dir, "vbdhub_search_aedes_aegypti_vt.json", search_payload)
        raw_artifacts.append(search_path.as_posix())
    except Exception as exc:  # noqa: BLE001 - source ingest should preserve a structured fetch gap
        return VectorByteTraitResult(
            source_id=VECTORBYTE_TRAITS_SOURCE_ID,
            records=[],
            gaps=[
                {
                    "source": VECTORBYTE_TRAITS_SOURCE_ID,
                    "reason": "vectorbyte_traits_search_failed",
                    "url": search_url,
                    "error": str(exc),
                    "retrieved_at": retrieved_at,
                }
            ],
            raw_artifacts=[],
            requested_urls=requested_urls,
        )

    dataset_ids = _dataset_ids(search_payload, dataset_limit=dataset_limit)
    if not dataset_ids:
        gaps.append(
            {
                "source": VECTORBYTE_TRAITS_SOURCE_ID,
                "reason": "vectorbyte_traits_no_search_hits",
                "url": search_url,
                "retrieved_at": retrieved_at,
            }
        )

    for dataset_id in dataset_ids:
        url = _dataset_url(dataset_id)
        requested_urls.append(url)
        try:
            payload = fetch(url)
        except Exception as exc:  # noqa: BLE001
            gaps.append(
                {
                    "source": VECTORBYTE_TRAITS_SOURCE_ID,
                    "reason": "vectorbyte_traits_dataset_fetch_failed",
                    "dataset_id": dataset_id,
                    "url": url,
                    "error": str(exc),
                    "retrieved_at": retrieved_at,
                }
            )
            continue
        raw_path = _write_raw(raw_dir, f"vectraits_dataset_{dataset_id}.json", payload)
        raw_artifacts.append(raw_path.as_posix())
        matched = 0
        for row in _dataset_rows(payload):
            if not _is_aedes_aegypti(row):
                continue
            records.append(_trait_record(row, raw_path=raw_path, source_url=url, retrieved_at=retrieved_at))
            matched += 1
            if len(records) >= row_limit:
                gaps.append(
                    {
                        "source": VECTORBYTE_TRAITS_SOURCE_ID,
                        "reason": "vectorbyte_traits_row_limit_applied",
                        "row_limit": row_limit,
                        "retrieved_at": retrieved_at,
                    }
                )
                return VectorByteTraitResult(VECTORBYTE_TRAITS_SOURCE_ID, records, gaps, raw_artifacts, requested_urls)
        if matched == 0:
            gaps.append(
                {
                    "source": VECTORBYTE_TRAITS_SOURCE_ID,
                    "reason": "vectorbyte_traits_no_aedes_rows",
                    "dataset_id": dataset_id,
                    "url": url,
                    "retrieved_at": retrieved_at,
                }
            )
    if not records and not gaps:
        gaps.append(
            {
                "source": VECTORBYTE_TRAITS_SOURCE_ID,
                "reason": "vectorbyte_traits_no_records",
                "retrieved_at": retrieved_at,
            }
        )
    return VectorByteTraitResult(VECTORBYTE_TRAITS_SOURCE_ID, records, gaps, raw_artifacts, requested_urls)
