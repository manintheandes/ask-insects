# Aedes VectorByte Traits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a source-grade VectorByte VecTraits lane for Aedes aegypti trait observations.

**Architecture:** Add a focused source adapter that searches VBD Hub for Aedes aegypti VecTraits datasets, fetches bounded VectorByte dataset JSON, normalizes each matching row into an `EvidenceRecord`, and installs records through the standard ingest metadata path. Wire the lane into CLI, hosted server, planner/answer routing, docs, coverage, tests, and hosted deploy.

**Tech Stack:** Python standard library HTTP/JSON, existing Ask Insects `EvidenceRecord`, `SourceIndex`, CLI, hosted server, SQLite FTS, `unittest`.

---

### Task 1: Source Adapter Tests

**Files:**
- Create: `tests/test_vectorbyte_traits_source.py`
- Create: `askinsects/sources/vectorbyte_traits.py`

- [ ] Write tests that inject fake VBD Hub search JSON and fake VecTraits dataset JSON.
- [ ] Verify row records include source `aedes_vectorbyte_traits`, lane `traits`, species `Aedes aegypti`, trait name, value, unit, temperature, location, citation, DOI, raw locator, and source URL.
- [ ] Verify rows for another species are skipped.
- [ ] Verify failed dataset fetches become structured gaps.
- [ ] Run `python3 -m unittest tests.test_vectorbyte_traits_source -v` and confirm the tests fail before implementation.
- [ ] Implement the source adapter.
- [ ] Rerun the source tests and confirm they pass.

### Task 2: Ingest Script Tests

**Files:**
- Create: `scripts/ingest_vectorbyte_traits.py`
- Create: `tests/test_ingest_vectorbyte_traits.py`

- [ ] Write an ingest test that builds a temporary index with another source row, runs the VectorByte ingest with fake fetchers, and verifies the other source survives.
- [ ] Write a failed-refresh test that preserves existing `aedes_vectorbyte_traits` rows when no new rows are fetched and gaps exist.
- [ ] Run `python3 -m unittest tests.test_ingest_vectorbyte_traits -v` and confirm failure before implementation.
- [ ] Implement the ingest script with metadata, receipt, and gap updates.
- [ ] Rerun the ingest tests and confirm they pass.

### Task 3: CLI And Hosted Server Wiring

**Files:**
- Modify: `askinsects/cli.py`
- Modify: `askinsects/server.py`
- Modify: `tests/test_cli_hosted.py`
- Modify: `tests/test_server.py`

- [ ] Add `ingest-vectorbyte-traits` with `--hosted`, `--query`, `--dataset-limit`, `--row-limit`, and `--search-limit`.
- [ ] Add hosted endpoint `/ingest/vectorbyte-traits`.
- [ ] Add CLI-hosted and server route tests.
- [ ] Run the targeted CLI/server tests and confirm failure before implementation.
- [ ] Implement local and hosted command forwarding.
- [ ] Rerun targeted tests and confirm they pass.

### Task 4: Ask Routing

**Files:**
- Modify: `askinsects/planner.py`
- Modify: `askinsects/answer.py`
- Modify: `tests/test_answer.py`

- [ ] Add tests proving trait/temperature/fecundity/transmission-potential questions prefer `aedes_vectorbyte_traits`.
- [ ] Run `python3 -m unittest tests.test_answer -v` and confirm failure before implementation.
- [ ] Add `traits` routing and prioritization.
- [ ] Rerun answer tests and confirm they pass.

### Task 5: Source Map, Docs, And Gate

**Files:**
- Modify: `config/source-map.yaml`
- Modify: `config/mosquito-intelligence-coverage.json`
- Modify: `README.md`
- Modify: `docs/source-lanes.md`
- Modify: `docs/querying-ask-insects.md`
- Modify: `scripts/verify_complete.py`
- Modify: `/Users/josh/.codex/skills/askinsects/SKILL.md`

- [ ] Declare `aedes_vectorbyte_traits` in the source map and coverage ledger.
- [ ] Document boundary, query examples, hosted ingest command, and provenance grain.
- [ ] Add verify-complete checks for adapter, ingest script, tests, source map, docs, and routed terms.
- [ ] Run `python3 scripts/verify_complete.py` and fix any failures.

### Task 6: Ingest, Deploy, Verify, Commit

**Files:**
- Local artifact: `artifacts/mosquito-v1/source_index.sqlite`
- Hosted artifact: `/home/josh/ask-insects/artifacts/mosquito-v1/source_index.sqlite`

- [ ] Run local ingest with a bounded pull.
- [ ] Verify local SQL count and local answer proof.
- [ ] Run the full test suite.
- [ ] Deploy to the hosted VM.
- [ ] Run hosted ingest.
- [ ] Verify hosted health, hosted SQL count, and hosted answer proof.
- [ ] Commit source changes only, leave `demo-recordings/` untracked.
- [ ] Push `main`.
