from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID = "who_malaria_threats_resistance_audit"
WHO_MALARIA_THREATS_BASE_URL = "https://xmart-api-public.who.int/MAL_THREATS"
WHO_MALARIA_THREATS_PAGE_URL = (
    "https://www.who.int/teams/global-malaria-programme/prevention/"
    "vector-control/global-database-on-insecticide-resistance-in-malaria-vectors"
)
WHO_MALARIA_THREATS_MAP_URL = "https://apps.who.int/malaria/maps/threats/"
DEFAULT_SPECIES = "Aedes aegypti"
USER_AGENT = "AskInsects/0.1 source-plane"
WHO_LICENSE = "WHO public data; WHO terms apply"


@dataclass(frozen=True)
class WhoMalariaThreatsResistanceResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    species: str
    sample_row_count: int
    aedes_row_count: int


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_name(value: str | None) -> str:
    if not value:
        return "unknown"
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_") or "unknown"


def _default_fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:
        return response.read()


def _write_raw(raw_dir: Path, filename: str, data: bytes) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_bytes(data)
    return path


def _write_raw_json(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    return _write_raw(raw_dir, filename, (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))


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


def _fact_prevention_url(base_url: str, params: dict[str, object]) -> str:
    return f"{base_url.rstrip('/')}/FACT_PREVENTION_VIEW?{urlencode(params)}"


def _csv_rows(payload: bytes) -> list[dict[str, str]]:
    text = payload.decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def _json_rows(payload: bytes) -> list[dict[str, object]]:
    data = json.loads(payload.decode("utf-8", errors="replace"))
    if not isinstance(data, dict):
        return []
    values = data.get("value")
    return [row for row in values if isinstance(row, dict)] if isinstance(values, list) else []


def _row_id(row: dict[str, object]) -> str:
    explicit = _first(row, "OBJECTID", "Code", "ID")
    if explicit:
        return f"who:malaria-threats:resistance:{safe_name(explicit).lower()}"
    digest = hashlib.sha1(json.dumps(row, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    return f"who:malaria-threats:resistance:{digest}"


def _source_record(*, raw_path: Path, source_url: str, sample_row_count: int, retrieved_at: str) -> EvidenceRecord:
    text = (
        "WHO Malaria Threats Map exposes the WHO global insecticide-resistance database through a public "
        "FACT_PREVENTION_VIEW data endpoint. Ask Insects audited the endpoint for Aedes rows and stored a bounded "
        f"sample of {sample_row_count} resistance rows with raw provenance."
    )
    return EvidenceRecord(
        record_id="who:malaria-threats:resistance:source",
        lane="resistance",
        source=WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID,
        title="WHO Malaria Threats Map insecticide-resistance database availability",
        text=text,
        species="mosquito vectors",
        url=WHO_MALARIA_THREATS_PAGE_URL,
        media_url=None,
        provenance=Provenance(
            source_id=WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#sample",
            retrieved_at=retrieved_at,
            license=WHO_LICENSE,
            source_url=source_url,
        ),
        payload={
            "source_page_url": WHO_MALARIA_THREATS_PAGE_URL,
            "map_url": WHO_MALARIA_THREATS_MAP_URL,
            "sample_row_count": sample_row_count,
        },
    )


def _gap_record(gap: dict[str, object], *, raw_path: Path | None, source_url: str, retrieved_at: str) -> EvidenceRecord:
    reason = str(gap.get("reason") or "who_malaria_threats_resistance_gap")
    species = str(gap.get("species") or DEFAULT_SPECIES)
    locator = raw_path.as_posix() if raw_path else "who malaria threats request"
    text = (
        f"WHO Malaria Threats Map resistance audit found no rows matching {species} through the public "
        "FACT_PREVENTION_VIEW species filter. Ask Insects keeps this as an explicit WHO database source gap "
        "instead of claiming WHO Aedes resistance rows are indexed."
    )
    return EvidenceRecord(
        record_id=f"who:malaria-threats:resistance:gap:{safe_name(species).lower()}:{safe_name(reason).lower()}",
        lane="resistance",
        source=WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID,
        title=f"WHO Malaria Threats Map Aedes resistance source gap: {reason}",
        text=text,
        species=species,
        url=WHO_MALARIA_THREATS_MAP_URL,
        media_url=None,
        provenance=Provenance(
            source_id=WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID,
            locator=f"{locator}#gap/{reason}",
            retrieved_at=retrieved_at,
            license=WHO_LICENSE,
            source_url=source_url,
        ),
        payload={"gap": gap},
    )


def _resistance_record(row: dict[str, object], *, raw_path: Path, source_url: str, row_index: int, retrieved_at: str) -> EvidenceRecord:
    species = _first(row, "SPECIES") or DEFAULT_SPECIES
    insecticide = _first(row, "INSECTICIDE_TYPE")
    country = _first(row, "ISO2", "COUNTRY_NAME")
    status = _first(row, "RESISTANCE_STATUS", "MECHANISM_STATUS")
    title_parts = [species, "WHO resistance"]
    for value in (insecticide, country, status):
        if value:
            title_parts.append(value)
    fields = [
        ("country", country),
        ("site", _first(row, "VILLAGE_NAME", "ADMIN2", "ADMIN1")),
        ("year", _first(row, "YEAR_START")),
        ("assay", _first(row, "ASSAY_TYPE", "TYPE")),
        ("insecticide class", _first(row, "INSECTICIDE_CLASS")),
        ("insecticide", insecticide),
        ("concentration", _first(row, "INSECTICIDE_CONC")),
        ("stage origin", _first(row, "STAGE_ORIGIN")),
        ("mosquito number", _first(row, "NUMBER")),
        ("mortality adjusted", _first(row, "MORTALITY_ADJUSTED")),
        ("resistance status", status),
        ("mechanism", _first(row, "MECHANISM_PROXY", "PROXY_TYPE")),
        ("citation", _first(row, "CITATION_LONG")),
    ]
    text = "WHO Malaria Threats Map insecticide-resistance record. " + "; ".join(f"{k}: {v}" for k, v in fields if v) + "."
    return EvidenceRecord(
        record_id=_row_id(row),
        lane="resistance",
        source=WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID,
        title=" - ".join(title_parts),
        text=text,
        species=species,
        url=_first(row, "CITATION_URL") or WHO_MALARIA_THREATS_MAP_URL,
        media_url=None,
        provenance=Provenance(
            source_id=WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#row/{row_index}",
            retrieved_at=retrieved_at,
            license=WHO_LICENSE,
            source_url=source_url,
        ),
        payload={"raw_row": row, "raw_row_index": row_index},
    )


def fetch_who_malaria_threats_resistance_records(
    *,
    raw_dir: Path,
    species: str = DEFAULT_SPECIES,
    base_url: str = WHO_MALARIA_THREATS_BASE_URL,
    sample_limit: int = 5,
    aedes_limit: int = 100,
    fetch_bytes: Callable[[str], bytes] | None = None,
    retrieved_at: str | None = None,
) -> WhoMalariaThreatsResistanceResult:
    retrieved = retrieved_at or utc_now()
    fetch = fetch_bytes or _default_fetch_bytes
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    sample_rows: list[dict[str, str]] = []
    aedes_rows: list[dict[str, object]] = []

    sample_url = _fact_prevention_url(base_url, {"$format": "csv", "$top": max(1, sample_limit)})
    aedes_url = _fact_prevention_url(base_url, {"$filter": "contains(SPECIES,'Aedes')", "$top": max(1, aedes_limit)})

    try:
        sample_payload = fetch(sample_url)
        sample_path = _write_raw(raw_dir, "FACT_PREVENTION_VIEW_sample.csv", sample_payload)
        raw_artifacts.append(sample_path.as_posix())
        sample_rows = _csv_rows(sample_payload)
        records.append(_source_record(raw_path=sample_path, source_url=sample_url, sample_row_count=len(sample_rows), retrieved_at=retrieved))
    except Exception as exc:
        gap = {
            "source": WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID,
            "lane": "resistance",
            "reason": "who_malaria_threats_sample_fetch_failed",
            "url": sample_url,
            "error": str(exc),
            "retrieved_at": retrieved,
        }
        gaps.append(gap)
        records.append(_gap_record(gap, raw_path=None, source_url=sample_url, retrieved_at=retrieved))
        return WhoMalariaThreatsResistanceResult(
            WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID,
            records,
            gaps,
            raw_artifacts,
            species,
            0,
            0,
        )

    try:
        aedes_payload = fetch(aedes_url)
        aedes_path = _write_raw_json(raw_dir, f"FACT_PREVENTION_VIEW_{safe_name(species)}.json", json.loads(aedes_payload.decode("utf-8")))
        raw_artifacts.append(aedes_path.as_posix())
        aedes_rows = _json_rows(aedes_payload)
    except Exception as exc:
        gap = {
            "source": WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID,
            "lane": "resistance",
            "reason": "who_malaria_threats_aedes_query_failed",
            "species": species,
            "url": aedes_url,
            "error": str(exc),
            "retrieved_at": retrieved,
        }
        gaps.append(gap)
        records.append(_gap_record(gap, raw_path=None, source_url=aedes_url, retrieved_at=retrieved))
        return WhoMalariaThreatsResistanceResult(
            WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID,
            records,
            gaps,
            raw_artifacts,
            species,
            len(sample_rows),
            0,
        )

    if not aedes_rows:
        gap = {
            "source": WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID,
            "lane": "resistance",
            "reason": "who_malaria_threats_no_aedes_rows",
            "species": species,
            "url": aedes_url,
            "sample_row_count": len(sample_rows),
            "retrieved_at": retrieved,
        }
        gaps.append(gap)
        records.append(_gap_record(gap, raw_path=aedes_path, source_url=aedes_url, retrieved_at=retrieved))
    else:
        for row_index, row in enumerate(aedes_rows, start=1):
            records.append(_resistance_record(row, raw_path=aedes_path, source_url=aedes_url, row_index=row_index, retrieved_at=retrieved))

    return WhoMalariaThreatsResistanceResult(
        WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID,
        records,
        gaps,
        raw_artifacts,
        species,
        len(sample_rows),
        len(aedes_rows),
    )
