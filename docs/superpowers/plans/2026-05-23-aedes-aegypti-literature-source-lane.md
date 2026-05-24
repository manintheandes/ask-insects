# Aedes aegypti Literature Source Lane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Source-grade every discoverable academic research article materially about `Aedes aegypti` since 2020 into an Ask Insects SQLite literature lane, with provenance, receipts, docs, verification gates, legal open full text where accessible, and explicit gaps for inaccessible full text.

**Architecture:** Add a new literature source module that discovers canonical papers from OpenAlex title, abstract, and accepted topic metadata, then enriches records with PubMed and Unpaywall. Reuse the existing `records` and `record_payloads` tables for normalized paper rows and raw source payloads, and add a focused `literature_fulltext_units` table for legal open full-text chunks.

**Tech Stack:** Python standard library, `urllib.request`, JSON artifacts, SQLite FTS5, OpenAlex Works and Topics APIs, NCBI E-utilities, Unpaywall API, `unittest`.

---

## File Structure

- Create `askinsects/sources/literature.py`: OpenAlex cursor pagination, topic discovery, PubMed enrichment, Unpaywall enrichment, legal full-text fetch and parse helpers, and conversion to `EvidenceRecord` rows plus full-text units and gaps.
- Modify `askinsects/index.py`: add `literature_fulltext_units` schema and upsert/query helpers.
- Modify `askinsects/records.py`: add optional `fulltext_units` support only if needed by the index helper; keep `EvidenceRecord` backwards compatible.
- Modify `askinsects/builder.py`: accept literature build options and merge returned records, payloads, full-text units, gaps, status, and receipts.
- Modify `scripts/build_source_index.py`: add CLI flags for `--openalex-literature`, dates, work type, topic discovery, page size, delay, optional Unpaywall email, full-text toggle, and max-work cap for smoke tests.
- Modify `askinsects/planner.py` and `askinsects/answer.py`: route literature questions to the literature lane and keep gap language source-specific.
- Modify `config/source-map.yaml`: declare `aedes_literature_openalex`.
- Modify `README.md`, `docs/source-lanes.md`, and `docs/querying-ask-insects.md`: document boundary, build commands, legal full-text rule, and verification.
- Modify `scripts/verify_complete.py`: require the literature spec, plan, tests, source map entry, deterministic build, and CLI query proof.
- Create `tests/test_literature_source.py`: deterministic source-loader tests for OpenAlex, topics, PubMed, Unpaywall, full text, and gaps.
- Modify `tests/test_builder.py`, `tests/test_cli.py`, `tests/test_index.py`, `tests/test_answer.py`, and `tests/test_verify_complete.py`: cover build wiring and query behavior.

## Task 1: Literature Source Tests

**Files:**
- Create: `tests/test_literature_source.py`
- No implementation files modified in this task.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_literature_source.py` with fake source responses. Use this full test skeleton:

```python
from __future__ import annotations

import json
from pathlib import Path
import unittest

from askinsects.sources.literature import (
    LITERATURE_SOURCE_ID,
    abstract_from_inverted_index,
    fetch_literature_records,
)


def openalex_work(work_id: str, *, title: str, abstract_terms: dict[str, list[int]], doi: str | None = None) -> dict[str, object]:
    return {
        "id": f"https://openalex.org/{work_id}",
        "doi": doi,
        "display_name": title,
        "publication_date": "2024-03-01",
        "type": "article",
        "abstract_inverted_index": abstract_terms,
        "authorships": [{"author": {"display_name": "Ada Researcher"}}],
        "primary_location": {"source": {"display_name": "Journal of Mosquito Work"}},
        "open_access": {"is_oa": bool(doi), "oa_url": "https://example.org/open.pdf" if doi else None},
        "ids": {"openalex": f"https://openalex.org/{work_id}", "doi": doi},
        "primary_topic": {"id": "https://openalex.org/T-AEDES", "display_name": "Aedes aegypti vector biology"},
        "topics": [{"id": "https://openalex.org/T-AEDES", "display_name": "Aedes aegypti vector biology"}],
        "keywords": [{"display_name": "Aedes aegypti"}],
    }


class LiteratureSourceTests(unittest.TestCase):
    def test_reconstructs_openalex_abstract(self) -> None:
        abstract = abstract_from_inverted_index({"Aedes": [0], "aegypti": [1], "vector": [2], "biology": [3]})
        self.assertEqual(abstract, "Aedes aegypti vector biology")

    def test_fetches_cursor_pages_and_normalizes_literature_records(self) -> None:
        calls: list[str] = []

        def fake_fetch_json(url: str) -> dict[str, object]:
            calls.append(url)
            if "/topics" in url:
                return {"results": [{"id": "https://openalex.org/T-AEDES", "display_name": "Aedes aegypti vector biology", "description": "Aedes aegypti mosquito papers", "keywords": ["Aedes aegypti"]}]}
            if "cursor=%2A" in url or "cursor=*" in url:
                return {
                    "meta": {"count": 2, "next_cursor": "page-2"},
                    "results": [openalex_work("W1", title="Aedes aegypti control", abstract_terms={"Aedes": [0], "aegypti": [1], "control": [2]}, doi="https://doi.org/10.1000/aedes1")],
                }
            return {
                "meta": {"count": 2, "next_cursor": None},
                "results": [openalex_work("W2", title="Dengue vector study", abstract_terms={"material": [0], "topic": [1]}, doi=None)],
            }

        result = fetch_literature_records(
            species="Aedes aegypti",
            from_date="2020-01-01",
            to_date="2026-05-23",
            work_type="article",
            include_topic_discovery=True,
            raw_dir=Path(self.create_tmpdir()) / "raw",
            page_size=1,
            delay_seconds=0,
            fetch_json=fake_fetch_json,
            fetch_text=lambda url: "legal open full text for Aedes aegypti",
            unpaywall_email="test@example.com",
            retrieved_at="2026-05-23T00:00:00Z",
        )

        self.assertEqual(result.source_id, LITERATURE_SOURCE_ID)
        self.assertEqual(len(result.records), 2)
        self.assertTrue(any(record.record_id == "openalex:W1" for record in result.records))
        self.assertTrue(any(record.lane == "literature" for record in result.records))
        self.assertGreaterEqual(len(result.raw_artifacts), 2)
        self.assertIn("title", result.inclusion_path_counts)
        self.assertIn("abstract", result.inclusion_path_counts)
        self.assertTrue(calls)

    def test_records_closed_full_text_gap(self) -> None:
        def fake_fetch_json(url: str) -> dict[str, object]:
            if "/topics" in url:
                return {"results": []}
            return {
                "meta": {"count": 1, "next_cursor": None},
                "results": [openalex_work("W3", title="Aedes aegypti closed paper", abstract_terms={"Aedes": [0], "aegypti": [1]}, doi=None)],
            }

        result = fetch_literature_records(
            species="Aedes aegypti",
            from_date="2020-01-01",
            to_date="2026-05-23",
            work_type="article",
            include_topic_discovery=True,
            raw_dir=Path(self.create_tmpdir()) / "raw",
            page_size=25,
            delay_seconds=0,
            fetch_json=fake_fetch_json,
            retrieved_at="2026-05-23T00:00:00Z",
        )

        reasons = {gap["reason"] for gap in result.gaps}
        self.assertIn("missing_doi", reasons)
        self.assertIn("openalex_topic_search_empty", reasons)

    def create_tmpdir(self) -> str:
        import tempfile

        return tempfile.mkdtemp(prefix="askinsects-literature-test-")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the failing tests**

```bash
python3 -m unittest tests.test_literature_source -v
```

Expected result: fail with `ModuleNotFoundError: No module named 'askinsects.sources.literature'`.

## Task 2: OpenAlex Literature Source Module

**Files:**
- Create: `askinsects/sources/literature.py`
- Test: `tests/test_literature_source.py`

- [ ] **Step 1: Implement the module constants and result dataclass**

Create `askinsects/sources/literature.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import time
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


LITERATURE_SOURCE_ID = "aedes_literature_openalex"
OPENALEX_API_BASE = "https://api.openalex.org"
PUBMED_API_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
UNPAYWALL_API_BASE = "https://api.unpaywall.org/v2"


@dataclass(frozen=True)
class FullTextUnit:
    unit_id: str
    record_id: str
    source: str
    unit_index: int
    text: str
    url: str | None
    license: str | None
    provenance: Provenance


@dataclass(frozen=True)
class LiteratureBuildResult:
    source_id: str
    records: list[EvidenceRecord]
    fulltext_units: list[FullTextUnit]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    topic_search_results: list[dict[str, object]]
    accepted_topic_ids: list[str]
    inclusion_path_counts: dict[str, int]
    reported_total_count: int
    page_count: int
    doi_count: int
    unpaywall_queried_count: int
    open_fulltext_count: int
```

- [ ] **Step 2: Implement utilities**

Add:

```python
def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_") or "source"


def write_raw_json(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def abstract_from_inverted_index(index: dict[str, list[int]] | None) -> str | None:
    if not index:
        return None
    positions: dict[int, str] = {}
    for token, indexes in index.items():
        for position in indexes:
            positions[int(position)] = token
    return " ".join(positions[position] for position in sorted(positions))


def openalex_work_key(work: dict[str, object]) -> str:
    raw_id = str(work.get("id") or "")
    return raw_id.rstrip("/").rsplit("/", 1)[-1]
```

- [ ] **Step 3: Implement HTTP clients**

Add `fetch_json_url` and `fetch_text_url`:

```python
def fetch_json_url(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": "ask-insects/0.1"})
    with urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object for {url}")
    return payload


def fetch_text_url(url: str) -> str:
    request = Request(url, headers={"User-Agent": "ask-insects/0.1"})
    with urlopen(request, timeout=60) as response:
        content_type = response.headers.get("content-type", "")
        body = response.read()
    if "pdf" in content_type.lower():
        return ""
    return body.decode("utf-8", errors="replace")
```

- [ ] **Step 4: Implement topic discovery**

Add:

```python
def topic_materially_matches_species(topic: dict[str, object], species: str) -> bool:
    species_lower = species.lower()
    fields = [
        topic.get("display_name"),
        topic.get("description"),
        " ".join(str(keyword) for keyword in topic.get("keywords", []) if isinstance(keyword, str)),
    ]
    return any(species_lower in str(field).lower() for field in fields if field)


def discover_topic_ids(species: str, *, fetch_json: Callable[[str], dict[str, object]], raw_dir: Path, retrieved_at: str) -> tuple[list[str], list[dict[str, object]], list[dict[str, object]], list[str]]:
    url = f"{OPENALEX_API_BASE}/topics?{urlencode({'search': species, 'per-page': 50})}"
    payload = fetch_json(url)
    raw_path = write_raw_json(raw_dir, "topics_search.json", payload)
    results = [item for item in payload.get("results", []) if isinstance(item, dict)]
    accepted = [str(item["id"]) for item in results if item.get("id") and topic_materially_matches_species(item, species)]
    gaps: list[dict[str, object]] = []
    if not accepted:
        gaps.append({"source": LITERATURE_SOURCE_ID, "lane": "literature", "reason": "openalex_topic_search_empty", "locator": f"{raw_path.as_posix()}#topics", "retrieved_at": retrieved_at})
    for item in results:
        if item.get("id") and str(item["id"]) not in accepted:
            gaps.append({"source": LITERATURE_SOURCE_ID, "lane": "literature", "reason": "openalex_topic_candidate_rejected", "external_id": item.get("id"), "locator": f"{raw_path.as_posix()}#topics/{item.get('id')}", "retrieved_at": retrieved_at})
    return accepted, results, gaps, [raw_path.as_posix()]
```

- [ ] **Step 5: Implement record conversion**

Add a converter that reconstructs abstracts and stores raw payloads:

```python
def literature_record(work: dict[str, object], *, raw_path: Path, retrieved_at: str, inclusion_paths: list[str], unpaywall_payload: dict[str, object] | None = None) -> EvidenceRecord:
    work_key = openalex_work_key(work)
    abstract = abstract_from_inverted_index(work.get("abstract_inverted_index") if isinstance(work.get("abstract_inverted_index"), dict) else None)
    doi = work.get("doi")
    ids = work.get("ids") if isinstance(work.get("ids"), dict) else {}
    venue = ""
    primary_location = work.get("primary_location")
    if isinstance(primary_location, dict):
        source = primary_location.get("source")
        if isinstance(source, dict):
            venue = str(source.get("display_name") or "")
    title = str(work.get("display_name") or work_key)
    pieces = [title]
    if abstract:
        pieces.append(abstract)
    if doi:
        pieces.append(f"DOI: {doi}")
    if venue:
        pieces.append(f"Venue: {venue}")
    pieces.append(f"Inclusion paths: {', '.join(sorted(inclusion_paths))}")
    return EvidenceRecord(
        record_id=f"openalex:{work_key}",
        lane="literature",
        source=LITERATURE_SOURCE_ID,
        title=title,
        text=" ".join(pieces),
        species="Aedes aegypti",
        url=str(work.get("id") or ""),
        media_url=None,
        provenance=Provenance(
            source_id=LITERATURE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#works/{work_key}",
            retrieved_at=retrieved_at,
            license="OpenAlex metadata",
            source_url=str(work.get("id") or ""),
        ),
        payload={"openalex": work, "unpaywall": unpaywall_payload, "inclusion_paths": inclusion_paths, "ids": ids},
    )
```

- [ ] **Step 6: Implement `fetch_literature_records` enough to pass tests**

Implement cursor pagination for the title/abstract query, topic discovery,
dedupe by OpenAlex work id, and structured gaps for missing DOI and missing
abstracts. Keep PubMed and Unpaywall hooks as empty no-op enrichments for now.
Use this signature from the tests:

```python
def fetch_literature_records(
    *,
    species: str,
    from_date: str,
    to_date: str,
    work_type: str,
    include_topic_discovery: bool,
    raw_dir: Path,
    page_size: int = 200,
    delay_seconds: float = 1.0,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    fetch_text: Callable[[str], str] | None = None,
    unpaywall_email: str | None = None,
    retrieved_at: str | None = None,
    max_works: int | None = None,
) -> LiteratureBuildResult:
```

- [ ] **Step 7: Run source tests**

```bash
python3 -m unittest tests.test_literature_source -v
```

Expected result: pass.

- [ ] **Step 8: Commit**

```bash
git add askinsects/sources/literature.py tests/test_literature_source.py
git commit -m "feat: add OpenAlex literature source loader"
```

## Task 3: Full-Text Storage Tests And Index Support

**Files:**
- Modify: `askinsects/index.py`
- Modify: `askinsects/sources/literature.py`
- Modify: `tests/test_index.py`
- Modify: `tests/test_literature_source.py`

- [ ] **Step 1: Add failing full-text unit index test**

Append to `tests/test_index.py`:

```python
def test_upserts_literature_fulltext_units(self):
    from askinsects.sources.literature import FullTextUnit

    index = SourceIndex(self.db_path)
    index.initialize()
    provenance = Provenance(source_id="aedes_literature_openalex", locator="raw/openalex/page.json#W1", retrieved_at="2026-05-23T00:00:00Z")
    unit = FullTextUnit(
        unit_id="openalex:W1:fulltext:0",
        record_id="openalex:W1",
        source="aedes_literature_openalex",
        unit_index=0,
        text="Aedes aegypti legal open full text",
        url="https://example.org/fulltext",
        license="cc-by",
        provenance=provenance,
    )
    index.upsert_fulltext_units([unit])
    rows = index.sql("select unit_id, text from literature_fulltext_units")
    self.assertEqual(rows[0]["unit_id"], "openalex:W1:fulltext:0")
    self.assertIn("Aedes aegypti", rows[0]["text"])
```

- [ ] **Step 2: Run failing test**

```bash
python3 -m unittest tests.test_index -v
```

Expected result: fail because `upsert_fulltext_units` and the table do not exist.

- [ ] **Step 3: Add schema and upsert helper**

In `askinsects/index.py`, add this table to `SCHEMA`:

```sql
CREATE TABLE IF NOT EXISTS literature_fulltext_units (
  unit_id TEXT PRIMARY KEY,
  record_id TEXT NOT NULL,
  source TEXT NOT NULL,
  unit_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  url TEXT,
  license TEXT,
  provenance_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_literature_fulltext_record_id ON literature_fulltext_units(record_id);
CREATE VIRTUAL TABLE IF NOT EXISTS literature_fulltext_fts
USING fts5(unit_id UNINDEXED, record_id UNINDEXED, text);
```

Add:

```python
def upsert_fulltext_units(self, units: list[object]) -> None:
    with self.connect() as conn:
        for unit in units:
            provenance_json = json.dumps(unit.provenance.to_dict(), sort_keys=True)
            conn.execute(
                """
                INSERT INTO literature_fulltext_units (
                  unit_id, record_id, source, unit_index, text, url, license, provenance_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(unit_id) DO UPDATE SET
                  record_id=excluded.record_id,
                  source=excluded.source,
                  unit_index=excluded.unit_index,
                  text=excluded.text,
                  url=excluded.url,
                  license=excluded.license,
                  provenance_json=excluded.provenance_json
                """,
                (unit.unit_id, unit.record_id, unit.source, unit.unit_index, unit.text, unit.url, unit.license, provenance_json),
            )
            conn.execute("DELETE FROM literature_fulltext_fts WHERE unit_id=?", (unit.unit_id,))
            conn.execute(
                "INSERT INTO literature_fulltext_fts(unit_id, record_id, text) VALUES (?, ?, ?)",
                (unit.unit_id, unit.record_id, unit.text),
            )
```

- [ ] **Step 4: Split legal full text into units**

In `askinsects/sources/literature.py`, add:

```python
def fulltext_units_for_record(record_id: str, text: str, *, url: str, license: str | None, retrieved_at: str) -> list[FullTextUnit]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    chunks = [cleaned[index:index + 4000] for index in range(0, len(cleaned), 4000)]
    return [
        FullTextUnit(
            unit_id=f"{record_id}:fulltext:{index}",
            record_id=record_id,
            source=LITERATURE_SOURCE_ID,
            unit_index=index,
            text=chunk,
            url=url,
            license=license,
            provenance=Provenance(source_id=LITERATURE_SOURCE_ID, locator=f"{url}#fulltext/{index}", retrieved_at=retrieved_at, license=license, source_url=url),
        )
        for index, chunk in enumerate(chunks)
    ]
```

- [ ] **Step 5: Run index and literature tests**

```bash
python3 -m unittest tests.test_index tests.test_literature_source -v
```

Expected result: pass.

- [ ] **Step 6: Commit**

```bash
git add askinsects/index.py askinsects/sources/literature.py tests/test_index.py tests/test_literature_source.py
git commit -m "feat: store legal literature full text units"
```

## Task 4: PubMed And Unpaywall Enrichment

**Files:**
- Modify: `askinsects/sources/literature.py`
- Modify: `tests/test_literature_source.py`

- [ ] **Step 1: Add failing enrichment test**

Add a test that passes fake Unpaywall and PubMed payloads into `fetch_literature_records` through URL-sensitive `fake_fetch_json`:

```python
def test_enriches_with_unpaywall_and_pubmed(self) -> None:
    def fake_fetch_json(url: str) -> dict[str, object]:
        if "api.unpaywall.org" in url:
            return {"doi": "10.1000/aedes1", "is_oa": True, "best_oa_location": {"url_for_pdf": "https://example.org/aedes.pdf", "license": "cc-by"}}
        if "esearch.fcgi" in url:
            return {"esearchresult": {"count": "1", "idlist": ["123"]}}
        if "esummary.fcgi" in url:
            return {"result": {"uids": ["123"], "123": {"uid": "123", "title": "Aedes aegypti control", "elocationid": "doi: 10.1000/aedes1"}}}
        if "/topics" in url:
            return {"results": []}
        return {"meta": {"count": 1, "next_cursor": None}, "results": [openalex_work("W1", title="Aedes aegypti control", abstract_terms={"Aedes": [0], "aegypti": [1]}, doi="https://doi.org/10.1000/aedes1")]}

    result = fetch_literature_records(
        species="Aedes aegypti",
        from_date="2020-01-01",
        to_date="2026-05-23",
        work_type="article",
        include_topic_discovery=True,
        raw_dir=Path(self.create_tmpdir()) / "raw",
        page_size=25,
        delay_seconds=0,
        fetch_json=fake_fetch_json,
        fetch_text=lambda url: "Aedes aegypti legal open full text",
        unpaywall_email="test@example.com",
        retrieved_at="2026-05-23T00:00:00Z",
    )
    self.assertEqual(result.unpaywall_queried_count, 1)
    self.assertEqual(result.open_fulltext_count, 1)
    self.assertEqual(len(result.fulltext_units), 1)
    self.assertEqual(result.fulltext_units[0].license, "cc-by")
    self.assertIn("unpaywall", result.records[0].payload)
```

- [ ] **Step 2: Run failing test**

```bash
python3 -m unittest tests.test_literature_source.LiteratureSourceTests.test_enriches_with_unpaywall_and_pubmed -v
```

Expected result: fail until Unpaywall/PubMed enrichment is implemented.

- [ ] **Step 3: Implement Unpaywall lookup**

Add:

```python
def normalize_doi(raw: object) -> str | None:
    if not raw:
        return None
    doi = str(raw).replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    return doi or None


def unpaywall_url(doi: str, email: str) -> str:
    return f"{UNPAYWALL_API_BASE}/{doi}?{urlencode({'email': email})}"


def best_open_fulltext(unpaywall_payload: dict[str, object]) -> tuple[str | None, str | None]:
    best = unpaywall_payload.get("best_oa_location")
    if not isinstance(best, dict):
        return None, None
    url = best.get("url_for_pdf") or best.get("url_for_landing_page")
    license_value = best.get("license")
    return (str(url) if url else None, str(license_value) if license_value else None)
```

- [ ] **Step 4: Implement PubMed lookup**

Add PubMed ESearch and ESummary calls using DOI terms for DOI-bearing works and title terms for DOI-missing works. Save raw JSON under `raw/pubmed/`. Store matched payloads in `record.payload["pubmed"]`.

Use URL shapes:

```python
f"{PUBMED_API_BASE}/esearch.fcgi?{urlencode({'db': 'pubmed', 'term': term, 'retmode': 'json', 'retmax': 5})}"
f"{PUBMED_API_BASE}/esummary.fcgi?{urlencode({'db': 'pubmed', 'id': ','.join(ids), 'retmode': 'json'})}"
```

- [ ] **Step 5: Wire enrichment into `fetch_literature_records`**

For each DOI-bearing work:

```python
doi = normalize_doi(work.get("doi"))
if doi and unpaywall_email:
    payload = fetch_json(unpaywall_url(doi, unpaywall_email))
    fulltext_url, license_value = best_open_fulltext(payload)
    if fulltext_url:
        text = fetch_text(fulltext_url)
        units.extend(fulltext_units_for_record(record_id, text, url=fulltext_url, license=license_value, retrieved_at=retrieved))
    else:
        gaps.append({"source": LITERATURE_SOURCE_ID, "lane": "literature", "record_id": record_id, "reason": "unpaywall_no_fulltext_url", "locator": f"raw/unpaywall/{safe_name(doi)}.json", "retrieved_at": retrieved})
elif not doi:
    gaps.append({"source": LITERATURE_SOURCE_ID, "lane": "literature", "record_id": record_id, "reason": "missing_doi", "locator": record_id, "retrieved_at": retrieved})
```

- [ ] **Step 6: Run enrichment tests**

```bash
python3 -m unittest tests.test_literature_source -v
```

Expected result: pass.

- [ ] **Step 7: Commit**

```bash
git add askinsects/sources/literature.py tests/test_literature_source.py
git commit -m "feat: enrich literature with PubMed and Unpaywall"
```

## Task 5: Builder And CLI Wiring

**Files:**
- Modify: `askinsects/builder.py`
- Modify: `scripts/build_source_index.py`
- Modify: `tests/test_builder.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add failing builder test**

In `tests/test_builder.py`, add a fake literature fetcher injection or monkeypatch. If the existing builder pattern does not use monkeypatching, add a keyword argument `literature_fetcher` to `build_source_index` for tests.

Test shape:

```python
def test_builds_literature_source_index(self):
    result = build_source_index(
        include_fixtures=True,
        include_gbif=False,
        include_inaturalist=False,
        include_literature=True,
        literature_species="Aedes aegypti",
        literature_from_date="2020-01-01",
        literature_to_date="2026-05-23",
        literature_work_type="article",
        include_topic_discovery=True,
        literature_page_size=25,
        literature_delay_seconds=0,
        literature_max_works=1,
        artifact_dir=self.artifact_dir,
        literature_fetch_json=fake_literature_fetch_json,
        literature_fetch_text=lambda url: "Aedes aegypti open full text",
        unpaywall_email="test@example.com",
    )
    self.assertTrue(result["ok"])
    self.assertIn("aedes_literature_openalex", result["sources"])
    self.assertEqual(result["literature"]["species"], "Aedes aegypti")
    self.assertGreaterEqual(result["literature"]["record_count"], 1)
```

- [ ] **Step 2: Add failing CLI parse test**

In `tests/test_cli.py`, add:

```python
def test_build_script_accepts_literature_flags(self):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_source_index.py",
            "--fixtures",
            "--openalex-literature",
            "--species",
            "Aedes aegypti",
            "--from-date",
            "2020-01-01",
            "--to-date",
            "2026-05-23",
            "--work-type",
            "article",
            "--include-topic-discovery",
            "--max-works",
            "1",
            "--delay-seconds",
            "0",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    self.assertNotEqual(result.returncode, 2)
```

- [ ] **Step 3: Run failing tests**

```bash
python3 -m unittest tests.test_builder tests.test_cli -v
```

Expected result: fail because builder and CLI do not know the literature flags.

- [ ] **Step 4: Modify builder**

In `askinsects/builder.py`:

- import `fetch_literature_records` and `LITERATURE_SOURCE_ID`
- add `include_literature: bool = False`
- add literature options matching the CLI flags
- include literature in the selected-source validation
- extend `records`, `gaps`, `sources`, `source_counts`, `receipt_sources`
- call `index.upsert_fulltext_units(literature_result.fulltext_units)` after `index.upsert_records(records)`

Receipt payload must include:

```python
literature_payload = {
    "species": literature_species,
    "from_date": literature_from_date,
    "to_date": literature_to_date,
    "work_type": literature_work_type,
    "include_topic_discovery": include_topic_discovery,
    "reported_total_count": literature_result.reported_total_count,
    "page_count": literature_result.page_count,
    "record_count": len(literature_result.records),
    "fulltext_unit_count": len(literature_result.fulltext_units),
    "gap_count": len(literature_result.gaps),
    "raw_artifacts": literature_result.raw_artifacts,
    "topic_search_results": literature_result.topic_search_results,
    "accepted_topic_ids": literature_result.accepted_topic_ids,
    "inclusion_path_counts": literature_result.inclusion_path_counts,
    "doi_count": literature_result.doi_count,
    "unpaywall_queried_count": literature_result.unpaywall_queried_count,
    "open_fulltext_count": literature_result.open_fulltext_count,
}
```

- [ ] **Step 5: Modify build script CLI**

In `scripts/build_source_index.py`, add:

```python
parser.add_argument("--openalex-literature", action="store_true", help="Fetch Aedes aegypti literature from OpenAlex, with PubMed and Unpaywall enrichment.")
parser.add_argument("--from-date", default="2020-01-01")
parser.add_argument("--to-date")
parser.add_argument("--work-type", default="article")
parser.add_argument("--include-topic-discovery", action="store_true")
parser.add_argument("--unpaywall-email")
parser.add_argument("--max-works", type=int)
```

Pass these through to `build_source_index`.

- [ ] **Step 6: Run builder and CLI tests**

```bash
python3 -m unittest tests.test_builder tests.test_cli -v
```

Expected result: pass.

- [ ] **Step 7: Commit**

```bash
git add askinsects/builder.py scripts/build_source_index.py tests/test_builder.py tests/test_cli.py
git commit -m "feat: wire Aedes literature source build"
```

## Task 6: Answer Routing, Source Map, Docs, And Completion Gate

**Files:**
- Modify: `askinsects/answer.py`
- Modify: `askinsects/planner.py`
- Modify: `config/source-map.yaml`
- Modify: `README.md`
- Modify: `docs/source-lanes.md`
- Modify: `docs/querying-ask-insects.md`
- Modify: `scripts/verify_complete.py`
- Modify: `tests/test_answer.py`
- Modify: `tests/test_verify_complete.py`

- [ ] **Step 1: Add answer test**

Add a test that builds a tiny literature index and asks:

```python
payload = answer_question("what papers since 2020 discuss Wolbachia and Aedes aegypti?", artifact_dir=self.artifact_dir)
self.assertTrue(payload["ok"])
self.assertEqual(payload["answer_shape"], "literature")
self.assertTrue(payload["evidence"])
self.assertEqual(payload["evidence"][0]["source"], "aedes_literature_openalex")
```

- [ ] **Step 2: Run failing answer test**

```bash
python3 -m unittest tests.test_answer -v
```

Expected result: fail until the fixture in the test builds a literature source and answer language becomes source-neutral enough for the new lane.

- [ ] **Step 3: Update planner and answer language**

In `askinsects/answer.py`, replace mosquito-specific gap text with source-plane wording:

```python
"I do not see enough indexed Ask Insects evidence for this question yet."
```

For literature answers, use:

```python
return f"From the Ask Insects literature index, {records[0].title}: {records[0].text}"
```

- [ ] **Step 4: Update source map**

Add to `config/source-map.yaml`:

```yaml
  - id: aedes_literature_openalex
    name: Aedes aegypti literature since 2020
    source_type: public_api_composite
    boundary: OpenAlex articles where Aedes aegypti is material in title, abstract, or accepted topic metadata from 2020-01-01 through run date
    query_plane: sqlite_atomic_index
    artifact_dir: artifacts/aedes-literature-2020
    artifacts:
      sqlite_index: artifacts/aedes-literature-2020/source_index.sqlite
      sqlite_payload_table: record_payloads
      sqlite_fulltext_table: literature_fulltext_units
      source_status: artifacts/aedes-literature-2020/source_status.json
      source_receipt: artifacts/aedes-literature-2020/source_receipt.json
      gaps: artifacts/aedes-literature-2020/gaps.json
    lanes:
      - literature
    provenance_required: true
    live_fetch: opt_in
    enrichment_sources:
      - pubmed_eutilities
      - unpaywall_api
```

- [ ] **Step 5: Update docs**

Document:

- canonical boundary: title, abstract, or topic
- OpenAlex as canonical source
- PubMed as cross-check enrichment
- Unpaywall as legal full-text resolver
- no Sci-Hub, no private cookies, no institutional scraping
- artifact directory and build commands
- query examples
- structured gaps

- [ ] **Step 6: Update completion verifier**

In `scripts/verify_complete.py`, add required files:

```python
"docs/superpowers/specs/2026-05-23-aedes-aegypti-literature-source-lane-design.md",
"docs/superpowers/plans/2026-05-23-aedes-aegypti-literature-source-lane.md",
"tests/test_literature_source.py",
```

Add `tests.test_literature_source` to `UNIT_TEST_MODULES`.

Add a deterministic literature build check using `--max-works 1`, `--delay-seconds 0`, and fake network hooks only if the build path supports injectable fixtures. If the build script cannot inject fake hooks from the command line, keep live network out of `verify_complete.py` and verify the deterministic unit module plus source-map presence instead.

- [ ] **Step 7: Run docs and verifier tests**

```bash
python3 -m unittest tests.test_answer tests.test_verify_complete -v
python3 scripts/verify_complete.py
```

Expected result: pass.

- [ ] **Step 8: Commit**

```bash
git add askinsects/answer.py askinsects/planner.py config/source-map.yaml README.md docs/source-lanes.md docs/querying-ask-insects.md scripts/verify_complete.py tests/test_answer.py tests/test_verify_complete.py
git commit -m "docs: document Aedes literature source lane"
```

## Task 7: Deterministic Full Verification

**Files:**
- No new files expected. Fix only files implicated by failing tests.

- [ ] **Step 1: Run all deterministic tests**

```bash
python3 -m unittest discover -s tests -v
```

Expected result: all tests pass.

- [ ] **Step 2: Run completion gate**

```bash
python3 scripts/verify_complete.py
```

Expected result: `verify_complete ok`.

- [ ] **Step 3: Inspect source-map registration**

```bash
python3 - <<'PY'
from pathlib import Path
text = Path("config/source-map.yaml").read_text()
assert "aedes_literature_openalex" in text
assert "literature_fulltext_units" in text
print("literature source map ok")
PY
```

Expected result: `literature source map ok`.

- [ ] **Step 4: Commit any verification fixes**

```bash
git status --short
```

If files changed while fixing verification:

```bash
git add askinsects/index.py askinsects/sources/literature.py askinsects/builder.py scripts/build_source_index.py askinsects/answer.py askinsects/planner.py config/source-map.yaml README.md docs/source-lanes.md docs/querying-ask-insects.md scripts/verify_complete.py tests/test_literature_source.py tests/test_builder.py tests/test_cli.py tests/test_index.py tests/test_answer.py tests/test_verify_complete.py
git commit -m "test: verify Aedes literature source lane"
```

## Task 8: Live Source-Grade Ingest Proof

**Files:**
- Runtime artifacts under `artifacts/aedes-literature-2020/`
- No tracked source changes expected unless docs need a receipt update.

- [ ] **Step 1: Run a small live smoke ingest**

```bash
python3 scripts/build_source_index.py \
  --fixtures \
  --openalex-literature \
  --species "Aedes aegypti" \
  --from-date 2020-01-01 \
  --to-date 2026-05-23 \
  --work-type article \
  --include-topic-discovery \
  --page-size 25 \
  --delay-seconds 1 \
  --max-works 25 \
  --artifact-dir artifacts/aedes-literature-2020-smoke
```

Expected result: command returns JSON with `ok: true`, source `aedes_literature_openalex`, at least one literature record, raw OpenAlex artifacts, and structured gaps for any inaccessible full text.

- [ ] **Step 2: Prove smoke query works**

```bash
python3 -m askinsects summary --artifact-dir artifacts/aedes-literature-2020-smoke
python3 -m askinsects sources --artifact-dir artifacts/aedes-literature-2020-smoke
python3 -m askinsects search literature "Aedes aegypti" --artifact-dir artifacts/aedes-literature-2020-smoke
python3 -m askinsects sql "select source, lane, count(*) as n from records group by source, lane" --artifact-dir artifacts/aedes-literature-2020-smoke
```

Expected result: literature rows are visible through the CLI.

- [ ] **Step 3: Run the full live ingest**

Use a real Unpaywall email if available. If no email is configured, run metadata and gap ingest first, then rerun Unpaywall enrichment after an email is supplied.

```bash
python3 scripts/build_source_index.py \
  --fixtures \
  --openalex-literature \
  --species "Aedes aegypti" \
  --from-date 2020-01-01 \
  --to-date 2026-05-23 \
  --work-type article \
  --include-topic-discovery \
  --page-size 200 \
  --delay-seconds 1 \
  --artifact-dir artifacts/aedes-literature-2020
```

Expected result: the receipt proves all OpenAlex cursor pages were fetched and the normalized literature count matches the canonical run count, subject only to explicitly structured gaps.

- [ ] **Step 4: Inspect full ingest receipt**

```bash
python3 - <<'PY'
import json
from pathlib import Path
receipt = json.loads(Path("artifacts/aedes-literature-2020/source_receipt.json").read_text())
status = json.loads(Path("artifacts/aedes-literature-2020/source_status.json").read_text())
print(json.dumps({
    "ok": status.get("ok"),
    "record_count": status.get("record_count"),
    "gap_count": status.get("gap_count"),
    "literature": receipt.get("aedes_literature_openalex") or receipt.get("literature"),
}, indent=2, sort_keys=True))
PY
```

Expected result: status is ok, record count is large enough for the canonical OpenAlex count, and receipt includes topic discovery, PubMed, Unpaywall, raw artifact, and full-text/gap counts.

- [ ] **Step 5: Prove full ingest query works**

```bash
python3 -m askinsects sources --artifact-dir artifacts/aedes-literature-2020
python3 -m askinsects summary --artifact-dir artifacts/aedes-literature-2020
python3 -m askinsects sql "select source, lane, count(*) as n from records group by source, lane" --artifact-dir artifacts/aedes-literature-2020
python3 -m askinsects sql "select reason, count(*) as n from json_each(readfile('artifacts/aedes-literature-2020/gaps.json')) group by reason" --artifact-dir artifacts/aedes-literature-2020
python3 -m askinsects search literature "Wolbachia dengue" --artifact-dir artifacts/aedes-literature-2020
python3 -m askinsects ask "what papers since 2020 discuss Wolbachia and Aedes aegypti?" --artifact-dir artifacts/aedes-literature-2020 --json
```

If the `readfile` SQL helper is unavailable in SQLite, replace the gap query with a Python JSON summary.

Expected result: CLI can list the source, summarize the index, search literature, and answer with provenance.

- [ ] **Step 6: Record live receipt docs if needed**

If the repo tracks source receipt docs, add a concise receipt file under `docs/`, for example:

```text
docs/aedes-aegypti-literature-2020-source.md
```

Include:

- run date
- canonical query
- record count
- full-text count
- gap count by reason
- artifact directory
- verification commands

- [ ] **Step 7: Commit docs only**

Do not commit large generated raw API artifacts unless the repo already tracks them intentionally. Commit source code, tests, docs, and small receipts only.

```bash
git add docs/aedes-aegypti-literature-2020-source.md
git commit -m "docs: receipt Aedes literature live ingest"
```

## Completion Audit

Before calling the goal complete, verify all of these with current-state evidence:

- `config/source-map.yaml` declares `aedes_literature_openalex`.
- `scripts/build_source_index.py` can build the literature lane.
- SQLite contains one `literature` record per canonical OpenAlex article from the approved title, abstract, or topic boundary.
- `record_payloads` contains raw per-paper OpenAlex payloads and enrichment payloads where available.
- `literature_fulltext_units` contains legal open full text where accessible.
- `gaps.json` records missing closed, inaccessible, or unparsable full text.
- `source_status.json` and `source_receipt.json` prove all OpenAlex cursor pages were fetched.
- CLI `sources`, `summary`, `search`, `sql`, and `ask` work against the literature artifact directory.
- `python3 -m unittest discover -s tests -v` passes.
- `python3 scripts/verify_complete.py` passes.
- The final live count is compared against OpenAlex reported count for the run filters.
