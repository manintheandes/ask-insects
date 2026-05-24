# Aedes VectorBase Genomics Lane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a VectorBase/VEuPathDB `Aedes aegypti` genomics source lane that indexes official GFF, protein FASTA, and GO GAF downloads into Ask Insects with provenance.

**Architecture:** Create a focused `askinsects/sources/vectorbase_genomics.py` parser/downloader, a local ingest script, and a hosted server route. Reuse the existing SQLite source pattern and existing genomics answer routing, with a small prioritizer tweak for VectorBase-specific questions.

**Tech Stack:** Python standard library, Ask Insects `EvidenceRecord`, `SourceIndex`, existing CLI/server ingest patterns, `unittest`.

---

### Task 1: Source Parser

**Files:**
- Create: `askinsects/sources/vectorbase_genomics.py`
- Test: `tests/test_vectorbase_genomics_source.py`

- [ ] **Step 1: Write failing parser tests**

Run:

```bash
python3 -m unittest tests.test_vectorbase_genomics_source -v
```

Expected: fail because `askinsects.sources.vectorbase_genomics` does not exist.

- [ ] **Step 2: Implement parser**

Parse local or downloaded GFF, annotated protein FASTA, and GO GAF files into `genes`, `transcripts`, `proteins`, and `genome_features`.

- [ ] **Step 3: Verify parser tests**

Run:

```bash
python3 -m unittest tests.test_vectorbase_genomics_source -v
```

Expected: pass.

### Task 2: Ingest Surfaces

**Files:**
- Create: `scripts/ingest_vectorbase_genomics.py`
- Modify: `askinsects/cli.py`
- Modify: `askinsects/server.py`
- Test: `tests/test_ingest_vectorbase_genomics.py`
- Test: `tests/test_cli_hosted.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Write failing ingest, CLI, and server tests**

Run:

```bash
python3 -m unittest tests.test_ingest_vectorbase_genomics tests.test_cli_hosted tests.test_server -v
```

Expected: fail because the ingest command and server route do not exist.

- [ ] **Step 2: Implement local and hosted ingest**

Add `ingest-vectorbase-genomics` and `POST /ingest/vectorbase-genomics`, preserving existing artifact rows and updating receipts.

- [ ] **Step 3: Verify ingest tests**

Run:

```bash
python3 -m unittest tests.test_ingest_vectorbase_genomics tests.test_cli_hosted tests.test_server -v
```

Expected: pass.

### Task 3: Docs, Coverage, And Gate

**Files:**
- Modify: `README.md`
- Modify: `docs/source-lanes.md`
- Modify: `docs/querying-ask-insects.md`
- Modify: `config/source-map.yaml`
- Modify: `config/mosquito-intelligence-coverage.json`
- Modify: `scripts/verify_complete.py`
- Modify: `/Users/josh/.codex/skills/askinsects/SKILL.md`

- [ ] **Step 1: Document the source boundary**

Add `vectorbase_aedes_genomics` to the source map, coverage ledger, docs, and skill summary.

- [ ] **Step 2: Add completion-gate checks**

Require the source file, ingest script, tests, source-map terms, and coverage terms in `scripts/verify_complete.py`.

- [ ] **Step 3: Verify the gate**

Run:

```bash
python3 scripts/verify_complete.py
```

Expected: pass.

### Task 4: Hosted Install And Final Verification

**Files:**
- Runtime artifact: hosted Ask Insects `mosquito-v1`

- [ ] **Step 1: Deploy server**

Run the repo deploy script already used for Ask Insects.

- [ ] **Step 2: Hosted ingest**

Run:

```bash
python3 -m askinsects ingest-vectorbase-genomics --hosted
```

- [ ] **Step 3: Hosted query proof**

Run:

```bash
python3 -m askinsects ask --hosted "show VectorBase gene annotation for Aedes aegypti odorant receptor" --json
```

Expected: answer evidence includes `vectorbase_aedes_genomics`.
