from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import time
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


INATURALIST_SOURCE_ID = "inaturalist_api"
INATURALIST_API_BASE = "https://api.inaturalist.org/v1"
DEFAULT_INATURALIST_SPECIES = ("Aedes aegypti",)


@dataclass(frozen=True)
class INaturalistBuildResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_species: list[str]
    place: str | None
    observation_limit: int
    page_size: int
    delay_seconds: float
    total_results: dict[str, int]


class INaturalistClient:
    def __init__(self, fetch_json: Callable[[str], dict[str, object]] | None = None):
        self.fetch_json = fetch_json or self._fetch_json

    def observations(self, species: str, *, place: str | None, page: int, page_size: int) -> tuple[str, dict[str, object]]:
        params = {
            "taxon_name": species,
            "page": page,
            "per_page": page_size,
            "photos": "true",
            "photo_licensed": "true",
            "order": "desc",
            "order_by": "observed_on",
        }
        if place:
            params["q"] = place
        url = f"{INATURALIST_API_BASE}/observations?{urlencode(params)}"
        return url, self.fetch_json(url)

    @staticmethod
    def _fetch_json(url: str) -> dict[str, object]:
        request = Request(url, headers={"User-Agent": "ask-insects/0.1"})
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"iNaturalist returned non-object JSON for {url}")
        return payload


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_name(value: str | None) -> str:
    if not value:
        return "anywhere"
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_") or "anywhere"


def write_raw_json(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _taxon_name(observation: dict[str, object], fallback: str) -> str:
    taxon = observation.get("taxon")
    if isinstance(taxon, dict) and taxon.get("name"):
        return str(taxon["name"])
    return fallback


def _photo(observation: dict[str, object]) -> dict[str, object] | None:
    photos = observation.get("photos")
    if not isinstance(photos, list):
        return None
    for item in photos:
        if isinstance(item, dict) and item.get("url"):
            return item
    return None


def _photo_url(photo: dict[str, object]) -> str:
    return str(photo["url"])


def _observation_url(observation: dict[str, object]) -> str:
    if observation.get("uri"):
        return str(observation["uri"])
    return f"https://www.inaturalist.org/observations/{observation['id']}"


def observation_record(
    observation: dict[str, object],
    photo: dict[str, object],
    *,
    species: str,
    query_url: str,
    raw_path: Path,
    retrieved_at: str,
) -> EvidenceRecord:
    observation_id = int(observation["id"])
    taxon_name = _taxon_name(observation, species)
    observed_on = observation.get("observed_on") or "unknown date"
    place_guess = observation.get("place_guess") or "unknown place"
    url = _observation_url(observation)
    photo_url = _photo_url(photo)
    license_code = str(photo.get("license_code") or observation.get("license_code") or "license not supplied")
    text = f"iNaturalist observation of {taxon_name} at {place_guess}, observed on {observed_on}, with a licensed photo."
    return EvidenceRecord(
        record_id=f"inat:observation:{observation_id}",
        lane="observations",
        source=INATURALIST_SOURCE_ID,
        title=f"{taxon_name} iNaturalist observation {observation_id}",
        text=text,
        species=taxon_name,
        url=url,
        media_url=photo_url,
        provenance=Provenance(
            source_id=INATURALIST_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#observations/{observation_id}",
            retrieved_at=retrieved_at,
            license=license_code,
            source_url=query_url,
        ),
        payload={
            "raw_observation": observation,
            "raw_photo": photo,
            "query_url": query_url,
        },
    )


def media_record(
    observation: dict[str, object],
    photo: dict[str, object],
    *,
    species: str,
    raw_path: Path,
    retrieved_at: str,
) -> EvidenceRecord:
    observation_id = int(observation["id"])
    photo_id = str(photo.get("id") or observation_id)
    taxon_name = _taxon_name(observation, species)
    place_guess = observation.get("place_guess") or "unknown place"
    url = _observation_url(observation)
    photo_url = _photo_url(photo)
    license_code = str(photo.get("license_code") or observation.get("license_code") or "license not supplied")
    attribution = photo.get("attribution")
    attribution_text = f" Attribution: {attribution}." if attribution else ""
    return EvidenceRecord(
        record_id=f"inat:media:{photo_id}",
        lane="media",
        source=INATURALIST_SOURCE_ID,
        title=f"{taxon_name} iNaturalist still image {photo_id}",
        text=f"iNaturalist still image for {taxon_name} at {place_guess}, from observation {observation_id}.{attribution_text}",
        species=taxon_name,
        url=url,
        media_url=photo_url,
        provenance=Provenance(
            source_id=INATURALIST_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#observations/{observation_id}/photos/{photo_id}",
            retrieved_at=retrieved_at,
            license=license_code,
            source_url=url,
        ),
        payload={
            "raw_observation": observation,
            "raw_photo": photo,
        },
    )


def fetch_inaturalist_records(
    species_names: list[str] | tuple[str, ...],
    *,
    raw_dir: Path,
    place: str | None = None,
    observation_limit: int = 10,
    page_size: int = 200,
    delay_seconds: float = 0.0,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
) -> INaturalistBuildResult:
    retrieved = retrieved_at or utc_now()
    client = INaturalistClient(fetch_json)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    total_results: dict[str, int] = {}
    seen_observations: set[str] = set()
    seen_media: set[str] = set()
    page_size = max(1, min(int(page_size), 200))
    observation_limit = max(0, int(observation_limit))

    for species in species_names:
        species_indexed_observations = 0
        species_seen_results = 0
        species_had_results = False
        photo_seen = False
        page = 1

        while species_indexed_observations < observation_limit:
            if page > 1 and delay_seconds > 0:
                time.sleep(delay_seconds)
            query_url, payload = client.observations(species, place=place, page=page, page_size=page_size)
            raw_path = write_raw_json(
                raw_dir,
                f"{safe_name(species)}_{safe_name(place)}_page_{page:03d}.json",
                payload,
            )
            raw_artifacts.append(raw_path.as_posix())
            total_results[species] = int(payload.get("total_results") or payload.get("total_count") or 0)
            results = payload.get("results")
            if not isinstance(results, list) or not results:
                break
            species_had_results = True
            species_seen_results += len(results)

            for observation in results:
                if species_indexed_observations >= observation_limit:
                    break
                if not isinstance(observation, dict) or not observation.get("id"):
                    continue
                observation_id = str(observation["id"])
                if observation_id in seen_observations:
                    continue
                photo = _photo(observation)
                if not photo:
                    continue
                photo_id = str(photo.get("id") or observation_id)
                if photo_id in seen_media:
                    continue
                photo_seen = True
                seen_observations.add(observation_id)
                seen_media.add(photo_id)
                records.append(
                    observation_record(
                        observation,
                        photo,
                        species=species,
                        query_url=query_url,
                        raw_path=raw_path,
                        retrieved_at=retrieved,
                    )
                )
                records.append(
                    media_record(
                        observation,
                        photo,
                        species=species,
                        raw_path=raw_path,
                        retrieved_at=retrieved,
                    )
                )
                species_indexed_observations += 1

            if species_seen_results >= total_results.get(species, 0):
                break
            page += 1

        if not species_had_results:
            gaps.append({"source": INATURALIST_SOURCE_ID, "lane": "observations", "species": species, "place": place, "reason": "iNaturalist returned no observations for this query."})
            continue

        if not photo_seen or species_indexed_observations == 0:
            gaps.append({"source": INATURALIST_SOURCE_ID, "lane": "media", "species": species, "place": place, "reason": "iNaturalist observations did not include usable licensed photos."})

    return INaturalistBuildResult(
        source_id=INATURALIST_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_species=list(species_names),
        place=place,
        observation_limit=observation_limit,
        page_size=page_size,
        delay_seconds=delay_seconds,
        total_results=total_results,
    )
