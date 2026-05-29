# Drosophila Suzukii Source Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a source-grade spotted wing drosophila (`Drosophila suzukii`) core boundary to Ask Insects.

**Architecture:** Add one composite source id, `drosophila_suzukii_core`, that reuses existing GBIF, iNaturalist, OpenAlex, and BOLD parsers, then retargets records into a species-specific source so existing Aedes rows are not overwritten. Wire the source through a local CLI ingest, source map, docs, and deterministic tests.

**Tech Stack:** Python standard library, existing Ask Insects `EvidenceRecord` and SQLite `SourceIndex`, existing public-source parser modules, `unittest`.

---

### Task 1: Composite Source Module

**Files:**
- Create: `askinsects/sources/drosophila_suzukii.py`
- Test: `tests/test_drosophila_suzukii_source.py`

- [x] Write fake-source tests covering GBIF, iNaturalist, OpenAlex, BOLD, source coverage, and SQLite search.
- [x] Add `fetch_drosophila_suzukii_records`.
- [x] Retarget upstream rows to source id `drosophila_suzukii_core`.
- [x] Emit explicit source-coverage records for deeper missing domains.

### Task 2: Incremental Ingest Script And CLI

**Files:**
- Create: `scripts/ingest_drosophila_suzukii.py`
- Modify: `askinsects/cli.py`
- Test: `tests/test_ingest_drosophila_suzukii.py`

- [x] Add an ingest script that replaces only `drosophila_suzukii_core`.
- [x] Update status, receipt, source counts, and gaps.
- [x] Add `python3 -m askinsects ingest-drosophila-suzukii`.
- [x] Test that existing fixture rows survive the ingest.

### Task 3: Source Map And Docs

**Files:**
- Modify: `config/source-map.yaml`
- Modify: `README.md`
- Modify: `docs/source-lanes.md`
- Modify: `docs/querying-ask-insects.md`

- [x] Declare the new source boundary and upstream sources.
- [x] Document how to ingest and query spotted wing drosophila.
- [x] State plainly that deeper Aedes-style lanes are still source gaps.

### Task 4: Verification

**Files:**
- Modify if needed based on test output.

- [x] Run focused tests for the new source.
- [x] Run `python3 scripts/verify_complete.py`.
- [x] Run a bounded live ingest.
- [x] Query the installed records for `Drosophila suzukii`.
