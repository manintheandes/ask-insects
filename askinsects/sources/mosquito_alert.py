from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance
from askinsects.species import resolve_species


MOSQUITO_ALERT_SOURCE_ID = "mosquito_alert_gbif"
MOSQUITO_ALERT_DATASET_KEY = "1fef1ead-3d02-495e-8ff1-6aeb01123408"
MOSQUITO_ALERT_DATASET_DOI = "10.15470/t5a1os"
AEDES_AEGYPTI_TAXON_KEY = 1651891
GBIF_API_BASE = "https://api.gbif.org"
GBIF_WEB_BASE = "https://www.gbif.org"


@dataclass(frozen=True)
class MosquitoAlertBuildResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    dataset_key: str
    dataset_doi: str
    taxon_key: int
    occurrence_limit: int
    occurrence_page_size: int
    total_results: int
    page_count: int


class MosquitoAlertClient:
    def __init__(self, fetch_json: Callable[[str], dict[str, object]] | None = None):
        self.fetch_json = fetch_json or self._fetch_json

    def dataset(self) -> tuple[str, dict[str, object]]:
        url = f"{GBIF_API_BASE}/v1/dataset/{MOSQUITO_ALERT_DATASET_KEY}"
        return url, self.fetch_json(url)

    def occurrences(self, *, taxon_key: int, limit: int, offset: int) -> tuple[str, dict[str, object]]:
        params = {
            "datasetKey": MOSQUITO_ALERT_DATASET_KEY,
            "taxonKey": taxon_key,
            "mediaType": "StillImage",
            "basisOfRecord": "HUMAN_OBSERVATION",
            "limit": limit,
            "offset": offset,
        }
        url = f"{GBIF_API_BASE}/v1/occurrence/search?{urlencode(params)}"
        return url, self.fetch_json(url)

    @staticmethod
    def _fetch_json(url: str) -> dict[str, object]:
        request = Request(url, headers={"User-Agent": "ask-insects/0.1"})
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Mosquito Alert GBIF endpoint returned non-object JSON for {url}")
        return payload


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_raw_json(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _safe_id(value: object) -> str:
    text = str(value or "")
    safe = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return safe or hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _media_items(occurrence: dict[str, object]) -> list[dict[str, object]]:
    media = occurrence.get("media")
    if not isinstance(media, list):
        return []
    return [item for item in media if isinstance(item, dict) and item.get("identifier")]


def _country(occurrence: dict[str, object]) -> str:
    return str(occurrence.get("country") or occurrence.get("countryCode") or "unknown country")


def _scientific_name(occurrence: dict[str, object]) -> str:
    # Species-scoped by the query: GBIF occurrence search is filtered to
    # AEDES_AEGYPTI_TAXON_KEY (taxonKey), so this default is legitimate query scope.
    raw = occurrence.get("species") or occurrence.get("scientificName")
    return resolve_species(raw, scope="Aedes aegypti")


def _occurrence_url(key: int) -> str:
    return f"{GBIF_WEB_BASE}/occurrence/{key}"


def occurrence_record(
    occurrence: dict[str, object],
    *,
    query_url: str,
    raw_path: Path,
    retrieved_at: str,
) -> EvidenceRecord:
    key = int(occurrence["key"])
    scientific_name = _scientific_name(occurrence)
    country = _country(occurrence)
    event_date = occurrence.get("eventDate") or "unknown date"
    basis = occurrence.get("basisOfRecord") or "human observation"
    identified_by = occurrence.get("identifiedBy")
    image_count = len(_media_items(occurrence))
    identifier_text = f" Identified by: {identified_by}." if identified_by else ""
    return EvidenceRecord(
        record_id=f"mosquito_alert:observation:{key}",
        lane="observations",
        source=MOSQUITO_ALERT_SOURCE_ID,
        title=f"{scientific_name} Mosquito Alert observation {key}",
        text=(
            f"Mosquito Alert citizen-science observation of {scientific_name} in {country}, "
            f"event date {event_date}, basis {basis}, with {image_count} still image(s).{identifier_text}"
        ),
        species=scientific_name,
        url=_occurrence_url(key),
        media_url=str(_media_items(occurrence)[0]["identifier"]) if _media_items(occurrence) else None,
        provenance=Provenance(
            source_id=MOSQUITO_ALERT_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#occurrence/{key}",
            retrieved_at=retrieved_at,
            license=str(occurrence.get("license") or "GBIF occurrence license not supplied"),
            source_url=_occurrence_url(key),
        ),
        payload={
            "raw_occurrence": occurrence,
            "query_url": query_url,
            "dataset_key": MOSQUITO_ALERT_DATASET_KEY,
            "dataset_doi": MOSQUITO_ALERT_DATASET_DOI,
        },
    )


def media_record(
    occurrence: dict[str, object],
    media: dict[str, object],
    *,
    media_index: int,
    raw_path: Path,
    retrieved_at: str,
) -> EvidenceRecord:
    key = int(occurrence["key"])
    scientific_name = _scientific_name(occurrence)
    country = _country(occurrence)
    identifier = str(media["identifier"])
    media_id = _safe_id(media.get("identifier") or f"{key}-{media_index}")
    attribution = media.get("creator") or media.get("rightsHolder")
    attribution_text = f" Attribution: {attribution}." if attribution else ""
    return EvidenceRecord(
        record_id=f"mosquito_alert:media:{key}:{media_id}",
        lane="media",
        source=MOSQUITO_ALERT_SOURCE_ID,
        title=f"{scientific_name} Mosquito Alert still image {key}",
        text=(
            f"Mosquito Alert still image for {scientific_name} from citizen-science observation {key} "
            f"in {country}.{attribution_text}"
        ),
        species=scientific_name,
        url=_occurrence_url(key),
        media_url=identifier,
        provenance=Provenance(
            source_id=MOSQUITO_ALERT_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#occurrence/{key}/media/{media_index}",
            retrieved_at=retrieved_at,
            license=str(media.get("license") or occurrence.get("license") or "media license not supplied"),
            source_url=identifier,
        ),
        payload={
            "raw_occurrence": occurrence,
            "raw_media": media,
            "dataset_key": MOSQUITO_ALERT_DATASET_KEY,
            "dataset_doi": MOSQUITO_ALERT_DATASET_DOI,
        },
    )


def fetch_mosquito_alert_records(
    *,
    raw_dir: Path,
    occurrence_limit: int = 1000,
    occurrence_page_size: int = 300,
    taxon_key: int = AEDES_AEGYPTI_TAXON_KEY,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
) -> MosquitoAlertBuildResult:
    if occurrence_limit < 0:
        raise ValueError("occurrence_limit must be zero or greater")
    if occurrence_page_size <= 0:
        raise ValueError("occurrence_page_size must be greater than zero")

    retrieved = retrieved_at or utc_now()
    page_size = max(1, min(int(occurrence_page_size), 300))
    client = MosquitoAlertClient(fetch_json)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []

    dataset_url, dataset_payload = client.dataset()
    dataset_path = write_raw_json(raw_dir, "dataset.json", dataset_payload)
    raw_artifacts.append(dataset_path.as_posix())

    total_results = 0
    page_count = 0
    target_count = int(occurrence_limit)
    offset = 0
    saw_occurrence = False
    while offset < target_count:
        limit = min(page_size, target_count - offset)
        occurrence_url, occurrence_payload = client.occurrences(taxon_key=taxon_key, limit=limit, offset=offset)
        total_results = int(occurrence_payload.get("count") or total_results)
        if total_results:
            target_count = min(target_count, total_results)
        occurrence_path = write_raw_json(raw_dir, f"aedes_aegypti_occurrences_offset_{offset:06d}.json", occurrence_payload)
        raw_artifacts.append(occurrence_path.as_posix())
        page_count += 1

        results = occurrence_payload.get("results")
        if not isinstance(results, list) or not results:
            break
        for occurrence in results:
            if not isinstance(occurrence, dict) or not occurrence.get("key"):
                continue
            saw_occurrence = True
            records.append(
                occurrence_record(
                    occurrence,
                    query_url=occurrence_url,
                    raw_path=occurrence_path,
                    retrieved_at=retrieved,
                )
            )
            for index, media in enumerate(_media_items(occurrence), start=1):
                records.append(media_record(occurrence, media, media_index=index, raw_path=occurrence_path, retrieved_at=retrieved))
        offset += len(results)

    if not saw_occurrence:
        gaps.append(
            {
                "source": MOSQUITO_ALERT_SOURCE_ID,
                "lane": "observations",
                "dataset_key": MOSQUITO_ALERT_DATASET_KEY,
                "taxon_key": taxon_key,
                "reason": "Mosquito Alert GBIF dataset returned no Aedes aegypti occurrence records.",
            }
        )

    return MosquitoAlertBuildResult(
        source_id=MOSQUITO_ALERT_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        dataset_key=MOSQUITO_ALERT_DATASET_KEY,
        dataset_doi=MOSQUITO_ALERT_DATASET_DOI,
        taxon_key=taxon_key,
        occurrence_limit=occurrence_limit,
        occurrence_page_size=page_size,
        total_results=total_results,
        page_count=page_count,
    )
