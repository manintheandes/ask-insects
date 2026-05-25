# Aedes Resistance Table Rows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a source-grade `aedes_resistance_table_rows` lane that promotes parsed resistance supplement rows into queryable Ask Insects records.

**Architecture:** Reuse the vector-competence parsed-table promotion pattern. Keep table-row promotion in a dedicated source module, expose it through a small ingest script, wire CLI/server hosted routes, then update source-map, docs, coverage, and answer ranking.

**Tech Stack:** Python stdlib, SQLite, existing `SourceIndex`, `EvidenceRecord`, and Ask Insects CLI/server.

---

### Task 1: Source Parser

**Files:**
- Create: `askinsects/sources/resistance_table_rows.py`
- Test: `tests/test_resistance_table_rows_source.py`

- [x] Write a failing test for promoting one parsed `aedes_extracted_facts` resistance table row.
- [x] Implement parser logic that validates parsed rows, extracts insecticide, marker, assay, and metric fields, and preserves provenance.
- [x] Write a gap record when no promotable rows exist.
- [x] Run the focused source tests.

### Task 2: Ingest, CLI, and Server

**Files:**
- Create: `scripts/ingest_resistance_table_rows.py`
- Modify: `askinsects/cli.py`
- Modify: `askinsects/server.py`
- Test: `tests/test_ingest_resistance_table_rows.py`
- Test: `tests/test_cli_hosted.py`
- Test: `tests/test_server.py`

- [x] Write failing tests for local ingest, hosted CLI forwarding, and hosted server dispatch.
- [x] Implement source replacement and metadata updates.
- [x] Add `ingest-resistance-table-rows` local and hosted CLI commands.
- [x] Add `/ingest/resistance-table-rows` server dispatch.
- [x] Run focused route tests.

### Task 3: Answer and Source Contract

**Files:**
- Modify: `askinsects/planner.py`
- Modify: `askinsects/answer.py`
- Modify: `config/source-map.yaml`
- Modify: `config/mosquito-intelligence-coverage.json`
- Modify: `README.md`
- Modify: `docs/source-lanes.md`
- Modify: `docs/querying-ask-insects.md`
- Modify: `scripts/verify_complete.py`

- [x] Add planner and answer tests for parsed resistance table questions.
- [x] Prefer schema-validated table rows for table/frequency resistance questions.
- [x] Declare the lane in the source map and coverage ledger.
- [x] Document local and hosted query commands.
- [x] Add the lane to completion verification.

### Task 4: Verification and Shipping

**Files:**
- Whole repo

- [ ] Run focused tests.
- [ ] Run `python3 scripts/verify_complete.py`.
- [ ] Run full unit tests.
- [ ] Ingest locally and prove SQL plus answer behavior.
- [ ] Commit and push to `origin/main`.
- [ ] Deploy the app and run hosted ingest.
- [ ] Prove hosted health, SQL counts, and a hosted answer with provenance.
