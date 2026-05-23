from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Callable
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


class GBIFClient:
    def __init__(self, fetch_json: Callable[[str], dict[str, object]] | None = None):
        self.fetch_json = fetch_json or self._fetch_json

    def species_match(self, species: str) -> tuple[str, dict[str, object]]:
        url = f"{GBIF_API_BASE}/v2/species/match?{urlencode({'name': species})}"
        return url, self.fetch_json(url)

    def occurrence_search(self, taxon_key: int, limit: int) -> tuple[str, dict[str, object]]:
        params = {"taxonKey": taxon_key, "limit": limit}
        url = f"{GBIF_API_BASE}/v1/occurrence/search?{urlencode(params)}"
        return url, self.fetch_json(url)

    @staticmethod
    def _fetch_json(url: str) -> dict[str, object]:
        request = Request(url, headers={"User-Agent": "ask-insects/0.1"})
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
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
) -> EvidenceRecord:
    taxon_key = int(match_payload["usageKey"])
    canonical = _canonical_species(species, match_payload)
    gbif_url = f"{GBIF_WEB_BASE}/species/{taxon_key}"
    return EvidenceRecord(
        record_id=f"gbif:taxon:{taxon_key}",
        lane="taxonomy",
        source=GBIF_SOURCE_ID,
        title=canonical,
        text=_taxonomy_text(match_payload),
        species=canonical,
        url=gbif_url,
        media_url=None,
        provenance=Provenance(
            source_id=GBIF_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#species/match?name={species}",
            retrieved_at=retrieved_at,
            license="GBIF API metadata",
            source_url=match_url,
        ),
    )


def occurrence_record(
    occurrence: dict[str, object],
    *,
    species: str,
    occurrence_url: str,
    raw_path: Path,
    retrieved_at: str,
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
        record_id=f"gbif:occurrence:{key}",
        lane="observations",
        source=GBIF_SOURCE_ID,
        title=f"{scientific_name} occurrence {key}",
        text=text,
        species=scientific_name,
        url=gbif_url,
        media_url=_media_url(occurrence),
        provenance=Provenance(
            source_id=GBIF_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#occurrence/{key}",
            retrieved_at=retrieved_at,
            license=str(occurrence.get("license") or "GBIF occurrence license not supplied"),
            source_url=gbif_url if not occurrence_url else gbif_url,
        ),
    )


def fetch_gbif_records(
    species_names: list[str] | tuple[str, ...],
    *,
    raw_dir: Path,
    occurrence_limit: int = 3,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
) -> GBIFBuildResult:
    retrieved = retrieved_at or utc_now()
    client = GBIFClient(fetch_json)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    taxon_keys: dict[str, int] = {}
    raw_artifacts: list[str] = []

    for species in species_names:
        safe_name = safe_species_name(species)
        match_url, match_payload = client.species_match(species)
        match_path = write_raw_json(raw_dir, f"{safe_name}_match.json", match_payload)
        raw_artifacts.append(match_path.as_posix())

        usage_key = match_payload.get("usageKey")
        if not usage_key:
            gaps.append({"source": GBIF_SOURCE_ID, "lane": "taxonomy", "species": species, "reason": "GBIF did not match this species name."})
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
            )
        )

        occurrence_url, occurrence_payload = client.occurrence_search(taxon_key, occurrence_limit)
        occurrence_path = write_raw_json(raw_dir, f"{safe_name}_occurrences.json", occurrence_payload)
        raw_artifacts.append(occurrence_path.as_posix())
        occurrence_results = occurrence_payload.get("results")
        if not isinstance(occurrence_results, list) or not occurrence_results:
            gaps.append({"source": GBIF_SOURCE_ID, "lane": "observations", "species": species, "reason": "GBIF returned no occurrence records for this species."})
            continue
        for occurrence in occurrence_results:
            if isinstance(occurrence, dict) and occurrence.get("key"):
                records.append(
                    occurrence_record(
                        occurrence,
                        species=_canonical_species(species, match_payload),
                        occurrence_url=occurrence_url,
                        raw_path=occurrence_path,
                        retrieved_at=retrieved,
                    )
                )

    return GBIFBuildResult(
        source_id=GBIF_SOURCE_ID,
        records=records,
        gaps=gaps,
        taxon_keys=taxon_keys,
        raw_artifacts=raw_artifacts,
        requested_species=list(species_names),
        occurrence_limit=occurrence_limit,
    )
