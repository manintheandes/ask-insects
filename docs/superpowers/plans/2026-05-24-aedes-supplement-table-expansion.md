# Aedes Supplement Table Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `aedes_extracted_facts` with opt-in Europe PMC / PMC supplement discovery and deterministic row-level parsing for supported table files.

**Architecture:** Keep the existing source id and ingest path. Add injectable supplement metadata fetchers and file fetchers, normalize all supplement candidates through the existing manifest path, parse supported local files into `TextCandidate`-compatible row records, and emit parsed fact records with raw-file provenance and `confidence="parsed"`.

**Tech Stack:** Python standard library, SQLite, CSV, XML, HTML parser, ZIP-based XLSX parsing, existing `EvidenceRecord` and `Provenance` models, `unittest`.

---

### Task 1: Discovery And Parser Tests

**Files:**
- Modify: `tests/test_extracted_facts_source.py`
- Modify: `askinsects/sources/extracted_facts.py`

- [x] Write failing tests for injectable Europe PMC and PMC metadata discovery.
- [x] Write failing tests for CSV, TSV, XLSX, XML, and HTML table rows becoming parsed records.
- [x] Verify the tests fail for missing APIs and missing parsed row records.
- [x] Implement minimal discovery, raw download, supported parsers, and parsed record emission.
- [x] Verify source tests pass.

### Task 2: Ingest And CLI Wiring

**Files:**
- Modify: `tests/test_ingest_extracted_facts.py`
- Modify: `tests/test_cli_hosted.py`
- Modify: `scripts/ingest_extracted_facts.py`
- Modify: `askinsects/cli.py`
- Modify: `askinsects/server.py`

- [x] Write failing tests for opt-in `--discover-supplements`, `--download-supplements`, `--max-supplement-files`, and `--max-supplement-bytes`.
- [x] Implement local ingest controls and metadata receipt fields.
- [x] Wire hosted payload options without changing default hosted behavior.
- [x] Verify ingest and CLI tests pass.

### Task 3: Docs And Coverage

**Files:**
- Modify: `README.md`
- Modify: `docs/source-lanes.md`
- Modify: `docs/querying-ask-insects.md`
- Modify: `config/source-map.yaml`
- Modify: `config/mosquito-intelligence-coverage.json`

- [x] Document supplement discovery and supported parse formats.
- [x] Mark row-level parsed facts as partial coverage, with validation and broader supplement parsing as remaining gaps.
- [x] Verify coverage tests pass.

### Task 4: Verification And Commit

**Files:**
- All changed files from Tasks 1 through 3

- [x] Run focused tests for extracted facts, ingest, CLI, server, answer, and coverage.
- [x] Run `python3 -m unittest discover -s tests -v`.
- [x] Run `python3 scripts/verify_complete.py`.
- [ ] Stage intended files only.
- [ ] Commit with message `feat: parse Aedes supplement tables`.
- [ ] Push `main`.
