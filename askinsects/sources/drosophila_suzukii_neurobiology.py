from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import re
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance

DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID = "drosophila_suzukii_neurobiology_sources"
SPECIES = "Drosophila suzukii"
COMMON_NAME = "spotted wing drosophila"
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# GEO DataSets restricted to SWD brain/antennal/chemosensory studies.
GEO_QUERY = (
    '("Drosophila suzukii"[Organism]) AND '
    '(antenna*[All Fields] OR olfact*[All Fields] OR chemosens*[All Fields] '
    'OR brain[All Fields] OR neuron*[All Fields] OR "odorant receptor"[All Fields])'
)
GEO_LICENSE = "NCBI GEO metadata; source terms apply"
USER_AGENT = "ask-insects/0.1 (+https://openinsects.org)"

# Brain/chemosensory domains Aedes covers; absence for SWD is recorded as a gap.
# A domain counts as "present" only when one of its DISTINCTIVE phrases appears in
# the raw GEO dataset text (title/summary/type). Distinctive phrases avoid false
# "present" matches: e.g. an antennal transcriptome must NOT satisfy the antennal-
# lobe-MAP domain, and a brain-query boilerplate word must NOT satisfy connectome.
EXPECTED_DOMAINS = (
    ("whole_brain_atlas", "whole-brain atlas", ("whole brain", "whole-brain", "brain atlas")),
    ("connectome", "brain connectome", ("connectome", "connectomic")),
    ("single_nucleus_brain_rnaseq", "single-nucleus brain RNA-seq",
     ("single-nucleus", "single nucleus", "snrna", "single-cell brain")),
    ("antennal_lobe_map", "antennal lobe map", ("antennal lobe", "antennal-lobe", "glomerul")),
)


@dataclass(frozen=True)
class DrosophilaSuzukiiNeurobiologyResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    query: str
    reported_total_count: int
    dataset_count: int


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
    values = {k: str(v) for k, v in params.items() if v is not None}
    values.setdefault("retmode", "json")
    values.setdefault("tool", "ask_insects")
    return f"{EUTILS_BASE}/{endpoint}.fcgi?{urlencode(values)}"


def _safe_id(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value or "")).strip("_") or "unknown"


def _as_string(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _int_value(value: object, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _record_for_dataset(docsum: dict[str, object], *, raw_path: Path, retrieved_at: str) -> EvidenceRecord:
    accession = _as_string(docsum.get("accession")) or _as_string(docsum.get("uid"))
    title = _as_string(docsum.get("title")) or f"GEO dataset {accession}"
    summary = _as_string(docsum.get("summary"))
    url = f"https://www.ncbi.nlm.nih.gov/gds/?term={accession}" if accession else "https://www.ncbi.nlm.nih.gov/gds"
    payload = {
        "atom_type": "geo_neurobiology_dataset",
        "accession": accession,
        "title": title,
        "summary": summary,
        "taxon": _as_string(docsum.get("taxon")),
        "gds_type": _as_string(docsum.get("gdstype")),
        "n_samples": _int_value(docsum.get("n_samples")),
        "primary_taxon": SPECIES,
        "common_name": COMMON_NAME,
        "query": GEO_QUERY,
    }
    text = " ".join(
        part for part in [
            title,
            f"{SPECIES} ({COMMON_NAME}) GEO dataset from the brain/chemosensory query.",
            f"accession={accession}",
            summary,
        ] if part
    )
    return EvidenceRecord(
        record_id=f"swd_neurobiology:geo:{_safe_id(accession)}",
        lane="neurobiology",
        source=DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID,
        title=title,
        text=text,
        species=SPECIES,
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#result/{accession}",
            retrieved_at=retrieved_at,
            license=GEO_LICENSE,
            source_url=url,
        ),
        payload=payload,
    )


def fetch_drosophila_suzukii_neurobiology_records(
    *,
    raw_dir: Path,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
    max_results: int = 200,
    page_size: int = 100,
    delay_seconds: float = 0.34,
) -> DrosophilaSuzukiiNeurobiologyResult:
    retrieved = retrieved_at or utc_now()
    fetch = fetch_json or fetch_json_url
    requested_urls: list[str] = []
    raw_artifacts: list[str] = []
    gaps: list[dict[str, object]] = []
    records: list[EvidenceRecord] = []
    domain_corpus: list[str] = []  # raw GEO title/summary/type text, for absence detection
    reported_total = 0
    ids: list[str] = []
    bounded_page = max(1, min(page_size, 100))
    limit = max(1, max_results)

    search_url = _eutils_url("esearch", db="gds", term=GEO_QUERY, retmax=bounded_page, sort="relevance")
    requested_urls.append(search_url)
    try:
        search_payload = fetch(search_url)
        raw_artifacts.append(write_raw_json(raw_dir, "geo_esearch_0001.json", search_payload).as_posix())
        result = search_payload.get("esearchresult", {}) if isinstance(search_payload, dict) else {}
        raw_ids = result.get("idlist") if isinstance(result, dict) else []
        ids = [str(v) for v in raw_ids if v][:limit] if isinstance(raw_ids, list) else []
        reported_total = _int_value(result.get("count")) if isinstance(result, dict) else 0
    except Exception as exc:
        gaps.append({
            "source": DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID,
            "lane": "neurobiology",
            "reason": "swd_geo_search_failed",
            "locator": search_url,
            "retrieved_at": retrieved,
            "error": str(exc),
        })

    if ids:
        summary_url = _eutils_url("esummary", db="gds", id=",".join(ids))
        requested_urls.append(summary_url)
        if delay_seconds:
            time.sleep(delay_seconds)
        try:
            summary_payload = fetch(summary_url)
            raw_path = write_raw_json(raw_dir, "geo_esummary_0001.json", summary_payload)
            raw_artifacts.append(raw_path.as_posix())
            block = summary_payload.get("result", {}) if isinstance(summary_payload, dict) else {}
            uids = block.get("uids", []) if isinstance(block, dict) else []
            for uid in uids:
                docsum = block.get(str(uid))
                if isinstance(docsum, dict):
                    records.append(_record_for_dataset(docsum, raw_path=raw_path, retrieved_at=retrieved))
                    domain_corpus.append(
                        " ".join([
                            _as_string(docsum.get("title")),
                            _as_string(docsum.get("summary")),
                            _as_string(docsum.get("gdstype")),
                        ]).lower()
                    )
        except Exception as exc:
            gaps.append({
                "source": DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID,
                "lane": "neurobiology",
                "reason": "swd_geo_summary_failed",
                "locator": summary_url,
                "retrieved_at": retrieved,
                "error": str(exc),
            })

    # Honest absence: any expected brain/chemosensory domain not evidenced by a
    # DISTINCTIVE phrase in the raw GEO dataset text becomes a queryable gap.
    # Detection reads the raw GEO corpus (not our record boilerplate), so an
    # antennal transcriptome does not falsely satisfy the antennal-lobe-map domain.
    corpus = " ".join(domain_corpus)
    for key, label, phrases in EXPECTED_DOMAINS:
        if not any(phrase in corpus for phrase in phrases):
            gaps.append({
                "source": DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID,
                "lane": "neurobiology",
                "reason": f"swd_neurobiology_domain_absent:{key}",
                "locator": f"expected_domain={label}",
                "retrieved_at": retrieved,
            })

    return DrosophilaSuzukiiNeurobiologyResult(
        source_id=DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        query=GEO_QUERY,
        reported_total_count=reported_total,
        dataset_count=len(records),
    )
