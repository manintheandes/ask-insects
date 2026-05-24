# Aedes Extracted Facts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Wave 1 option 2: deterministic supplement discovery and extracted fact records across all priority Aedes lanes.

**Architecture:** Add one reusable `aedes_extracted_facts` source module that reads the existing SQLite source plane, discovers supplement candidates from paper identifiers and payload metadata, and emits structured `EvidenceRecord` payloads into existing lanes. Keep extraction deterministic and provenance-backed, with confidence labels that distinguish manifest, candidate, and parsed records.

**Tech Stack:** Python standard library, SQLite through `SourceIndex`, existing `EvidenceRecord` and `Provenance` models, `unittest`.

---

### Task 1: Source Tests

**Files:**
- Create: `tests/test_extracted_facts_source.py`
- Create: `askinsects/sources/extracted_facts.py`

- [x] Write failing tests that create a temporary source index with one Aedes literature paper, record payload identifiers, and legal full-text units covering vector competence, resistance, behavior, ecology, and public-health snippets.
- [x] Verify the tests fail because `askinsects.sources.extracted_facts` does not exist.
- [x] Implement the minimal source builder that emits `aedes_extracted_facts` records with payload fields, confidence labels, and provenance locators.
- [x] Verify the source tests pass.

### Task 2: Ingest Tests

**Files:**
- Create: `tests/test_ingest_extracted_facts.py`
- Create: `scripts/ingest_extracted_facts.py`

- [x] Write a failing ingest test that proves the source installs records without deleting an unrelated fixture source.
- [x] Verify the test fails because `scripts.ingest_extracted_facts` does not exist.
- [x] Implement local ingest with status, receipt, source counts, and gap updates.
- [x] Verify the ingest test passes.

### Task 3: CLI And Hosted Route Tests

**Files:**
- Modify: `tests/test_cli_hosted.py`
- Modify: `tests/test_server.py`
- Modify: `askinsects/cli.py`
- Modify: `askinsects/server.py`

- [x] Write failing tests for `python3 -m askinsects ingest-extracted-facts --hosted` and `POST /ingest/extracted-facts`.
- [x] Verify the tests fail because the command and route do not exist.
- [x] Add local and hosted CLI wiring.
- [x] Add an additive hosted server route that preserves unrelated existing server edits.
- [x] Verify CLI and server tests pass.

### Task 4: Docs And Coverage

**Files:**
- Modify: `README.md`
- Modify: `docs/source-lanes.md`
- Modify: `docs/querying-ask-insects.md`
- Modify: `config/source-map.yaml`
- Modify: `config/mosquito-intelligence-coverage.json`

- [x] Document `aedes_extracted_facts` as the Wave 1 cross-lane extraction spine.
- [x] Mark supplement and table extraction as partially covered, with validation and deeper binary parsing still listed as gaps.
- [x] Verify source-map and coverage tests pass.

### Task 5: Verification And Commit

**Files:**
- All changed files from Tasks 1 through 4

- [x] Run focused unit tests for the new source, ingest, CLI, and server route.
- [x] Run `python3 -m unittest discover -s tests -v`.
- [x] Run `python3 scripts/verify_complete.py`.
- [ ] Stage only intended files, leaving local Obsidian and other-agent changes intact.
- [ ] Commit with message `feat: add Aedes extracted facts lane`.
