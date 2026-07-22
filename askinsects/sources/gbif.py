from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


GBIF_SOURCE_ID = "gbif_api"
GBIF_API_BASE = "https://api.gbif.org"
GBIF_WEB_BASE = "https://www.gbif.org"
DEFAULT_GBIF_SPECIES = ("Aedes aegypti", "Culex pipiens", "Anopheles gambiae")


@dataclass(frozen=True)
class GBIFBuildResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    taxon_keys: dict[str, int]
    raw_artifacts: list[str]
    requested_species: list[str]
    occurrence_limit: int
    occurrence_page_size: int
    occurrence_workers: int
    total_results: dict[str, int]
    page_count: int


class GBIFClient:
    def __init__(self, fetch_json: Callable[[str], dict[str, object]] | None = None):
        self.fetch_json = fetch_json or self._fetch_json

    def species_match(self, species: str) -> tuple[str, dict[str, object]]:
        url = f"{GBIF_API_BASE}/v1/species/match?{urlencode({'name': species})}"
        return url, self.fetch_json(url)

    def occurrence_search(self, taxon_key: int, limit: int, offset: int = 0) -> tuple[str, dict[str, object]]:
        params = {"taxonKey": taxon_key, "limit": limit, "offset": offset}
        url = f"{GBIF_API_BASE}/v1/occurrence/search?{urlencode(params)}"
        return url, self.fetch_json(url)

    @staticmethod
    def _fetch_json(url: str) -> dict[str, object]:
        payload: object | None = None
        request = Request(url, headers={"User-Agent": "ask-insects/0.1"})
        retryable_statuses = {429, 500, 502, 503, 504}
        for attempt in range(5):
            try:
                with urlopen(request, timeout=30) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except HTTPError as exc:
                if exc.code not in retryable_statuses or attempt == 4:
                    raise
            except (TimeoutError, URLError):
                if attempt == 4:
                    raise
            time.sleep(2**attempt)
        if not isinstance(payload, dict):
            raise ValueError(f"GBIF returned non-object JSON for {url}")
        return payload


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_species_name(species: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", species).strip("_")


def write_raw_json(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _canonical_species(species: str, match_payload: dict[str, object]) -> str:
    return str(match_payload.get("canonicalName") or match_payload.get("species") or species)


def _taxonomy_text(match_payload: dict[str, object]) -> str:
    canonical = str(match_payload.get("canonicalName") or match_payload.get("species") or "Unknown species")
    family = match_payload.get("family")
    genus = match_payload.get("genus")
    status = match_payload.get("status") or "matched"
    rank = match_payload.get("rank") or "taxon"
    parts = [f"GBIF accepted species match for {canonical}"]
    if family or genus:
        parts.append(f"placed in family {family or 'unknown'} and genus {genus or 'unknown'}")
    parts.append(f"with rank {rank} and status {status}.")
    return ", ".join(parts)


def _media_url(occurrence: dict[str, object]) -> str | None:
    media = occurrence.get("media")
    if not isinstance(media, list):
        return None
    for item in media:
        if isinstance(item, dict) and item.get("identifier"):
            return str(item["identifier"])
    return None


def taxonomy_record(
    species: str,
    match_payload: dict[str, object],
    *,
    match_url: str,
    raw_path: Path,
    retrieved_at: str,
    source_id: str = GBIF_SOURCE_ID,
    record_prefix: str = "gbif",
) -> EvidenceRecord:
    taxon_key = int(match_payload["usageKey"])
    canonical = _canonical_species(species, match_payload)
    gbif_url = f"{GBIF_WEB_BASE}/species/{taxon_key}"
    return EvidenceRecord(
        record_id=f"{record_prefix}:taxon:{taxon_key}",
        lane="taxonomy",
        source=source_id,
        title=canonical,
        text=_taxonomy_text(match_payload),
        species=canonical,
        url=gbif_url,
        media_url=None,
        provenance=Provenance(
            source_id=source_id,
            locator=f"{raw_path.as_posix()}#species/match?name={species}",
            retrieved_at=retrieved_at,
            license="GBIF API metadata",
            source_url=match_url,
        ),
        payload={
            "raw_match": match_payload,
            "query_url": match_url,
        },
    )


def occurrence_record(
    occurrence: dict[str, object],
    *,
    species: str,
    occurrence_url: str,
    raw_path: Path,
    retrieved_at: str,
    source_id: str = GBIF_SOURCE_ID,
    record_prefix: str = "gbif",
) -> EvidenceRecord:
    key = int(occurrence["key"])
    country = occurrence.get("country") or "unknown country"
    event_date = occurrence.get("eventDate") or "unknown date"
    dataset_name = occurrence.get("datasetName") or occurrence.get("datasetKey") or "unknown GBIF dataset"
    scientific_name = str(occurrence.get("species") or occurrence.get("scientificName") or species)
    gbif_url = f"{GBIF_WEB_BASE}/occurrence/{key}"
    text = (
        f"GBIF occurrence record for {scientific_name} in {country}, "
        f"event date {event_date}, from {dataset_name}."
    )
    return EvidenceRecord(
        record_id=f"{record_prefix}:occurrence:{key}",
        lane="observations",
        source=source_id,
        title=f"{scientific_name} occurrence {key}",
        text=text,
        species=scientific_name,
        url=gbif_url,
        media_url=_media_url(occurrence),
        provenance=Provenance(
            source_id=source_id,
            locator=f"{raw_path.as_posix()}#occurrence/{key}",
            retrieved_at=retrieved_at,
            license=str(occurrence.get("license") or "GBIF occurrence license not supplied"),
            source_url=gbif_url if not occurrence_url else gbif_url,
        ),
        payload={
            "raw_occurrence": occurrence,
            "query_url": occurrence_url,
        },
    )


def fetch_occurrence_page(
    client: GBIFClient,
    *,
    taxon_key: int,
    page_limit: int,
    offset: int,
    raw_dir: Path,
    safe_name: str,
) -> tuple[int, str, dict[str, object], Path]:
    occurrence_url, occurrence_payload = client.occurrence_search(taxon_key, page_limit, offset=offset)
    occurrence_path = write_raw_json(raw_dir, f"{safe_name}_occurrences_offset_{offset:06d}.json", occurrence_payload)
    return offset, occurrence_url, occurrence_payload, occurrence_path


def fetch_gbif_records(
    species_names: list[str] | tuple[str, ...],
    *,
    raw_dir: Path,
    occurrence_limit: int = 3,
    occurrence_page_size: int = 300,
    occurrence_workers: int = 1,
    delay_seconds: float = 0.0,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
    source_id: str = GBIF_SOURCE_ID,
    record_prefix: str = "gbif",
) -> GBIFBuildResult:
    if occurrence_limit < 0:
        raise ValueError("occurrence_limit must be zero or greater")
    if occurrence_page_size <= 0:
        raise ValueError("occurrence_page_size must be greater than zero")
    if occurrence_workers <= 0:
        raise ValueError("occurrence_workers must be greater than zero")
    retrieved = retrieved_at or utc_now()
    client = GBIFClient(fetch_json)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    taxon_keys: dict[str, int] = {}
    raw_artifacts: list[str] = []
    total_results: dict[str, int] = {}
    page_count = 0

    for species in species_names:
        safe_name = safe_species_name(species)
        match_url, match_payload = client.species_match(species)
        match_path = write_raw_json(raw_dir, f"{safe_name}_match.json", match_payload)
        raw_artifacts.append(match_path.as_posix())

        usage_key = match_payload.get("usageKey")
        if not usage_key:
            gaps.append({"source": source_id, "lane": "taxonomy", "species": species, "reason": "GBIF did not match this species name."})
            continue

        taxon_key = int(usage_key)
        taxon_keys[species] = taxon_key
        records.append(
            taxonomy_record(
                species,
                match_payload,
                match_url=match_url,
                raw_path=match_path,
                retrieved_at=retrieved,
                source_id=source_id,
                record_prefix=record_prefix,
            )
        )

        target_count = occurrence_limit
        pages: list[tuple[int, str, dict[str, object], Path]] = []
        if occurrence_limit > 0:
            first_page_limit = min(occurrence_page_size, occurrence_limit)
            first_page = fetch_occurrence_page(
                client,
                taxon_key=taxon_key,
                page_limit=first_page_limit,
                offset=0,
                raw_dir=raw_dir,
                safe_name=safe_name,
            )
            pages.append(first_page)
            first_payload = first_page[2]
            reported_count = int(first_payload.get("count") or 0)
            total_results[species] = reported_count
            if reported_count:
                target_count = min(occurrence_limit, reported_count)
            first_results = first_payload.get("results")
            first_result_count = len(first_results) if isinstance(first_results, list) else 0
            remaining_offsets = list(range(first_result_count, target_count, occurrence_page_size))
            if occurrence_workers == 1:
                for offset in remaining_offsets:
                    if delay_seconds:
                        time.sleep(delay_seconds)
                    page_limit = min(occurrence_page_size, target_count - offset)
                    pages.append(
                        fetch_occurrence_page(
                            client,
                            taxon_key=taxon_key,
                            page_limit=page_limit,
                            offset=offset,
                            raw_dir=raw_dir,
                            safe_name=safe_name,
                        )
                    )
            elif remaining_offsets:
                with ThreadPoolExecutor(max_workers=occurrence_workers) as executor:
                    futures = [
                        executor.submit(
                            fetch_occurrence_page,
                            client,
                            taxon_key=taxon_key,
                            page_limit=min(occurrence_page_size, target_count - offset),
                            offset=offset,
                            raw_dir=raw_dir,
                            safe_name=safe_name,
                        )
                        for offset in remaining_offsets
                    ]
                    for future in as_completed(futures):
                        pages.append(future.result())

        saw_occurrence = False
        page_count += len(pages)
        for _offset, occurrence_url, occurrence_payload, occurrence_path in sorted(pages, key=lambda item: item[0]):
            raw_artifacts.append(occurrence_path.as_posix())
            occurrence_results = occurrence_payload.get("results")
            if not isinstance(occurrence_results, list) or not occurrence_results:
                continue
            for occurrence in occurrence_results:
                if isinstance(occurrence, dict) and occurrence.get("key"):
                    saw_occurrence = True
                    records.append(
                        occurrence_record(
                            occurrence,
                            species=_canonical_species(species, match_payload),
                            occurrence_url=occurrence_url,
                            raw_path=occurrence_path,
                            retrieved_at=retrieved,
                            source_id=source_id,
                            record_prefix=record_prefix,
                        )
                    )

        if not saw_occurrence:
            gaps.append({"source": source_id, "lane": "observations", "species": species, "reason": "GBIF returned no occurrence records for this species."})

    return GBIFBuildResult(
        source_id=source_id,
        records=records,
        gaps=gaps,
        taxon_keys=taxon_keys,
        raw_artifacts=raw_artifacts,
        requested_species=list(species_names),
        occurrence_limit=occurrence_limit,
        occurrence_page_size=occurrence_page_size,
        occurrence_workers=occurrence_workers,
        total_results=total_results,
        page_count=page_count,
    )
