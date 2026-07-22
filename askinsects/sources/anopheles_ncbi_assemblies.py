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


ANOPHELES_NCBI_ASSEMBLIES_SOURCE_ID = "anopheles_ncbi_assemblies"
NCBI_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
USER_AGENT = "AskInsects/0.1 source-plane"


@dataclass(frozen=True)
class AnophelesNCBIAssembliesResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    target_taxa: tuple[str, ...]
    reported_total_counts: dict[str, int]
    assembly_counts: dict[str, int]
    limit_per_taxon: int


class NCBIAssemblyClient:
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
            raise ValueError(f"NCBI Assembly endpoint returned non-object JSON for {url}")
        return payload

    def esearch(self, *, species: str, retmax: int) -> tuple[str, dict[str, object]]:
        params = {
            "db": "assembly",
            "term": f'"{species}"[Organism]',
            "retmode": "json",
            "retmax": retmax,
            "sort": "date",
            "tool": "ask-insects",
        }
        url = f"{NCBI_EUTILS_BASE}/esearch.fcgi?{urlencode(params)}"
        return url, self.fetch_json(url)

    def esummary(self, ids: list[str]) -> tuple[str, dict[str, object]]:
        params = {
            "db": "assembly",
            "id": ",".join(ids),
            "retmode": "json",
            "report": "full",
            "tool": "ask-insects",
        }
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


def _search_ids(payload: dict[str, object]) -> tuple[int, list[str]]:
    result = payload.get("esearchresult")
    if not isinstance(result, dict):
        return 0, []
    try:
        total = int(str(result.get("count") or 0))
    except ValueError:
        total = 0
    ids = result.get("idlist")
    return total, [str(value) for value in ids if value] if isinstance(ids, list) else []


def _summary_items(payload: dict[str, object], ids: list[str]) -> list[tuple[str, dict[str, object]]]:
    result = payload.get("result")
    if not isinstance(result, dict):
        return []
    return [(uid, result[uid]) for uid in ids if isinstance(result.get(uid), dict)]


def _bioprojects(item: dict[str, object]) -> list[str]:
    accessions: list[str] = []
    for key in ("rs_bioprojects", "gb_bioprojects"):
        projects = item.get(key)
        if not isinstance(projects, list):
            continue
        for project in projects:
            if isinstance(project, dict) and project.get("bioprojectaccn"):
                accessions.append(_clean(project["bioprojectaccn"]))
    return list(dict.fromkeys(value for value in accessions if value))


def _assembly_record(
    *, species_query: str, uid: str, item: dict[str, object], raw_path: Path, summary_url: str, retrieved_at: str
) -> EvidenceRecord | None:
    accession = _clean(item.get("assemblyaccession"))
    if not accession:
        return None
    species = _clean(item.get("speciesname")) or species_query
    organism = _clean(item.get("organism")) or species
    name = _clean(item.get("assemblyname")) or accession
    level = _clean(item.get("assemblystatus")) or "unknown"
    assembly_type = _clean(item.get("assemblytype"))
    biosample = _clean(item.get("biosampleaccn"))
    bioprojects = _bioprojects(item)
    coverage = _clean(item.get("coverage"))
    release_date = _clean(item.get("asmreleasedate_refseq"))
    if not release_date or release_date.startswith("1/01/01"):
        release_date = _clean(item.get("asmreleasedate_genbank"))
    submitter = _clean(item.get("submitterorganization"))
    refseq_category = _clean(item.get("refseq_category"))
    genbank_ftp = _clean(item.get("ftppath_genbank"))
    refseq_ftp = _clean(item.get("ftppath_refseq"))
    assembly_report_ftp = _clean(item.get("ftppath_assembly_rpt"))
    contig_n50 = item.get("contign50") or ""
    scaffold_n50 = item.get("scaffoldn50") or ""
    properties = item.get("propertylist") if isinstance(item.get("propertylist"), list) else []
    source_url = f"https://www.ncbi.nlm.nih.gov/datasets/genome/{accession}/"
    text = " ".join(
        part
        for part in (
            f"NCBI genome assembly {accession} ({name}) for {organism}.",
            f"Assembly level: {level}.",
            f"Assembly type: {assembly_type}." if assembly_type else "",
            f"BioProject: {', '.join(bioprojects)}." if bioprojects else "",
            f"BioSample: {biosample}." if biosample else "",
            f"Coverage: {coverage}." if coverage else "",
            f"Contig N50: {contig_n50}." if contig_n50 else "",
            f"Scaffold N50: {scaffold_n50}." if scaffold_n50 else "",
            f"Release date: {release_date}." if release_date else "",
            f"Submitter: {submitter}." if submitter else "",
            f"RefSeq category: {refseq_category}." if refseq_category else "",
        )
        if part
    )
    return EvidenceRecord(
        record_id=f"anopheles_ncbi:assembly:{accession}",
        lane="genome_assemblies",
        source=ANOPHELES_NCBI_ASSEMBLIES_SOURCE_ID,
        title=f"{species} genome assembly {accession}: {name}",
        text=text,
        species=species,
        url=source_url,
        media_url=None,
        provenance=Provenance(
            source_id=ANOPHELES_NCBI_ASSEMBLIES_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#result/{uid}",
            retrieved_at=retrieved_at,
            license="NCBI Assembly public metadata; NCBI terms apply",
            source_url=summary_url,
        ),
        payload={
            "record_type": "ncbi_assembly",
            "uid": uid,
            "species_query": species_query,
            "species": species,
            "organism": organism,
            "assembly_accession": accession,
            "assembly_name": name,
            "assembly_level": level,
            "assembly_type": assembly_type,
            "bioprojects": bioprojects,
            "biosample": biosample,
            "coverage": coverage,
            "contig_n50": contig_n50,
            "scaffold_n50": scaffold_n50,
            "release_date": release_date,
            "submitter": submitter,
            "refseq_category": refseq_category,
            "properties": properties,
            "genbank_ftp": genbank_ftp,
            "refseq_ftp": refseq_ftp,
            "assembly_report_ftp": assembly_report_ftp,
            "raw_json_path": raw_path.as_posix(),
        },
    )


def fetch_anopheles_ncbi_assemblies(
    *,
    raw_dir: Path,
    target_taxa: list[str] | tuple[str, ...] = ANOPHELES_NCBI_BIOSAMPLES_TARGET_TAXA,
    limit_per_taxon: int = 25,
    delay_seconds: float = 0.34,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
) -> AnophelesNCBIAssembliesResult:
    retrieved = retrieved_at or _utc_now()
    client = NCBIAssemblyClient(fetch_json)
    records_by_id: dict[str, EvidenceRecord] = {}
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []
    totals: dict[str, int] = {}
    counts: dict[str, int] = {}
    taxa = tuple(dict.fromkeys(str(value).strip() for value in target_taxa if str(value).strip()))
    limit = max(0, int(limit_per_taxon))

    for species in taxa:
        try:
            search_url, search_payload = client.esearch(species=species, retmax=limit)
            requested_urls.append(search_url)
            search_path = _write_raw(raw_dir, f"{_safe_name(species)}_assembly_esearch.json", search_payload)
            raw_artifacts.append(search_path.as_posix())
            total, ids = _search_ids(search_payload)
            totals[species] = total
            if not ids:
                counts[species] = 0
                gaps.append({"source": ANOPHELES_NCBI_ASSEMBLIES_SOURCE_ID, "lane": "genome_assemblies", "reason": "assembly_search_returned_no_ids", "species": species, "retrieved_at": retrieved})
                continue
            if delay_seconds:
                time.sleep(delay_seconds)
            summary_url, summary_payload = client.esummary(ids)
            requested_urls.append(summary_url)
            summary_path = _write_raw(raw_dir, f"{_safe_name(species)}_assembly_esummary.json", summary_payload)
            raw_artifacts.append(summary_path.as_posix())
            species_count = 0
            for uid, item in _summary_items(summary_payload, ids):
                record = _assembly_record(species_query=species, uid=uid, item=item, raw_path=summary_path, summary_url=summary_url, retrieved_at=retrieved)
                if record is not None:
                    records_by_id[record.record_id] = record
                    species_count += 1
            counts[species] = species_count
            if total > len(ids):
                gaps.append({"source": ANOPHELES_NCBI_ASSEMBLIES_SOURCE_ID, "lane": "genome_assemblies", "reason": "assembly_limit_applied", "species": species, "reported_total_count": total, "fetched_count": len(ids), "limit": limit, "retrieved_at": retrieved})
            if delay_seconds:
                time.sleep(delay_seconds)
        except Exception as exc:
            counts.setdefault(species, 0)
            gaps.append({"source": ANOPHELES_NCBI_ASSEMBLIES_SOURCE_ID, "lane": "genome_assemblies", "reason": "assembly_fetch_failed", "species": species, "error": str(exc), "retrieved_at": retrieved})

    gaps.append({"source": ANOPHELES_NCBI_ASSEMBLIES_SOURCE_ID, "lane": "genome_features", "reason": "assembly_metadata_only_genome_features_not_yet_parsed", "retrieved_at": retrieved})
    return AnophelesNCBIAssembliesResult(
        source_id=ANOPHELES_NCBI_ASSEMBLIES_SOURCE_ID,
        records=list(records_by_id.values()), gaps=gaps, raw_artifacts=list(dict.fromkeys(raw_artifacts)),
        requested_urls=requested_urls, target_taxa=taxa, reported_total_counts=totals,
        assembly_counts=counts, limit_per_taxon=limit,
    )
