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


DROSOPHILA_SUZUKII_NCBI_MARKER_REVIEW_SOURCE_ID = "drosophila_suzukii_ncbi_marker_review"
SPECIES = "Drosophila suzukii"
COMMON_NAME = "spotted wing drosophila"
NCBI_API_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_MARKER_REVIEW_QUERY = (
    'Drosophila suzukii[Organism] AND (mitochondrion OR mitochondrial OR COI OR COX1 OR COII OR COX2 '
    'OR NADH OR ND1 OR ND2 OR ND3 OR ND4 OR ND5 OR ND6 OR cytochrome OR ribosomal OR "18S" OR "28S" '
    'OR ITS OR "internal transcribed spacer" OR "elongation factor" OR EF1 OR nuclear OR barcode)'
)
NCBI_MARKER_REVIEW_LICENSE = "NCBI GenBank nucleotide metadata; source terms apply"
USER_AGENT = "ask-insects/0.1 (+https://openinsects.org)"


@dataclass(frozen=True)
class DrosophilaSuzukiiNcbiMarkerReviewResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    query: str
    reported_total_count: int
    fetched_count: int
    page_count: int
    marker_group_counts: dict[str, int]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _write_raw_json(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _eutils_url(endpoint: str, **params: object) -> str:
    values = {key: str(value) for key, value in params.items() if value is not None}
    values.setdefault("retmode", "json")
    values.setdefault("tool", "ask_insects")
    return f"{NCBI_API_BASE}/{endpoint}.fcgi?{urlencode(values)}"


def _as_string(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _int_value(value: object, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _safe_id(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value or "")).strip("_") or "unknown"


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


def _marker_group(item: dict[str, object]) -> str:
    haystack = " ".join(_as_string(item.get(key)) for key in ("title", "extra", "tech", "genome")).lower()
    if any(
        term in haystack
        for term in (
            "coi",
            "cox1",
            "cytochrome oxidase subunit 1",
            "cytochrome oxidase subunit i",
            "cytochrome c oxidase subunit 1",
            "cytochrome c oxidase subunit i",
            "barcode",
        )
    ):
        return "mitochondrial_coi_barcode"
    if any(term in haystack for term in ("cox2", "coii", "cytochrome b", "nadh", "nd1", "nd2", "nd3", "nd4", "nd5", "nd6", "mitochond")):
        return "mitochondrial_other"
    if any(term in haystack for term in ("18s", "28s", "ribosomal", "internal transcribed spacer", "its1", "its2")):
        return "nuclear_ribosomal_or_its"
    if any(term in haystack for term in ("elongation factor", "ef1", "ef-1", "nuclear")):
        return "nuclear_protein_coding_or_other"
    return "marker_review_other"


def _record_for_item(*, uid: str, item: dict[str, object], raw_path: Path, retrieved_at: str) -> EvidenceRecord:
    title = _as_string(item.get("title")) or f"NCBI nuccore UID {uid}"
    accession_version = _as_string(item.get("accessionversion")) or _as_string(item.get("caption")) or uid
    sequence_length = _int_value(item.get("slen"))
    marker_group = _marker_group(item)
    url = f"https://www.ncbi.nlm.nih.gov/nuccore/{accession_version}"
    payload = {
        "atom_type": "ncbi_marker_review",
        "uid": uid,
        "accession_version": accession_version,
        "title": title,
        "marker_group": marker_group,
        "sequence_length": sequence_length or None,
        "biomol": _as_string(item.get("biomol")) or None,
        "moltype": _as_string(item.get("moltype")) or None,
        "genome": _as_string(item.get("genome")) or None,
        "tech": _as_string(item.get("tech")) or None,
        "taxid": _int_value(item.get("taxid")) or None,
        "createdate": _as_string(item.get("createdate")) or None,
        "updatedate": _as_string(item.get("updatedate")) or None,
        "candidate_source": "ncbi_nuccore_esearch_esummary",
        "query": NCBI_MARKER_REVIEW_QUERY,
        "scope": f"{SPECIES} broader mitochondrial/nuclear marker review",
        "primary_taxon": SPECIES,
        "common_name": COMMON_NAME,
    }
    text = (
        f"{title} {SPECIES} ({COMMON_NAME}) NCBI broader marker-review record. "
        f"accession={accession_version} marker_group={marker_group}"
    )
    if sequence_length:
        text += f" sequence_length={sequence_length} bp"
    return EvidenceRecord(
        record_id=f"swd_ncbi_marker_review:nuccore:{_safe_id(accession_version)}",
        lane="dna_barcodes",
        source=DROSOPHILA_SUZUKII_NCBI_MARKER_REVIEW_SOURCE_ID,
        title=title,
        text=text,
        species=SPECIES,
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_NCBI_MARKER_REVIEW_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#result/{uid}",
            retrieved_at=retrieved_at,
            license=NCBI_MARKER_REVIEW_LICENSE,
            source_url=url,
        ),
        payload=payload,
    )


def fetch_drosophila_suzukii_ncbi_marker_review_records(
    *,
    raw_dir: Path,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
    max_results: int = 2000,
    page_size: int = 100,
    delay_seconds: float = 0.34,
) -> DrosophilaSuzukiiNcbiMarkerReviewResult:
    retrieved = retrieved_at or utc_now()
    fetch = fetch_json or fetch_json_url
    max_results = max(0, max_results)
    page_size = max(1, min(page_size, 500))
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []
    search_url = _eutils_url(
        "esearch",
        db="nuccore",
        term=NCBI_MARKER_REVIEW_QUERY,
        retmax=max_results,
        retstart=0,
        sort="relevance",
    )
    requested_urls.append(search_url)
    try:
        search_payload = fetch(search_url)
    except Exception as exc:
        return DrosophilaSuzukiiNcbiMarkerReviewResult(
            source_id=DROSOPHILA_SUZUKII_NCBI_MARKER_REVIEW_SOURCE_ID,
            records=[],
            gaps=[
                {
                    "source": DROSOPHILA_SUZUKII_NCBI_MARKER_REVIEW_SOURCE_ID,
                    "lane": "dna_barcodes",
                    "species": SPECIES,
                    "reason": "swd_ncbi_marker_review_search_failed",
                    "error": str(exc),
                    "query": NCBI_MARKER_REVIEW_QUERY,
                    "retrieved_at": retrieved,
                }
            ],
            raw_artifacts=[],
            requested_urls=requested_urls,
            query=NCBI_MARKER_REVIEW_QUERY,
            reported_total_count=0,
            fetched_count=0,
            page_count=0,
            marker_group_counts={},
        )
    search_path = _write_raw_json(raw_dir, "Drosophila_suzukii_marker_review_esearch.json", search_payload)
    raw_artifacts.append(search_path.as_posix())
    ids, reported_total = _candidate_ids(search_payload)
    if reported_total > len(ids):
        gaps.append(
            {
                "source": DROSOPHILA_SUZUKII_NCBI_MARKER_REVIEW_SOURCE_ID,
                "lane": "dna_barcodes",
                "species": SPECIES,
                "reason": "swd_ncbi_marker_review_limit_applied",
                "reported_total_count": reported_total,
                "fetched_id_count": len(ids),
                "max_results": max_results,
                "retrieved_at": retrieved,
            }
        )
    records: list[EvidenceRecord] = []
    page_count = 0
    marker_group_counts: dict[str, int] = {}
    for page_start in range(0, len(ids), page_size):
        page_ids = ids[page_start : page_start + page_size]
        if not page_ids:
            continue
        if page_start and delay_seconds:
            time.sleep(delay_seconds)
        summary_url = _eutils_url("esummary", db="nuccore", id=",".join(page_ids))
        requested_urls.append(summary_url)
        try:
            summary_payload = fetch(summary_url)
        except Exception as exc:
            gaps.append(
                {
                    "source": DROSOPHILA_SUZUKII_NCBI_MARKER_REVIEW_SOURCE_ID,
                    "lane": "dna_barcodes",
                    "species": SPECIES,
                    "reason": "swd_ncbi_marker_review_summary_failed",
                    "error": str(exc),
                    "ids": page_ids,
                    "retrieved_at": retrieved,
                }
            )
            continue
        summary_path = _write_raw_json(raw_dir, f"Drosophila_suzukii_marker_review_esummary_{page_start:06d}.json", summary_payload)
        raw_artifacts.append(summary_path.as_posix())
        page_count += 1
        for uid, item in _summary_items(summary_payload):
            record = _record_for_item(uid=uid, item=item, raw_path=summary_path, retrieved_at=retrieved)
            records.append(record)
            group = str(record.payload.get("marker_group") if record.payload else "unknown")
            marker_group_counts[group] = marker_group_counts.get(group, 0) + 1
    return DrosophilaSuzukiiNcbiMarkerReviewResult(
        source_id=DROSOPHILA_SUZUKII_NCBI_MARKER_REVIEW_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        query=NCBI_MARKER_REVIEW_QUERY,
        reported_total_count=reported_total,
        fetched_count=len(records),
        page_count=page_count,
        marker_group_counts=marker_group_counts,
    )
