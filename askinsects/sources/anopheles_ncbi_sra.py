from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import time
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance

from .anopheles_ncbi_biosamples import ANOPHELES_NCBI_BIOSAMPLES_TARGET_TAXA


ANOPHELES_NCBI_SRA_SOURCE_ID = "anopheles_ncbi_sra_runs"
NCBI_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
USER_AGENT = "AskInsects/0.1 source-plane"


@dataclass(frozen=True)
class AnophelesNCBISRAResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    target_taxa: tuple[str, ...]
    reported_total_counts: dict[str, int]
    fetched_experiment_counts: dict[str, int]
    run_counts: dict[str, int]
    experiment_limit_per_taxon: int
    page_size: int


class NCBISRAClient:
    def __init__(self, fetch_json: Callable[[str], dict[str, object]] | None = None):
        self.fetch_json = fetch_json or self._fetch_json

    @staticmethod
    def _fetch_json(url: str) -> dict[str, object]:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        for attempt in range(3):
            try:
                with urlopen(request, timeout=120) as response:
                    payload = json.loads(response.read().decode("utf-8", "replace"))
                break
            except HTTPError as exc:
                if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                    raise
                time.sleep(1.0 + attempt)
        if not isinstance(payload, dict):
            raise ValueError(f"NCBI SRA endpoint returned non-object JSON for {url}")
        return payload

    def esearch(self, *, species: str, retstart: int, retmax: int) -> tuple[str, dict[str, object]]:
        params = {
            "db": "sra",
            "term": f'"{species}"[Organism]',
            "retmode": "json",
            "retstart": retstart,
            "retmax": retmax,
            "sort": "modification date",
            "tool": "ask-insects",
        }
        url = f"{NCBI_EUTILS_BASE}/esearch.fcgi?{urlencode(params)}"
        return url, self.fetch_json(url)

    def esummary(self, ids: list[str]) -> tuple[str, dict[str, object]]:
        params = {"db": "sra", "id": ",".join(ids), "retmode": "json", "tool": "ask-insects"}
        url = f"{NCBI_EUTILS_BASE}/esummary.fcgi?{urlencode(params)}"
        return url, self.fetch_json(url)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")


def _write_raw(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _field(item: dict[str, object], *names: str) -> object:
    lowered = {str(key).lower(): value for key, value in item.items()}
    for name in names:
        if name in item:
            return item[name]
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _xml_text(xml: str, tag: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", xml, flags=re.IGNORECASE | re.DOTALL)
    return _clean(re.sub(r"<[^>]+>", " ", match.group(1))) if match else ""


def _xml_attr(xml: str, tag: str, attr: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*\s{attr}=[\"']([^\"']+)[\"']", xml, flags=re.IGNORECASE)
    return _clean(match.group(1)) if match else ""


def _run_attrs(runs_xml: str) -> list[dict[str, str]]:
    runs: list[dict[str, str]] = []
    for match in re.finditer(r"<Run\b([^>]*)/?>", runs_xml, flags=re.IGNORECASE):
        attrs = {
            key: value
            for key, value in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)=[\"']([^\"']*)[\"']", match.group(1))
        }
        if attrs.get("acc"):
            runs.append(attrs)
    return runs


def _search_ids(payload: dict[str, object]) -> tuple[int, list[str]]:
    result = payload.get("esearchresult")
    if not isinstance(result, dict):
        return 0, []
    try:
        total_count = int(str(result.get("count") or 0))
    except ValueError:
        total_count = 0
    ids = result.get("idlist")
    return total_count, [str(value) for value in ids if value] if isinstance(ids, list) else []


def _summary_items(payload: dict[str, object], ids: list[str]) -> list[tuple[str, dict[str, object]]]:
    result = payload.get("result")
    if not isinstance(result, dict):
        return []
    return [(uid, result[uid]) for uid in ids if isinstance(result.get(uid), dict)]


def _run_records(
    *,
    species: str,
    uid: str,
    item: dict[str, object],
    raw_path: Path,
    summary_url: str,
    retrieved_at: str,
) -> tuple[list[EvidenceRecord], bool]:
    exp_xml = _clean(_field(item, "ExpXml", "expxml"))
    runs_xml = _clean(_field(item, "Runs", "runs"))
    title = _clean(_field(item, "Title", "title")) or _xml_text(exp_xml, "Title") or f"SRA experiment {uid}"
    experiment_accession = _clean(_field(item, "Accession", "accession")) or _xml_attr(exp_xml, "Experiment", "acc") or uid
    bioproject = _xml_text(exp_xml, "Bioproject")
    biosample = _xml_text(exp_xml, "Biosample")
    platform = _xml_attr(exp_xml, "Platform", "instrument_model") or _xml_text(exp_xml, "Platform")
    library_strategy = _xml_text(exp_xml, "LibraryStrategy") or _xml_text(exp_xml, "LIBRARY_STRATEGY")
    library_source = _xml_text(exp_xml, "LibrarySource") or _xml_text(exp_xml, "LIBRARY_SOURCE")
    library_selection = _xml_text(exp_xml, "LibrarySelection") or _xml_text(exp_xml, "LIBRARY_SELECTION")
    runs = _run_attrs(runs_xml)
    records: list[EvidenceRecord] = []
    for run_index, run in enumerate(runs, start=1):
        run_accession = run["acc"]
        spots = run.get("total_spots", "")
        bases = run.get("total_bases", "")
        size = run.get("size", "")
        url = f"https://www.ncbi.nlm.nih.gov/sra/{run_accession}"
        text = " ".join(
            part
            for part in (
                f"NCBI SRA run {run_accession} for {species}.",
                f"Experiment: {experiment_accession}.",
                f"Title: {title}.",
                f"BioProject: {bioproject}." if bioproject else "",
                f"BioSample: {biosample}." if biosample else "",
                f"Platform: {platform}." if platform else "",
                f"Library strategy: {library_strategy}." if library_strategy else "",
                f"Library source: {library_source}." if library_source else "",
                f"Library selection: {library_selection}." if library_selection else "",
                f"Spots: {spots}." if spots else "",
                f"Bases: {bases}." if bases else "",
                f"Size: {size}." if size else "",
            )
            if part
        )
        records.append(
            EvidenceRecord(
                record_id=f"anopheles_sra:run:{run_accession}",
                lane="datasets",
                source=ANOPHELES_NCBI_SRA_SOURCE_ID,
                title=f"{species} SRA run {run_accession}: {title}",
                text=text,
                species=species,
                url=url,
                media_url=None,
                provenance=Provenance(
                    source_id=ANOPHELES_NCBI_SRA_SOURCE_ID,
                    locator=f"{raw_path.as_posix()}#result/{uid}/run/{run_index}",
                    retrieved_at=retrieved_at,
                    license="NCBI SRA public metadata; NCBI terms apply",
                    source_url=summary_url,
                ),
                payload={
                    "record_type": "ncbi_sra_run",
                    "uid": uid,
                    "species_query": species,
                    "experiment_accession": experiment_accession,
                    "run_accession": run_accession,
                    "title": title,
                    "bioproject": bioproject,
                    "biosample": biosample,
                    "platform": platform,
                    "library_strategy": library_strategy,
                    "library_source": library_source,
                    "library_selection": library_selection,
                    "total_spots": spots,
                    "total_bases": bases,
                    "size": size,
                    "raw_json_path": raw_path.as_posix(),
                },
            )
        )
    return records, bool(runs)


def fetch_anopheles_ncbi_sra_records(
    *,
    raw_dir: Path,
    target_taxa: list[str] | tuple[str, ...] = ANOPHELES_NCBI_BIOSAMPLES_TARGET_TAXA,
    experiment_limit_per_taxon: int = 100,
    page_size: int = 100,
    delay_seconds: float = 0.34,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
) -> AnophelesNCBISRAResult:
    retrieved = retrieved_at or _utc_now()
    client = NCBISRAClient(fetch_json)
    records_by_id: dict[str, EvidenceRecord] = {}
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []
    reported_total_counts: dict[str, int] = {}
    fetched_experiment_counts: dict[str, int] = {}
    run_counts: dict[str, int] = {}
    requested_taxa = tuple(dict.fromkeys(str(taxon).strip() for taxon in target_taxa if str(taxon).strip()))
    limit = max(0, int(experiment_limit_per_taxon))
    bounded_page_size = max(1, int(page_size))

    for species in requested_taxa:
        fetched_ids: list[str] = []
        species_run_count = 0
        for retstart in range(0, limit, bounded_page_size):
            retmax = min(bounded_page_size, limit - retstart)
            try:
                search_url, search_payload = client.esearch(species=species, retstart=retstart, retmax=retmax)
            except Exception as exc:
                gaps.append({"source": ANOPHELES_NCBI_SRA_SOURCE_ID, "lane": "datasets", "reason": "sra_esearch_failed", "species": species, "retstart": retstart, "error": str(exc), "retrieved_at": retrieved})
                break
            requested_urls.append(search_url)
            search_path = _write_raw(raw_dir, f"{_safe_name(species)}_sra_esearch_{retstart:06d}.json", search_payload)
            raw_artifacts.append(search_path.as_posix())
            total_count, ids = _search_ids(search_payload)
            reported_total_counts[species] = total_count
            if not ids:
                break
            fetched_ids.extend(ids)
            if delay_seconds:
                time.sleep(delay_seconds)
            try:
                summary_url, summary_payload = client.esummary(ids)
            except Exception as exc:
                gaps.append({"source": ANOPHELES_NCBI_SRA_SOURCE_ID, "lane": "datasets", "reason": "sra_esummary_failed", "species": species, "retstart": retstart, "ids": ids, "error": str(exc), "retrieved_at": retrieved})
                continue
            requested_urls.append(summary_url)
            summary_path = _write_raw(raw_dir, f"{_safe_name(species)}_sra_esummary_{retstart:06d}.json", summary_payload)
            raw_artifacts.append(summary_path.as_posix())
            for uid, item in _summary_items(summary_payload, ids):
                records, has_runs = _run_records(
                    species=species,
                    uid=uid,
                    item=item,
                    raw_path=summary_path,
                    summary_url=summary_url,
                    retrieved_at=retrieved,
                )
                if not has_runs:
                    gaps.append({"source": ANOPHELES_NCBI_SRA_SOURCE_ID, "lane": "datasets", "reason": "sra_summary_no_run_accessions", "species": species, "uid": uid, "retrieved_at": retrieved})
                for record in records:
                    records_by_id[record.record_id] = record
                species_run_count += len(records)
            if delay_seconds:
                time.sleep(delay_seconds)
        fetched_experiment_counts[species] = len(fetched_ids)
        run_counts[species] = species_run_count
        if reported_total_counts.get(species, 0) > len(fetched_ids):
            gaps.append({"source": ANOPHELES_NCBI_SRA_SOURCE_ID, "lane": "datasets", "reason": "sra_experiment_limit_applied", "species": species, "reported_total_count": reported_total_counts[species], "fetched_experiment_count": len(fetched_ids), "experiment_limit": limit, "retrieved_at": retrieved})

    gaps.extend(
        [
            {"source": ANOPHELES_NCBI_SRA_SOURCE_ID, "lane": "datasets", "reason": "raw_sra_reads_not_downloaded", "retrieved_at": retrieved},
            {"source": ANOPHELES_NCBI_SRA_SOURCE_ID, "lane": "datasets", "reason": "sra_reanalysis_not_performed", "retrieved_at": retrieved},
        ]
    )
    return AnophelesNCBISRAResult(
        source_id=ANOPHELES_NCBI_SRA_SOURCE_ID,
        records=list(records_by_id.values()),
        gaps=gaps,
        raw_artifacts=list(dict.fromkeys(raw_artifacts)),
        requested_urls=requested_urls,
        target_taxa=requested_taxa,
        reported_total_counts=reported_total_counts,
        fetched_experiment_counts=fetched_experiment_counts,
        run_counts=run_counts,
        experiment_limit_per_taxon=limit,
        page_size=bounded_page_size,
    )
