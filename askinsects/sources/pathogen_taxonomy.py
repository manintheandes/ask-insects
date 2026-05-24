from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


PATHOGEN_TAXONOMY_SOURCE_ID = "aedes_pathogen_taxonomy"
NCBI_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
USER_AGENT = "AskInsects/0.1 source-plane"


@dataclass(frozen=True)
class PathogenSpec:
    taxid: int
    display_name: str
    pathogen_group: str
    aedes_context: str


DEFAULT_PATHOGENS = (
    PathogenSpec(12637, "Dengue virus", "flavivirus", "core Aedes aegypti arbovirus"),
    PathogenSpec(64320, "Zika virus", "flavivirus", "core Aedes aegypti arbovirus"),
    PathogenSpec(37124, "Chikungunya virus", "alphavirus", "core Aedes aegypti arbovirus"),
    PathogenSpec(11089, "Yellow fever virus", "flavivirus", "core Aedes aegypti arbovirus"),
    PathogenSpec(11082, "West Nile virus", "flavivirus", "Aedes-relevant experimental vector-competence pathogen"),
    PathogenSpec(59301, "Mayaro virus", "alphavirus", "Aedes-relevant experimental vector-competence pathogen"),
)


@dataclass(frozen=True)
class PathogenTaxonomyResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_taxids: list[int]
    pathogen_count: int


class NCBITaxonomyClient:
    def __init__(self, fetch_json: Callable[[str], dict[str, object]] | None = None):
        self.fetch_json = fetch_json or self._fetch_json

    def summaries(self, taxids: list[int]) -> tuple[str, dict[str, object]]:
        params = {
            "db": "taxonomy",
            "id": ",".join(str(taxid) for taxid in taxids),
            "retmode": "json",
            "tool": "ask-insects",
        }
        url = f"{NCBI_EUTILS_BASE}/esummary.fcgi?{urlencode(params)}"
        return url, self.fetch_json(url)

    @staticmethod
    def _fetch_json(url: str) -> dict[str, object]:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"NCBI taxonomy endpoint returned non-object JSON for {url}")
        return payload


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_raw_json(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _taxonomy_url(taxid: int) -> str:
    return f"https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id={taxid}"


def _record_for_pathogen(
    spec: PathogenSpec,
    summary: dict[str, object],
    *,
    raw_path: Path,
    query_url: str,
    retrieved_at: str,
) -> EvidenceRecord:
    scientific_name = str(summary.get("scientificname") or spec.display_name)
    rank = str(summary.get("rank") or "unknown rank")
    division = str(summary.get("division") or summary.get("genbankdivision") or "unknown division")
    taxid = int(summary.get("taxid") or spec.taxid)
    text = (
        f"NCBI Taxonomy pathogen record for {scientific_name} (taxid {taxid}), {rank}, {division}. "
        f"Pathogen group: {spec.pathogen_group}. Aedes context: {spec.aedes_context}. "
        "Use this record as the pathogen identity anchor for Aedes aegypti vector-competence and public-health evidence."
    )
    return EvidenceRecord(
        record_id=f"pathogen:ncbi_taxonomy:{taxid}",
        lane="vector_competence",
        source=PATHOGEN_TAXONOMY_SOURCE_ID,
        title=f"Aedes aegypti pathogen taxonomy {scientific_name}",
        text=text,
        species="Aedes aegypti",
        url=_taxonomy_url(taxid),
        media_url=None,
        provenance=Provenance(
            source_id=PATHOGEN_TAXONOMY_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#taxonomy/{taxid}",
            retrieved_at=retrieved_at,
            license="NCBI Taxonomy public data; NCBI terms apply",
            source_url=query_url,
        ),
        payload={
            "taxid": taxid,
            "display_name": spec.display_name,
            "pathogen_group": spec.pathogen_group,
            "aedes_context": spec.aedes_context,
            "raw_summary": summary,
        },
    )


def fetch_pathogen_taxonomy_records(
    pathogen_specs: list[PathogenSpec] | tuple[PathogenSpec, ...] = DEFAULT_PATHOGENS,
    *,
    raw_dir: Path,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
) -> PathogenTaxonomyResult:
    retrieved = retrieved_at or utc_now()
    client = NCBITaxonomyClient(fetch_json)
    specs = list(pathogen_specs)
    taxids = [spec.taxid for spec in specs]
    gaps: list[dict[str, object]] = []
    records: list[EvidenceRecord] = []
    raw_artifacts: list[str] = []
    try:
        query_url, payload = client.summaries(taxids)
    except Exception as exc:
        return PathogenTaxonomyResult(
            source_id=PATHOGEN_TAXONOMY_SOURCE_ID,
            records=[],
            gaps=[
                {
                    "source": PATHOGEN_TAXONOMY_SOURCE_ID,
                    "lane": "vector_competence",
                    "reason": "ncbi_taxonomy_fetch_failed",
                    "requested_taxids": taxids,
                    "error": str(exc),
                    "retrieved_at": retrieved,
                }
            ],
            raw_artifacts=[],
            requested_taxids=taxids,
            pathogen_count=0,
        )

    raw_path = write_raw_json(raw_dir, "aedes_pathogen_taxonomy_esummary.json", payload)
    raw_artifacts.append(raw_path.as_posix())
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("NCBI taxonomy response missing result object")
    for spec in specs:
        summary = result.get(str(spec.taxid))
        if not isinstance(summary, dict):
            gaps.append(
                {
                    "source": PATHOGEN_TAXONOMY_SOURCE_ID,
                    "lane": "vector_competence",
                    "reason": "ncbi_taxonomy_taxid_missing",
                    "taxid": spec.taxid,
                    "retrieved_at": retrieved,
                }
            )
            continue
        records.append(
            _record_for_pathogen(
                spec,
                summary,
                raw_path=raw_path,
                query_url=query_url,
                retrieved_at=retrieved,
            )
        )

    return PathogenTaxonomyResult(
        source_id=PATHOGEN_TAXONOMY_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_taxids=taxids,
        pathogen_count=len(records),
    )
