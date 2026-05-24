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
import xml.etree.ElementTree as ET

from askinsects.records import EvidenceRecord, Provenance


NCBI_BIOSAMPLE_SOURCE_ID = "ncbi_biosamples"
NCBI_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_BIOSAMPLE_SPECIES = "Aedes aegypti"
USER_AGENT = "AskInsects/0.1 source-plane"


@dataclass(frozen=True)
class NCBIBioSampleResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    species: str
    total_count: int
    requested_limit: int
    fetched_count: int
    page_count: int


class NCBIBioSampleClient:
    def __init__(self, fetch_json: Callable[[str], dict[str, object]] | None = None):
        self.fetch_json = fetch_json or self._fetch_json

    def esearch(self, *, species: str, retstart: int, retmax: int) -> tuple[str, dict[str, object]]:
        params = {
            "db": "biosample",
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
        params = {
            "db": "biosample",
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
            raise ValueError(f"NCBI BioSample endpoint returned non-object JSON for {url}")
        return payload


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


def _biosample_url(accession: str) -> str:
    return f"https://www.ncbi.nlm.nih.gov/biosample/{accession}"


def _parse_sampledata(sampledata: str) -> dict[str, object]:
    if not sampledata.strip():
        return {"ids": {}, "attributes": {}}
    try:
        root = ET.fromstring(sampledata)
    except ET.ParseError:
        return {"ids": {}, "attributes": {}, "parse_error": "sampledata_xml_parse_failed"}

    ids: dict[str, str] = {}
    for item in root.findall("./Ids/Id"):
        key = item.attrib.get("db") or item.attrib.get("db_label") or "unknown"
        text = (item.text or "").strip()
        if text:
            if key in ids:
                ids[key] = f"{ids[key]}; {text}"
            else:
                ids[key] = text

    attributes: dict[str, str] = {}
    for item in root.findall("./Attributes/Attribute"):
        key = item.attrib.get("harmonized_name") or item.attrib.get("attribute_name") or item.attrib.get("display_name") or "unknown"
        text = (item.text or "").strip()
        if text:
            if key in attributes:
                attributes[key] = f"{attributes[key]}; {text}"
            else:
                attributes[key] = text

    owner = root.findtext("./Owner/Name")
    status = root.find("./Status")
    package = root.find("./Package")
    return {
        "ids": ids,
        "attributes": attributes,
        "owner": owner,
        "status": status.attrib if status is not None else {},
        "package": package.attrib.get("display_name") if package is not None else None,
    }


def _record_text(summary: dict[str, object], parsed: dict[str, object]) -> str:
    accession = str(summary.get("accession") or summary.get("uid") or "unknown accession")
    organism = str(summary.get("organism") or DEFAULT_BIOSAMPLE_SPECIES)
    attributes = parsed.get("attributes") if isinstance(parsed.get("attributes"), dict) else {}
    ids = parsed.get("ids") if isinstance(parsed.get("ids"), dict) else {}
    sample_name = ids.get("Sample name") or ids.get("BioSample") or accession
    geo = attributes.get("geo_loc_name") or attributes.get("geographic location") or "unknown geography"
    tissue = attributes.get("tissue") or "unknown tissue"
    isolate = attributes.get("isolate") or "unknown isolate"
    strain = attributes.get("strain") or attributes.get("breed") or "unknown strain"
    collection_date = attributes.get("collection_date") or "unknown collection date"
    isolation_source = attributes.get("isolation_source") or "unknown isolation source"
    sra = ids.get("SRA") or "no SRA id detected"
    organization = str(summary.get("organization") or parsed.get("owner") or "unknown organization")
    return (
        f"NCBI BioSample {accession} for {organism}. Sample name: {sample_name}. "
        f"Organization: {organization}. Geography: {geo}. Collection date: {collection_date}. "
        f"Tissue: {tissue}. Isolation source: {isolation_source}. Isolate: {isolate}. "
        f"Strain or breed: {strain}. Linked SRA: {sra}."
    )


def _biosample_record(
    summary: dict[str, object],
    *,
    raw_path: Path,
    summary_url: str,
    retrieved_at: str,
) -> EvidenceRecord:
    parsed = _parse_sampledata(str(summary.get("sampledata") or ""))
    accession = str(summary.get("accession") or summary.get("uid") or "unknown")
    uid = str(summary.get("uid") or accession)
    organism = str(summary.get("organism") or DEFAULT_BIOSAMPLE_SPECIES)
    attributes = parsed.get("attributes") if isinstance(parsed.get("attributes"), dict) else {}
    ids = parsed.get("ids") if isinstance(parsed.get("ids"), dict) else {}
    sample_name = ids.get("Sample name") or accession
    title = str(summary.get("title") or f"BioSample {accession}")
    searchable_bits = " ".join(
        str(value)
        for value in (
            title,
            accession,
            sample_name,
            attributes.get("geo_loc_name"),
            attributes.get("collection_date"),
            attributes.get("tissue"),
            attributes.get("isolation_source"),
            attributes.get("isolate"),
            attributes.get("strain"),
            ids.get("SRA"),
        )
        if value
    )
    return EvidenceRecord(
        record_id=f"ncbi:biosample:{accession}",
        lane="biosamples",
        source=NCBI_BIOSAMPLE_SOURCE_ID,
        title=f"{organism} BioSample {accession}: {sample_name}",
        text=f"{_record_text(summary, parsed)} Search terms: {searchable_bits}.",
        species=organism,
        url=_biosample_url(accession),
        media_url=None,
        provenance=Provenance(
            source_id=NCBI_BIOSAMPLE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#uid/{uid}",
            retrieved_at=retrieved_at,
            license="NCBI BioSample public metadata; NCBI terms apply",
            source_url=summary_url,
        ),
        payload={
            "uid": uid,
            "accession": accession,
            "organism": organism,
            "title": title,
            "summary": summary,
            "parsed_sampledata": parsed,
        },
    )


def fetch_ncbi_biosample_records(
    *,
    species: str = DEFAULT_BIOSAMPLE_SPECIES,
    raw_dir: Path,
    limit: int = 1000,
    page_size: int = 200,
    delay_seconds: float = 0.34,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
) -> NCBIBioSampleResult:
    retrieved = retrieved_at or utc_now()
    client = NCBIBioSampleClient(fetch_json)
    gaps: list[dict[str, object]] = []
    records: list[EvidenceRecord] = []
    raw_artifacts: list[str] = []
    requested_limit = max(0, limit)
    page_size = max(1, page_size)
    total_count = 0
    fetched_ids: list[str] = []
    page_count = 0

    for retstart in range(0, requested_limit, page_size):
        retmax = min(page_size, requested_limit - retstart)
        try:
            search_url, search_payload = client.esearch(species=species, retstart=retstart, retmax=retmax)
        except Exception as exc:
            gaps.append(
                {
                    "source": NCBI_BIOSAMPLE_SOURCE_ID,
                    "lane": "biosamples",
                    "reason": "biosample_esearch_failed",
                    "species": species,
                    "retstart": retstart,
                    "error": str(exc),
                    "retrieved_at": retrieved,
                }
            )
            break
        search_path = write_raw_json(raw_dir, f"{safe_name(species)}_esearch_{retstart:06d}.json", search_payload)
        raw_artifacts.append(search_path.as_posix())
        page_count += 1
        result = search_payload.get("esearchresult")
        if not isinstance(result, dict):
            gaps.append(
                {
                    "source": NCBI_BIOSAMPLE_SOURCE_ID,
                    "lane": "biosamples",
                    "reason": "biosample_esearch_missing_result",
                    "species": species,
                    "retstart": retstart,
                    "retrieved_at": retrieved,
                }
            )
            break
        total_count = int(result.get("count") or total_count or 0)
        ids = [str(value) for value in result.get("idlist", [])]
        if not ids:
            break
        fetched_ids.extend(ids)
        if delay_seconds:
            time.sleep(delay_seconds)
        try:
            summary_url, summary_payload = client.esummary(ids)
        except Exception as exc:
            gaps.append(
                {
                    "source": NCBI_BIOSAMPLE_SOURCE_ID,
                    "lane": "biosamples",
                    "reason": "biosample_esummary_failed",
                    "species": species,
                    "retstart": retstart,
                    "ids": ids,
                    "error": str(exc),
                    "retrieved_at": retrieved,
                }
            )
            continue
        summary_path = write_raw_json(raw_dir, f"{safe_name(species)}_esummary_{retstart:06d}.json", summary_payload)
        raw_artifacts.append(summary_path.as_posix())
        result_payload = summary_payload.get("result")
        if not isinstance(result_payload, dict):
            gaps.append(
                {
                    "source": NCBI_BIOSAMPLE_SOURCE_ID,
                    "lane": "biosamples",
                    "reason": "biosample_esummary_missing_result",
                    "species": species,
                    "retstart": retstart,
                    "retrieved_at": retrieved,
                }
            )
            continue
        for uid in ids:
            summary = result_payload.get(uid)
            if isinstance(summary, dict):
                records.append(_biosample_record(summary, raw_path=summary_path, summary_url=summary_url, retrieved_at=retrieved))
        if delay_seconds:
            time.sleep(delay_seconds)

    if total_count > len(records):
        gaps.append(
            {
                "source": NCBI_BIOSAMPLE_SOURCE_ID,
                "lane": "biosamples",
                "reason": "biosample_limit_applied",
                "species": species,
                "reported_total_count": total_count,
                "record_count": len(records),
                "requested_limit": requested_limit,
                "retrieved_at": retrieved,
            }
        )

    return NCBIBioSampleResult(
        source_id=NCBI_BIOSAMPLE_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        species=species,
        total_count=total_count,
        requested_limit=requested_limit,
        fetched_count=len(fetched_ids),
        page_count=page_count,
    )
