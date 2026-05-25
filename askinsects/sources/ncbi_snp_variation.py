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


NCBI_SNP_VARIATION_SOURCE_ID = "aedes_ncbi_snp_variation"
NCBI_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_SNP_SPECIES = "Aedes aegypti"
USER_AGENT = "AskInsects/0.1 source-plane"
NCBI_SNP_LICENSE = "NCBI dbSNP public metadata; NCBI terms apply"


@dataclass(frozen=True)
class NCBISnpVariationResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    species: str
    total_count: int
    requested_limit: int
    fetched_count: int
    page_count: int


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_name(value: str | None) -> str:
    if not value:
        return "unknown"
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_") or "unknown"


def write_raw_json(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


class NCBISnpClient:
    def __init__(self, fetch_json: Callable[[str], dict[str, object]] | None = None):
        self.fetch_json = fetch_json or self._fetch_json

    def esearch(self, *, species: str, retstart: int, retmax: int) -> tuple[str, dict[str, object]]:
        params = {
            "db": "snp",
            "term": f'"{species}"[Organism]',
            "retmode": "json",
            "retstart": retstart,
            "retmax": retmax,
            "sort": "snp_id",
            "tool": "ask-insects",
        }
        url = f"{NCBI_EUTILS_BASE}/esearch.fcgi?{urlencode(params)}"
        return url, self.fetch_json(url)

    def esummary(self, ids: list[str]) -> tuple[str, dict[str, object]]:
        params = {
            "db": "snp",
            "id": ",".join(ids),
            "retmode": "json",
            "tool": "ask-insects",
        }
        url = f"{NCBI_EUTILS_BASE}/esummary.fcgi?{urlencode(params)}"
        return url, self.fetch_json(url)

    @staticmethod
    def _fetch_json(url: str) -> dict[str, object]:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        for attempt in range(3):
            try:
                with urlopen(request, timeout=90) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except HTTPError as exc:
                if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                    raise
                time.sleep(1.0 + attempt)
        if not isinstance(payload, dict):
            raise ValueError(f"NCBI dbSNP endpoint returned non-object JSON for {url}")
        return payload


def _snp_url(uid: str) -> str:
    return f"https://www.ncbi.nlm.nih.gov/snp/{uid}"


def _summary_value(summary: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = summary.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _snp_record(
    summary: dict[str, object],
    *,
    species: str,
    raw_path: Path,
    summary_url: str,
    retrieved_at: str,
) -> EvidenceRecord:
    uid = str(summary.get("uid") or summary.get("snp_id") or summary.get("refsnp_id") or "unknown")
    rsid = uid if uid.lower().startswith("rs") else f"rs{uid}"
    chromosome = _summary_value(summary, "chr", "chromosome", "chrpos")
    allele = _summary_value(summary, "allele", "alleles", "variation")
    fxn = _summary_value(summary, "fxn_class", "function_class", "function")
    gene = _summary_value(summary, "genes", "gene", "gene_name")
    assembly = _summary_value(summary, "assembly", "build")
    title = f"{species} dbSNP variant {rsid}"
    text_parts = [
        f"NCBI dbSNP variant {rsid} for {species}.",
        f"Chromosome or position: {chromosome}." if chromosome else "",
        f"Allele or variation: {allele}." if allele else "",
        f"Functional class: {fxn}." if fxn else "",
        f"Gene: {gene}." if gene else "",
        f"Assembly: {assembly}." if assembly else "",
    ]
    return EvidenceRecord(
        record_id=f"ncbi_snp_variation:{rsid}",
        lane="genome_features",
        source=NCBI_SNP_VARIATION_SOURCE_ID,
        title=title,
        text=" ".join(part for part in text_parts if part),
        species=species,
        url=_snp_url(rsid),
        media_url=None,
        provenance=Provenance(
            source_id=NCBI_SNP_VARIATION_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#uid/{uid}",
            retrieved_at=retrieved_at,
            license=NCBI_SNP_LICENSE,
            source_url=summary_url,
        ),
        payload={"uid": uid, "rsid": rsid, "raw_summary": summary},
    )


def _gap_record(gap: dict[str, object], *, raw_path: Path | None, source_url: str | None, retrieved_at: str) -> EvidenceRecord:
    reason = str(gap.get("reason") or "ncbi_snp_variation_gap")
    species = str(gap.get("species") or DEFAULT_SNP_SPECIES)
    locator = raw_path.as_posix() if raw_path else str(gap.get("locator") or "ncbi dbSNP request")
    title = f"Aedes aegypti NCBI dbSNP variation source gap: {reason}"
    if reason == "ncbi_snp_no_aedes_records":
        text = (
            f"NCBI dbSNP returned zero records for {species} using the bounded organism query. "
            "Ask Insects records this as an explicit variant-source gap instead of implying NCBI dbSNP variants are indexed."
        )
    else:
        text = f"NCBI dbSNP variation audit gap for {species}: {reason}."
    return EvidenceRecord(
        record_id=f"ncbi_snp_variation:gap:{safe_name(species).lower()}:{safe_name(reason).lower()}",
        lane="genome_features",
        source=NCBI_SNP_VARIATION_SOURCE_ID,
        title=title,
        text=text,
        species=species,
        url=source_url,
        media_url=None,
        provenance=Provenance(
            source_id=NCBI_SNP_VARIATION_SOURCE_ID,
            locator=f"{locator}#gap/{reason}",
            retrieved_at=retrieved_at,
            license=NCBI_SNP_LICENSE,
            source_url=source_url,
        ),
        payload={"gap": gap},
    )


def _ids_from_search(payload: dict[str, object]) -> tuple[list[str], int]:
    result = payload.get("esearchresult")
    if not isinstance(result, dict):
        return [], 0
    ids = [str(value) for value in result.get("idlist", []) if value]
    try:
        count = int(str(result.get("count") or "0"))
    except ValueError:
        count = 0
    return ids, count


def fetch_ncbi_snp_variation_records(
    *,
    species: str = DEFAULT_SNP_SPECIES,
    raw_dir: Path,
    limit: int = 1000,
    page_size: int = 200,
    delay_seconds: float = 0.34,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
) -> NCBISnpVariationResult:
    retrieved = retrieved_at or utc_now()
    client = NCBISnpClient(fetch_json)
    requested_limit = max(0, limit)
    page_size = max(1, page_size)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    fetched_ids: list[str] = []
    total_count = 0
    page_count = 0
    first_search_path: Path | None = None
    first_search_url: str | None = None

    for retstart in range(0, requested_limit, page_size):
        retmax = min(page_size, requested_limit - retstart)
        try:
            search_url, search_payload = client.esearch(species=species, retstart=retstart, retmax=retmax)
        except Exception as exc:
            gap = {
                "source": NCBI_SNP_VARIATION_SOURCE_ID,
                "lane": "genome_features",
                "reason": "ncbi_snp_search_failed",
                "species": species,
                "retstart": retstart,
                "error": str(exc),
                "retrieved_at": retrieved,
            }
            gaps.append(gap)
            records.append(_gap_record(gap, raw_path=None, source_url=None, retrieved_at=retrieved))
            break
        search_path = write_raw_json(raw_dir, f"{safe_name(species)}_snp_esearch_{retstart:06d}.json", search_payload)
        if first_search_path is None:
            first_search_path = search_path
            first_search_url = search_url
        raw_artifacts.append(search_path.as_posix())
        page_count += 1
        ids, reported_count = _ids_from_search(search_payload)
        total_count = max(total_count, reported_count)
        if not ids:
            break
        fetched_ids.extend(ids)
        if delay_seconds:
            time.sleep(delay_seconds)
        try:
            summary_url, summary_payload = client.esummary(ids)
        except Exception as exc:
            gap = {
                "source": NCBI_SNP_VARIATION_SOURCE_ID,
                "lane": "genome_features",
                "reason": "ncbi_snp_summary_failed",
                "species": species,
                "retstart": retstart,
                "ids": ids,
                "error": str(exc),
                "retrieved_at": retrieved,
            }
            gaps.append(gap)
            records.append(_gap_record(gap, raw_path=search_path, source_url=search_url, retrieved_at=retrieved))
            continue
        summary_path = write_raw_json(raw_dir, f"{safe_name(species)}_snp_esummary_{retstart:06d}.json", summary_payload)
        raw_artifacts.append(summary_path.as_posix())
        result = summary_payload.get("result")
        if not isinstance(result, dict):
            gap = {
                "source": NCBI_SNP_VARIATION_SOURCE_ID,
                "lane": "genome_features",
                "reason": "ncbi_snp_summary_missing_result",
                "species": species,
                "retstart": retstart,
                "retrieved_at": retrieved,
            }
            gaps.append(gap)
            records.append(_gap_record(gap, raw_path=summary_path, source_url=summary_url, retrieved_at=retrieved))
            continue
        for uid in ids:
            summary = result.get(uid)
            if isinstance(summary, dict):
                records.append(
                    _snp_record(
                        summary,
                        species=species,
                        raw_path=summary_path,
                        summary_url=summary_url,
                        retrieved_at=retrieved,
                    )
                )
        if delay_seconds:
            time.sleep(delay_seconds)

    if total_count == 0 and not any(str(gap.get("reason", "")).endswith("_failed") for gap in gaps):
        gap = {
            "source": NCBI_SNP_VARIATION_SOURCE_ID,
            "lane": "genome_features",
            "reason": "ncbi_snp_no_aedes_records",
            "species": species,
            "reported_total_count": total_count,
            "requested_limit": requested_limit,
            "retrieved_at": retrieved,
            "locator": first_search_path.as_posix() if first_search_path else "ncbi dbSNP esearch",
        }
        gaps.append(gap)
        records.append(_gap_record(gap, raw_path=first_search_path, source_url=first_search_url, retrieved_at=retrieved))
    elif total_count > len([record for record in records if not record.record_id.startswith("ncbi_snp_variation:gap:")]):
        gaps.append(
            {
                "source": NCBI_SNP_VARIATION_SOURCE_ID,
                "lane": "genome_features",
                "reason": "ncbi_snp_limit_applied",
                "species": species,
                "reported_total_count": total_count,
                "record_count": len(records),
                "requested_limit": requested_limit,
                "retrieved_at": retrieved,
            }
        )

    return NCBISnpVariationResult(
        source_id=NCBI_SNP_VARIATION_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        species=species,
        total_count=total_count,
        requested_limit=requested_limit,
        fetched_count=len(fetched_ids),
        page_count=page_count,
    )
