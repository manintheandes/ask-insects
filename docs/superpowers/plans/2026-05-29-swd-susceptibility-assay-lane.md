# SWD Susceptibility Assay Lane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a source-grade Drosophila suzukii susceptibility/resistance evidence lane that answers insecticide susceptibility questions from pest-control evidence instead of generic resistance-gene records.

**Architecture:** Mirror the Aedes resistance-table promotion pattern, but keep SWD honesty explicit: promote parsed supplement table rows when present, promote structured candidate susceptibility facts for broad questions, and install a queryable table-row gap when no parsed SWD susceptibility table passes validation. Wire the new source into Ask routing, source map, coverage docs, receipts, and tests.

**Tech Stack:** Python, SQLite source index, Ask Insects EvidenceRecord payloads, unittest, repo-local ingest scripts.

---

### Task 1: Source Module And Tests

**Files:**
- Create: `askinsects/sources/drosophila_suzukii_susceptibility_assay_rows.py`
- Create: `tests/test_drosophila_suzukii_susceptibility_assay_rows.py`

- [ ] **Step 1: Write failing tests**

Test that parsed SWD supplement table rows become `resistance` records with table provenance, and that candidate extracted facts with insecticide plus assay or response fields become broad susceptibility evidence records. Test that an empty source index still produces a queryable `source_gap`.

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m unittest tests.test_drosophila_suzukii_susceptibility_assay_rows -v`

- [ ] **Step 3: Implement source module**

Read from `drosophila_suzukii_extracted_facts` resistance records. Promote `confidence=parsed` table rows when schema fields exist. Promote bounded `confidence=candidate` records when they include insecticide terms and an assay or response metric. Emit an explicit gap record for missing parsed susceptibility table rows.

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m unittest tests.test_drosophila_suzukii_susceptibility_assay_rows -v`

### Task 2: Ingest Script And Metadata

**Files:**
- Create: `scripts/ingest_drosophila_suzukii_susceptibility_assay_rows.py`
- Create: `tests/test_ingest_drosophila_suzukii_susceptibility_assay_rows.py`

- [ ] **Step 1: Write failing ingest test**

Test that ingest replaces only the new source, preserves unrelated records, writes `source_status.json`, `source_receipt.json`, and deduplicates this source's gaps in `gaps.json`.

- [ ] **Step 2: Implement ingest script**

Follow the existing `scripts/ingest_resistance_table_rows.py` shape with the SWD source id and method text.

- [ ] **Step 3: Run ingest tests**

Run: `python3 -m unittest tests.test_ingest_drosophila_suzukii_susceptibility_assay_rows -v`

### Task 3: Ask Routing

**Files:**
- Modify: `askinsects/answer.py`
- Add tests in an existing answer test file or a focused new test if needed.

- [ ] **Step 1: Write failing answer test**

Ask: `what insecticide susceptibility or resistance evidence do we have for Drosophila suzukii?` Expect a SWD susceptibility evidence source ahead of genome-file gene records.

- [ ] **Step 2: Implement routing**

Add the new source id, fetch it for resistance-shaped questions, and rank it above gene/protein resistance hits when the question is about SWD insecticides, bioassays, mortality, LC50, or susceptibility.

- [ ] **Step 3: Run focused answer test**

Run the focused answer test plus the new source and ingest tests.

### Task 4: Source Map, Docs, Ingest, Ship

**Files:**
- Modify: `config/source-map.yaml`
- Modify: `README.md`
- Modify: `docs/source-lanes.md`
- Modify coverage rows if needed in `askinsects/sources/drosophila_suzukii.py`
- Modify: `scripts/verify_complete.py` if source-map validation requires the new lane.

- [ ] **Step 1: Add source-map entry**

Declare source id `drosophila_suzukii_susceptibility_assay_rows`, input source `drosophila_suzukii_extracted_facts`, lanes `resistance`, and validation status `parsed_or_candidate_not_human_validated`.

- [ ] **Step 2: Update docs and coverage language**

Say broad susceptibility evidence is now queryable, while fully human-validated assay tables remain follow-on work if no parsed table rows pass.

- [ ] **Step 3: Ingest locally and verify**

Run the new ingest script, focused tests, `python3 scripts/verify_complete.py`, and a real Ask query.

- [ ] **Step 4: Commit, push, deploy, hosted ingest, and hosted proof**

Use the repo ship path: commit, push `origin/main`, deploy to the Ask Insects VM, ingest the new lane hosted, and prove with hosted SQL plus the human Ask query.
