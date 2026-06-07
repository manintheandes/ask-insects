from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.literature import normalize_doi

ELICIT_SEARCH_URL = "https://elicit.com/api/v1/search"
DEFAULT_API_KEY_PATH = Path.home() / ".config" / "elicit" / "api_key"

SPECIES_CONFIG: dict[str, dict[str, object]] = {
    "drosophila_suzukii": {
        "source_id": "drosophila_suzukii_elicit_discovery",
        "species": "Drosophila suzukii",
        "queries": [
            "Drosophila suzukii repellent and oviposition deterrent behavior",
            "spotted-wing drosophila olfactory receptor response to volatiles",
            "Drosophila suzukii antennal electrophysiology semiochemical",
        ],
    },
    "aedes_aegypti": {
        "source_id": "aedes_aegypti_elicit_discovery",
        "species": "Aedes aegypti",
        "queries": [
            "Aedes aegypti spatial repellent behavioral response",
            "Aedes aegypti odorant receptor host-seeking olfaction",
            "Aedes aegypti repellent DEET alternative efficacy assay",
        ],
    },
}


@dataclass(frozen=True)
class ElicitDiscoveryResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_queries: list[str]
    returned_count: int
    new_count: int
    dedup_dropped: int


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "query"


def _title_key(title: str | None) -> str | None:
    if not title:
        return None
    key = re.sub(r"[^a-z0-9]+", " ", title.lower())
    key = re.sub(r"\s+", " ", key).strip()
    return key or None


def _write_raw(raw_dir: Path, name: str, payload: object) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _candidate_key(doi: str | None, elicit_id: str, title: str) -> str:
    if doi:
        return f"doi:{doi}"
    if elicit_id:
        return f"elicit:{elicit_id}"
    tk = _title_key(title)
    return f"title:{tk}" if tk else f"title:{abs(hash(title))}"


def _load_api_key(api_key: str | None = None) -> str:
    if api_key:
        return api_key
    env = os.environ.get("ELICIT_API_KEY")
    if env:
        return env
    if DEFAULT_API_KEY_PATH.exists():
        return DEFAULT_API_KEY_PATH.read_text(encoding="utf-8").strip()
    raise RuntimeError("No Elicit API key (set ELICIT_API_KEY or ~/.config/elicit/api_key)")


def default_fetch_json(query: str, *, max_results: int, min_year: int, api_key: str | None = None) -> dict:
    key = _load_api_key(api_key)
    body = json.dumps({
        "query": query, "maxResults": max_results,
        "corpus": "elicit", "searchMode": "semantic",
        "filters": {"minYear": min_year},
    }).encode("utf-8")
    req = Request(ELICIT_SEARCH_URL, data=body, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "Accept": "application/json",
        # Elicit's edge (Cloudflare) returns 403 to urllib's default Python-urllib UA.
        "User-Agent": "ask-insects/0.1 (+https://openinsects.org)",
    })
    with urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def default_existing_doi_lookup(dois: set[str], *, cli: str = "ask-insects", batch_size: int = 25) -> set[str]:
    """Batched exact-match lookup against the hosted plane.

    Uses OR-of-equalities, NOT ``IN`` and NOT a ``LIKE`` scan: on the hosted SQL
    endpoint ``url IN (...)`` and full scans time out, while ``url='a' OR url='b'``
    unions index probes and stays fast. Batches keep each query small.
    """
    found: set[str] = set()
    doi_list = sorted(dois)
    for start in range(0, len(doi_list), batch_size):
        chunk = doi_list[start:start + batch_size]
        clause = " or ".join("url='" + d.replace("'", "''") + "'" for d in chunk)
        out = subprocess.run(
            [cli, "sql", f"select url from records where {clause}", "--limit", "100000"],
            capture_output=True, text=True, timeout=120,
        )
        if out.returncode != 0:
            raise RuntimeError(f"hosted dedup lookup failed: {out.stderr[:200]}")
        data = json.loads(out.stdout)
        for row in data.get("rows", []):
            if row.get("url"):
                found.add(str(row["url"]).lower())
    return found


def fetch_elicit_discovery_records(
    *,
    species: str,
    queries: list[str] | None = None,
    raw_dir: Path,
    retrieved_at: str | None = None,
    max_results: int = 50,
    min_year: int = 2020,
    fetch_json: Callable[..., dict] | None = None,
    existing_doi_lookup: Callable[[set[str]], set[str]] | None = None,
) -> ElicitDiscoveryResult:
    config = SPECIES_CONFIG[species]
    source_id = str(config["source_id"])
    species_name = str(config["species"])
    query_list = queries if queries is not None else list(config["queries"])  # type: ignore[arg-type]
    retrieved = retrieved_at or utc_now()
    if fetch_json is None:
        raise ValueError("fetch_json is required (inject default_fetch_json in production)")

    candidates: dict[str, dict] = {}
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    returned = 0

    for query in query_list:
        try:
            payload = fetch_json(query, max_results=max_results, min_year=min_year)
        except Exception as exc:  # noqa: BLE001 - failures are gaps, not crashes
            gaps.append({"source": source_id, "query": query, "reason": f"elicit_fetch_failed:{exc}"})
            continue
        raw_path = _write_raw(raw_dir, f"{_slug(query)}.json", payload)
        raw_artifacts.append(raw_path.as_posix())
        papers = payload.get("papers") if isinstance(payload, dict) else None
        if not isinstance(papers, list):
            gaps.append({"source": source_id, "query": query, "reason": "elicit_no_papers_field"})
            continue
        for idx, paper in enumerate(papers):
            if not isinstance(paper, dict):
                continue
            returned += 1
            title = (paper.get("title") or "").strip()
            if not title:
                continue
            doi = normalize_doi(paper.get("doi"))
            elicit_id = (paper.get("elicitId") or "").strip()
            key = _candidate_key(doi, elicit_id, title)
            if key in candidates:
                candidates[key]["discovery_queries"].append(query)
                continue
            candidates[key] = {
                "title": title, "doi": doi, "elicit_id": elicit_id, "paper": paper,
                "query": query, "raw_locator": f"{raw_path.as_posix()}#papers/{idx}",
                "no_doi": doi is None, "discovery_queries": [query],
            }

    dois = {c["doi"] for c in candidates.values() if c["doi"]}
    existing = existing_doi_lookup(dois) if (existing_doi_lookup and dois) else set()
    records: list[EvidenceRecord] = []
    dropped = 0
    for cand in candidates.values():
        if cand["doi"] and cand["doi"] in existing:
            dropped += 1
            continue
        paper = cand["paper"]
        abstract = (paper.get("abstract") or "").strip()
        record_payload = {
            "doi": cand["doi"], "pmid": (paper.get("pmid") or None),
            "elicit_id": cand["elicit_id"] or None, "year": paper.get("year"),
            "venue": paper.get("venue"), "authors": paper.get("authors") or [],
            "cited_by_count": paper.get("citedByCount"), "abstract": abstract or None,
            "confidence_band": "elicit_search_candidate",
            "depth_outcome": "supplement_discovery_not_run",
            "no_doi": cand["no_doi"],
            "discovery": {
                "query": cand["query"], "all_queries": sorted(set(cand["discovery_queries"])),
                "search_mode": "semantic", "corpus": "elicit", "min_year": min_year,
                "species": species_name,
            },
        }
        rid_base = cand["doi"] or cand["elicit_id"] or _title_key(cand["title"]) or cand["title"]
        urls = paper.get("urls") if isinstance(paper.get("urls"), list) else []
        record = EvidenceRecord(
            record_id=f"{source_id}:{rid_base}",
            lane="literature", source=source_id, title=cand["title"],
            text=" ".join(p for p in [cand["title"], abstract] if p),
            species=species_name,
            url=cand["doi"] or (urls[0] if urls else None),
            media_url=None,
            provenance=Provenance(
                source_id=source_id, locator=cand["raw_locator"], retrieved_at=retrieved,
                license="Elicit API metadata",
                source_url=(f"https://doi.org/{cand['doi']}" if cand["doi"] else None),
            ),
            payload=record_payload,
        )
        records.append(record)

    return ElicitDiscoveryResult(
        source_id=source_id, records=records, gaps=gaps, raw_artifacts=raw_artifacts,
        requested_queries=query_list, returned_count=returned,
        new_count=len(records), dedup_dropped=dropped,
    )
