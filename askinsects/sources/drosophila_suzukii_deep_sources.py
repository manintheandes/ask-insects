from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Callable
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


DROSOPHILA_SUZUKII_DEEP_SOURCE_ID = "drosophila_suzukii_deep_sources"
SPECIES = "Drosophila suzukii"
COMMON_NAME = "spotted wing drosophila"
NCBI_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
UNIPROTKB_BASE = "https://rest.uniprot.org/uniprotkb/search"
UNIPROT_PROTEOME_BASE = "https://rest.uniprot.org/proteomes/search"
ZENODO_API_BASE = "https://zenodo.org/api/records"
FIGSHARE_API_BASE = "https://api.figshare.com/v2"
DRYAD_API_BASE = "https://datadryad.org/api/v2/search"
DRYAD_SITE_BASE = "https://datadryad.org"
USER_AGENT = "AskInsects/0.1 source-plane"
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".m4v", ".webm", ".mpg", ".mpeg")
ARCHIVE_EXTENSIONS = (".zip", ".tar", ".tar.gz", ".tgz", ".7z")
TABLE_EXTENSIONS = (".csv", ".tsv", ".xls", ".xlsx", ".json", ".txt")
SPECIES_PATTERN = re.compile(r"\bDrosophila\s+suzukii\b|spotted[-\s]+wing\s+drosophila|\bSWD\b", re.I)
REPOSITORY_VIDEO_QUERIES = (
    "Drosophila suzukii video",
    "spotted wing drosophila video",
    "Drosophila suzukii behavior",
    "Drosophila suzukii oviposition",
    "Drosophila suzukii tracking",
    "Drosophila suzukii flight",
    "Drosophila suzukii assay",
)
REPOSITORY_DATASET_QUERIES = (
    "Drosophila suzukii",
    "spotted wing drosophila",
    "Drosophila suzukii behavior",
    "Drosophila suzukii oviposition",
    "Drosophila suzukii tracking",
)


@dataclass(frozen=True)
class DrosophilaSuzukiiDeepResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    source_counts: dict[str, int]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fetch_json(url: str) -> object:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _post_json(url: str, payload: dict[str, object]) -> object:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _write_raw(raw_dir: Path, filename: str, payload: object) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _clean(value: object) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _safe_id(value: object) -> str:
    return re.sub(r"[^a-z0-9_.:-]+", "_", str(value or "").lower()).strip("_") or "unknown"


def _digest(*parts: object) -> str:
    return hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:12]


def _dedupe_records(records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    deduped: dict[str, EvidenceRecord] = {}
    for record in records:
        deduped.setdefault(record.record_id, record)
    return list(deduped.values())


def _eutils_url(endpoint: str, **params: object) -> str:
    return f"{NCBI_EUTILS_BASE}/{endpoint}.fcgi?{urlencode(params)}"


def _ids(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []
    result = payload.get("esearchresult")
    if not isinstance(result, dict):
        return []
    idlist = result.get("idlist")
    return [str(item) for item in idlist if item] if isinstance(idlist, list) else []


def _result_count(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    result = payload.get("esearchresult")
    if not isinstance(result, dict):
        return 0
    try:
        return int(str(result.get("count") or 0))
    except ValueError:
        return 0


def _summary_items(payload: object) -> list[tuple[str, dict[str, object]]]:
    if not isinstance(payload, dict):
        return []
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


def _field(item: dict[str, object], *names: str) -> object:
    lowered = {str(key).lower(): value for key, value in item.items()}
    for name in names:
        if name in item:
            return item[name]
        value = lowered.get(name.lower())
        if value is not None:
            return value
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
        attrs = {key: value for key, value in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)=[\"']([^\"']*)[\"']", match.group(1))}
        if attrs.get("acc"):
            runs.append(attrs)
    return runs


def _record(
    *,
    record_id: str,
    lane: str,
    title: str,
    text: str,
    url: str | None,
    raw_path: Path,
    locator_suffix: str,
    retrieved_at: str,
    license_text: str,
    source_url: str | None = None,
    media_url: str | None = None,
    payload: dict[str, object] | None = None,
) -> EvidenceRecord:
    return EvidenceRecord(
        record_id=record_id,
        lane=lane,
        source=DROSOPHILA_SUZUKII_DEEP_SOURCE_ID,
        title=title,
        text=text,
        species=SPECIES,
        url=url,
        media_url=media_url,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_DEEP_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#{locator_suffix}",
            retrieved_at=retrieved_at,
            license=license_text,
            source_url=source_url or url,
        ),
        payload=payload,
    )


def _source_gap_record(
    *,
    reason: str,
    lane: str,
    title: str,
    text: str,
    raw_path: Path,
    retrieved_at: str,
    payload: dict[str, object] | None = None,
) -> EvidenceRecord:
    return _record(
        record_id=f"swd:deep:gap:{_safe_id(reason)}",
        lane=lane,
        title=title,
        text=text,
        url=None,
        raw_path=raw_path,
        locator_suffix=f"gap/{reason}",
        retrieved_at=retrieved_at,
        license_text="Ask Insects source boundary audit",
        payload={"atom_type": "source_gap", "reason": reason, **(payload or {})},
    )


def _fetch_ncbi_db(
    *,
    db: str,
    term: str,
    limit: int,
    raw_dir: Path,
    fetch_json: Callable[[str], object],
    requested_urls: list[str],
    gaps: list[dict[str, object]],
    retrieved_at: str,
) -> tuple[list[tuple[str, dict[str, object]]], list[Path], int]:
    search_url = _eutils_url("esearch", db=db, term=term, retmode="json", retmax=max(0, int(limit)))
    requested_urls.append(search_url)
    try:
        search_payload = fetch_json(search_url)
    except Exception as exc:
        gaps.append({"source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, "lane": "genome_features", "db": db, "reason": "ncbi_search_failed", "error": str(exc), "retrieved_at": retrieved_at})
        return [], [], 0
    raw_paths = [_write_raw(raw_dir, f"ncbi_{db}_esearch.json", search_payload)]
    ids = _ids(search_payload)
    total_count = _result_count(search_payload)
    if total_count > len(ids):
        gaps.append(
            {
                "source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID,
                "lane": "genome_features",
                "db": db,
                "reason": "ncbi_limit_applied",
                "total_count": total_count,
                "fetched_count": len(ids),
                "limit": limit,
                "retrieved_at": retrieved_at,
            }
        )
    if not ids:
        gaps.append({"source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, "lane": "genome_features", "db": db, "reason": "ncbi_no_results", "retrieved_at": retrieved_at})
        return [], raw_paths, total_count
    if fetch_json is _fetch_json:
        time.sleep(0.34)
    summary_url = _eutils_url("esummary", db=db, id=",".join(ids), retmode="json")
    requested_urls.append(summary_url)
    try:
        summary_payload = fetch_json(summary_url)
    except Exception as exc:
        gaps.append({"source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, "lane": "genome_features", "db": db, "reason": "ncbi_summary_failed", "error": str(exc), "retrieved_at": retrieved_at, "ids": ids})
        return [], raw_paths, total_count
    summary_raw = _write_raw(raw_dir, f"ncbi_{db}_esummary.json", summary_payload)
    raw_paths.append(summary_raw)
    return _summary_items(summary_payload), raw_paths, total_count


def _assembly_records(items: list[tuple[str, dict[str, object]]], *, raw_path: Path, retrieved_at: str) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    for uid, item in items:
        accession = _clean(_field(item, "assemblyaccession", "assemblyAccession")) or uid
        name = _clean(_field(item, "assemblyname", "assemblyName")) or accession
        organism = _clean(_field(item, "organism")) or SPECIES
        status = _clean(_field(item, "assemblystatus", "assemblyStatus"))
        bioproject = _clean(_field(item, "bioprojectaccn", "bioprojectAccn"))
        biosample = _clean(_field(item, "biosampleaccn", "biosampleAccn"))
        url = f"https://www.ncbi.nlm.nih.gov/assembly/{accession}"
        text = (
            f"NCBI Assembly record {accession} for {organism} ({COMMON_NAME}). "
            f"Assembly name: {name}. Status: {status or 'not supplied'}. "
            f"BioProject: {bioproject or 'not supplied'}. BioSample: {biosample or 'not supplied'}."
        )
        records.append(
            _record(
                record_id=f"swd:assembly:{accession}",
                lane="genome_assemblies",
                title=f"Drosophila suzukii assembly {accession}: {name}",
                text=text,
                url=url,
                raw_path=raw_path,
                locator_suffix=f"result/{uid}",
                retrieved_at=retrieved_at,
                license_text="NCBI public metadata",
                payload={
                    "record_type": "ncbi_assembly",
                    "uid": uid,
                    "accession": accession,
                    "assembly_name": name,
                    "organism": organism,
                    "status": status,
                    "bioproject": bioproject,
                    "biosample": biosample,
                    "raw_summary": item,
                },
            )
        )
    return records


def _bioproject_records(items: list[tuple[str, dict[str, object]]], *, raw_path: Path, retrieved_at: str) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    for uid, item in items:
        accession = _clean(_field(item, "project_acc", "Project_Acc", "accession")) or uid
        title = _clean(_field(item, "title", "Project_Title")) or f"BioProject {accession}"
        description = _clean(_field(item, "description", "Project_Description"))
        url = f"https://www.ncbi.nlm.nih.gov/bioproject/{accession}"
        records.append(
            _record(
                record_id=f"swd:bioproject:{accession}",
                lane="genome_features",
                title=f"Drosophila suzukii BioProject {accession}: {title}",
                text=f"NCBI BioProject {accession} for {SPECIES}. Title: {title}. Description: {description or 'not supplied'}.",
                url=url,
                raw_path=raw_path,
                locator_suffix=f"result/{uid}",
                retrieved_at=retrieved_at,
                license_text="NCBI public metadata",
                payload={"record_type": "ncbi_bioproject", "uid": uid, "accession": accession, "title": title, "description": description, "raw_summary": item},
            )
        )
    return records


def _biosample_records(items: list[tuple[str, dict[str, object]]], *, raw_path: Path, retrieved_at: str) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    for uid, item in items:
        accession = _clean(_field(item, "accession", "Accession")) or uid
        title = _clean(_field(item, "title", "Title")) or f"BioSample {accession}"
        organism = _clean(_field(item, "organism", "Organism")) or SPECIES
        url = f"https://www.ncbi.nlm.nih.gov/biosample/{accession}"
        records.append(
            _record(
                record_id=f"swd:biosample:{accession}",
                lane="biosamples",
                title=f"Drosophila suzukii BioSample {accession}",
                text=f"NCBI BioSample {accession} for {organism}. Title: {title}.",
                url=url,
                raw_path=raw_path,
                locator_suffix=f"result/{uid}",
                retrieved_at=retrieved_at,
                license_text="NCBI public metadata",
                payload={"record_type": "ncbi_biosample", "uid": uid, "accession": accession, "title": title, "organism": organism, "raw_summary": item},
            )
        )
    return records


def _sra_records(items: list[tuple[str, dict[str, object]]], *, raw_path: Path, retrieved_at: str) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    for uid, item in items:
        exp_xml = _clean(_field(item, "ExpXml", "expxml"))
        runs_xml = _clean(_field(item, "Runs", "runs"))
        title = _clean(_field(item, "Title", "title")) or _xml_text(exp_xml, "Title") or f"SRA experiment {uid}"
        experiment_accession = _clean(_field(item, "Accession", "accession")) or _xml_attr(exp_xml, "Experiment", "acc") or uid
        bioproject = _xml_text(exp_xml, "Bioproject")
        biosample = _xml_text(exp_xml, "Biosample")
        platform = _xml_attr(exp_xml, "Platform", "instrument_model") or _xml_text(exp_xml, "Platform")
        runs = _run_attrs(runs_xml)
        if not runs:
            runs = [{"acc": experiment_accession}]
        for run_index, run in enumerate(runs, start=1):
            run_accession = run.get("acc") or experiment_accession
            url = f"https://www.ncbi.nlm.nih.gov/sra/{run_accession}"
            records.append(
                _record(
                    record_id=f"swd:sra:{run_accession}",
                    lane="expression",
                    title=f"Drosophila suzukii SRA run {run_accession}: {title}",
                    text=(
                        f"NCBI SRA run {run_accession} for {SPECIES}. Experiment: {experiment_accession}. "
                        f"Title: {title}. BioProject: {bioproject or 'not supplied'}. BioSample: {biosample or 'not supplied'}. Platform: {platform or 'not supplied'}."
                    ),
                    url=url,
                    raw_path=raw_path,
                    locator_suffix=f"result/{uid}/run/{run_index}",
                    retrieved_at=retrieved_at,
                    license_text="NCBI SRA public metadata",
                    payload={
                        "record_type": "ncbi_sra_run",
                        "uid": uid,
                        "experiment_accession": experiment_accession,
                        "run_accession": run_accession,
                        "bioproject": bioproject,
                        "biosample": biosample,
                        "platform": platform,
                        "raw_summary": item,
                    },
                )
            )
    return records


def _uniprot_records(
    *,
    raw_dir: Path,
    fetch_json: Callable[[str], object],
    requested_urls: list[str],
    gaps: list[dict[str, object]],
    retrieved_at: str,
    protein_limit: int,
    proteome_limit: int,
) -> tuple[list[EvidenceRecord], list[str]]:
    records: list[EvidenceRecord] = []
    raw_artifacts: list[str] = []
    query = f'organism_name:"{SPECIES}"'
    protein_url = f"{UNIPROTKB_BASE}?{urlencode({'query': query, 'fields': 'accession,id,reviewed,protein_name,gene_names,organism_name,go_id,cc_function,keyword', 'format': 'json', 'size': max(1, int(protein_limit))})}"
    requested_urls.append(protein_url)
    try:
        protein_payload = fetch_json(protein_url)
    except Exception as exc:
        gaps.append({"source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, "lane": "proteins", "reason": "uniprot_proteins_fetch_failed", "error": str(exc), "retrieved_at": retrieved_at})
    else:
        raw_path = _write_raw(raw_dir, "uniprotkb_drosophila_suzukii.json", protein_payload)
        raw_artifacts.append(raw_path.as_posix())
        results = protein_payload.get("results") if isinstance(protein_payload, dict) else []
        for index, entry in enumerate(results if isinstance(results, list) else [], start=1):
            if not isinstance(entry, dict):
                continue
            accession = _clean(entry.get("primaryAccession"))
            if not accession:
                continue
            protein_name = _clean(entry.get("uniProtkbId")) or accession
            description = entry.get("proteinDescription")
            if isinstance(description, dict):
                recommended = description.get("recommendedName")
                if isinstance(recommended, dict):
                    full_name = recommended.get("fullName")
                    if isinstance(full_name, dict) and full_name.get("value"):
                        protein_name = _clean(full_name["value"])
            url = f"https://www.uniprot.org/uniprotkb/{accession}/entry"
            records.append(
                _record(
                    record_id=f"swd:uniprot:protein:{accession}",
                    lane="proteins",
                    title=f"Drosophila suzukii UniProt protein {accession}",
                    text=f"UniProt protein record {accession} for {SPECIES}. Protein: {protein_name}.",
                    url=url,
                    raw_path=raw_path,
                    locator_suffix=f"results/{index}",
                    retrieved_at=retrieved_at,
                    license_text="UniProt public data; CC BY 4.0",
                    payload={"record_type": "uniprotkb_protein", "accession": accession, "protein_name": protein_name, "raw_entry": entry},
                )
            )
    proteome_url = f"{UNIPROT_PROTEOME_BASE}?{urlencode({'query': query, 'format': 'json', 'size': max(1, int(proteome_limit))})}"
    requested_urls.append(proteome_url)
    try:
        proteome_payload = fetch_json(proteome_url)
    except Exception as exc:
        gaps.append({"source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, "lane": "proteins", "reason": "uniprot_proteome_fetch_failed", "error": str(exc), "retrieved_at": retrieved_at})
    else:
        raw_path = _write_raw(raw_dir, "uniprot_proteomes_drosophila_suzukii.json", proteome_payload)
        raw_artifacts.append(raw_path.as_posix())
        results = proteome_payload.get("results") if isinstance(proteome_payload, dict) else []
        for index, entry in enumerate(results if isinstance(results, list) else [], start=1):
            if not isinstance(entry, dict):
                continue
            proteome_id = _clean(entry.get("id"))
            if not proteome_id:
                continue
            url = f"https://www.uniprot.org/proteomes/{proteome_id}"
            records.append(
                _record(
                    record_id=f"swd:uniprot:proteome:{proteome_id}",
                    lane="proteins",
                    title=f"Drosophila suzukii UniProt proteome {proteome_id}",
                    text=f"UniProt proteome record {proteome_id} for {SPECIES}.",
                    url=url,
                    raw_path=raw_path,
                    locator_suffix=f"results/{index}",
                    retrieved_at=retrieved_at,
                    license_text="UniProt public data; CC BY 4.0",
                    payload={"record_type": "uniprot_proteome", "proteome_id": proteome_id, "raw_entry": entry},
                )
            )
    return records, raw_artifacts


def _material_text(payload: dict[str, object]) -> str:
    return " ".join(_clean(payload.get(key)) for key in ("title", "description", "notes", "doi"))


def _is_video_file(filename: str, content_type: str = "") -> bool:
    lower = filename.lower()
    return lower.endswith(VIDEO_EXTENSIONS) or content_type.lower().startswith("video/")


def _is_archive_file(filename: str, content_type: str = "") -> bool:
    lower = filename.lower()
    return lower.endswith(ARCHIVE_EXTENSIONS) or "zip" in content_type.lower() or "compressed" in content_type.lower()


def _is_table_file(filename: str, content_type: str = "") -> bool:
    lower = filename.lower()
    return lower.endswith(TABLE_EXTENSIONS) or any(term in content_type.lower() for term in ("csv", "excel", "spreadsheet", "json", "text/plain"))


def _link(payload: dict[str, object], rel: str) -> str | None:
    links = payload.get("_links") if isinstance(payload.get("_links"), dict) else {}
    item = links.get(rel) if isinstance(links, dict) else None
    if not isinstance(item, dict):
        return None
    href = str(item.get("href") or "")
    return urljoin(DRYAD_SITE_BASE, href) if href else None


def _zenodo_records(
    *,
    raw_dir: Path,
    fetch_json: Callable[[str], object],
    requested_urls: list[str],
    gaps: list[dict[str, object]],
    retrieved_at: str,
    size: int,
    query: str = "Drosophila suzukii video",
) -> tuple[list[EvidenceRecord], list[str]]:
    url = f"{ZENODO_API_BASE}?{urlencode({'q': query, 'size': max(1, min(int(size), 25)), 'sort': 'bestmatch'})}"
    requested_urls.append(url)
    try:
        payload = fetch_json(url)
    except Exception as exc:
        gaps.append({"source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, "lane": "media", "reason": "zenodo_search_failed", "query": query, "error": str(exc), "retrieved_at": retrieved_at})
        return [], []
    raw_path = _write_raw(raw_dir, f"zenodo_{_safe_id(query)}.json", payload)
    records: list[EvidenceRecord] = []
    hits = payload.get("hits", {}).get("hits", []) if isinstance(payload, dict) else []
    for hit_index, hit in enumerate(hits if isinstance(hits, list) else [], start=1):
        if not isinstance(hit, dict):
            continue
        metadata = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
        files = hit.get("files") if isinstance(hit.get("files"), list) else []
        if not SPECIES_PATTERN.search(_material_text(metadata)):
            continue
        video_files = [file for file in files if isinstance(file, dict) and _is_video_file(str(file.get("key") or file.get("filename") or ""), str(file.get("type") or ""))]
        if not video_files:
            gaps.append({"source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, "lane": "media", "reason": "zenodo_material_record_no_video_files", "record_id": hit.get("id"), "query": query, "retrieved_at": retrieved_at})
        for file_index, file_payload in enumerate(video_files, start=1):
            filename = str(file_payload.get("key") or file_payload.get("filename") or f"file-{file_index}")
            links = file_payload.get("links") if isinstance(file_payload.get("links"), dict) else {}
            hit_links = hit.get("links") if isinstance(hit.get("links"), dict) else {}
            download_url = str(links.get("self") or links.get("download") or "") or None
            source_url = str(hit.get("doi_url") or hit_links.get("html") or "") or None
            records.append(
                _record(
                    record_id=f"swd:zenodo:video:{_safe_id(hit.get('id'))}:{_safe_id(filename)}",
                    lane="media",
                    title=f"Drosophila suzukii Zenodo video file {filename}",
                    text=f"Zenodo {SPECIES} video candidate {filename} from {_clean(metadata.get('title')) or hit.get('id')}.",
                    url=source_url,
                    media_url=download_url,
                    raw_path=raw_path,
                    locator_suffix=f"hits/{hit_index}/files/{file_index}",
                    retrieved_at=retrieved_at,
                    license_text=str((metadata.get("license") or {}).get("id") if isinstance(metadata.get("license"), dict) else metadata.get("license") or "Zenodo license not supplied"),
                    source_url=download_url or source_url,
                    payload={"record_type": "zenodo_video_manifest", "raw_record": hit, "raw_file": file_payload},
                )
            )
    if not records:
        gaps.append({"source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, "lane": "media", "reason": "zenodo_no_queryable_video_files", "query": query, "retrieved_at": retrieved_at})
    return records, [raw_path.as_posix()]


def _figshare_records(
    *,
    raw_dir: Path,
    fetch_json: Callable[[str], object],
    requested_urls: list[str],
    gaps: list[dict[str, object]],
    retrieved_at: str,
    page_size: int,
    query: str = "Drosophila suzukii video",
) -> tuple[list[EvidenceRecord], list[str]]:
    search_payload = {
        "search_for": query,
        "page_size": max(1, min(int(page_size), 100)),
        "order": "published_date",
        "order_direction": "desc",
    }
    search_url = f"{FIGSHARE_API_BASE}/articles/search"
    requested_urls.append(f"{search_url}?{urlencode(search_payload)}")
    try:
        if fetch_json is _fetch_json:
            payload = _post_json(search_url, search_payload)
        else:
            payload = fetch_json(f"{search_url}?{urlencode(search_payload)}")
    except Exception as exc:
        gaps.append({"source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, "lane": "media", "reason": "figshare_search_failed", "query": query, "error": str(exc), "retrieved_at": retrieved_at})
        return [], []
    search_raw = _write_raw(raw_dir, f"figshare_{_safe_id(query)}_search.json", payload)
    records: list[EvidenceRecord] = []
    raw_paths = [search_raw.as_posix()]
    rows = payload if isinstance(payload, list) else []
    for row_index, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or not row.get("id"):
            continue
        detail_url = f"{FIGSHARE_API_BASE}/articles/{row['id']}"
        requested_urls.append(detail_url)
        try:
            detail = fetch_json(detail_url)
        except Exception as exc:
            gaps.append({"source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, "lane": "media", "reason": "figshare_detail_fetch_failed", "article_id": row.get("id"), "query": query, "error": str(exc), "retrieved_at": retrieved_at})
            continue
        detail_raw = _write_raw(raw_dir, f"figshare_article_{row['id']}.json", detail)
        raw_paths.append(detail_raw.as_posix())
        if not isinstance(detail, dict) or not SPECIES_PATTERN.search(_material_text(detail)):
            continue
        files = detail.get("files") if isinstance(detail.get("files"), list) else []
        video_files = [file for file in files if isinstance(file, dict) and _is_video_file(str(file.get("name") or file.get("filename") or ""), str(file.get("mimetype") or ""))]
        if not video_files:
            gaps.append({"source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, "lane": "media", "reason": "figshare_material_record_no_video_files", "article_id": row.get("id"), "query": query, "retrieved_at": retrieved_at})
        for file_index, file_payload in enumerate(video_files, start=1):
            filename = str(file_payload.get("name") or file_payload.get("filename") or f"file-{file_index}")
            records.append(
                _record(
                    record_id=f"swd:figshare:video:{_safe_id(row.get('id'))}:{_safe_id(filename)}",
                    lane="media",
                    title=f"Drosophila suzukii Figshare video file {filename}",
                    text=f"Figshare {SPECIES} video candidate {filename} from {_clean(detail.get('title')) or row.get('id')}.",
                    url=str(detail.get("url_public_html") or detail.get("figshare_url") or "") or None,
                    media_url=str(file_payload.get("download_url") or "") or None,
                    raw_path=detail_raw,
                    locator_suffix=f"files/{file_index}",
                    retrieved_at=retrieved_at,
                    license_text=str((detail.get("license") or {}).get("name") if isinstance(detail.get("license"), dict) else detail.get("license") or "Figshare license not supplied"),
                    source_url=str(file_payload.get("download_url") or detail.get("url_public_html") or "") or None,
                    payload={"record_type": "figshare_video_manifest", "raw_article": detail, "raw_file": file_payload},
                )
            )
    if not records:
        gaps.append({"source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, "lane": "media", "reason": "figshare_no_queryable_video_files", "query": query, "retrieved_at": retrieved_at})
    return records, raw_paths


def _dryad_records(
    *,
    raw_dir: Path,
    fetch_json: Callable[[str], object],
    requested_urls: list[str],
    gaps: list[dict[str, object]],
    retrieved_at: str,
    page_size: int,
    query: str = "Drosophila suzukii",
) -> tuple[list[EvidenceRecord], list[str]]:
    url = f"{DRYAD_API_BASE}?{urlencode({'q': query, 'per_page': max(1, min(int(page_size), 100))})}"
    requested_urls.append(url)
    try:
        payload = fetch_json(url)
    except Exception as exc:
        gaps.append({"source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, "lane": "behavior", "reason": "dryad_search_failed", "query": query, "error": str(exc), "retrieved_at": retrieved_at})
        return [], []
    raw_path = _write_raw(raw_dir, f"dryad_{_safe_id(query)}_search.json", payload)
    records: list[EvidenceRecord] = []
    raw_paths = [raw_path.as_posix()]
    embedded = payload.get("_embedded") if isinstance(payload, dict) else {}
    stash = embedded.get("stash:datasets", []) if isinstance(embedded, dict) else []
    for index, dataset in enumerate(stash if isinstance(stash, list) else [], start=1):
        if not isinstance(dataset, dict):
            continue
        text = " ".join(_clean(dataset.get(key)) for key in ("title", "abstract", "description"))
        if not SPECIES_PATTERN.search(text):
            continue
        doi = _clean(dataset.get("identifier")) or _clean(dataset.get("doi"))
        dataset_record_id = f"swd:dryad:dataset:{_safe_id(doi or index)}"
        records.append(
            _record(
                record_id=dataset_record_id,
                lane="behavior",
                title=f"Drosophila suzukii Dryad dataset {doi or index}",
                text=f"Dryad dataset candidate for {SPECIES}. Title: {_clean(dataset.get('title'))}. DOI: {doi or 'not supplied'}.",
                url=str(dataset.get("sharingLink") or dataset.get("url") or "") or None,
                raw_path=raw_path,
                locator_suffix=f"datasets/{index}",
                retrieved_at=retrieved_at,
                license_text=str(dataset.get("license") or "Dryad metadata license not supplied"),
                payload={"record_type": "dryad_dataset_candidate", "raw_dataset": dataset},
            )
        )
        version_url = _link(dataset, "stash:version")
        if not version_url:
            gaps.append({"source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, "lane": "behavior", "reason": "dryad_version_link_missing", "dataset_record_id": dataset_record_id, "doi": doi, "query": query, "retrieved_at": retrieved_at})
            continue
        requested_urls.append(version_url)
        try:
            version_payload = fetch_json(version_url)
        except Exception as exc:
            gaps.append({"source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, "lane": "behavior", "reason": "dryad_version_fetch_failed", "dataset_record_id": dataset_record_id, "doi": doi, "query": query, "error": str(exc), "retrieved_at": retrieved_at})
            continue
        version_raw = _write_raw(raw_dir, f"dryad_version_{_safe_id(doi or index)}.json", version_payload)
        raw_paths.append(version_raw.as_posix())
        files_url = _link(version_payload, "stash:files") if isinstance(version_payload, dict) else None
        if not files_url:
            gaps.append({"source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, "lane": "behavior", "reason": "dryad_files_link_missing", "dataset_record_id": dataset_record_id, "doi": doi, "query": query, "retrieved_at": retrieved_at})
            continue
        requested_urls.append(files_url)
        try:
            files_payload = fetch_json(files_url)
        except Exception as exc:
            gaps.append({"source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, "lane": "behavior", "reason": "dryad_files_fetch_failed", "dataset_record_id": dataset_record_id, "doi": doi, "query": query, "error": str(exc), "retrieved_at": retrieved_at})
            continue
        files_raw = _write_raw(raw_dir, f"dryad_files_{_safe_id(doi or index)}.json", files_payload)
        raw_paths.append(files_raw.as_posix())
        embedded_files = files_payload.get("_embedded", {}).get("stash:files", []) if isinstance(files_payload, dict) else []
        if not embedded_files:
            gaps.append({"source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, "lane": "behavior", "reason": "dryad_file_manifest_empty", "dataset_record_id": dataset_record_id, "doi": doi, "query": query, "retrieved_at": retrieved_at})
            continue
        for file_index, file_payload in enumerate(embedded_files if isinstance(embedded_files, list) else [], start=1):
            if not isinstance(file_payload, dict):
                continue
            file_path = _clean(file_payload.get("path")) or f"file-{file_index}"
            mime_type = _clean(file_payload.get("mimeType"))
            media = _is_video_file(file_path, mime_type) or _is_archive_file(file_path, mime_type)
            table = _is_table_file(file_path, mime_type)
            download_url = _link(file_payload, "stash:download")
            description = _clean(file_payload.get("description"))
            lane = "media" if media else "behavior"
            kind = "video/archive" if media else "table/data" if table else "data"
            records.append(
                _record(
                    record_id=f"swd:dryad:file:{_safe_id(doi or index)}:{_safe_id(file_path)}",
                    lane=lane,
                    title=f"Drosophila suzukii Dryad {kind} file {file_path}",
                    text=(
                        f"Dryad file manifest for {SPECIES} dataset {doi or index}. "
                        f"File: {file_path}. MIME type: {mime_type or 'not supplied'}. "
                        f"Size: {file_payload.get('size') or 'not supplied'}. Description: {description or 'not supplied'}."
                    ),
                    url=str(dataset.get("sharingLink") or dataset.get("url") or "") or None,
                    media_url=download_url if media else None,
                    raw_path=files_raw,
                    locator_suffix=f"files/{file_index}",
                    retrieved_at=retrieved_at,
                    license_text=str(dataset.get("license") or "Dryad metadata license not supplied"),
                    source_url=download_url or str(dataset.get("sharingLink") or dataset.get("url") or "") or None,
                    payload={
                        "record_type": "dryad_file_manifest",
                        "source_dataset_record_id": dataset_record_id,
                        "dataset_doi": doi,
                        "file_path": file_path,
                        "mime_type": mime_type,
                        "byte_size": file_payload.get("size"),
                        "digest": file_payload.get("digest"),
                        "digest_type": file_payload.get("digestType"),
                        "download_url": download_url,
                        "is_video_or_archive": media,
                        "is_table_or_data_file": table,
                        "raw_dataset": dataset,
                        "raw_version": version_payload,
                        "raw_file": file_payload,
                        "version_raw_path": version_raw.as_posix(),
                    },
                )
            )
    if not records:
        gaps.append({"source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, "lane": "behavior", "reason": "dryad_no_material_dataset_candidates", "query": query, "retrieved_at": retrieved_at})
    return records, raw_paths


def fetch_drosophila_suzukii_deep_records(
    *,
    raw_dir: Path,
    retrieved_at: str | None = None,
    fetch_json: Callable[[str], object] | None = None,
    ncbi_limit: int = 50,
    protein_limit: int = 100,
    proteome_limit: int = 10,
    repository_limit: int = 50,
) -> DrosophilaSuzukiiDeepResult:
    retrieved = retrieved_at or utc_now()
    fetch = fetch_json or _fetch_json
    raw_dir.mkdir(parents=True, exist_ok=True)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []

    ncbi_dir = raw_dir / "ncbi"
    for db, lane, term, builder in (
        ("assembly", "genome_assemblies", f'"{SPECIES}"[Organism]', _assembly_records),
        ("bioproject", "genome_features", f'"{SPECIES}"[Organism]', _bioproject_records),
        ("biosample", "biosamples", f'"{SPECIES}"[Organism]', _biosample_records),
        ("sra", "expression", f'"{SPECIES}"[Organism]', _sra_records),
    ):
        items, paths, _total = _fetch_ncbi_db(
            db=db,
            term=term,
            limit=ncbi_limit,
            raw_dir=ncbi_dir,
            fetch_json=fetch,
            requested_urls=requested_urls,
            gaps=gaps,
            retrieved_at=retrieved,
        )
        raw_artifacts.extend(path.as_posix() for path in paths)
        summary_path = paths[-1] if paths else ncbi_dir / f"ncbi_{db}_esummary.json"
        built = builder(items, raw_path=summary_path, retrieved_at=retrieved)
        records.extend(built)
        if not built:
            gaps.append({"source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, "lane": lane, "db": db, "reason": "no_queryable_records_built", "retrieved_at": retrieved})
        if fetch is _fetch_json:
            time.sleep(0.5)

    uniprot_records, uniprot_artifacts = _uniprot_records(
        raw_dir=raw_dir / "uniprot",
        fetch_json=fetch,
        requested_urls=requested_urls,
        gaps=gaps,
        retrieved_at=retrieved,
        protein_limit=protein_limit,
        proteome_limit=proteome_limit,
    )
    records.extend(uniprot_records)
    raw_artifacts.extend(uniprot_artifacts)

    for query in REPOSITORY_VIDEO_QUERIES:
        repo_records, repo_artifacts = _zenodo_records(
            raw_dir=raw_dir / "zenodo",
            fetch_json=fetch,
            requested_urls=requested_urls,
            gaps=gaps,
            retrieved_at=retrieved,
            size=repository_limit,
            query=query,
        )
        records.extend(repo_records)
        raw_artifacts.extend(repo_artifacts)
        repo_records, repo_artifacts = _figshare_records(
            raw_dir=raw_dir / "figshare",
            fetch_json=fetch,
            requested_urls=requested_urls,
            gaps=gaps,
            retrieved_at=retrieved,
            page_size=repository_limit,
            query=query,
        )
        records.extend(repo_records)
        raw_artifacts.extend(repo_artifacts)

    for query in REPOSITORY_DATASET_QUERIES:
        repo_records, repo_artifacts = _dryad_records(
            raw_dir=raw_dir / "dryad",
            fetch_json=fetch,
            requested_urls=requested_urls,
            gaps=gaps,
            retrieved_at=retrieved,
            page_size=repository_limit,
            query=query,
        )
        records.extend(repo_records)
        raw_artifacts.extend(repo_artifacts)

    boundary_path = _write_raw(
        raw_dir,
        "source_boundary.json",
        {
            "source": DROSOPHILA_SUZUKII_DEEP_SOURCE_ID,
            "species": SPECIES,
            "common_name": COMMON_NAME,
            "retrieved_at": retrieved,
            "note": "Deep SWD source lane maps genomics, proteins, SRA/BioSample, and repository candidates. Heavy genome-file parsing, full supplement parsing, and validated crop-management synthesis remain explicit next gates.",
        },
    )
    raw_artifacts.append(boundary_path.as_posix())
    for reason, lane, text in (
        ("genome_feature_file_parsing_not_yet_done", "genome_features", "NCBI assembly metadata is indexed, but full GFF/FASTA feature parsing is not yet mirrored for Drosophila suzukii."),
        ("literature_supplement_audit_not_yet_done", "literature", "The core OpenAlex literature rows exist, but PubMed reconciliation, Unpaywall full text, and per-paper supplement audit are not yet complete for Drosophila suzukii."),
        ("crop_damage_management_guidance_not_yet_done", "ecology", "Crop damage, phenology, pest-management guidance, and regional extension datasets still need source-grade ingestion for Drosophila suzukii."),
        ("resistance_biocontrol_structured_assays_not_yet_done", "resistance", "Insecticide resistance, parasitoid/biocontrol, and management-efficacy assays are not yet parsed as structured Drosophila suzukii rows."),
    ):
        records.append(
            _source_gap_record(
                reason=reason,
                lane=lane,
                title=f"Drosophila suzukii source gap: {reason}",
                text=f"{SPECIES} ({COMMON_NAME}) source gap: {text}",
                raw_path=boundary_path,
                retrieved_at=retrieved,
            )
        )

    source_counts: dict[str, int] = {}
    records = _dedupe_records(records)
    for record in records:
        source_counts[record.lane] = source_counts.get(record.lane, 0) + 1
    return DrosophilaSuzukiiDeepResult(
        source_id=DROSOPHILA_SUZUKII_DEEP_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        source_counts=source_counts,
    )
