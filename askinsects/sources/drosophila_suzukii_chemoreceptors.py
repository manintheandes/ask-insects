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

DROSOPHILA_SUZUKII_CHEMORECEPTORS_SOURCE_ID = "drosophila_suzukii_chemoreceptors"
SPECIES = "Drosophila suzukii"
COMMON_NAME = "spotted wing drosophila"
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# NCBI Gene query for the SWD chemosensory receptor repertoire. This is the sensory
# layer that joins to repellency hits (which receptors a repellent compound acts on).
GENE_QUERY = (
    '("Drosophila suzukii"[Organism]) AND '
    '("odorant receptor"[All Fields] OR "olfactory receptor"[All Fields] '
    'OR "ionotropic receptor"[All Fields] OR "gustatory receptor"[All Fields] '
    'OR "odorant binding"[All Fields] OR chemosensory[All Fields])'
)
GENE_LICENSE = "NCBI Gene public metadata; NCBI terms apply"
USER_AGENT = "ask-insects/0.1 (+https://openinsects.org)"

# Receptor families expected in a chemosensory repertoire; absence is a queryable gap.
EXPECTED_RECEPTOR_CLASSES = (
    ("odorant_receptor", "odorant receptor (Or)"),
    ("ionotropic_receptor", "ionotropic receptor (Ir)"),
    ("gustatory_receptor", "gustatory receptor (Gr)"),
)


@dataclass(frozen=True)
class DrosophilaSuzukiiChemoreceptorsResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    query: str
    reported_total_count: int
    receptor_count: int


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


def _classify(name: str, description: str) -> str:
    blob = f"{name} {description}".lower()
    if "gustatory" in blob or re.search(r"\bgr\d", blob):
        return "gustatory_receptor"
    if "ionotropic" in blob or re.search(r"\bir\d", blob):
        return "ionotropic_receptor"
    if "odorant binding" in blob or re.search(r"\bobp", blob):
        return "odorant_binding_protein"
    if "odorant" in blob or "olfactory" in blob or re.search(r"\bor\d", blob):
        return "odorant_receptor"
    return "chemosensory_other"


def _record_for_gene(uid: str, gene: dict[str, object], *, raw_path: Path, retrieved_at: str) -> EvidenceRecord:
    symbol = _as_string(gene.get("name")) or f"gene {uid}"
    description = _as_string(gene.get("description"))
    receptor_class = _classify(symbol, description)
    chromosome = _as_string(gene.get("chromosome"))
    url = f"https://www.ncbi.nlm.nih.gov/gene/{uid}"
    payload = {
        "atom_type": "chemoreceptor_gene",
        "gene_id": uid,
        "symbol": symbol,
        "description": description,
        "receptor_class": receptor_class,
        "chromosome": chromosome,
        "aliases": _as_string(gene.get("otheraliases")),
        "primary_taxon": SPECIES,
        "common_name": COMMON_NAME,
        "query": GENE_QUERY,
    }
    text = " ".join(part for part in [
        f"{symbol}: {description}" if description else symbol,
        f"{SPECIES} ({COMMON_NAME}) chemosensory receptor gene.",
        f"receptor_class={receptor_class}",
        f"gene_id={uid}",
        f"chromosome={chromosome}" if chromosome else "",
    ] if part)
    return EvidenceRecord(
        record_id=f"swd_chemoreceptor:gene:{_safe_id(uid)}",
        lane="neurobiology",
        source=DROSOPHILA_SUZUKII_CHEMORECEPTORS_SOURCE_ID,
        title=f"{symbol} ({receptor_class}) — {SPECIES}",
        text=text,
        species=SPECIES,
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_CHEMORECEPTORS_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#gene/{uid}",
            retrieved_at=retrieved_at,
            license=GENE_LICENSE,
            source_url=url,
        ),
        payload=payload,
    )


def fetch_drosophila_suzukii_chemoreceptor_records(
    *,
    raw_dir: Path,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    retrieved_at: str | None = None,
    max_results: int = 600,
    page_size: int = 200,
    delay_seconds: float = 0.34,
) -> DrosophilaSuzukiiChemoreceptorsResult:
    retrieved = retrieved_at or utc_now()
    fetch = fetch_json or fetch_json_url
    requested_urls: list[str] = []
    raw_artifacts: list[str] = []
    gaps: list[dict[str, object]] = []
    records: list[EvidenceRecord] = []
    class_corpus: list[str] = []
    candidate_ids: list[str] = []
    reported_total = 0
    bounded_page = max(1, min(page_size, 200))
    limit = max(1, max_results)

    for page_index, retstart in enumerate(range(0, limit, bounded_page), start=1):
        url = _eutils_url("esearch", db="gene", term=GENE_QUERY, retstart=retstart, retmax=bounded_page, sort="relevance")
        requested_urls.append(url)
        try:
            payload = fetch(url)
        except Exception as exc:
            gaps.append({
                "source": DROSOPHILA_SUZUKII_CHEMORECEPTORS_SOURCE_ID, "lane": "neurobiology",
                "reason": "swd_chemoreceptor_search_failed", "locator": url,
                "retrieved_at": retrieved, "error": str(exc),
            })
            break
        raw_artifacts.append(write_raw_json(raw_dir, f"gene_esearch_{page_index:04d}.json", payload).as_posix())
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
    summary_batch = 150
    for batch_index, start in enumerate(range(0, len(candidate_ids), summary_batch), start=1):
        batch = candidate_ids[start:start + summary_batch]
        summary_url = _eutils_url("esummary", db="gene", id=",".join(batch))
        requested_urls.append(summary_url)
        if delay_seconds:
            time.sleep(delay_seconds)
        try:
            summary_payload = fetch(summary_url)
            raw_path = write_raw_json(raw_dir, f"gene_esummary_{batch_index:04d}.json", summary_payload)
            raw_artifacts.append(raw_path.as_posix())
            block = summary_payload.get("result", {}) if isinstance(summary_payload, dict) else {}
            uids = block.get("uids", []) if isinstance(block, dict) else []
            for uid in uids:
                gene = block.get(str(uid))
                if isinstance(gene, dict):
                    rec = _record_for_gene(str(uid), gene, raw_path=raw_path, retrieved_at=retrieved)
                    records.append(rec)
                    class_corpus.append(str(rec.payload.get("receptor_class", "")))
        except Exception as exc:
            gaps.append({
                "source": DROSOPHILA_SUZUKII_CHEMORECEPTORS_SOURCE_ID, "lane": "neurobiology",
                "reason": "swd_chemoreceptor_summary_failed", "locator": summary_url,
                "retrieved_at": retrieved, "error": str(exc),
            })

    found_classes = set(class_corpus)
    for key, label in EXPECTED_RECEPTOR_CLASSES:
        if key not in found_classes:
            gaps.append({
                "source": DROSOPHILA_SUZUKII_CHEMORECEPTORS_SOURCE_ID, "lane": "neurobiology",
                "reason": f"swd_receptor_class_absent:{key}",
                "locator": f"expected_receptor_class={label}",
                "retrieved_at": retrieved,
            })

    return DrosophilaSuzukiiChemoreceptorsResult(
        source_id=DROSOPHILA_SUZUKII_CHEMORECEPTORS_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        query=GENE_QUERY,
        reported_total_count=reported_total,
        receptor_count=len(records),
    )
