from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import re
import time
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


DROSOPHILA_SUZUKII_NCBI_NUCLEOTIDE_SOURCE_ID = "drosophila_suzukii_ncbi_nucleotide"
SPECIES = "Drosophila suzukii"
COMMON_NAME = "spotted wing drosophila"
NCBI_API_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_NUCCORE_QUERY = (
    'Drosophila suzukii[Organism] AND (COI OR COX1 OR "cytochrome oxidase" OR barcode)'
)
NCBI_NUCCORE_LICENSE = "NCBI GenBank nucleotide metadata; source terms apply"
USER_AGENT = "ask-insects/0.1 (+https://openinsects.org)"


@dataclass(frozen=True)
class DrosophilaSuzukiiNcbiNucleotideResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    query: str
    reported_total_count: int
    candidate_count: int
    existing_barcode_row_count: int
    bold_accession_matched_count: int
    genbank_only_count: int


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_raw_json(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def fetch_json_url(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError(f"URL returned non-object JSON for {url}")
            return payload
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("unreachable")


def _eutils_url(endpoint: str, **params: object) -> str:
    values = {key: str(value) for key, value in params.items() if value is not None}
    values.setdefault("retmode", "json")
    values.setdefault("tool", "ask_insects")
    return f"{NCBI_API_BASE}/{endpoint}.fcgi?{urlencode(values)}"


def _safe_id(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value or "")).strip("_") or "unknown"


def _as_string(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _int_value(value: object, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _normalize_accession(value: object) -> str:
    text = _as_string(value).upper()
    return text.split(".", 1)[0] if text else ""


def _candidate_ids(search_payload: dict[str, object]) -> tuple[list[str], int]:
    result = search_payload.get("esearchresult")
    if not isinstance(result, dict):
        return [], 0
    raw_ids = result.get("idlist")
    ids = [str(value) for value in raw_ids if value] if isinstance(raw_ids, list) else []
    return ids, _int_value(result.get("count"))


def _summary_items(summary_payload: dict[str, object]) -> Iterable[tuple[str, dict[str, object]]]:
    result = summary_payload.get("result")
    if not isinstance(result, dict):
        return []
    uids = result.get("uids")
    ids = [str(uid) for uid in uids if uid] if isinstance(uids, list) else []
    return [(uid, result[uid]) for uid in ids if isinstance(result.get(uid), dict)]


def _parse_source_modifiers(item: dict[str, object]) -> dict[str, str]:
    subtypes = _as_string(item.get("subtype")).split("|") if item.get("subtype") else []
    subnames = _as_string(item.get("subname")).split("|") if item.get("subname") else []
    parsed: dict[str, str] = {}
    for key, value in zip(subtypes, subnames, strict=False):
        key = key.strip()
        value = value.strip()
        if key and value:
            parsed[key] = value
    return parsed


def _existing_accession_index(existing_barcode_rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    by_accession: dict[str, list[dict[str, object]]] = {}
    for row in existing_barcode_rows:
        candidates = [
            row.get("genbank_accession"),
            row.get("accession"),
        ]
        payload = row.get("payload")
        if isinstance(payload, dict):
            candidates.extend(
                [
                    payload.get("genbank_accession"),
                    payload.get("accession"),
                    (payload.get("bold_row") or {}).get("genbank_accession") if isinstance(payload.get("bold_row"), dict) else None,
                ]
            )
        for candidate in candidates:
            accession = _normalize_accession(candidate)
            if accession:
                by_accession.setdefault(accession, []).append(row)
    return by_accession


def _marker_from_item(item: dict[str, object]) -> str:
    haystack = " ".join(_as_string(item.get(key)) for key in ("title", "extra", "tech")).lower()
    if "coi-5p" in haystack:
        return "COI-5P"
    if "cox1" in haystack or "coi" in haystack or "cytochrome oxidase subunit 1" in haystack:
        return "COI/COX1"
    if "cytochrome oxidase" in haystack:
        return "cytochrome oxidase"
    if "barcode" in haystack:
        return "barcode"
    return "nucleotide"


def _record_for_item(
    *,
    uid: str,
    item: dict[str, object],
    raw_path: Path,
    retrieved_at: str,
    by_accession: dict[str, list[dict[str, object]]],
) -> EvidenceRecord:
    title = _as_string(item.get("title")) or f"NCBI nuccore UID {uid}"
    accession_version = _as_string(item.get("accessionversion")) or _as_string(item.get("caption"))
    accession = _normalize_accession(accession_version)
    source_modifiers = _parse_source_modifiers(item)
    marker = _marker_from_item(item)
    matched_rows = by_accession.get(accession, []) if accession else []
    matched_record_ids = sorted({_as_string(row.get("record_id")) for row in matched_rows if row.get("record_id")})
    match_status = "bold_accession_matched" if matched_record_ids else "genbank_only"
    sequence_length = _int_value(item.get("slen"))
    url = f"https://www.ncbi.nlm.nih.gov/nuccore/{accession_version or uid}"
    payload = {
        "atom_type": "ncbi_nucleotide_crosscheck",
        "uid": uid,
        "accession_version": accession_version or None,
        "accession": accession or None,
        "title": title,
        "marker": marker,
        "sequence_length": sequence_length or None,
        "biomol": _as_string(item.get("biomol")) or None,
        "moltype": _as_string(item.get("moltype")) or None,
        "topology": _as_string(item.get("topology")) or None,
        "source_db": _as_string(item.get("sourcedb")) or None,
        "genome": _as_string(item.get("genome")) or None,
        "tech": _as_string(item.get("tech")) or None,
        "taxid": _int_value(item.get("taxid")) or None,
        "createdate": _as_string(item.get("createdate")) or None,
        "updatedate": _as_string(item.get("updatedate")) or None,
        "source_modifiers": source_modifiers,
        "country": source_modifiers.get("country"),
        "collection_date": source_modifiers.get("collection_date"),
        "specimen_voucher": source_modifiers.get("specimen_voucher"),
        "bold_match_status": match_status,
        "matched_bold_record_ids": matched_record_ids,
        "candidate_source": "ncbi_nuccore_esearch_esummary",
        "query": NCBI_NUCCORE_QUERY,
        "scope": f"{SPECIES} GenBank COI/barcode nucleotide cross-check",
        "primary_taxon": SPECIES,
        "common_name": COMMON_NAME,
    }
    text_parts = [
        title,
        f"{SPECIES} ({COMMON_NAME}) NCBI GenBank nucleotide cross-check.",
        f"accession={accession_version or uid}",
        f"marker={marker}",
        f"bold_match_status={match_status}",
    ]
    if sequence_length:
        text_parts.append(f"sequence_length={sequence_length} bp")
    for label, key in (("country", "country"), ("collection_date", "collection_date"), ("voucher", "specimen_voucher")):
        if source_modifiers.get(key):
            text_parts.append(f"{label}={source_modifiers[key]}")
    if matched_record_ids:
        text_parts.append("matched_bold_record_ids=" + "; ".join(matched_record_ids[:10]))
    return EvidenceRecord(
        record_id=f"swd_ncbi_nucleotide:nuccore:{_safe_id(accession_version or uid)}",
        lane="dna_barcodes",
        source=DROSOPHILA_SUZUKII_NCBI_NUCLEOTIDE_SOURCE_ID,
        title=title,
        text=" ".join(text_parts),
        species=SPECIES,
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_NCBI_NUCLEOTIDE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#result/{uid}",
            retrieved_at=retrieved_at,
            license=NCBI_NUCCORE_LICENSE,
            source_url=url,
        ),
        payload=payload,
    )


def fetch_drosophila_suzukii_ncbi_nucleotide_records(
    *,
    raw_dir: Path,
    existing_barcode_rows: list[dict[str, object]] | None = None,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
    max_results: int = 1000,
    page_size: int = 100,
    delay_seconds: float = 0.34,
) -> DrosophilaSuzukiiNcbiNucleotideResult:
    retrieved = retrieved_at or utc_now()
    fetch = fetch_json or fetch_json_url
    max_results = max(0, max_results)
    page_size = max(1, min(page_size, 500))
    by_accession = _existing_accession_index(existing_barcode_rows or [])
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []
    search_url = _eutils_url(
        "esearch",
        db="nuccore",
        term=NCBI_NUCCORE_QUERY,
        retmax=max_results,
        retstart=0,
        sort="relevance",
    )
    requested_urls.append(search_url)
    try:
        search_payload = fetch(search_url)
    except Exception as exc:
        return DrosophilaSuzukiiNcbiNucleotideResult(
            source_id=DROSOPHILA_SUZUKII_NCBI_NUCLEOTIDE_SOURCE_ID,
            records=[],
            gaps=[
                {
                    "source": DROSOPHILA_SUZUKII_NCBI_NUCLEOTIDE_SOURCE_ID,
                    "lane": "dna_barcodes",
                    "species": SPECIES,
                    "reason": "swd_ncbi_nucleotide_search_failed",
                    "error": str(exc),
                    "query": NCBI_NUCCORE_QUERY,
                    "retrieved_at": retrieved,
                }
            ],
            raw_artifacts=[],
            requested_urls=requested_urls,
            query=NCBI_NUCCORE_QUERY,
            reported_total_count=0,
            candidate_count=0,
            existing_barcode_row_count=len(existing_barcode_rows or []),
            bold_accession_matched_count=0,
            genbank_only_count=0,
        )
    search_path = write_raw_json(raw_dir, "nuccore_esearch.json", search_payload)
    raw_artifacts.append(search_path.as_posix())
    candidate_ids, reported_total = _candidate_ids(search_payload)
    if reported_total > max_results:
        gaps.append(
            {
                "source": DROSOPHILA_SUZUKII_NCBI_NUCLEOTIDE_SOURCE_ID,
                "lane": "dna_barcodes",
                "species": SPECIES,
                "reason": "swd_ncbi_nucleotide_limit_applied",
                "reported_total_count": reported_total,
                "max_results": max_results,
                "query": NCBI_NUCCORE_QUERY,
                "retrieved_at": retrieved,
            }
        )
    records: list[EvidenceRecord] = []
    for start in range(0, len(candidate_ids), page_size):
        page_ids = candidate_ids[start : start + page_size]
        if not page_ids:
            continue
        summary_url = _eutils_url("esummary", db="nuccore", id=",".join(page_ids))
        requested_urls.append(summary_url)
        try:
            summary_payload = fetch(summary_url)
        except Exception as exc:
            gaps.append(
                {
                    "source": DROSOPHILA_SUZUKII_NCBI_NUCLEOTIDE_SOURCE_ID,
                    "lane": "dna_barcodes",
                    "species": SPECIES,
                    "reason": "swd_ncbi_nucleotide_summary_failed",
                    "error": str(exc),
                    "id_count": len(page_ids),
                    "retrieved_at": retrieved,
                }
            )
            break
        summary_path = write_raw_json(raw_dir, f"nuccore_esummary_{(start // page_size) + 1:04d}.json", summary_payload)
        raw_artifacts.append(summary_path.as_posix())
        for uid, item in _summary_items(summary_payload):
            records.append(
                _record_for_item(
                    uid=uid,
                    item=item,
                    raw_path=summary_path,
                    retrieved_at=retrieved,
                    by_accession=by_accession,
                )
            )
        if delay_seconds and start + page_size < len(candidate_ids):
            time.sleep(max(0.0, delay_seconds))
    matched_count = sum(1 for record in records if record.payload and record.payload.get("bold_match_status") == "bold_accession_matched")
    return DrosophilaSuzukiiNcbiNucleotideResult(
        source_id=DROSOPHILA_SUZUKII_NCBI_NUCLEOTIDE_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        query=NCBI_NUCCORE_QUERY,
        reported_total_count=reported_total,
        candidate_count=len(candidate_ids),
        existing_barcode_row_count=len(existing_barcode_rows or []),
        bold_accession_matched_count=matched_count,
        genbank_only_count=len(records) - matched_count,
    )
