from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..records import EvidenceRecord, Provenance
from ..species import resolve_species


EXPRESSION_OMICS_SOURCE_ID = "aedes_expression_omics"
USER_AGENT = "AskInsects/0.1 source-plane"
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
GEO_TERM = '"Aedes aegypti"[Organism] AND (expression OR RNA-seq OR transcriptome)'
SRA_TERM = '"Aedes aegypti"[Organism] AND RNA-Seq'
ANALYSIS_SCOPE_GAPS = (
    {
        "reason": "raw_sra_reanalysis_not_performed",
        "title": "Aedes aegypti raw SRA reanalysis source gap",
        "text": (
            "Aedes aegypti expression omics source gap: raw SRA reanalysis into "
            "count matrices and normalized expression matrices has not yet been "
            "performed as source-grade Ask Insects rows."
        ),
    },
    {
        "reason": "differential_expression_outputs_not_indexed",
        "title": "Aedes aegypti differential-expression output source gap",
        "text": (
            "Aedes aegypti expression omics source gap: differential-expression "
            "outputs are not yet indexed as queryable source-grade rows."
        ),
    },
)


@dataclass(frozen=True)
class ExpressionOmicsResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]


def _default_fetch_json(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(4):
        try:
            with urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8", "replace"))
        except HTTPError as exc:
            if exc.code != 429 or attempt == 3:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable NCBI fetch state")


def _eutils_url(endpoint: str, **params: object) -> str:
    return f"{EUTILS_BASE}/{endpoint}.fcgi?{urlencode(params)}"


def _write_raw(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _analysis_scope_boundary(raw_dir: Path, retrieved_at: str) -> tuple[Path, list[dict[str, object]]]:
    gaps = [
        {
            "source": EXPRESSION_OMICS_SOURCE_ID,
            "lane": "expression",
            "reason": str(gap["reason"]),
            "retrieved_at": retrieved_at,
            "scope": (
                "Current expression omics coverage indexes NCBI GEO dataset metadata "
                "and SRA run metadata. It does not yet perform raw-read reanalysis, "
                "count-matrix construction, normalized expression matrices, or "
                "differential-expression output extraction."
            ),
        }
        for gap in ANALYSIS_SCOPE_GAPS
    ]
    path = _write_raw(
        raw_dir,
        "source_boundary.json",
        {
            "source": EXPRESSION_OMICS_SOURCE_ID,
            "retrieved_at": retrieved_at,
            "gaps": gaps,
        },
    )
    return path, gaps


def _analysis_scope_gap_records(boundary_path: Path, gaps: list[dict[str, object]], *, retrieved_at: str) -> list[EvidenceRecord]:
    gap_text_by_reason = {str(gap["reason"]): str(gap["text"]) for gap in ANALYSIS_SCOPE_GAPS}
    gap_title_by_reason = {str(gap["reason"]): str(gap["title"]) for gap in ANALYSIS_SCOPE_GAPS}
    records: list[EvidenceRecord] = []
    for gap in gaps:
        reason = str(gap["reason"])
        records.append(
            EvidenceRecord(
                record_id=f"expression:gap:{reason}",
                lane="expression",
                source=EXPRESSION_OMICS_SOURCE_ID,
                title=gap_title_by_reason.get(reason, f"Aedes aegypti expression omics source gap {reason}"),
                text=gap_text_by_reason.get(reason, f"Aedes aegypti expression omics source gap: {reason}."),
                species="Aedes aegypti",
                url="https://www.ncbi.nlm.nih.gov/sra",
                media_url=None,
                provenance=Provenance(
                    source_id=EXPRESSION_OMICS_SOURCE_ID,
                    locator=f"{boundary_path.as_posix()}#gap/{reason}",
                    retrieved_at=retrieved_at,
                    license="Ask Insects source boundary audit",
                    source_url="https://www.ncbi.nlm.nih.gov/sra",
                ),
                payload={
                    "atom_type": "source_gap",
                    "reason": reason,
                    "gap": gap,
                    "raw_json_path": boundary_path.as_posix(),
                },
            )
        )
    return records


def _clean(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _xml_text(xml: str, tag: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", xml, flags=re.IGNORECASE | re.DOTALL)
    return _clean(re.sub(r"<[^>]+>", " ", match.group(1))) if match else ""


def _xml_attr(xml: str, tag: str, attr: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*\s{attr}=[\"']([^\"']+)[\"']", xml, flags=re.IGNORECASE)
    return _clean(match.group(1)) if match else ""


def _run_attrs(runs_xml: str) -> list[dict[str, str]]:
    runs: list[dict[str, str]] = []
    for match in re.finditer(r"<Run\b([^>]*)/?>", runs_xml, flags=re.IGNORECASE):
        attrs: dict[str, str] = {}
        for key, value in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)=[\"']([^\"']*)[\"']", match.group(1)):
            attrs[key] = value
        if attrs.get("acc"):
            runs.append(attrs)
    return runs


def _ids(payload: dict[str, object]) -> list[str]:
    result = payload.get("esearchresult")
    if not isinstance(result, dict):
        return []
    idlist = result.get("idlist")
    if not isinstance(idlist, list):
        return []
    return [str(item) for item in idlist if item]


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


def _field(item: dict[str, object], *names: str) -> object:
    lowered = {str(key).lower(): value for key, value in item.items()}
    for name in names:
        if name in item:
            return item[name]
        value = lowered.get(name.lower())
        if value is not None:
            return value
    return None


def _result_count(payload: dict[str, object]) -> int:
    result = payload.get("esearchresult")
    if not isinstance(result, dict):
        return 0
    try:
        return int(str(result.get("count") or 0))
    except ValueError:
        return 0


def _chunked(values: list[str], size: int) -> list[list[str]]:
    size = max(1, int(size))
    return [values[index : index + size] for index in range(0, len(values), size)]


def _paged_raw_name(db: str, kind: str, ordinal: int, total: int) -> str:
    if total == 1:
        return f"{db}_{kind}.json"
    return f"{db}_{kind}_{ordinal + 1:04d}.json"


def _geo_record(uid: str, item: dict[str, object], *, raw_path: Path, retrieved_at: str) -> EvidenceRecord:
    accession = _clean(_field(item, "accession")) or uid
    title = _clean(item.get("title")) or f"GEO expression dataset {accession}"
    summary = _clean(item.get("summary"))
    # Species-scoped by the query: GEO_TERM pins '"Aedes aegypti"[Organism]'. The scope
    # argument is warranted because the search is genuinely pinned to this organism.
    taxon = resolve_species(_clean(item.get("taxon")), scope="Aedes aegypti")
    sample_count = _clean(_field(item, "n_samples"))
    platform = _clean(_field(item, "gpl"))
    gds_type = _clean(_field(item, "gdsType", "gdstype", "entryType"))
    url = f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={accession}"
    text = " ".join(
        part
        for part in (
            f"GEO Aedes aegypti expression omics dataset {accession}.",
            f"Title: {title}.",
            f"Type: {gds_type}." if gds_type else "",
            f"Samples: {sample_count}." if sample_count else "",
            f"Platform: {platform}." if platform else "",
            f"Summary: {summary}" if summary else "",
        )
        if part
    )
    return EvidenceRecord(
        record_id=f"expression:geo:{accession}",
        lane="expression",
        source=EXPRESSION_OMICS_SOURCE_ID,
        title=f"GEO expression dataset {accession}: {title}",
        text=text,
        species=taxon,
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=EXPRESSION_OMICS_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#result/{uid}",
            retrieved_at=retrieved_at,
            license="NCBI GEO public metadata",
            source_url=url,
        ),
        payload={
            "db": "gds",
            "uid": uid,
            "accession": accession,
            "title": title,
            "summary": summary,
            "taxon": taxon,
            "sample_count": sample_count,
            "platform": platform,
            "type": gds_type,
            "raw_json_path": raw_path.as_posix(),
        },
    )


def _sra_records(uid: str, item: dict[str, object], *, raw_path: Path, retrieved_at: str) -> list[EvidenceRecord]:
    exp_xml = _clean(_field(item, "ExpXml", "expxml"))
    runs_xml = _clean(_field(item, "Runs", "runs"))
    title = _clean(_field(item, "Title", "title")) or _xml_text(exp_xml, "Title") or f"SRA expression experiment {uid}"
    bioproject = _xml_text(exp_xml, "Bioproject")
    biosample = _xml_text(exp_xml, "Biosample")
    platform = _xml_attr(exp_xml, "Platform", "instrument_model") or _xml_text(exp_xml, "Platform")
    experiment_accession = _clean(_field(item, "Accession", "accession")) or _xml_attr(exp_xml, "Experiment", "acc") or uid
    runs = _run_attrs(runs_xml)
    records: list[EvidenceRecord] = []
    if not runs:
        return records
    for run_index, run in enumerate(runs, start=1):
        run_accession = run.get("acc") or experiment_accession
        spots = run.get("total_spots", "")
        bases = run.get("total_bases", "")
        url = f"https://www.ncbi.nlm.nih.gov/sra/{run_accession}"
        text = " ".join(
            part
            for part in (
                f"SRA Aedes aegypti RNA-seq run {run_accession}.",
                f"Experiment: {experiment_accession}.",
                f"Title: {title}.",
                f"BioProject: {bioproject}." if bioproject else "",
                f"BioSample: {biosample}." if biosample else "",
                f"Platform: {platform}." if platform else "",
                f"Spots: {spots}." if spots else "",
                f"Bases: {bases}." if bases else "",
            )
            if part
        )
        records.append(
            EvidenceRecord(
                record_id=f"expression:sra_run:{run_accession}",
                lane="expression",
                source=EXPRESSION_OMICS_SOURCE_ID,
                title=f"SRA RNA-seq run {run_accession}: {title}",
                text=text,
                species="Aedes aegypti",
                url=url,
                media_url=None,
                provenance=Provenance(
                    source_id=EXPRESSION_OMICS_SOURCE_ID,
                    locator=f"{raw_path.as_posix()}#result/{uid}/run/{run_index}",
                    retrieved_at=retrieved_at,
                    license="NCBI SRA public metadata",
                    source_url=url,
                ),
                payload={
                    "db": "sra",
                    "uid": uid,
                    "experiment_accession": experiment_accession,
                    "run_accession": run_accession,
                    "title": title,
                    "bioproject": bioproject,
                    "biosample": biosample,
                    "platform": platform,
                    "total_spots": spots,
                    "total_bases": bases,
                    "raw_json_path": raw_path.as_posix(),
                },
            )
        )
    return records


def fetch_expression_omics_records(
    *,
    raw_dir: Path,
    fetch_json=None,
    retrieved_at: str,
    geo_limit: int = 25,
    sra_limit: int = 25,
    search_page_size: int = 100,
    summary_batch_size: int = 100,
) -> ExpressionOmicsResult:
    fetch = fetch_json or _default_fetch_json
    raw_dir.mkdir(parents=True, exist_ok=True)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []
    search_page_size = max(1, int(search_page_size))
    summary_batch_size = max(1, int(summary_batch_size))
    boundary_path, analysis_gaps = _analysis_scope_boundary(raw_dir, retrieved_at)
    raw_artifacts.append(boundary_path.as_posix())
    gaps.extend(analysis_gaps)
    records.extend(_analysis_scope_gap_records(boundary_path, analysis_gaps, retrieved_at=retrieved_at))

    for db, term, limit, no_result_reason in (
        ("gds", GEO_TERM, geo_limit, "expression_omics_no_geo_results"),
        ("sra", SRA_TERM, sra_limit, "expression_omics_no_sra_results"),
    ):
        limit = max(0, int(limit))
        ids: list[str] = []
        total_count = 0
        search_payloads: list[tuple[int, dict[str, object]]] = []
        search_failed = False
        search_starts = [0] if limit == 0 else list(range(0, limit, search_page_size))
        for retstart in search_starts:
            if fetch_json is None and requested_urls:
                time.sleep(0.34)
            retmax = 0 if limit == 0 else min(search_page_size, limit - len(ids))
            search_url = _eutils_url("esearch", db=db, term=term, retmode="json", retmax=retmax, retstart=retstart)
            requested_urls.append(search_url)
            try:
                search_payload = fetch(search_url)
            except Exception as exc:
                gaps.append({"source": EXPRESSION_OMICS_SOURCE_ID, "lane": "expression", "db": db, "reason": "expression_omics_search_failed", "error": str(exc), "retrieved_at": retrieved_at})
                search_failed = True
                break
            if not search_payloads:
                total_count = _result_count(search_payload)
            search_payloads.append((retstart, search_payload))
            page_ids = _ids(search_payload)
            ids.extend(page_ids)
            if limit == 0 or not page_ids or len(ids) >= limit or len(ids) >= total_count:
                break
        if search_failed and not search_payloads:
            continue
        for ordinal, (_retstart, search_payload) in enumerate(search_payloads):
            search_raw = _write_raw(raw_dir, _paged_raw_name(db, "esearch", ordinal, len(search_payloads)), search_payload)
            raw_artifacts.append(search_raw.as_posix())
        ids = ids[:limit]
        if total_count > len(ids):
            gaps.append(
                {
                    "source": EXPRESSION_OMICS_SOURCE_ID,
                    "lane": "expression",
                    "db": db,
                    "reason": "expression_omics_limit_applied",
                    "total_count": total_count,
                    "fetched_count": len(ids),
                    "limit": max(0, int(limit)),
                    "retrieved_at": retrieved_at,
                }
            )
        if not ids:
            gaps.append({"source": EXPRESSION_OMICS_SOURCE_ID, "lane": "expression", "db": db, "reason": no_result_reason, "retrieved_at": retrieved_at})
            continue
        summary_batches = _chunked(ids, summary_batch_size)
        for ordinal, summary_ids in enumerate(summary_batches):
            if fetch_json is None:
                time.sleep(0.34)
            summary_url = _eutils_url("esummary", db=db, id=",".join(summary_ids), retmode="json")
            requested_urls.append(summary_url)
            try:
                summary_payload = fetch(summary_url)
            except Exception as exc:
                gaps.append({"source": EXPRESSION_OMICS_SOURCE_ID, "lane": "expression", "db": db, "reason": "expression_omics_summary_failed", "error": str(exc), "retrieved_at": retrieved_at, "ids": summary_ids})
                continue
            summary_raw = _write_raw(raw_dir, _paged_raw_name(db, "esummary", ordinal, len(summary_batches)), summary_payload)
            raw_artifacts.append(summary_raw.as_posix())
            for uid, item in _summary_items(summary_payload):
                if db == "gds":
                    records.append(_geo_record(uid, item, raw_path=summary_raw, retrieved_at=retrieved_at))
                else:
                    sra_records = _sra_records(uid, item, raw_path=summary_raw, retrieved_at=retrieved_at)
                    if not sra_records:
                        gaps.append(
                            {
                                "source": EXPRESSION_OMICS_SOURCE_ID,
                                "lane": "expression",
                                "db": db,
                                "uid": uid,
                                "reason": "expression_omics_sra_runs_missing",
                                "retrieved_at": retrieved_at,
                            }
                        )
                    records.extend(sra_records)

    return ExpressionOmicsResult(
        source_id=EXPRESSION_OMICS_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
    )
