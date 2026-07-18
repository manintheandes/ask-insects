from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import re
from typing import Callable

from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.literature import (
    OPENALEX_API_BASE,
    abstract_from_inverted_index,
    fetch_json_url,
    literature_record,
    write_raw_json,
)


PLUTELLA_XYLOSTELLA_LITERATURE_SOURCE_ID = "plutella_xylostella_literature"
PLUTELLA_XYLOSTELLA_SPECIES = "Plutella xylostella"
PLUTELLA_XYLOSTELLA_OPENALEX_WORK_IDS = (
    "W1994548084",  # olfaction and vision in host-plant finding
    "W2114561940",  # host selection, olfaction, oviposition, and fecundity
    "W4409241407",  # antennal responses and field attractants from Brassica volatiles
    "W4413460540",  # four-choice semiochemical assay and field attract-and-kill
    "W4391482378",  # intercropping, VOCs, adults, larvae, and crop damage
    "W4387738540",  # citronella laboratory and field endpoints
    "W4407297126",  # adult diel locomotor behavior
    "W1996826081",  # isothiocyanates that stimulate oviposition
    "W2164349268",  # phylloplane waxiness and oviposition
    "W3093961030",  # larva-induced plant volatiles and female attraction
)


@dataclass(frozen=True)
class PlutellaXylostellaLiteratureResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]


def _names_exact_species(work: dict[str, object]) -> bool:
    title = str(work.get("display_name") or "")
    abstract = abstract_from_inverted_index(work.get("abstract_inverted_index"))  # type: ignore[arg-type]
    text = f"{title} {abstract}".casefold()
    return "plutella xylostella" in text or "diamondback moth" in text


def fetch_plutella_xylostella_literature_records(
    *,
    raw_dir: Path,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str,
) -> PlutellaXylostellaLiteratureResult:
    fetcher = fetch_json or fetch_json_url
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []

    for work_id in PLUTELLA_XYLOSTELLA_OPENALEX_WORK_IDS:
        url = f"{OPENALEX_API_BASE}/works/{work_id}"
        requested_urls.append(url)
        try:
            work = fetcher(url)
        except Exception as exc:
            gaps.append(
                {
                    "source": PLUTELLA_XYLOSTELLA_LITERATURE_SOURCE_ID,
                    "lane": "literature",
                    "reason": "openalex_exact_work_fetch_failed",
                    "locator": url,
                    "openalex_work_id": work_id,
                    "error": str(exc),
                    "retrieved_at": retrieved_at,
                }
            )
            continue

        raw_path = write_raw_json(
            raw_dir,
            f"{work_id}.json",
            {"retrieved_at": retrieved_at, "request_url": url, "work": work},
        )
        raw_artifacts.append(raw_path.as_posix())
        if not _names_exact_species(work):
            gaps.append(
                {
                    "source": PLUTELLA_XYLOSTELLA_LITERATURE_SOURCE_ID,
                    "lane": "literature",
                    "reason": "exact_species_not_confirmed",
                    "locator": f"{raw_path.as_posix()}#jsonpath=$.work",
                    "openalex_work_id": work_id,
                    "retrieved_at": retrieved_at,
                }
            )
            continue

        base_record = literature_record(
            work,
            raw_path,
            retrieved_at,
            ["curated_exact_species_work"],
            PLUTELLA_XYLOSTELLA_SPECIES,
            skip_pubmed=True,
            search_term=PLUTELLA_XYLOSTELLA_SPECIES,
            candidate_status="human_reviewed_exact_species",
        )
        original_url = str(base_record.url or work.get("id") or url)
        if re.fullmatch(r"10\.\S+/\S+", original_url, flags=re.IGNORECASE):
            source_url = f"https://doi.org/{original_url}"
        else:
            source_url = original_url
        records.append(
            replace(
                base_record,
                record_id=f"dbm:openalex:{work_id}",
                source=PLUTELLA_XYLOSTELLA_LITERATURE_SOURCE_ID,
                species=PLUTELLA_XYLOSTELLA_SPECIES,
                provenance=Provenance(
                    source_id=PLUTELLA_XYLOSTELLA_LITERATURE_SOURCE_ID,
                    locator=f"{raw_path.as_posix()}#jsonpath=$.work",
                    retrieved_at=retrieved_at,
                    license=base_record.provenance.license,
                    source_url=source_url,
                ),
                payload={
                    **(base_record.payload or {}),
                    "curation_status": "human_reviewed_exact_species",
                    "openalex_work_id": work_id,
                },
            )
        )

    return PlutellaXylostellaLiteratureResult(
        source_id=PLUTELLA_XYLOSTELLA_LITERATURE_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
    )
