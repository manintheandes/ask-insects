# Mosquito Repellent Literature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, ship, ingest, and verify a source-grade mosquito repellent literature lane for articles from 2020 onward.

**Architecture:** Add a focused source adapter that fetches bounded PubMed and Crossref public metadata, saves raw JSON, filters to mosquito repellent scope, deduplicates article candidates, compares them with existing literature rows, and emits one queryable record per candidate. Wire the lane through ingest, CLI, hosted server, source map, coverage ledger, docs, answer routing, skills, and verification.

**Tech Stack:** Python standard library, SQLite `SourceIndex`, PubMed E-utilities, Crossref REST API, unittest.

---

### Task 1: Source Adapter

**Files:**
- Create: `askinsects/sources/mosquito_repellent_literature.py`
- Create: `tests/test_mosquito_repellent_literature_source.py`

- [x] Write tests for PubMed parsing, Crossref parsing, deduplication, raw locators, coverage status, counts, and structured gaps.
- [x] Implement the source adapter with bounded PubMed and Crossref fetches and saved raw artifacts.
- [x] Run the source tests and verify they pass.

### Task 2: Ingest

**Files:**
- Create: `scripts/ingest_mosquito_repellent_literature.py`
- Create: `tests/test_ingest_mosquito_repellent_literature.py`

- [x] Write tests proving the ingest preserves non-repellent literature rows and preserves existing repellent rows on failed refresh.
- [x] Implement metadata, receipt, gap, and source replacement behavior.
- [x] Run the ingest tests and verify they pass.

### Task 3: Ask Surface

**Files:**
- Modify: `askinsects/cli.py`
- Modify: `askinsects/server.py`
- Modify: `askinsects/answer.py`
- Modify: `tests/test_cli_hosted.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_answer.py`

- [x] Add CLI and hosted endpoint tests for `ingest-mosquito-repellent-literature`.
- [x] Add answer-routing tests for repellent-literature questions.
- [x] Implement CLI, hosted route, and answer preference.
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
- [x] Run local ingest against live PubMed/Crossref with a bounded cap.
- [x] Run focused tests, full tests, and `scripts/verify_complete.py`.
- [ ] Commit, push, deploy, hosted-ingest, and hosted-verify.
