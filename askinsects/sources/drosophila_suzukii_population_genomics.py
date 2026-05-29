from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID = "drosophila_suzukii_population_genomics"
SPECIES = "Drosophila suzukii"
COMMON_NAME = "spotted wing drosophila"
USER_AGENT = "AskInsects/0.1 source-plane"
NCBI_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_SEARCH_TERM = (
    '("Drosophila suzukii"[Organism]) AND '
    "(population genomics OR population samples OR pool-seq OR whole genome sequence OR genome sequencing)"
)


@dataclass(frozen=True)
class DrosophilaSuzukiiPopulationGenomicsResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    reported_count: int


def _default_fetch_json(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    return payload if isinstance(payload, dict) else {}


def _write_json(raw_dir: Path, filename: str, payload: object) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def _search_url(term: str, limit: int) -> str:
    return f"{NCBI_EUTILS_BASE}/esearch.fcgi?" + urlencode(
        {
            "db": "bioproject",
            "term": term,
            "retmode": "json",
            "retmax": max(1, int(limit)),
            "sort": "date",
            "tool": "ask-insects",
        }
    )


def _summary_url(ids: list[str]) -> str:
    return f"{NCBI_EUTILS_BASE}/esummary.fcgi?" + urlencode(
        {"db": "bioproject", "id": ",".join(ids), "retmode": "json", "tool": "ask-insects"}
    )


def _ids(payload: dict[str, object]) -> tuple[list[str], int]:
    result = payload.get("esearchresult")
    if not isinstance(result, dict):
        return [], 0
    ids = result.get("idlist")
    try:
        count = int(str(result.get("count") or 0))
    except ValueError:
        count = 0
    return [str(item) for item in ids if item] if isinstance(ids, list) else [], count


def _summary_items(payload: dict[str, object]) -> list[tuple[str, dict[str, object]]]:
    result = payload.get("result")
    if not isinstance(result, dict):
        return []
    uids = result.get("uids")
    if not isinstance(uids, list):
        return []
    items: list[tuple[str, dict[str, object]]] = []
    for uid in uids:
        item = result.get(str(uid))
        if isinstance(item, dict):
            items.append((str(uid), item))
    return items


def _field(item: dict[str, object], *names: str) -> str:
    lowered = {str(key).lower(): value for key, value in item.items()}
    for name in names:
        value = item.get(name)
        if value is None:
            value = lowered.get(name.lower())
        if value is not None:
            return _clean(value)
    return ""


def _record(uid: str, item: dict[str, object], *, raw_path: Path, retrieved_at: str, source_url: str) -> EvidenceRecord:
    accession = _field(item, "project_acc", "Project_Acc", "accession") or uid
    title = _field(item, "project_title", "project_name", "title", "Project_Title") or f"BioProject {accession}"
    description = _field(item, "project_description", "description", "Project_Description")
    data_type = _field(item, "project_data_type", "data_type")
    target_scope = _field(item, "project_target_scope", "target_scope")
    submitter = _field(item, "submitter_organization", "submitter")
    registration_date = _field(item, "registration_date", "registration")
    text = (
        f"NCBI BioProject population-genomics record {accession} for {SPECIES} ({COMMON_NAME}). "
        f"Title: {title}. Data type: {data_type or 'not supplied'}. "
        f"Target scope: {target_scope or 'not supplied'}. Submitter: {submitter or 'not supplied'}. "
        f"Registration date: {registration_date or 'not supplied'}. Description: {description or 'not supplied'}."
    )
    return EvidenceRecord(
        record_id=f"swd_population_genomics:bioproject:{accession}",
        lane="genome_features",
        source=DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID,
        title=f"Drosophila suzukii population genomics BioProject {accession}: {title}",
        text=text,
        species=SPECIES,
        url=f"https://www.ncbi.nlm.nih.gov/bioproject/{accession}",
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#result/{uid}",
            retrieved_at=retrieved_at,
            license="NCBI E-utilities public metadata; source terms apply",
            source_url=source_url,
        ),
        payload={
            "atom_type": "swd_population_genomics_bioproject",
            "uid": uid,
            "accession": accession,
            "title": title,
            "description": description,
            "data_type": data_type,
            "target_scope": target_scope,
            "submitter": submitter,
            "registration_date": registration_date,
            "raw_summary": item,
        },
    )


def fetch_drosophila_suzukii_population_genomics_records(
    *,
    raw_dir: Path,
    retrieved_at: str,
    fetch_json=None,
    limit: int = 100,
    term: str = DEFAULT_SEARCH_TERM,
) -> DrosophilaSuzukiiPopulationGenomicsResult:
    fetch = fetch_json or _default_fetch_json
    raw_dir.mkdir(parents=True, exist_ok=True)
    requested_urls: list[str] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []

    search = _search_url(term, limit)
    requested_urls.append(search)
    try:
        search_payload = fetch(search)
    except Exception as exc:
        return DrosophilaSuzukiiPopulationGenomicsResult(
            source_id=DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID,
            records=[],
            gaps=[
                {
                    "source": DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID,
                    "lane": "genome_features",
                    "reason": "swd_population_genomics_bioproject_search_failed",
                    "url": search,
                    "error": str(exc),
                    "retrieved_at": retrieved_at,
                }
            ],
            raw_artifacts=[],
            requested_urls=requested_urls,
            reported_count=0,
        )
    search_path = _write_json(raw_dir, "ncbi_bioproject_population_genomics_search.json", search_payload)
    raw_artifacts.append(search_path.as_posix())
    ids, reported_count = _ids(search_payload)
    if reported_count > len(ids):
        gaps.append(
            {
                "source": DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID,
                "lane": "genome_features",
                "reason": "swd_population_genomics_bioproject_limit_applied",
                "url": search,
                "reported_count": reported_count,
                "fetched_count": len(ids),
                "limit": limit,
                "retrieved_at": retrieved_at,
            }
        )
    if not ids:
        gaps.append(
            {
                "source": DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID,
                "lane": "genome_features",
                "reason": "swd_population_genomics_bioproject_search_empty",
                "url": search,
                "retrieved_at": retrieved_at,
            }
        )
        return DrosophilaSuzukiiPopulationGenomicsResult(
            source_id=DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID,
            records=[],
            gaps=gaps,
            raw_artifacts=raw_artifacts,
            requested_urls=requested_urls,
            reported_count=reported_count,
        )
    summary = _summary_url(ids)
    requested_urls.append(summary)
    try:
        summary_payload = fetch(summary)
    except Exception as exc:
        gaps.append(
            {
                "source": DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID,
                "lane": "genome_features",
                "reason": "swd_population_genomics_bioproject_summary_failed",
                "url": summary,
                "ids": ids,
                "error": str(exc),
                "retrieved_at": retrieved_at,
            }
        )
        return DrosophilaSuzukiiPopulationGenomicsResult(
            source_id=DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID,
            records=[],
            gaps=gaps,
            raw_artifacts=raw_artifacts,
            requested_urls=requested_urls,
            reported_count=reported_count,
        )
    summary_path = _write_json(raw_dir, "ncbi_bioproject_population_genomics_summary.json", summary_payload)
    raw_artifacts.append(summary_path.as_posix())
    records = [
        _record(uid, item, raw_path=summary_path, retrieved_at=retrieved_at, source_url=summary)
        for uid, item in _summary_items(summary_payload)
    ]
    if not records:
        gaps.append(
            {
                "source": DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID,
                "lane": "genome_features",
                "reason": "swd_population_genomics_no_queryable_records_built",
                "url": summary,
                "ids": ids,
                "retrieved_at": retrieved_at,
            }
        )
    return DrosophilaSuzukiiPopulationGenomicsResult(
        source_id=DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        reported_count=reported_count,
    )
