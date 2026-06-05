# SWD Neurobiology + Olfaction Lane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a source-grade `Drosophila suzukii` brain/chemosensory (`neurobiology`) lane and a SWD olfaction-literature lane to Ask Insects, live on the hosted plane, honest about gaps.

**Architecture:** Two new source modules following the repo's established adapter pattern (see `askinsects/sources/drosophila_suzukii_pubmed_literature.py` as the canonical template). The neurobiology source is GEO-query-driven via NCBI E-utilities `db=gds` (deterministic against injected fixtures in tests, bounded live query in production) and emits queryable `source_gap` records for brain/chemosensory domains that do not exist for SWD. The olfaction-literature source is a focused clone of the PubMed-literature source with a chemosensation query. Both persist via `run_source_ingest` so gap-only runs preserve existing rows.

**Tech Stack:** Python 3, stdlib `urllib`, NCBI E-utilities, SQLite (`askinsects.index.SourceIndex`), `unittest`.

---

## File Structure

- Create: `askinsects/sources/drosophila_suzukii_neurobiology.py` — GEO-driven SWD brain/chemosensory source (records + gaps).
- Create: `scripts/ingest_drosophila_suzukii_neurobiology.py` — persistence wrapper (mirrors `scripts/ingest_drosophila_suzukii_pubmed_literature.py`).
- Create: `tests/test_drosophila_suzukii_neurobiology_source.py` — source-level tests + GEO fixtures (`ESEARCH_GDS`, `ESUMMARY_GDS`).
- Create: `tests/test_ingest_drosophila_suzukii_neurobiology.py` — ingest/persistence tests.
- Create: `askinsects/sources/drosophila_suzukii_olfaction_literature.py` — chemosensation-scoped clone of the PubMed source.
- Create: `scripts/ingest_drosophila_suzukii_olfaction_literature.py` — persistence wrapper clone.
- Create: `tests/test_ingest_drosophila_suzukii_olfaction_literature.py` — ingest test.
- Modify: `askinsects/cli.py` — register two subparsers + two dispatch blocks.
- Modify: `askinsects/server.py` — two hosted handlers + two routes.
- Modify: `config/source-map.yaml` — two source entries.
- Modify: `scripts/verify_complete.py` — add the two spec files to `REQUIRED_FILES`.
- Create: `config/swd-source-plane-benchmark.json` — parity benchmark seed (neurobiology + olfaction categories).

Conventions every new module follows (verified against the template):
- Module constants: `*_SOURCE_ID`, `SPECIES = "Drosophila suzukii"`, `COMMON_NAME = "spotted wing drosophila"`, API base, query, license, `USER_AGENT = "ask-insects/0.1 (+https://openinsects.org)"`.
- `utc_now()`, `write_raw_json(raw_dir, filename, payload)`, `fetch_json_url(url)` with 3-try backoff, `_eutils_url(endpoint, **params)`.
- A frozen `*Result` dataclass with `records`, `gaps`, `raw_artifacts`, `requested_urls`, and count fields.
- A `fetch_*_records(*, raw_dir, fetch_json=None, retrieved_at=None, max_results, page_size, delay_seconds)` entrypoint returning the Result.
- The script's `ingest_*()` calls `fetch_*_records(...)` then `run_source_ingest(...)` then `_update_metadata(...)`.
- `EvidenceRecord(record_id, lane, source, title, text, species, url, media_url, provenance, payload)`; `Provenance(source_id, locator, retrieved_at, license=None, source_url=None)`.

Run tests from repo root with: `python3 -m pytest <path> -v` (repo uses `.venv`; `python3` resolves correctly there).

---

## Task 1: Neurobiology GEO fixtures + species/lane record shape

**Files:**
- Create: `tests/test_drosophila_suzukii_neurobiology_source.py`
- Create: `askinsects/sources/drosophila_suzukii_neurobiology.py`

- [ ] **Step 1: Write the failing test** (`tests/test_drosophila_suzukii_neurobiology_source.py`)

```python
import unittest
from pathlib import Path
import tempfile

from askinsects.sources.drosophila_suzukii_neurobiology import (
    DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID,
    fetch_drosophila_suzukii_neurobiology_records,
)

# Minimal NCBI E-utilities db=gds shaped fixtures.
ESEARCH_GDS = {"esearchresult": {"count": "1", "idlist": ["200012345"]}}
ESUMMARY_GDS = {
    "result": {
        "uids": ["200012345"],
        "200012345": {
            "uid": "200012345",
            "accession": "GSE12345",
            "title": "Antennal transcriptome of Drosophila suzukii",
            "summary": "RNA-seq of Drosophila suzukii antennae profiling odorant receptor expression.",
            "taxon": "Drosophila suzukii",
            "gdstype": "Expression profiling by high throughput sequencing",
            "gpl": "GPL00000",
            "n_samples": "6",
        },
    }
}


def _fake_fetch(url):
    if "esearch.fcgi" in url:
        return ESEARCH_GDS
    if "esummary.fcgi" in url:
        return ESUMMARY_GDS
    raise AssertionError(url)


class NeurobiologySourceTests(unittest.TestCase):
    def test_geo_dataset_becomes_neurobiology_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = fetch_drosophila_suzukii_neurobiology_records(
                raw_dir=Path(tmp) / "raw",
                fetch_json=_fake_fetch,
                retrieved_at="2026-06-05T00:00:00Z",
                max_results=10,
                page_size=10,
                delay_seconds=0,
            )
        datasets = [r for r in result.records if ":gap:" not in r.record_id]
        self.assertEqual(len(datasets), 1)
        rec = datasets[0]
        self.assertEqual(rec.lane, "neurobiology")
        self.assertEqual(rec.source, DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID)
        self.assertEqual(rec.species, "Drosophila suzukii")
        self.assertIn("GSE12345", rec.payload["accession"])
        self.assertIn("antenna", rec.text.lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_drosophila_suzukii_neurobiology_source.py -v`
Expected: FAIL — `ModuleNotFoundError: askinsects.sources.drosophila_suzukii_neurobiology`.

- [ ] **Step 3: Write minimal implementation** (`askinsects/sources/drosophila_suzukii_neurobiology.py`)

```python
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
EXPECTED_DOMAINS = (
    ("whole_brain_atlas", "whole-brain atlas"),
    ("connectome", "brain connectome"),
    ("single_nucleus_brain_rnaseq", "single-nucleus brain RNA-seq"),
    ("antennal_lobe_map", "antennal lobe map"),
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
            f"{SPECIES} ({COMMON_NAME}) brain/chemosensory GEO dataset.",
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
        except Exception as exc:
            gaps.append({
                "source": DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID,
                "lane": "neurobiology",
                "reason": "swd_geo_summary_failed",
                "locator": summary_url,
                "retrieved_at": retrieved,
                "error": str(exc),
            })

    # Honest absence: any expected brain/chemosensory domain with no dataset becomes a queryable gap.
    have_text = " ".join(r.text.lower() for r in records)
    for key, label in EXPECTED_DOMAINS:
        token = label.split()[0].lower()
        if token not in have_text:
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
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python3 -m pytest tests/test_drosophila_suzukii_neurobiology_source.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add askinsects/sources/drosophila_suzukii_neurobiology.py tests/test_drosophila_suzukii_neurobiology_source.py
git commit -m "feat: SWD neurobiology GEO source module"
```

---

## Task 2: Honest-gap behavior when SWD GEO returns nothing

**Files:**
- Test: `tests/test_drosophila_suzukii_neurobiology_source.py` (add a test)

- [ ] **Step 1: Write the failing test** (append to the test class)

```python
    def test_empty_geo_emits_domain_gap_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = fetch_drosophila_suzukii_neurobiology_records(
                raw_dir=Path(tmp) / "raw",
                fetch_json=lambda url: {"esearchresult": {"count": "0", "idlist": []}},
                retrieved_at="2026-06-05T00:00:00Z",
                max_results=10,
                page_size=10,
                delay_seconds=0,
            )
        datasets = [r for r in result.records if ":gap:" not in r.record_id]
        self.assertEqual(datasets, [])
        reasons = {g["reason"] for g in result.gaps}
        self.assertIn("swd_neurobiology_domain_absent:connectome", reasons)
        self.assertIn("swd_neurobiology_domain_absent:whole_brain_atlas", reasons)
```

- [ ] **Step 2: Run it to verify it passes** (the Task-1 implementation already covers this)

Run: `python3 -m pytest tests/test_drosophila_suzukii_neurobiology_source.py -v`
Expected: PASS for both tests. If `test_empty_geo_emits_domain_gap_records` fails, the `EXPECTED_DOMAINS` gap loop in `fetch_drosophila_suzukii_neurobiology_records` is wrong — fix it there.

- [ ] **Step 3: Commit**

```bash
git add tests/test_drosophila_suzukii_neurobiology_source.py
git commit -m "test: SWD neurobiology emits honest domain-absence gaps"
```

---

## Task 3: Neurobiology ingest script (persistence via run_source_ingest)

**Files:**
- Create: `scripts/ingest_drosophila_suzukii_neurobiology.py`
- Test: `tests/test_ingest_drosophila_suzukii_neurobiology.py`

- [ ] **Step 1: Write the failing test** (`tests/test_ingest_drosophila_suzukii_neurobiology.py`)

```python
import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from scripts.ingest_drosophila_suzukii_neurobiology import ingest_drosophila_suzukii_neurobiology
from tests.test_drosophila_suzukii_neurobiology_source import ESEARCH_GDS, ESUMMARY_GDS


def _fake_fetch(url):
    if "esearch.fcgi" in url:
        return ESEARCH_GDS
    if "esummary.fcgi" in url:
        return ESUMMARY_GDS
    raise AssertionError(url)


class IngestNeurobiologyTests(unittest.TestCase):
    def test_ingest_installs_neurobiology_lane(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "mosquito-v1"
            result = ingest_drosophila_suzukii_neurobiology(
                artifact_dir=artifact_dir,
                fetch_json=_fake_fetch,
                retrieved_at="2026-06-05T00:00:00Z",
                max_results=10,
                page_size=10,
                delay_seconds=0,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["source"], "drosophila_suzukii_neurobiology_sources")
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select lane, count(*) as n from records "
                "where source='drosophila_suzukii_neurobiology_sources' group by lane",
                limit=50,
            )
            lanes = {r["lane"]: r["n"] for r in rows}
            self.assertGreaterEqual(lanes.get("neurobiology", 0), 1)

    def test_failed_refresh_preserves_existing_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "mosquito-v1"
            ingest_drosophila_suzukii_neurobiology(
                artifact_dir=artifact_dir, fetch_json=_fake_fetch,
                retrieved_at="2026-06-05T00:00:00Z", max_results=10, page_size=10, delay_seconds=0,
            )
            failed = ingest_drosophila_suzukii_neurobiology(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-06-05T01:00:00Z", max_results=10, page_size=10, delay_seconds=0,
            )
            self.assertTrue(failed["preserved_existing"])
            self.assertGreaterEqual(failed["record_count"], 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_ingest_drosophila_suzukii_neurobiology.py -v`
Expected: FAIL — `ModuleNotFoundError: scripts.ingest_drosophila_suzukii_neurobiology`.

- [ ] **Step 3: Write the script** (`scripts/ingest_drosophila_suzukii_neurobiology.py`)

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

from askinsects.builder import DEFAULT_ARTIFACT_DIR, utc_now, write_json
from askinsects.index import SourceIndex
from askinsects.ingest_runner import run_source_ingest
from askinsects.sources.drosophila_suzukii_neurobiology import (
    DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID,
    fetch_drosophila_suzukii_neurobiology_records,
)


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [
        gap for gap in existing
        if not (isinstance(gap, dict) and gap.get("source") == DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID)
    ]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_record_count(index: SourceIndex) -> int:
    with index.connect() as conn:
        return int(conn.execute(
            "select count(*) as n from records where source=?",
            (DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID,),
        ).fetchone()["n"])


def _update_metadata(artifact_dir: Path, result, retrieved_at: str, *, ok: bool, preserved_existing: bool) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    installed = _source_record_count(index)
    source_counts = {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=2000)
    }
    source_payload = {
        "source": DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID,
        "query": result.query,
        "requested_urls": result.requested_urls,
        "record_count": installed,
        "refresh_record_count": len(result.records),
        "reported_total_count": result.reported_total_count,
        "dataset_count": result.dataset_count,
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
        "retrieved_at": retrieved_at,
        "refresh_failed": not ok,
        "preserved_existing": preserved_existing,
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID not in sources:
                sources.append(DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload[DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "source": DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID,
        "record_count": installed,
        "refresh_record_count": len(result.records),
        "dataset_count": result.dataset_count,
        "gap_count": len(result.gaps),
        "preserved_existing": preserved_existing,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_drosophila_suzukii_neurobiology(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    fetch_json=None,
    retrieved_at: str | None = None,
    max_results: int = 200,
    page_size: int = 100,
    delay_seconds: float = 0.34,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    result = fetch_drosophila_suzukii_neurobiology_records(
        raw_dir=artifact_dir / "raw" / "drosophila_suzukii_neurobiology",
        fetch_json=fetch_json,
        retrieved_at=retrieved,
        max_results=max_results,
        page_size=page_size,
        delay_seconds=delay_seconds,
    )
    outcome = run_source_ingest(
        index=index,
        artifact_dir=artifact_dir,
        source_id=DROSOPHILA_SUZUKII_NEUROBIOLOGY_SOURCE_ID,
        records=result.records,
        gaps=result.gaps,
        retrieved_at=retrieved,
        raw_artifacts=getattr(result, "raw_artifacts", None),
        persist_gap_records=True,
    )
    return _update_metadata(
        artifact_dir, result, retrieved,
        ok=not outcome["refresh_failed"],
        preserved_existing=outcome["preserved_existing"],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest the Drosophila suzukii neurobiology/chemosensory lane.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--max-results", type=int, default=200)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--retrieved-at")
    parser.add_argument("--delay-seconds", type=float, default=0.34)
    args = parser.parse_args(argv)
    result = ingest_drosophila_suzukii_neurobiology(
        artifact_dir=Path(args.artifact_dir),
        max_results=args.max_results,
        page_size=args.page_size,
        retrieved_at=args.retrieved_at,
        delay_seconds=args.delay_seconds,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python3 -m pytest tests/test_ingest_drosophila_suzukii_neurobiology.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/ingest_drosophila_suzukii_neurobiology.py tests/test_ingest_drosophila_suzukii_neurobiology.py
git commit -m "feat: SWD neurobiology ingest script with gap-preserving persistence"
```

---

## Task 4: Wire neurobiology into the CLI (local + hosted)

**Files:**
- Modify: `askinsects/cli.py` (subparser near line 190; dispatch near line 785)
- Modify: `askinsects/server.py` (handler near line 3576; route near line 4187)

- [ ] **Step 1: Add the subparser** in `askinsects/cli.py`, immediately after the `ingest-drosophila-suzukii-pubmed-literature` subparser block (after current line ~195):

```python
    ingest_swd_neuro = sub.add_parser("ingest-drosophila-suzukii-neurobiology")
    ingest_swd_neuro.add_argument("--hosted", action="store_true")
    ingest_swd_neuro.add_argument("--max-results", type=int, default=200)
    ingest_swd_neuro.add_argument("--page-size", type=int, default=100)
    ingest_swd_neuro.add_argument("--delay-seconds", type=float, default=0.34)
    ingest_swd_neuro.add_argument("--retrieved-at")
```

- [ ] **Step 2: Add the dispatch block** in `askinsects/cli.py`, immediately after the `ingest-drosophila-suzukii-pubmed-literature` dispatch block (after current line ~802):

```python
    if args.command == "ingest-drosophila-suzukii-neurobiology":
        request_payload = {
            "max_results": args.max_results,
            "page_size": args.page_size,
            "delay_seconds": args.delay_seconds,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-neurobiology", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_neurobiology import ingest_drosophila_suzukii_neurobiology

        payload = ingest_drosophila_suzukii_neurobiology(artifact_dir=artifact_dir, **request_payload)
        emit(payload)
        return 0 if payload.get("ok") else 2
```

- [ ] **Step 3: Add the hosted handler** in `askinsects/server.py`, after `ingest_drosophila_suzukii_pubmed_literature_hosted` (after current line ~3592):

```python
def ingest_drosophila_suzukii_neurobiology_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_neurobiology import ingest_drosophila_suzukii_neurobiology

    response = ingest_drosophila_suzukii_neurobiology(
        artifact_dir=artifact_dir,
        max_results=int(payload.get("max_results", 200)),
        page_size=int(payload.get("page_size", 100)),
        delay_seconds=float(payload.get("delay_seconds", 0.34)),
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response
```

- [ ] **Step 4: Add the route** in `askinsects/server.py`, after the `/ingest/drosophila-suzukii-pubmed-literature` route (after current line ~4190):

```python
        if method == "POST" and path == "/ingest/drosophila-suzukii-neurobiology":
            result = ingest_drosophila_suzukii_neurobiology_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
```

- [ ] **Step 5: Verify the CLI parses and dispatches locally**

Run:
```bash
python3 -m askinsects ingest-drosophila-suzukii-neurobiology --help
ASK_INSECTS_ARTIFACT_DIR=$(mktemp -d)/mosquito-v1 python3 -m askinsects ingest-drosophila-suzukii-neurobiology --max-results 1 --delay-seconds 0
```
Expected: help prints the new flags; the live run prints a JSON object with `"source": "drosophila_suzukii_neurobiology_sources"` and an `ok` field (live NCBI call; if offline it should still return a JSON object with gaps, not crash).

- [ ] **Step 6: Commit**

```bash
git add askinsects/cli.py askinsects/server.py
git commit -m "feat: wire SWD neurobiology into CLI and hosted server"
```

---

## Task 5: Olfaction-literature source (clone of the PubMed source, chemosensation-scoped)

**Files:**
- Create: `askinsects/sources/drosophila_suzukii_olfaction_literature.py`
- Create: `scripts/ingest_drosophila_suzukii_olfaction_literature.py`
- Create: `tests/test_ingest_drosophila_suzukii_olfaction_literature.py`

This source is a focused clone of the committed PubMed-literature source. Cloning the working file (rather than re-deriving) is the DRY path; the edits below are exhaustive.

- [ ] **Step 1: Copy the template files**

```bash
cd "$HOME/Documents/ask-insects"
cp askinsects/sources/drosophila_suzukii_pubmed_literature.py askinsects/sources/drosophila_suzukii_olfaction_literature.py
cp scripts/ingest_drosophila_suzukii_pubmed_literature.py scripts/ingest_drosophila_suzukii_olfaction_literature.py
```

- [ ] **Step 2: Edit the source module** `askinsects/sources/drosophila_suzukii_olfaction_literature.py`:
  - Replace every `DROSOPHILA_SUZUKII_PUBMED_LITERATURE_SOURCE_ID` with `DROSOPHILA_SUZUKII_OLFACTION_LITERATURE_SOURCE_ID`, value `"drosophila_suzukii_olfaction_literature"`.
  - Replace the `PUBMED_QUERY` value with the chemosensation-scoped query:

```python
PUBMED_QUERY = (
    '(("Drosophila suzukii"[Title/Abstract] OR "spotted wing drosophila"[Title/Abstract] '
    'OR "spotted-wing drosophila"[Title/Abstract]) AND '
    '(olfact*[Title/Abstract] OR chemosens*[Title/Abstract] OR antenna*[Title/Abstract] '
    'OR "odorant receptor"[Title/Abstract] OR oviposition[Title/Abstract] '
    'OR "host seeking"[Title/Abstract] OR neuro*[Title/Abstract])) AND '
    '("2010/01/01"[Date - Publication] : "3000"[Date - Publication])'
)
```
  - Rename the result dataclass `DrosophilaSuzukiiPubMedLiteratureResult` → `DrosophilaSuzukiiOlfactionLiteratureResult` and the entrypoint `fetch_drosophila_suzukii_pubmed_literature_records` → `fetch_drosophila_suzukii_olfaction_literature_records`.
  - Change the record_id prefix `swd_pubmed_literature:pubmed:` → `swd_olfaction_literature:pubmed:`.
  - Leave `lane="literature"` (olfaction papers are literature, routed by query terms).

- [ ] **Step 3: Edit the ingest script** `scripts/ingest_drosophila_suzukii_olfaction_literature.py`:
  - Update imports to the renamed source module/symbols.
  - Replace every `DROSOPHILA_SUZUKII_PUBMED_LITERATURE_SOURCE_ID` with `DROSOPHILA_SUZUKII_OLFACTION_LITERATURE_SOURCE_ID`.
  - Rename `ingest_drosophila_suzukii_pubmed_literature` → `ingest_drosophila_suzukii_olfaction_literature` and the raw dir to `drosophila_suzukii_olfaction_literature`.
  - Keep the existing-literature-rows reconciliation (still joins against `drosophila_suzukii_core` literature rows).

- [ ] **Step 4: Write the ingest test** `tests/test_ingest_drosophila_suzukii_olfaction_literature.py`:

```python
import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from scripts.ingest_drosophila_suzukii_olfaction_literature import ingest_drosophila_suzukii_olfaction_literature
from tests.test_drosophila_suzukii_pubmed_literature_source import ESEARCH, ESUMMARY


def _fake_fetch(url):
    if "esearch.fcgi" in url:
        return ESEARCH
    if "esummary.fcgi" in url:
        return ESUMMARY
    raise AssertionError(url)


class IngestOlfactionLiteratureTests(unittest.TestCase):
    def test_ingest_installs_olfaction_literature(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "mosquito-v1"
            result = ingest_drosophila_suzukii_olfaction_literature(
                artifact_dir=artifact_dir, fetch_json=_fake_fetch,
                retrieved_at="2026-06-05T00:00:00Z", max_results=20, page_size=10, delay_seconds=0,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["source"], "drosophila_suzukii_olfaction_literature")
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select count(*) as n from records where source='drosophila_suzukii_olfaction_literature'",
                limit=5,
            )
            self.assertGreaterEqual(rows[0]["n"], 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 5: Run the olfaction tests**

Run: `python3 -m pytest tests/test_ingest_drosophila_suzukii_olfaction_literature.py -v`
Expected: PASS. (Reuses the committed `ESEARCH`/`ESUMMARY` fixtures from the PubMed source test.)

- [ ] **Step 6: Commit**

```bash
git add askinsects/sources/drosophila_suzukii_olfaction_literature.py scripts/ingest_drosophila_suzukii_olfaction_literature.py tests/test_ingest_drosophila_suzukii_olfaction_literature.py
git commit -m "feat: SWD olfaction-literature source, script, and test"
```

---

## Task 6: Wire olfaction-literature into CLI + server

**Files:**
- Modify: `askinsects/cli.py`
- Modify: `askinsects/server.py`

- [ ] **Step 1: Subparser** in `askinsects/cli.py` (after the neurobiology subparser from Task 4):

```python
    ingest_swd_olf = sub.add_parser("ingest-drosophila-suzukii-olfaction-literature")
    ingest_swd_olf.add_argument("--hosted", action="store_true")
    ingest_swd_olf.add_argument("--max-results", type=int, default=1000)
    ingest_swd_olf.add_argument("--page-size", type=int, default=100)
    ingest_swd_olf.add_argument("--delay-seconds", type=float, default=0.34)
    ingest_swd_olf.add_argument("--retrieved-at")
```

- [ ] **Step 2: Dispatch block** in `askinsects/cli.py` (after the neurobiology dispatch from Task 4):

```python
    if args.command == "ingest-drosophila-suzukii-olfaction-literature":
        request_payload = {
            "max_results": args.max_results,
            "page_size": args.page_size,
            "delay_seconds": args.delay_seconds,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-olfaction-literature", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_olfaction_literature import ingest_drosophila_suzukii_olfaction_literature

        payload = ingest_drosophila_suzukii_olfaction_literature(artifact_dir=artifact_dir, **request_payload)
        emit(payload)
        return 0 if payload.get("ok") else 2
```

- [ ] **Step 3: Hosted handler** in `askinsects/server.py` (after the neurobiology handler from Task 4):

```python
def ingest_drosophila_suzukii_olfaction_literature_hosted(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
) -> dict[str, object]:
    from scripts.ingest_drosophila_suzukii_olfaction_literature import ingest_drosophila_suzukii_olfaction_literature

    response = ingest_drosophila_suzukii_olfaction_literature(
        artifact_dir=artifact_dir,
        max_results=int(payload.get("max_results", 1000)),
        page_size=int(payload.get("page_size", 100)),
        delay_seconds=float(payload.get("delay_seconds", 0.34)),
        retrieved_at=str(payload["retrieved_at"]) if payload.get("retrieved_at") else None,
    )
    response["activated_artifact_dir"] = str(artifact_dir)
    response["updated_in_place"] = True
    return response
```

- [ ] **Step 4: Route** in `askinsects/server.py` (after the neurobiology route from Task 4):

```python
        if method == "POST" and path == "/ingest/drosophila-suzukii-olfaction-literature":
            result = ingest_drosophila_suzukii_olfaction_literature_hosted(payload or {}, artifact_dir=artifact_dir)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
```

- [ ] **Step 5: Verify CLI parses**

Run: `python3 -m askinsects ingest-drosophila-suzukii-olfaction-literature --help`
Expected: prints the new flags.

- [ ] **Step 6: Commit**

```bash
git add askinsects/cli.py askinsects/server.py
git commit -m "feat: wire SWD olfaction-literature into CLI and hosted server"
```

---

## Task 7: Register sources in source-map.yaml

**Files:**
- Modify: `config/source-map.yaml`

- [ ] **Step 1: Add both source entries** under the SWD section (mirror the existing `drosophila_suzukii_pubmed_literature` entry at line ~193). Append:

```yaml
  - id: drosophila_suzukii_neurobiology_sources
    name: Drosophila suzukii neurobiology and chemosensory source metadata
    source_type: public_api_metadata
    boundary: Bounded NCBI GEO DataSets metadata for Drosophila suzukii brain, antennal, and chemosensory studies, with queryable source_gap records for absent whole-brain atlas, connectome, single-nucleus brain RNA-seq, and antennal-lobe-map domains
    query_plane: ncbi_gds_esearch_esummary_to_sqlite_neurobiology_records
    artifact_dir: artifacts/mosquito-v1
    raw_artifact_dir: artifacts/mosquito-v1/raw/drosophila_suzukii_neurobiology
    lanes:
      - neurobiology
    provenance_required: true
    live_fetch: bounded_opt_in

  - id: drosophila_suzukii_olfaction_literature
    name: Drosophila suzukii olfaction and chemosensation literature
    source_type: public_api_metadata_audit
    boundary: Bounded PubMed ESearch and ESummary metadata for Drosophila suzukii olfaction, chemosensation, antennal, oviposition, and host-seeking papers, reconciled against canonical drosophila_suzukii_core OpenAlex literature rows
    query_plane: pubmed_esearch_esummary_to_sqlite_literature_audit_records
    artifact_dir: artifacts/mosquito-v1
    raw_artifact_dir: artifacts/mosquito-v1/raw/drosophila_suzukii_olfaction_literature
    lanes:
      - literature
    provenance_required: true
    live_fetch: bounded_opt_in
```

- [ ] **Step 2: Verify YAML parses**

Run: `python3 -c "import yaml; yaml.safe_load(open('config/source-map.yaml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add config/source-map.yaml
git commit -m "config: map SWD neurobiology and olfaction-literature sources"
```

---

## Task 8: Parity benchmark seed + completion-gate spec registration

**Files:**
- Create: `config/swd-source-plane-benchmark.json`
- Modify: `scripts/verify_complete.py` (`REQUIRED_FILES` tuple)

- [ ] **Step 1: Create** `config/swd-source-plane-benchmark.json`:

```json
{
  "species": "Drosophila suzukii",
  "parity_rule": "covered = at least one non-gap record OR at least one source_gap record per applicable category",
  "skip_categories": ["vector_competence", "public_health", "wolbachia_interventions", "dengue_surveillance"],
  "categories": [
    {"key": "neurobiology", "source_ids": ["drosophila_suzukii_neurobiology_sources"], "status": "in_progress"},
    {"key": "olfaction_literature", "source_ids": ["drosophila_suzukii_olfaction_literature"], "status": "in_progress"}
  ]
}
```

- [ ] **Step 2: Register the two spec files** by adding these entries to the `REQUIRED_FILES` tuple in `scripts/verify_complete.py`:

```python
    "docs/superpowers/specs/2026-06-05-swd-aedes-parity-program-design.md",
    "docs/superpowers/specs/2026-06-05-swd-neurobiology-olfaction-lane-design.md",
```

- [ ] **Step 3: Run the full test suite** (regression check that nothing else broke)

Run: `python3 -m pytest tests/test_drosophila_suzukii_neurobiology_source.py tests/test_ingest_drosophila_suzukii_neurobiology.py tests/test_ingest_drosophila_suzukii_olfaction_literature.py -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add config/swd-source-plane-benchmark.json scripts/verify_complete.py
git commit -m "config: SWD parity benchmark seed + register brain/smell specs in completion gate"
```

---

## Task 9: Hosted ingest + live verification

**Files:** none (operational)

- [ ] **Step 1: Confirm hosted server is reachable**

Run: `python3 -m askinsects health --hosted`
Expected: JSON with `"ok": true`.

- [ ] **Step 2: Run both ingests against the hosted plane**

```bash
python3 -m askinsects ingest-drosophila-suzukii-neurobiology --hosted --max-results 200
python3 -m askinsects ingest-drosophila-suzukii-olfaction-literature --hosted --max-results 1000
```
Expected: each prints JSON with `"ok": true` and a `record_count` / `gap_count`. Record what came back (datasets found vs. honest gaps) — this is the answer to "how much SWD brain/smell data actually exists."

- [ ] **Step 3: Verify the lanes are live and queryable**

```bash
python3 -m askinsects sql "select source, lane, count(*) n from records where source like 'drosophila_suzukii_%neuro%' or source='drosophila_suzukii_olfaction_literature' group by source, lane" --hosted
python3 -m askinsects ask "what chemosensory or brain data exists for Drosophila suzukii?" --hosted
```
Expected: neurobiology + olfaction rows present (or honest gap records), and the `ask` answer cites the new local SWD evidence.

- [ ] **Step 4: Run the repo completion gate**

Run: `python3 scripts/verify_complete.py`
Expected: gate passes (exit 0). If it flags missing required files for *other* lanes unrelated to this change, that is pre-existing; note it but do not fix unrelated lanes here.

- [ ] **Step 5: Final commit (receipts/status only, if changed)**

```bash
git add -A
git commit -m "chore: hosted SWD neurobiology + olfaction-literature ingest receipts" || echo "no receipt changes to commit"
```

---

## Self-Review

- **Spec coverage:** neurobiology source (Tasks 1-4) ✓; olfaction literature (Tasks 5-6) ✓; honest gaps via `run_source_ingest`/domain-absence records (Tasks 1-3) ✓; source-map mapping (Task 7) ✓; query routing relies on existing answer-routing keyword logic — verified terms (`neurobiology`, `antennal`, etc.) already route in the Aedes lane; no code change needed; hosted + verify (Tasks 8-9) ✓; parity benchmark seed (Task 8) ✓.
- **Placeholder scan:** every code step contains complete code; the olfaction clone lists exhaustive edits against a named existing file. No TBD/TODO.
- **Type consistency:** `fetch_drosophila_suzukii_neurobiology_records` returns `DrosophilaSuzukiiNeurobiologyResult` with `.records/.gaps/.raw_artifacts/.requested_urls/.query/.reported_total_count/.dataset_count`; the script reads exactly those attributes. Source IDs are consistent across module, script, CLI, server, source-map, and benchmark.
- **Known follow-on (out of scope here, tracked in umbrella spec):** answer-routing may benefit from explicitly listing the SWD neurobiology source in any species-scoped routing table; verify during Task 9 Step 3 and open a follow-up if the `ask` answer does not surface the new rows.
