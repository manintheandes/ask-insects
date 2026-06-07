# Elicit Discovery Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Onboard two source-grade Ask Insects lanes — `drosophila_suzukii_elicit_discovery` and `aedes_aegypti_elicit_discovery` — that use Elicit to discover papers not already in the hosted corpus and store them as candidate-band literature records with provenance and a queryable depth-outcome gap.

**Architecture:** One shared, dependency-injected adapter (`askinsects/sources/elicit_discovery.py`) does the Elicit fetch, dedup against hosted by DOI, and record building. Two thin ingest scripts (one per species) call it and write via `replace_source_records`, updating `source_status.json` / `source_receipt.json` / `gaps.json`. Tests inject `fetch_json` and `existing_doi_lookup` so nothing touches the network or the hosted plane.

**Tech Stack:** Python 3.11+, stdlib `urllib`, project `EvidenceRecord`/`Provenance`/`SourceIndex`, `normalize_doi`. Tests via `uv run --with pytest --group dev python -m pytest`.

---

## File Structure

- Create: `askinsects/sources/elicit_discovery.py` — shared adapter (fetch, dedup, build records). One responsibility: turn Elicit queries into new EvidenceRecords for a species.
- Create: `scripts/ingest_drosophila_suzukii_elicit_discovery.py` — SWD ingest entrypoint.
- Create: `scripts/ingest_aedes_aegypti_elicit_discovery.py` — Aedes ingest entrypoint.
- Create: `tests/test_elicit_discovery_source.py` — adapter unit tests (offline).
- Create: `tests/test_ingest_drosophila_suzukii_elicit_discovery.py` — SWD ingest test (offline).
- Create: `tests/test_ingest_aedes_aegypti_elicit_discovery.py` — Aedes ingest test (offline).
- Modify: `config/source-map.yaml` — add both source entries.
- Modify: `docs/source-lanes.md`, `README.md`, `docs/querying-ask-insects.md` — document the lanes.
- Create: `docs/elicit-discovery-source.md` — per-source receipt doc.

Shared constants (`SPECIES_CONFIG`) live in the adapter; ingest scripts import them. DRY: ingest scripts are near-identical thin wrappers differing only by species key.

---

### Task 1: Adapter — fetch Elicit results and build candidate records

**Files:**
- Create: `askinsects/sources/elicit_discovery.py`
- Test: `tests/test_elicit_discovery_source.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_elicit_discovery_source.py
from pathlib import Path
from askinsects.sources.elicit_discovery import fetch_elicit_discovery_records

def _fake_fetch(papers_by_query):
    def _fetch(query, *, max_results, min_year):
        return {"papers": papers_by_query.get(query, [])}
    return _fetch

def test_builds_candidate_record_with_payload(tmp_path):
    papers = {"q1": [{
        "title": "Repellency of X against Drosophila suzukii",
        "authors": ["A. Author"], "year": 2023, "venue": "Pest Manag Sci",
        "doi": "10.1000/abc", "pmid": "123", "elicitId": "E1",
        "citedByCount": 4, "abstract": "We test repellency."}]}
    result = fetch_elicit_discovery_records(
        species="drosophila_suzukii", queries=["q1"], raw_dir=tmp_path,
        retrieved_at="2026-06-07T00:00:00Z",
        fetch_json=_fake_fetch(papers),
        existing_doi_lookup=lambda dois: set())
    assert result.source_id == "drosophila_suzukii_elicit_discovery"
    assert len(result.records) == 1
    rec = result.records[0]
    assert rec.lane == "literature"
    assert rec.url == "10.1000/abc"
    assert rec.species == "Drosophila suzukii"
    assert rec.payload["confidence_band"] == "elicit_search_candidate"
    assert rec.payload["depth_outcome"] == "supplement_discovery_not_run"
    assert rec.payload["discovery"]["query"] == "q1"
    assert rec.payload["doi"] == "10.1000/abc"
    assert result.returned_count == 1 and result.new_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --group dev python -m pytest tests/test_elicit_discovery_source.py::test_builds_candidate_record_with_payload -v`
Expected: FAIL with `ModuleNotFoundError: askinsects.sources.elicit_discovery`

- [ ] **Step 3: Write minimal implementation**

```python
# askinsects/sources/elicit_discovery.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import re
from pathlib import Path
from typing import Callable

from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.literature import normalize_doi

ELICIT_SEARCH_URL = "https://elicit.com/api/v1/search"

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
                candidates[key].setdefault("discovery_queries", []).append(query)
                continue
            candidates[key] = {
                "title": title, "doi": doi, "elicit_id": elicit_id, "paper": paper,
                "query": query, "raw_locator": f"{raw_path.as_posix()}#papers/{idx}",
                "no_doi": doi is None, "discovery_queries": [query],
            }

    # dedup against hosted by DOI
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
        payload = {
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
        record = EvidenceRecord(
            record_id=f"{source_id}:{rid_base}",
            lane="literature", source=source_id, title=cand["title"],
            text=" ".join(p for p in [cand["title"], abstract] if p),
            species=species_name,
            url=cand["doi"] or (paper.get("urls") or [None])[0],
            media_url=None,
            provenance=Provenance(
                source_id=source_id, locator=cand["raw_locator"], retrieved_at=retrieved,
                license="Elicit API metadata",
                source_url=(f"https://doi.org/{cand['doi']}" if cand["doi"] else None),
            ),
            payload=payload,
        )
        records.append(record)

    return ElicitDiscoveryResult(
        source_id=source_id, records=records, gaps=gaps, raw_artifacts=raw_artifacts,
        requested_queries=query_list, returned_count=returned,
        new_count=len(records), dedup_dropped=dropped,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --group dev python -m pytest tests/test_elicit_discovery_source.py::test_builds_candidate_record_with_payload -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add askinsects/sources/elicit_discovery.py tests/test_elicit_discovery_source.py
git commit -m "feat(elicit): adapter builds candidate literature records from Elicit results"
```

---

### Task 2: Adapter — dedup against hosted + within-harvest

**Files:**
- Modify: `tests/test_elicit_discovery_source.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_drops_dois_already_in_hosted(tmp_path):
    papers = {"q1": [
        {"title": "New paper", "doi": "10.1/new", "elicitId": "E1"},
        {"title": "Old paper", "doi": "10.1/old", "elicitId": "E2"}]}
    result = fetch_elicit_discovery_records(
        species="aedes_aegypti", queries=["q1"], raw_dir=tmp_path,
        retrieved_at="t", fetch_json=_fake_fetch(papers),
        existing_doi_lookup=lambda dois: {"10.1/old"})
    assert result.new_count == 1
    assert result.dedup_dropped == 1
    assert result.records[0].url == "10.1/new"

def test_dedups_same_doi_across_queries(tmp_path):
    paper = {"title": "Dup", "doi": "10.1/dup", "elicitId": "E1"}
    papers = {"q1": [paper], "q2": [paper]}
    result = fetch_elicit_discovery_records(
        species="aedes_aegypti", queries=["q1", "q2"], raw_dir=tmp_path,
        retrieved_at="t", fetch_json=_fake_fetch(papers),
        existing_doi_lookup=lambda dois: set())
    assert result.new_count == 1
    assert result.records[0].payload["discovery"]["all_queries"] == ["q1", "q2"]
```

- [ ] **Step 2: Run tests to verify they fail or pass**

Run: `uv run --with pytest --group dev python -m pytest tests/test_elicit_discovery_source.py -v`
Expected: Both new tests PASS (logic already implemented in Task 1). If either fails, fix the adapter dedup logic before continuing.

- [ ] **Step 3: Commit**

```bash
git add tests/test_elicit_discovery_source.py
git commit -m "test(elicit): cover hosted dedup and cross-query dedup"
```

---

### Task 3: Adapter — failed fetches become gaps, not crashes

**Files:**
- Modify: `tests/test_elicit_discovery_source.py`

- [ ] **Step 1: Write the failing test**

```python
def test_fetch_failure_records_gap(tmp_path):
    def _boom(query, *, max_results, min_year):
        raise RuntimeError("403 plan")
    result = fetch_elicit_discovery_records(
        species="aedes_aegypti", queries=["q1"], raw_dir=tmp_path,
        retrieved_at="t", fetch_json=_boom, existing_doi_lookup=lambda d: set())
    assert result.records == []
    assert result.gaps and result.gaps[0]["reason"].startswith("elicit_fetch_failed:")
```

- [ ] **Step 2: Run test**

Run: `uv run --with pytest --group dev python -m pytest tests/test_elicit_discovery_source.py::test_fetch_failure_records_gap -v`
Expected: PASS (try/except already in Task 1). Fix adapter if not.

- [ ] **Step 3: Commit**

```bash
git add tests/test_elicit_discovery_source.py
git commit -m "test(elicit): fetch failures are queryable gaps"
```

---

### Task 4: Default production fetch + hosted DOI lookup helpers

**Files:**
- Modify: `askinsects/sources/elicit_discovery.py`
- Modify: `tests/test_elicit_discovery_source.py`

- [ ] **Step 1: Write the failing test (URL/headers build, no network)**

```python
def test_default_fetch_builds_request(monkeypatch, tmp_path):
    import askinsects.sources.elicit_discovery as ed
    captured = {}
    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"papers": []}'
    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["auth"] = req.headers.get("Authorization")
        captured["body"] = req.data
        return FakeResp()
    monkeypatch.setattr(ed, "urlopen", fake_urlopen)
    out = ed.default_fetch_json("q", max_results=5, min_year=2020, api_key="elk_live_X")
    assert captured["url"] == ed.ELICIT_SEARCH_URL
    assert captured["auth"] == "Bearer elk_live_X"
    assert b'"q"' in captured["body"]
    assert out == {"papers": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --group dev python -m pytest tests/test_elicit_discovery_source.py::test_default_fetch_builds_request -v`
Expected: FAIL with `AttributeError: ... has no attribute 'default_fetch_json'`

- [ ] **Step 3: Implement default helpers**

```python
# add to askinsects/sources/elicit_discovery.py
import os
import subprocess
from urllib.request import Request, urlopen

DEFAULT_API_KEY_PATH = Path.home() / ".config" / "elicit" / "api_key"


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
    })
    with urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def default_existing_doi_lookup(dois: set[str], *, cli: str = "ask-insects") -> set[str]:
    """Batched exact-match lookup against the hosted plane. Full scans time out; exact IN is indexed."""
    found: set[str] = set()
    doi_list = sorted(dois)
    for start in range(0, len(doi_list), 200):
        chunk = doi_list[start:start + 200]
        in_list = ",".join("'" + d.replace("'", "''") + "'" for d in chunk)
        out = subprocess.run(
            [cli, "sql", f"select url from records where url in ({in_list})", "--limit", "100000"],
            capture_output=True, text=True, timeout=120,
        )
        if out.returncode != 0:
            raise RuntimeError(f"hosted dedup lookup failed: {out.stderr[:200]}")
        data = json.loads(out.stdout)
        for row in data.get("rows", []):
            if row.get("url"):
                found.add(str(row["url"]).lower())
    return found
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --group dev python -m pytest tests/test_elicit_discovery_source.py::test_default_fetch_builds_request -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add askinsects/sources/elicit_discovery.py tests/test_elicit_discovery_source.py
git commit -m "feat(elicit): default Elicit fetch and batched hosted DOI dedup"
```

---

### Task 5: SWD ingest script

**Files:**
- Create: `scripts/ingest_drosophila_suzukii_elicit_discovery.py`
- Test: `tests/test_ingest_drosophila_suzukii_elicit_discovery.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingest_drosophila_suzukii_elicit_discovery.py
import json
from pathlib import Path
import importlib.util

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def test_ingest_writes_records_and_receipt(tmp_path):
    mod = _load("ingest_swd_elicit", Path("scripts/ingest_drosophila_suzukii_elicit_discovery.py"))
    def fake_fetch(query, *, max_results, min_year):
        return {"papers": [{"title": f"P {query}", "doi": f"10.1/{abs(hash(query))%9}", "elicitId": "E"}]}
    result = mod.ingest(
        artifact_dir=tmp_path, fetch_json=fake_fetch,
        existing_doi_lookup=lambda d: set(), retrieved_at="2026-06-07T00:00:00Z")
    assert result["ok"] is True
    assert result["source"] == "drosophila_suzukii_elicit_discovery"
    assert result["new_count"] >= 1
    status = json.loads((tmp_path / "source_status.json").read_text())
    assert "drosophila_suzukii_elicit_discovery" in json.dumps(status)

def test_ingest_all_fail_preserves(tmp_path):
    mod = _load("ingest_swd_elicit2", Path("scripts/ingest_drosophila_suzukii_elicit_discovery.py"))
    def boom(query, *, max_results, min_year): raise RuntimeError("429")
    result = mod.ingest(artifact_dir=tmp_path, fetch_json=boom,
        existing_doi_lookup=lambda d: set(), retrieved_at="t")
    assert result["ok"] is False
    assert result["refresh_failed"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --group dev python -m pytest tests/test_ingest_drosophila_suzukii_elicit_discovery.py -v`
Expected: FAIL (file not found / no `ingest`)

- [ ] **Step 3: Implement the ingest script**

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.index import SourceIndex
from askinsects.sources.elicit_discovery import (
    SPECIES_CONFIG, fetch_elicit_discovery_records, utc_now,
    default_fetch_json, default_existing_doi_lookup,
)

SPECIES = "drosophila_suzukii"
SOURCE_ID = str(SPECIES_CONFIG[SPECIES]["source_id"])
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "mosquito-v1"


def _read_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def ingest(*, artifact_dir: Path = DEFAULT_ARTIFACT_DIR, fetch_json=None,
           existing_doi_lookup=None, retrieved_at: str | None = None,
           max_results: int = 50, min_year: int = 2020) -> dict:
    retrieved = retrieved_at or utc_now()
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    result = fetch_elicit_discovery_records(
        species=SPECIES,
        raw_dir=artifact_dir / "raw" / SOURCE_ID,
        retrieved_at=retrieved,
        max_results=max_results, min_year=min_year,
        fetch_json=fetch_json or default_fetch_json,
        existing_doi_lookup=existing_doi_lookup or default_existing_doi_lookup,
    )
    refresh_failed = (not result.records) and bool(result.gaps)
    if not refresh_failed:
        index.replace_source_records(SOURCE_ID, result.records)
    source_payload = {
        "source": SOURCE_ID,
        "boundary": f"Elicit semantic-search discovery of {SPECIES_CONFIG[SPECIES]['species']} candidate papers not already in the hosted corpus.",
        "requested_queries": result.requested_queries,
        "returned_count": result.returned_count,
        "new_count": result.new_count,
        "dedup_dropped": result.dedup_dropped,
        "gap_reasons": sorted({str(g.get("reason")) for g in result.gaps if g.get("reason")}),
        "gap_count": len(result.gaps),
        "raw_artifacts": result.raw_artifacts,
        "retrieved_at": retrieved,
        "refresh_failed": refresh_failed,
    }
    gaps_path = artifact_dir / "gaps.json"
    existing_gaps = [g for g in _read_json(gaps_path, []) if not (isinstance(g, dict) and g.get("source") == SOURCE_ID)]
    existing_gaps.extend(result.gaps)
    _write_json(gaps_path, existing_gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        payload[SOURCE_ID] = source_payload
        _write_json(path, payload)
    return {"ok": not refresh_failed, "source": SOURCE_ID, "new_count": result.new_count,
            "returned_count": result.returned_count, "dedup_dropped": result.dedup_dropped,
            "gap_count": len(result.gaps), "refresh_failed": refresh_failed,
            "artifact_dir": artifact_dir.as_posix()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=f"Ingest {SOURCE_ID} into Ask Insects.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--max-results", type=int, default=50)
    parser.add_argument("--min-year", type=int, default=2020)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest(artifact_dir=Path(args.artifact_dir), max_results=args.max_results,
                    min_year=args.min_year, retrieved_at=args.retrieved_at)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --group dev python -m pytest tests/test_ingest_drosophila_suzukii_elicit_discovery.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/ingest_drosophila_suzukii_elicit_discovery.py tests/test_ingest_drosophila_suzukii_elicit_discovery.py
git commit -m "feat(elicit): SWD elicit-discovery ingest script with preserve-on-failure"
```

---

### Task 6: Aedes ingest script

**Files:**
- Create: `scripts/ingest_aedes_aegypti_elicit_discovery.py`
- Test: `tests/test_ingest_aedes_aegypti_elicit_discovery.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingest_aedes_aegypti_elicit_discovery.py
import json
from pathlib import Path
import importlib.util

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def test_aedes_ingest_writes_records(tmp_path):
    mod = _load("ingest_aedes_elicit", Path("scripts/ingest_aedes_aegypti_elicit_discovery.py"))
    def fake_fetch(query, *, max_results, min_year):
        return {"papers": [{"title": f"A {query}", "doi": f"10.2/{abs(hash(query))%9}", "elicitId": "E"}]}
    result = mod.ingest(artifact_dir=tmp_path, fetch_json=fake_fetch,
        existing_doi_lookup=lambda d: set(), retrieved_at="2026-06-07T00:00:00Z")
    assert result["ok"] is True
    assert result["source"] == "aedes_aegypti_elicit_discovery"
    assert result["new_count"] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --group dev python -m pytest tests/test_ingest_aedes_aegypti_elicit_discovery.py -v`
Expected: FAIL (file not found)

- [ ] **Step 3: Implement (copy Task 5 script, change only the species constants)**

Create `scripts/ingest_aedes_aegypti_elicit_discovery.py` identical to the SWD script except:

```python
SPECIES = "aedes_aegypti"
SOURCE_ID = str(SPECIES_CONFIG[SPECIES]["source_id"])
```

(All other code identical — same `ingest`/`main`/helpers.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --group dev python -m pytest tests/test_ingest_aedes_aegypti_elicit_discovery.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/ingest_aedes_aegypti_elicit_discovery.py tests/test_ingest_aedes_aegypti_elicit_discovery.py
git commit -m "feat(elicit): Aedes elicit-discovery ingest script"
```

---

### Task 7: Map both sources in source-map.yaml (Gate 1: Mapped)

**Files:**
- Modify: `config/source-map.yaml`

- [ ] **Step 1: Add both entries (append under `sources:`)**

```yaml
  - id: drosophila_suzukii_elicit_discovery
    name: Drosophila suzukii Elicit semantic-search discovery since 2020
    source_type: elicit_api_discovery
    boundary: Bounded Elicit semantic-search discovery of Drosophila suzukii candidate papers (repellency, behavior, olfaction focus, 2020 onward) that are not already in the hosted corpus, stored as elicit_search_candidate literature records with a supplement_discovery_not_run depth-outcome gap.
    query_plane: elicit_search_to_sqlite_candidate_literature_records
    api_base:
      - https://elicit.com/api/v1
    raw_artifact_dir: artifacts/mosquito-v1/raw/drosophila_suzukii_elicit_discovery
    ingest_script: scripts/ingest_drosophila_suzukii_elicit_discovery.py
    lanes:
      - literature
    provenance_required: true
    live_fetch: opt_in_bounded_pro_api_key
  - id: aedes_aegypti_elicit_discovery
    name: Aedes aegypti Elicit semantic-search discovery since 2020
    source_type: elicit_api_discovery
    boundary: Bounded Elicit semantic-search discovery of Aedes aegypti candidate papers (repellency, behavior, olfaction focus, 2020 onward) that are not already in the hosted corpus, stored as elicit_search_candidate literature records with a supplement_discovery_not_run depth-outcome gap.
    query_plane: elicit_search_to_sqlite_candidate_literature_records
    api_base:
      - https://elicit.com/api/v1
    raw_artifact_dir: artifacts/mosquito-v1/raw/aedes_aegypti_elicit_discovery
    ingest_script: scripts/ingest_aedes_aegypti_elicit_discovery.py
    lanes:
      - literature
    provenance_required: true
    live_fetch: opt_in_bounded_pro_api_key
```

- [ ] **Step 2: Run the completion gate**

Run: `python3 scripts/verify_complete.py`
Expected: PASS (if it parses source-map and checks referenced ingest scripts exist, both scripts are present). If it fails, read the error and fix the YAML/script reference.

- [ ] **Step 3: Commit**

```bash
git add config/source-map.yaml
git commit -m "feat(elicit): map SWD and Aedes elicit-discovery sources"
```

---

### Task 8: Docs + receipt (Gate 4 prep) and full test run

**Files:**
- Modify: `docs/source-lanes.md`, `README.md`, `docs/querying-ask-insects.md`
- Create: `docs/elicit-discovery-source.md`

- [ ] **Step 1: Add lane descriptions**

In `docs/source-lanes.md`, add a paragraph for each source describing boundary (Elicit candidate discovery, 2020+, repellency/behavior/olfaction), confidence band (`elicit_search_candidate`), the `supplement_discovery_not_run` depth gap, and that dedup is against the hosted corpus by DOI. In `README.md`, add both ids to the lane inventory. In `docs/querying-ask-insects.md`, add an example: `ask-insects sql "select source, count(*) n from records where source like '%elicit_discovery' group by source"`.

- [ ] **Step 2: Write the receipt doc**

Create `docs/elicit-discovery-source.md` documenting: source ids, boundary, Elicit endpoint + Pro key location (`~/.config/elicit/api_key`, never committed), queries, dedup method (batched exact hosted lookup; full scans time out), safety contract (preserve-on-failure), depth-outcome gap, and that hosted promotion is gated on Josh's approval.

- [ ] **Step 3: Run the full relevant test suite + gate**

Run:
```bash
uv run --with pytest --group dev python -m pytest tests/test_elicit_discovery_source.py tests/test_ingest_drosophila_suzukii_elicit_discovery.py tests/test_ingest_aedes_aegypti_elicit_discovery.py -q
python3 scripts/verify_complete.py
```
Expected: all tests PASS, gate PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/source-lanes.md README.md docs/querying-ask-insects.md docs/elicit-discovery-source.md
git commit -m "docs(elicit): document SWD and Aedes elicit-discovery lanes + receipt"
```

---

## Post-implementation (NOT part of the code tasks — gated)

1. **Local live build** (real Elicit key, real hosted dedup):
   `python3 scripts/ingest_drosophila_suzukii_elicit_discovery.py` and the Aedes script.
2. **Show Josh** the new-paper list + counts (returned / new / dedup-dropped / gaps).
3. **Gate:** only after Josh approves, promote the new records to the hosted plane via the repo's hosted deploy path, then verify from outside:
   `ask-insects ask --hosted "What new Drosophila suzukii repellency papers did Elicit add?"`
4. Run `/verify` to capture the Evaluation Pack and close out.

## Self-Review

- **Spec coverage:** two species sources (Tasks 1,5,6,7) ✓; candidate band + depth gap (Task 1 payload) ✓; dedup vs hosted (Tasks 2,4) ✓; safety/preserve-on-failure (Task 5) ✓; receipts/status/gaps (Task 5) ✓; Four Gates: Mapped (Task 7), Accessible (Task 4 default fetch + post-impl live build), Atomically queryable (Task 1), Ask-surface wired (Task 8 + post-impl) ✓; verify_complete gate (Tasks 7,8) ✓; docs (Task 8) ✓; production gate (post-impl) ✓.
- **Placeholder scan:** Task 6 references Task 5 code by design (single-line species delta) — acceptable and explicit, not a hidden placeholder. No TBDs.
- **Type consistency:** `fetch_elicit_discovery_records` / `ElicitDiscoveryResult` fields (`records`, `gaps`, `requested_queries`, `returned_count`, `new_count`, `dedup_dropped`) used consistently across adapter and ingest. `ingest(...)` signature identical in both scripts.
