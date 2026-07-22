from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


ANOPHELES_PATHOGEN_TAXONOMY_SOURCE_ID = "anopheles_pathogen_taxonomy"
NCBI_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
USER_AGENT = "AskInsects/0.1 source-plane"


@dataclass(frozen=True)
class AnophelesPathogenSpec:
    taxid: int
    display_name: str
    evidence_role: str


ANOPHELES_PATHOGENS = (
    AnophelesPathogenSpec(5833, "Plasmodium falciparum", "major human malaria parasite"),
    AnophelesPathogenSpec(5855, "Plasmodium vivax", "major human malaria parasite"),
    AnophelesPathogenSpec(5858, "Plasmodium malariae", "human malaria parasite"),
    AnophelesPathogenSpec(36330, "Plasmodium ovale", "human malaria parasite species complex"),
    AnophelesPathogenSpec(864141, "Plasmodium ovale curtisi", "human malaria parasite subspecies"),
    AnophelesPathogenSpec(864142, "Plasmodium ovale wallikeri", "human malaria parasite subspecies"),
    AnophelesPathogenSpec(5850, "Plasmodium knowlesi", "zoonotic human malaria parasite"),
    AnophelesPathogenSpec(5821, "Plasmodium berghei", "laboratory malaria model parasite"),
    AnophelesPathogenSpec(5861, "Plasmodium yoelii", "laboratory malaria model parasite"),
    AnophelesPathogenSpec(5827, "Plasmodium cynomolgi", "primate malaria and vivax-model parasite"),
)


@dataclass(frozen=True)
class AnophelesPathogenTaxonomyResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_taxids: list[int]
    pathogen_count: int
    query_url: str | None


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fetch_json(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("NCBI taxonomy endpoint returned non-object JSON")
    return payload


def fetch_anopheles_pathogen_taxonomy(
    *,
    raw_dir: Path,
    pathogen_specs: tuple[AnophelesPathogenSpec, ...] | list[AnophelesPathogenSpec] = ANOPHELES_PATHOGENS,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
) -> AnophelesPathogenTaxonomyResult:
    retrieved = retrieved_at or _utc_now()
    specs = list(pathogen_specs)
    taxids = [spec.taxid for spec in specs]
    query_url = f"{NCBI_EUTILS_BASE}/esummary.fcgi?{urlencode({'db': 'taxonomy', 'id': ','.join(map(str, taxids)), 'retmode': 'json', 'tool': 'ask-insects'})}"
    try:
        payload = (fetch_json or _fetch_json)(query_url)
    except Exception as exc:
        return AnophelesPathogenTaxonomyResult(
            source_id=ANOPHELES_PATHOGEN_TAXONOMY_SOURCE_ID,
            records=[],
            gaps=[{
                "source": ANOPHELES_PATHOGEN_TAXONOMY_SOURCE_ID,
                "lane": "vector_competence",
                "reason": "ncbi_taxonomy_fetch_failed",
                "requested_taxids": taxids,
                "source_url": query_url,
                "error": str(exc),
            }],
            raw_artifacts=[], requested_taxids=taxids, pathogen_count=0, query_url=query_url,
        )

    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / "anopheles_pathogen_taxonomy_esummary.json"
    raw_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("NCBI taxonomy response missing result object")

    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    for spec in specs:
        summary = result.get(str(spec.taxid))
        if not isinstance(summary, dict):
            gaps.append({
                "source": ANOPHELES_PATHOGEN_TAXONOMY_SOURCE_ID,
                "lane": "vector_competence",
                "reason": "ncbi_taxonomy_taxid_missing",
                "taxid": spec.taxid,
                "source_url": query_url,
                "locator": f"{raw_path.as_posix()}#taxonomy/{spec.taxid}",
            })
            continue
        taxid = int(summary.get("taxid") or spec.taxid)
        scientific_name = str(summary.get("scientificname") or spec.display_name)
        rank = str(summary.get("rank") or "unknown rank")
        division = str(summary.get("division") or summary.get("genbankdivision") or "unknown division")
        records.append(EvidenceRecord(
            record_id=f"anopheles_pathogen:ncbi_taxonomy:{taxid}",
            lane="vector_competence",
            source=ANOPHELES_PATHOGEN_TAXONOMY_SOURCE_ID,
            title=f"Anopheles pathogen taxonomy: {scientific_name}",
            text=(
                f"NCBI Taxonomy record for {scientific_name} (taxid {taxid}), {rank}, {division}. "
                f"Evidence role: {spec.evidence_role}. This is a pathogen identity anchor for Anopheles research; "
                "it does not by itself prove vector competence, transmission, or epidemiological importance."
            ),
            species=scientific_name,
            url=f"https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id={taxid}",
            media_url=None,
            provenance=Provenance(
                source_id=ANOPHELES_PATHOGEN_TAXONOMY_SOURCE_ID,
                locator=f"{raw_path.as_posix()}#taxonomy/{taxid}",
                retrieved_at=retrieved,
                license="NCBI Taxonomy public data; NCBI terms apply",
                source_url=query_url,
            ),
            payload={
                "record_type": "anopheles_pathogen_taxonomy",
                "taxid": taxid,
                "display_name": spec.display_name,
                "evidence_role": spec.evidence_role,
                "raw_summary": summary,
            },
        ))

    return AnophelesPathogenTaxonomyResult(
        source_id=ANOPHELES_PATHOGEN_TAXONOMY_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=[raw_path.as_posix()],
        requested_taxids=taxids,
        pathogen_count=len(records),
        query_url=query_url,
    )
