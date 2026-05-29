# SWD Biocontrol Outcome Lane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a source-grade Drosophila suzukii biocontrol outcome evidence lane so parasitoid and natural-enemy questions answer from dedicated outcome rows instead of loose literature matches.

**Architecture:** Promote SWD `drosophila_suzukii_extracted_facts` biocontrol records into a dedicated derived SQLite source. Preserve source paper ID, extracted-fact ID, exact locator, agent, target stage, assay, effect metrics, and numeric values where available, while keeping human validation and parsed biocontrol supplement tables explicit as remaining gaps.

**Tech Stack:** Python, SQLite source index, Ask Insects EvidenceRecord payloads, unittest, repo-local ingest scripts.

---

### Task 1: Source Module And Tests

**Files:**
- Create: `askinsects/sources/drosophila_suzukii_biocontrol_outcome_rows.py`
- Create: `tests/test_drosophila_suzukii_biocontrol_outcome_rows.py`

- [ ] **Step 1: Write failing tests**

Test that candidate SWD biocontrol extracted facts with an agent plus outcome context become `biocontrol` records with provenance preserved. Test that an empty index produces a queryable source-gap record.

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m unittest tests.test_drosophila_suzukii_biocontrol_outcome_rows -v`

- [ ] **Step 3: Implement source module**

Read `drosophila_suzukii_extracted_facts` records where `lane='biocontrol'` and `fact_type='biocontrol'`. Promote candidate records when they include a biological-control agent plus an effect metric, assay, target stage, percent value, or temperature value. Emit a gap if no promotable rows exist, and emit a second gap when no parsed biocontrol supplement table rows exist.

- [ ] **Step 4: Run source tests**

Run: `python3 -m unittest tests.test_drosophila_suzukii_biocontrol_outcome_rows -v`

### Task 2: Ingest Script And Metadata

**Files:**
- Create: `scripts/ingest_drosophila_suzukii_biocontrol_outcome_rows.py`
- Create: `tests/test_ingest_drosophila_suzukii_biocontrol_outcome_rows.py`

- [ ] **Step 1: Write failing ingest test**

Test that ingest replaces only `drosophila_suzukii_biocontrol_outcome_rows`, preserves unrelated records, updates source status and receipt metadata, and deduplicates this source's gaps.

- [ ] **Step 2: Implement ingest script**

Follow the SWD susceptibility ingest shape with the biocontrol source id and method text.

- [ ] **Step 3: Run ingest tests**

Run: `python3 -m unittest tests.test_ingest_drosophila_suzukii_biocontrol_outcome_rows -v`

### Task 3: Ask Routing

**Files:**
- Modify: `askinsects/answer.py`
- Modify: `tests/test_answer.py`

- [ ] **Step 1: Write failing answer tests**

Ask `show Drosophila suzukii parasitoid biocontrol outcomes`. Expect `drosophila_suzukii_biocontrol_outcome_rows` ahead of generic extracted facts. Also verify fallback to `drosophila_suzukii_extracted_facts` when the dedicated lane is absent.

- [ ] **Step 2: Implement routing**

Import the new source id, preload it for SWD `answer_shape='biocontrol'`, and rank it before generic literature or extracted-fact biocontrol rows.

- [ ] **Step 3: Run focused answer tests**

Run the focused answer tests plus the source and ingest tests.

### Task 4: Source Map, Docs, Ingest, Ship

**Files:**
- Modify: `config/source-map.yaml`
- Modify: `README.md`
- Modify: `docs/source-lanes.md`
- Modify: `docs/querying-ask-insects.md`
- Modify: `askinsects/sources/drosophila_suzukii.py`
- Modify: `askinsects/cli.py`
- Modify: `askinsects/server.py`
- Modify: `scripts/verify_complete.py`

- [ ] **Step 1: Add source-map entry**

Declare `drosophila_suzukii_biocontrol_outcome_rows` as a derived source from `drosophila_suzukii_extracted_facts` into the `biocontrol` lane.

- [ ] **Step 2: Update docs and coverage language**

Say candidate biocontrol outcome evidence is now queryable, while human-validated outcome tables remain follow-on work.

- [ ] **Step 3: Ingest locally and verify**

Run the new ingest command, focused tests, `python3 scripts/verify_complete.py`, and a real Ask query.

- [ ] **Step 4: Commit, push, deploy, hosted ingest, and hosted proof**

Commit, push `origin/main`, deploy to the Ask Insects VM, ingest the new lane hosted, and prove with hosted SQL plus a hosted Ask query.
