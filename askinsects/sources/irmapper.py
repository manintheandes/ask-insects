from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.request import Request, urlopen

from ..records import EvidenceRecord, Provenance


IRMAPPER_SOURCE_ID = "irmapper_aedes"
IRMAPPER_API_URL = "https://api.irmapper.com/api/aedes"
DEFAULT_IRMAPPER_SPECIES = "Aedes aegypti"
USER_AGENT = "AskInsects/0.1 source-plane"


@dataclass(frozen=True)
class IRMapperBuildResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_species: str
    fetched_row_count: int


def _default_fetch_json(url: str) -> object:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def _clean(value: object) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    if text.lower() in {"", "na", "n/a", "null", "none", "undefined"}:
        return ""
    return text


def _first(row: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = _clean(row.get(key))
        if value:
            return value
    return ""


def _rows(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "records", "results", "features"):
            values = payload.get(key)
            if isinstance(values, list):
                if key == "features":
                    rows = []
                    for feature in values:
                        if isinstance(feature, dict):
                            properties = feature.get("properties")
                            rows.append(properties if isinstance(properties, dict) else feature)
                    return rows
                return [row for row in values if isinstance(row, dict)]
    return []


def _safe_species(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "species"


def _write_raw_json(raw_dir: Path, species: str, payload: object) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{_safe_species(species)}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _row_id(row: dict[str, object]) -> str:
    explicit_id = _clean(row.get("id") or row.get("ID") or row.get("record_id"))
    if explicit_id:
        return f"irmapper:aedes:{explicit_id}"
    digest = hashlib.sha1(json.dumps(row, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    return f"irmapper:aedes:{digest}"


def _year_range(row: dict[str, object]) -> str:
    start = _first(row, "collection_Year_Start", "collection_year_start", "year_start", "year", "Year")
    end = _first(row, "collection_Year_End", "collection_year_end", "year_end")
    if start and end and start != end:
        return f"{start}-{end}"
    return start or end


def _title(species: str, row: dict[str, object]) -> str:
    insecticide = _first(row, "chemical_Type", "chemical_type", "insecticide", "active_ingredient", "chemical")
    country = _first(row, "country", "Country")
    status = _first(row, "resistance_Status", "resistance_status", "status")
    parts = [species, "IR Mapper resistance"]
    if insecticide:
        parts.append(insecticide)
    if country:
        parts.append(country)
    if status:
        parts.append(status)
    return " - ".join(parts)


def _record_text(species: str, row: dict[str, object]) -> str:
    fields = [
        ("species", species),
        ("country", _first(row, "country", "Country")),
        ("locality", _first(row, "locality", "location", "site", "district", "city")),
        ("year", _year_range(row)),
        ("life stage", _first(row, "vector_Developmental_Stage", "developmental_stage", "stage")),
        ("assay", _first(row, "iR_Test_Method", "test_method", "method", "bioassay", "assay")),
        ("insecticide class", _first(row, "chemical_Class", "chemical_class", "class")),
        ("insecticide", _first(row, "chemical_Type", "chemical_type", "insecticide", "active_ingredient", "chemical")),
        ("dose", _first(row, "insecticide_Dosage", "insecticide_dosage", "dose")),
        ("mode of action", _first(row, "iraC_MoA", "mode_of_action")),
        ("mortality", _first(row, "iR_Test_mortality", "mortality", "mortality_percent")),
        ("resistance status", _first(row, "resistance_Status", "resistance_status", "status")),
        ("mechanism", _first(row, "iR_Mechanism_Name", "mechanism", "resistance_mechanism")),
        ("mutation frequency", _first(row, "mutation_frequency", "mutationFrequency")),
        ("mechanism status", _first(row, "iR_Mechanism_Status", "mechanism_status")),
        ("reference", _first(row, "reference_Name", "reference", "publication", "source")),
    ]
    chunks = [f"{label}: {value}" for label, value in fields if value]
    return "IR Mapper Aedes insecticide resistance record. " + "; ".join(chunks) + "."


def _species_matches(row_species: str, requested_species: str) -> bool:
    normalized = row_species.lower().replace("ae.", "aedes").replace("ae ", "aedes ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    requested = re.sub(r"\s+", " ", requested_species.lower()).strip()
    return normalized == requested


def _record(row: dict[str, object], *, species: str, raw_path: Path, row_index: int, retrieved_at: str) -> EvidenceRecord:
    url = _first(row, "url", "source_url", "reference_url", "doi")
    if url and url.startswith("10."):
        url = f"https://doi.org/{url}"
    return EvidenceRecord(
        record_id=_row_id(row),
        lane="resistance",
        source=IRMAPPER_SOURCE_ID,
        title=_title(species, row),
        text=_record_text(species, row),
        species=species,
        url=url or None,
        media_url=None,
        provenance=Provenance(
            source_id=IRMAPPER_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#row/{row_index}",
            retrieved_at=retrieved_at,
            license="IR Mapper public API",
            source_url=IRMAPPER_API_URL,
        ),
        payload={"raw_row": row, "raw_row_index": row_index, "requested_species": species},
    )


def fetch_irmapper_records(
    *,
    raw_dir: Path,
    species: str = DEFAULT_IRMAPPER_SPECIES,
    api_url: str = IRMAPPER_API_URL,
    fetch_json=None,
    retrieved_at: str,
) -> IRMapperBuildResult:
    fetch = fetch_json or _default_fetch_json
    gaps: list[dict[str, object]] = []
    records: list[EvidenceRecord] = []
    raw_artifacts: list[str] = []

    try:
        payload = fetch(api_url)
    except Exception as exc:
        gaps.append(
            {
                "source": IRMAPPER_SOURCE_ID,
                "lane": "resistance",
                "species": species,
                "reason": "irmapper_fetch_failed",
                "url": api_url,
                "error": str(exc),
                "retrieved_at": retrieved_at,
            }
        )
        return IRMapperBuildResult(IRMAPPER_SOURCE_ID, [], gaps, [], species, 0)

    raw_path = _write_raw_json(raw_dir, species, payload)
    raw_artifacts.append(raw_path.as_posix())
    rows = _rows(payload)
    for row_index, row in enumerate(rows, start=1):
        row_species = _first(row, "vector_Species", "vector_species", "species", "Species", "scientific_name")
        if not _species_matches(row_species, species):
            continue
        records.append(_record(row, species=species, raw_path=raw_path, row_index=row_index, retrieved_at=retrieved_at))

    if not records:
        gaps.append(
            {
                "source": IRMAPPER_SOURCE_ID,
                "lane": "resistance",
                "species": species,
                "reason": "irmapper_species_rows_missing",
                "fetched_row_count": len(rows),
                "retrieved_at": retrieved_at,
            }
        )

    return IRMapperBuildResult(IRMAPPER_SOURCE_ID, records, gaps, raw_artifacts, species, len(rows))
