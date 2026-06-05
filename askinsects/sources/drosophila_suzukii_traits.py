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

DROSOPHILA_SUZUKII_TRAITS_SOURCE_ID = "drosophila_suzukii_traits"
SPECIES = "Drosophila suzukii"
COMMON_NAME = "spotted wing drosophila"
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# PubMed query for SWD life-history / physiological trait literature.
PUBMED_QUERY = (
    '(("Drosophila suzukii"[Title/Abstract] OR "spotted wing drosophila"[Title/Abstract] '
    'OR "spotted-wing drosophila"[Title/Abstract]) AND '
    '("life history"[Title/Abstract] OR development*[Title/Abstract] OR fecundity[Title/Abstract] '
    'OR longevity[Title/Abstract] OR fertility[Title/Abstract] OR thermal[Title/Abstract] '
    'OR temperature[Title/Abstract] OR diapause[Title/Abstract] OR overwinter*[Title/Abstract] '
    'OR "cold tolerance"[Title/Abstract] OR "cold hardiness"[Title/Abstract] OR fitness[Title/Abstract] '
    'OR survival[Title/Abstract]))'
)
TRAITS_LICENSE = "NCBI PubMed metadata; source terms apply"
USER_AGENT = "ask-insects/0.1 (+https://openinsects.org)"

# Canonical life-history trait classes. A class counts as present only when one of its
# DISTINCTIVE phrases appears in the raw PubMed title/abstract corpus; otherwise a
# queryable source_gap records the honest absence.
EXPECTED_TRAIT_CLASSES = (
    ("development_time", "development time", ("development", "developmental", "larval period", "pupal")),
    ("fecundity", "fecundity / fertility", ("fecundity", "fertility", "egg load", "oviposition rate")),
    ("longevity", "adult longevity", ("longevity", "lifespan", "life span", "adult survival")),
    ("thermal_tolerance", "thermal tolerance", ("thermal", "temperature", "ctmax", "ctmin", "heat tolerance")),
    ("diapause_overwintering", "diapause / overwintering", ("diapause", "overwinter", "winter morph", "reproductive dormancy")),
    ("cold_hardiness", "cold hardiness", ("cold tolerance", "cold hardiness", "supercooling", "chill")),
)


@dataclass(frozen=True)
class DrosophilaSuzukiiTraitsResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    query: str
    reported_total_count: int
    trait_record_count: int


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


def _record_for_article(pmid: str, article: dict[str, object], *, raw_path: Path, retrieved_at: str) -> EvidenceRecord:
    title = _as_string(article.get("title")) or f"PubMed PMID {pmid}"
    journal = _as_string(article.get("fulljournalname")) or _as_string(article.get("source")) or None
    pubdate = _as_string(article.get("pubdate")) or _as_string(article.get("epubdate"))
    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    payload = {
        "atom_type": "swd_trait_literature",
        "pmid": pmid,
        "title": title,
        "journal": journal,
        "publication_date": pubdate or None,
        "primary_taxon": SPECIES,
        "common_name": COMMON_NAME,
        "query": PUBMED_QUERY,
    }
    text = " ".join(part for part in [
        title,
        f"{SPECIES} ({COMMON_NAME}) life-history / physiological trait literature candidate.",
        f"pmid={pmid}",
        f"journal={journal}" if journal else "",
        f"publication_date={pubdate}" if pubdate else "",
    ] if part)
    return EvidenceRecord(
        record_id=f"swd_traits:pubmed:{_safe_id(pmid)}",
        lane="traits",
        source=DROSOPHILA_SUZUKII_TRAITS_SOURCE_ID,
        title=title,
        text=text,
        species=SPECIES,
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_TRAITS_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#result/{pmid}",
            retrieved_at=retrieved_at,
            license=TRAITS_LICENSE,
            source_url=url,
        ),
        payload=payload,
    )


def fetch_drosophila_suzukii_traits_records(
    *,
    raw_dir: Path,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
    max_results: int = 1000,
    page_size: int = 100,
    delay_seconds: float = 0.34,
) -> DrosophilaSuzukiiTraitsResult:
    retrieved = retrieved_at or utc_now()
    fetch = fetch_json or fetch_json_url
    requested_urls: list[str] = []
    raw_artifacts: list[str] = []
    gaps: list[dict[str, object]] = []
    records: list[EvidenceRecord] = []
    trait_corpus: list[str] = []
    candidate_ids: list[str] = []
    reported_total = 0
    bounded_page = max(1, min(page_size, 100))
    limit = max(1, max_results)

    for page_index, retstart in enumerate(range(0, limit, bounded_page), start=1):
        url = _eutils_url("esearch", db="pubmed", term=PUBMED_QUERY, retstart=retstart, retmax=bounded_page, sort="pub+date")
        requested_urls.append(url)
        try:
            payload = fetch(url)
        except Exception as exc:
            gaps.append({
                "source": DROSOPHILA_SUZUKII_TRAITS_SOURCE_ID, "lane": "traits",
                "reason": "swd_traits_search_failed", "locator": url,
                "retrieved_at": retrieved, "error": str(exc),
            })
            break
        raw_artifacts.append(write_raw_json(raw_dir, f"pubmed_esearch_{page_index:04d}.json", payload).as_posix())
        result = payload.get("esearchresult", {}) if isinstance(payload, dict) else {}
        raw_ids = result.get("idlist") if isinstance(result, dict) else []
        ids = [str(v) for v in raw_ids if v] if isinstance(raw_ids, list) else []
        reported_total = max(reported_total, _int_value(result.get("count")) if isinstance(result, dict) else 0)
        candidate_ids.extend(uid for uid in ids if uid not in candidate_ids)
        if len(candidate_ids) >= min(reported_total, limit) or not ids:
            break
        if delay_seconds:
            time.sleep(delay_seconds)

    candidate_ids = candidate_ids[:limit]
    # Batch esummary: a single GET with hundreds of ids exceeds the URI length limit (HTTP 414).
    summary_batch_size = 150
    for batch_index, start in enumerate(range(0, len(candidate_ids), summary_batch_size), start=1):
        batch = candidate_ids[start:start + summary_batch_size]
        summary_url = _eutils_url("esummary", db="pubmed", id=",".join(batch))
        requested_urls.append(summary_url)
        if delay_seconds:
            time.sleep(delay_seconds)
        try:
            summary_payload = fetch(summary_url)
            raw_path = write_raw_json(raw_dir, f"pubmed_esummary_{batch_index:04d}.json", summary_payload)
            raw_artifacts.append(raw_path.as_posix())
            block = summary_payload.get("result", {}) if isinstance(summary_payload, dict) else {}
            uids = block.get("uids", []) if isinstance(block, dict) else []
            for uid in uids:
                article = block.get(str(uid))
                if isinstance(article, dict):
                    records.append(_record_for_article(str(uid), article, raw_path=raw_path, retrieved_at=retrieved))
                    trait_corpus.append(" ".join([
                        _as_string(article.get("title")),
                        _as_string(article.get("source")),
                        _as_string(article.get("fulljournalname")),
                    ]).lower())
        except Exception as exc:
            gaps.append({
                "source": DROSOPHILA_SUZUKII_TRAITS_SOURCE_ID, "lane": "traits",
                "reason": "swd_traits_summary_failed", "locator": summary_url,
                "retrieved_at": retrieved, "error": str(exc),
            })

    # Honest absence: a trait class with no distinctive phrase in the corpus is gapped.
    corpus = " ".join(trait_corpus)
    for key, label, phrases in EXPECTED_TRAIT_CLASSES:
        if not any(phrase in corpus for phrase in phrases):
            gaps.append({
                "source": DROSOPHILA_SUZUKII_TRAITS_SOURCE_ID, "lane": "traits",
                "reason": f"swd_traits_class_absent:{key}",
                "locator": f"expected_trait_class={label}",
                "retrieved_at": retrieved,
            })

    return DrosophilaSuzukiiTraitsResult(
        source_id=DROSOPHILA_SUZUKII_TRAITS_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        query=PUBMED_QUERY,
        reported_total_count=reported_total,
        trait_record_count=len(records),
    )
