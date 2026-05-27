# Aedes Supplement Discovery Gap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand Ask Insects supplement discovery so the Aedes paper corpus is audited through metadata, repository, landing-page, and full-text routes instead of accepting the current shallow 66-manifest frontier.

**Architecture:** Keep the existing `aedes_extracted_facts` source as the single supplement audit lane. Add deterministic discovery adapters inside `askinsects/sources/extracted_facts.py` for Crossref/DataCite relation metadata, Unpaywall OA locations, article landing-page link extraction, and indexed full-text/link hints. Preserve every discovered file as a normal supplement manifest, and keep every non-success as an audit/gap reason in the same source plane.

**Tech Stack:** Python standard library, SQLite source index, existing Ask Insects CLI/server/deploy path, `unittest`.

---

### Task 1: Add Deep Metadata Discovery Tests

**Files:**
- Modify: `tests/test_extracted_facts_source.py`
- Modify: `askinsects/sources/extracted_facts.py`

- [x] **Step 1: Write failing tests**

Add tests that call `fetch_public_supplement_metadata()` with fake JSON/HTML fetchers and assert:

```python
def test_fetch_public_supplement_metadata_discovers_crossref_relations(self):
    ...

def test_fetch_public_supplement_metadata_discovers_unpaywall_oa_locations(self):
    ...

def test_fetch_public_supplement_metadata_discovers_landing_page_links(self):
    ...
```

- [x] **Step 2: Run tests to verify failure**

Run:

```bash
python3 -m unittest tests.test_extracted_facts_source.ExtractedFactsSourceTests.test_fetch_public_supplement_metadata_discovers_crossref_relations tests.test_extracted_facts_source.ExtractedFactsSourceTests.test_fetch_public_supplement_metadata_discovers_unpaywall_oa_locations tests.test_extracted_facts_source.ExtractedFactsSourceTests.test_fetch_public_supplement_metadata_discovers_landing_page_links
```

Expected: fails because the new routes are not implemented yet.

- [x] **Step 3: Implement minimal route support**

In `askinsects/sources/extracted_facts.py`, extend `fetch_public_supplement_metadata()` to aggregate:

```text
Crossref relation URLs from message.relation
DataCite relatedIdentifiers for dataset/supplement URLs
Unpaywall best/open OA locations and PDF/landing URLs
HTML article landing pages with supplemental-material-looking links
```

- [x] **Step 4: Run tests to verify pass**

Run the same three tests and then:

```bash
python3 -m unittest tests.test_extracted_facts_source
```

### Task 2: Add Full-Text Link Mining Tests

**Files:**
- Modify: `tests/test_extracted_facts_source.py`
- Modify: `askinsects/sources/extracted_facts.py`

- [x] **Step 1: Write failing test**

Add a test where an indexed legal full-text unit contains supplementary file URLs and verify `build_extracted_fact_records(... discover_supplements=True ...)` emits supplement manifests without needing external metadata.

- [x] **Step 2: Run test to verify failure**

Run:

```bash
python3 -m unittest tests.test_extracted_facts_source.ExtractedFactsSourceTests.test_build_extracted_fact_records_discovers_supplements_from_fulltext_links
```

Expected: fails because full-text URLs are not mined into supplement candidates yet.

- [x] **Step 3: Implement text mining**

Add a helper that extracts supported supplement-looking URLs from paper text/full-text units and adds them through the same dedupe path with source `fulltext_link_mining`.

- [x] **Step 4: Run tests**

Run:

```bash
python3 -m unittest tests.test_extracted_facts_source tests.test_ingest_extracted_facts
```

### Task 3: Receipt, Docs, and Hosted Answer Proof

**Files:**
- Modify: `scripts/ingest_extracted_facts.py`
- Modify: `README.md`
- Modify: `docs/querying-ask-insects.md`
- Modify: `config/source-map.yaml`
- Modify: `config/mosquito-intelligence-coverage.json`
- Modify: `askinsects/answer.py` if summary wording needs new fields

- [x] **Step 1: Add receipt fields**

Record discovery route counts if present, for example:

```json
{
  "supplement_discovery_route_counts": {
    "crossref": 12,
    "datacite": 4,
    "unpaywall": 6,
    "landing_page": 20,
    "fulltext_link_mining": 8
  }
}
```

- [x] **Step 2: Update docs**

Document that `no_supplement_metadata_found` means no supplement found across the configured discovery routes, not proof of no supplement existing.

- [x] **Step 3: Run local gates**

Run:

```bash
python3 -m unittest tests.test_extracted_facts_source tests.test_ingest_extracted_facts tests.test_answer
git diff --check
```

### Task 4: Hosted Refresh and Ship

**Files:**
- Runtime only unless deployment script changes are needed.

- [ ] **Step 1: Deploy code to hosted VM**

Run the repo deploy command with the configured hosted token.

- [ ] **Step 2: Run hosted supplement refresh**

Run hosted `ingest-extracted-facts` with:

```bash
--discover-supplements
--download-supplements
--max-supplement-discovery-records 20000
--max-repository-supplement-discovery-records 20000
--max-supplement-files 10000
--max-supplement-bytes 20000000
```

- [ ] **Step 3: Promote structured rows**

Run hosted vector-competence and resistance table-row promotions after extracted facts refresh.

- [ ] **Step 4: Verify live behavior**

Run hosted SQL and ask:

```bash
ask-insects sql --hosted "select count(*) from records where source='aedes_extracted_facts' and title='Aedes aegypti supplement audit'"
ask-insects ask --hosted --json "Show Aedes aegypti supplement audit coverage status. Include discovery route counts."
```

- [ ] **Step 5: Ship**

Commit, push, open/merge PR, deploy current `origin/main`, refresh `/Users/josh/.local/share/ask-insects/main`, verify hosted CLI behavior, and report exact counts.

---

Self-review:

- Spec coverage: plan covers discovery routes, parsing, promotion, receipts, hosted verification, and ship.
- Placeholder scan: no `TBD` or unresolved implementation placeholders.
- Type consistency: route count names are represented as dictionary fields on the extracted facts result and receipt.
