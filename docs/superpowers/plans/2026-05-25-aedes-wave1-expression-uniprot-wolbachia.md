# Aedes Wave 1 Expression, UniProt, And Wolbachia Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Install three source-grade Aedes lanes: expression omics, UniProt proteins, and Wolbachia intervention evidence.

**Architecture:** Reuse the existing `EvidenceRecord`, `SourceIndex.replace_source_records`, local ingest script, hosted server route, CLI command, docs, source-map, and verification-gate pattern.

---

### Task 1: Expression Omics Lane

**Files:**
- `askinsects/sources/expression_omics.py`
- `scripts/ingest_expression_omics.py`
- `tests/test_expression_omics_source.py`

- [ ] Add bounded NCBI GEO/SRA E-utilities fetches.
- [ ] Save raw search and summary JSON under `raw/expression_omics/`.
- [ ] Emit GEO dataset and SRA run records in the `expression` lane.
- [ ] Record empty-result and fetch-failure gaps.

### Task 2: UniProt Protein Lane

**Files:**
- `askinsects/sources/uniprot_proteins.py`
- `scripts/ingest_uniprot_proteins.py`
- `tests/test_uniprot_proteins_source.py`

- [ ] Add bounded UniProtKB and proteome REST fetches for taxonomy `7159`.
- [ ] Save raw JSON under `raw/uniprot_proteins/`.
- [ ] Emit protein and proteome records in the `proteins` lane.
- [ ] Preserve accession, reviewed status, gene names, function text, GO and VectorBase cross-references, and proteome metadata.

### Task 3: Wolbachia Intervention Lane

**Files:**
- `askinsects/sources/wolbachia_interventions.py`
- `scripts/ingest_wolbachia_interventions.py`
- `tests/test_wolbachia_interventions_source.py`

- [ ] Fetch default World Mosquito Program public pages and optional override URLs.
- [ ] Save raw HTML under `raw/wolbachia_interventions/`.
- [ ] Emit page-grain `public_health` records with source-mentioned metrics.
- [ ] Record missing URL and fetch-failure gaps.

### Task 4: Ask, CLI, Hosted, Docs, And Gate

**Files:**
- `askinsects/answer.py`
- `askinsects/cli.py`
- `askinsects/planner.py`
- `askinsects/server.py`
- `tests/test_answer.py`
- `tests/test_cli_hosted.py`
- `tests/test_server.py`
- `README.md`
- `docs/source-lanes.md`
- `docs/querying-ask-insects.md`
- `config/source-map.yaml`
- `config/mosquito-intelligence-coverage.json`
- `scripts/verify_complete.py`

- [ ] Wire local and hosted CLI ingest commands.
- [ ] Wire hosted server endpoints.
- [ ] Prefer new lanes for matching questions.
- [ ] Add source-map and coverage-ledger entries.
- [ ] Make `scripts/verify_complete.py` require the new lanes.

### Task 5: Install And Verify

- [ ] Run focused unit tests.
- [ ] Run live bounded local ingests.
- [ ] Prove local ask/search/SQL for each lane.
- [ ] Run full unittest and `scripts/verify_complete.py`.
- [ ] Commit and push.
- [ ] Deploy to the Ask Insects VM.
- [ ] Run hosted ingests and hosted ask/search/SQL proof.
- [ ] Run remote `scripts/verify_complete.py`.
