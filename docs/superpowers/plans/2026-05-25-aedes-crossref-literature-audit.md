# Aedes Crossref Literature Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a source-grade Crossref audit lane for `Aedes aegypti` literature since 2020.

**Architecture:** Add a focused Crossref source adapter that fetches bounded `/works` pages, saves raw JSON, filters material Aedes candidates, compares them with existing literature rows, and emits one audit record per Crossref work. Wire the lane through ingest, CLI, hosted server, source map, coverage ledger, docs, answer routing, and verification.

**Tech Stack:** Python standard library, SQLite `SourceIndex`, Crossref REST API, unittest.

---

### Task 1: Source Adapter

**Files:**
- Create: `askinsects/sources/aedes_crossref_literature_audit.py`
- Create: `tests/test_aedes_crossref_literature_audit_source.py`

- [x] Write tests for Crossref page parsing, material Aedes filtering, DOI/title matching, raw locators, counts, and structured gaps.
- [x] Run the source tests and verify they fail because the module is missing.
- [x] Implement the source adapter with bounded cursor pagination and saved raw artifacts.
- [x] Run the source tests and verify they pass.

### Task 2: Ingest

**Files:**
- Create: `scripts/ingest_aedes_crossref_literature_audit.py`
- Create: `tests/test_ingest_aedes_crossref_literature_audit.py`

- [x] Write tests proving the ingest preserves non-Crossref literature rows and preserves existing Crossref rows on failed refresh.
- [x] Run the ingest tests and verify they fail because the ingest module is missing.
- [x] Implement metadata, receipt, gap, and source replacement behavior.
- [x] Run the ingest tests and verify they pass.

### Task 3: Ask Surface

**Files:**
- Modify: `askinsects/cli.py`
- Modify: `askinsects/server.py`
- Modify: `askinsects/answer.py`
- Modify: `askinsects/planner.py`
- Modify: `tests/test_cli_hosted.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_answer.py`

- [x] Add CLI and hosted endpoint tests for `ingest-crossref-literature-audit`.
- [x] Add answer-routing tests for Crossref literature audit questions.
- [x] Implement CLI, hosted route, planner, and answer preference.
- [x] Run focused ask-surface tests and verify they pass.

### Task 4: Source Contract and Docs

**Files:**
- Modify: `config/source-map.yaml`
- Modify: `config/mosquito-intelligence-coverage.json`
- Modify: `README.md`
- Modify: `docs/source-lanes.md`
- Modify: `docs/querying-ask-insects.md`
- Modify: `scripts/verify_complete.py`
- Modify: `/Users/josh/.codex/skills/insectsource/SKILL.md`
- Modify: `/Users/josh/.codex/skills/askinsects/SKILL.md`

- [x] Declare source map, coverage ledger, docs, and skill guidance.
- [x] Extend `verify_complete.py` to enforce the new lane.
- [ ] Run local ingest against live Crossref with a bounded cap.
- [ ] Run focused tests, full tests, and `scripts/verify_complete.py`.
- [ ] Commit, push, deploy, hosted-ingest, and hosted-verify.
