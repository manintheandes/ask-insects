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


EXPRESSION_OMICS_SOURCE_ID = "aedes_expression_omics"
USER_AGENT = "AskInsects/0.1 source-plane"
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
GEO_TERM = '"Aedes aegypti"[Organism] AND (expression OR RNA-seq OR transcriptome)'
SRA_TERM = '"Aedes aegypti"[Organism] AND RNA-Seq'


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


def _geo_record(uid: str, item: dict[str, object], *, raw_path: Path, retrieved_at: str) -> EvidenceRecord:
    accession = _clean(_field(item, "accession")) or uid
    title = _clean(item.get("title")) or f"GEO expression dataset {accession}"
    summary = _clean(item.get("summary"))
    taxon = _clean(item.get("taxon")) or "Aedes aegypti"
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
) -> ExpressionOmicsResult:
    fetch = fetch_json or _default_fetch_json
    raw_dir.mkdir(parents=True, exist_ok=True)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []

    for db, term, limit, no_result_reason in (
        ("gds", GEO_TERM, geo_limit, "expression_omics_no_geo_results"),
        ("sra", SRA_TERM, sra_limit, "expression_omics_no_sra_results"),
    ):
        if fetch_json is None and requested_urls:
            time.sleep(0.34)
        search_url = _eutils_url("esearch", db=db, term=term, retmode="json", retmax=max(0, int(limit)))
        requested_urls.append(search_url)
        try:
            search_payload = fetch(search_url)
        except Exception as exc:
            gaps.append({"source": EXPRESSION_OMICS_SOURCE_ID, "lane": "expression", "db": db, "reason": "expression_omics_search_failed", "error": str(exc), "retrieved_at": retrieved_at})
            continue
        search_raw = _write_raw(raw_dir, f"{db}_esearch.json", search_payload)
        raw_artifacts.append(search_raw.as_posix())
        ids = _ids(search_payload)
        total_count = _result_count(search_payload)
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
        if fetch_json is None:
            time.sleep(0.34)
        summary_url = _eutils_url("esummary", db=db, id=",".join(ids), retmode="json")
        requested_urls.append(summary_url)
        try:
            summary_payload = fetch(summary_url)
        except Exception as exc:
            gaps.append({"source": EXPRESSION_OMICS_SOURCE_ID, "lane": "expression", "db": db, "reason": "expression_omics_summary_failed", "error": str(exc), "retrieved_at": retrieved_at})
            continue
        summary_raw = _write_raw(raw_dir, f"{db}_esummary.json", summary_payload)
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
