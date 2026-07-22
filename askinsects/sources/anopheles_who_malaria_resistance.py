from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


ANOPHELES_WHO_MALARIA_RESISTANCE_SOURCE_ID = "anopheles_who_malaria_resistance"
WHO_ENDPOINT = "https://xmart-api-public.who.int/MAL_THREATS/FACT_PREVENTION_VIEW"
WHO_PAGE_URL = "https://www.who.int/teams/global-malaria-programme/prevention/vector-control/global-database-on-insecticide-resistance-in-malaria-vectors"
WHO_MAP_URL = "https://apps.who.int/malaria/maps/threats/"
WHO_LICENSE = "WHO public data; WHO terms apply"
USER_AGENT = "AskInsects/0.1 source-plane"
ANOPHELES_FILTER = "(contains(SPECIES,'An.') or contains(SPECIES,'Anopheles')) and INSECTICIDE_TYPE ne 'NA'"


@dataclass(frozen=True)
class AnophelesWHOMalariaResistanceResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    fetched_row_count: int
    species_labels: dict[str, int]
    page_size: int
    max_rows: int


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return "" if text.lower() in {"", "na", "n/a", "null", "none", "undefined", "nr"} else text


def _first(row: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = _clean(row.get(key))
        if value:
            return value
    return ""


def _default_fetch_json(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=180) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
            break
        except HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise
            time.sleep(1.0 + attempt)
    if not isinstance(payload, dict):
        raise ValueError("WHO malaria threats endpoint returned non-object JSON")
    return payload


def _write_raw(raw_dir: Path, page_number: int, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"FACT_PREVENTION_VIEW_anopheles_{page_number:04d}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _rows(payload: dict[str, object]) -> list[dict[str, object]]:
    values = payload.get("value")
    return [row for row in values if isinstance(row, dict)] if isinstance(values, list) else []


def _record_id(row: dict[str, object]) -> str:
    explicit = _first(row, "Code", "ID", "OBJECTID")
    digest = hashlib.sha1(json.dumps(row, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]
    if explicit:
        return f"anopheles_who:resistance:{re.sub(r'[^A-Za-z0-9_.-]+', '_', explicit)}:{digest}"
    return f"anopheles_who:resistance:{digest}"


def _record(
    row: dict[str, object], *, raw_path: Path, row_index: int, source_url: str, retrieved_at: str
) -> EvidenceRecord:
    species = _first(row, "SPECIES") or "Anopheles spp."
    country = _first(row, "COUNTRY_NAME", "ISO2")
    locality = _first(row, "VILLAGE_NAME", "ADMIN2", "ADMIN1")
    insecticide = _first(row, "INSECTICIDE_TYPE")
    insecticide_class = _first(row, "INSECTICIDE_CLASS")
    status = _first(row, "RESISTANCE_STATUS", "MECHANISM_STATUS")
    year_start = _first(row, "YEAR_START")
    year_end = _first(row, "YEAR_END")
    year = f"{year_start}-{year_end}" if year_start and year_end and year_start != year_end else year_start or year_end
    citation = _first(row, "CITATION_LONG")
    citation_url = _first(row, "CITATION_URL")
    fields = [
        ("species", species), ("country", country), ("locality", locality), ("year", year),
        ("investigation type", _first(row, "INVESTIGATION_TYPE")),
        ("assay", _first(row, "ASSAY_TYPE", "TYPE")),
        ("insecticide class", insecticide_class), ("insecticide", insecticide),
        ("concentration", _first(row, "INSECTICIDE_CONC")),
        ("intensity", _first(row, "INSECTICIDE_INTENSITY", "RESISTANCE_INTENSITY")),
        ("stage origin", _first(row, "STAGE_ORIGIN")), ("mosquito number", _first(row, "NUMBER")),
        ("mortality adjusted", _first(row, "MORTALITY_ADJUSTED", "MORTALITY_ADJUSTED_INSECTICIDE")),
        ("resistance status", status), ("mechanism", _first(row, "MECHANISM_PROXY", "PROXY_TYPE")),
        ("mechanism frequency", _first(row, "MECHANISM_FREQUENCY")), ("citation", citation),
    ]
    text = "WHO malaria-vector insecticide-resistance record. " + "; ".join(f"{label}: {value}" for label, value in fields if value) + "."
    title_parts = [species, "WHO resistance"] + [value for value in (insecticide, country, status) if value]
    return EvidenceRecord(
        record_id=_record_id(row), lane="resistance", source=ANOPHELES_WHO_MALARIA_RESISTANCE_SOURCE_ID,
        title=" - ".join(title_parts), text=text, species=species,
        url=citation_url or WHO_MAP_URL, media_url=None,
        provenance=Provenance(
            source_id=ANOPHELES_WHO_MALARIA_RESISTANCE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#value/{row_index}", retrieved_at=retrieved_at,
            license=WHO_LICENSE, source_url=source_url,
        ),
        payload={
            "record_type": "who_malaria_vector_resistance_row", "raw_row": row, "raw_row_index": row_index,
            "query_stratum": "anopheles_rows_with_named_insecticide",
            "species_label": species, "country": country, "locality": locality, "year": year,
            "insecticide": insecticide, "insecticide_class": insecticide_class, "resistance_status": status,
        },
    )


def fetch_anopheles_who_malaria_resistance(
    *, raw_dir: Path, page_size: int = 1000, max_rows: int = 10000,
    delay_seconds: float = 0.2, fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
) -> AnophelesWHOMalariaResistanceResult:
    retrieved = retrieved_at or _utc_now()
    fetch = fetch_json or _default_fetch_json
    bounded_page_size = min(5000, max(1, int(page_size)))
    bounded_max_rows = max(0, int(max_rows))
    records_by_id: dict[str, EvidenceRecord] = {}
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []
    species_labels: dict[str, int] = {}
    fetched_rows = 0
    page_number = 0

    while fetched_rows < bounded_max_rows:
        top = min(bounded_page_size, bounded_max_rows - fetched_rows)
        params = {"$filter": ANOPHELES_FILTER, "$top": top, "$skip": fetched_rows, "$format": "json"}
        url = f"{WHO_ENDPOINT}?{urlencode(params)}"
        page_number += 1
        requested_urls.append(url)
        try:
            payload = fetch(url)
        except Exception as exc:
            gaps.append({"source": ANOPHELES_WHO_MALARIA_RESISTANCE_SOURCE_ID, "lane": "resistance", "reason": "who_anopheles_page_fetch_failed", "page": page_number, "skip": fetched_rows, "error": str(exc), "retrieved_at": retrieved})
            break
        raw_path = _write_raw(raw_dir, page_number, payload)
        raw_artifacts.append(raw_path.as_posix())
        rows = _rows(payload)
        for row_index, row in enumerate(rows):
            record = _record(row, raw_path=raw_path, row_index=row_index, source_url=url, retrieved_at=retrieved)
            records_by_id[record.record_id] = record
            label = record.species or "Anopheles spp."
            species_labels[label] = species_labels.get(label, 0) + 1
        fetched_rows += len(rows)
        if len(rows) < top:
            break
        if delay_seconds:
            time.sleep(delay_seconds)
    if fetched_rows >= bounded_max_rows and bounded_max_rows > 0:
        gaps.append({"source": ANOPHELES_WHO_MALARIA_RESISTANCE_SOURCE_ID, "lane": "resistance", "reason": "who_anopheles_max_rows_reached", "max_rows": bounded_max_rows, "fetched_row_count": fetched_rows, "retrieved_at": retrieved})
    if not records_by_id:
        gaps.append({"source": ANOPHELES_WHO_MALARIA_RESISTANCE_SOURCE_ID, "lane": "resistance", "reason": "who_anopheles_no_rows_parsed", "retrieved_at": retrieved})
    return AnophelesWHOMalariaResistanceResult(
        source_id=ANOPHELES_WHO_MALARIA_RESISTANCE_SOURCE_ID, records=list(records_by_id.values()), gaps=gaps,
        raw_artifacts=raw_artifacts, requested_urls=requested_urls, fetched_row_count=fetched_rows,
        species_labels=species_labels, page_size=bounded_page_size, max_rows=bounded_max_rows,
    )
