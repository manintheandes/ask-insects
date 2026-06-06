# SWD Post-2020 Literature Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand canonical `Drosophila suzukii` paper discovery since 2020 by querying multiple SWD aliases through OpenAlex while preserving hosted-answer discipline.

**Architecture:** Keep `drosophila_suzukii_core` as the canonical paper source. Add optional multi-search-term support to the shared OpenAlex literature fetcher, then pass SWD aliases from the SWD core source module. PubMed remains a reconciliation lane, not the canonical paper-count owner.

**Tech Stack:** Python standard library, existing Ask Insects source modules, SQLite-backed `EvidenceRecord` index, pytest/unittest tests.

---

### Task 1: Add A Failing Multi-Term OpenAlex Discovery Test

**Files:**
- Modify: `tests/test_drosophila_suzukii_source.py`

- [ ] **Step 1: Add a fake OpenAlex fetcher that returns different pages by search term**

Add a test helper that inspects the URL query string, returns one paper for `Drosophila suzukii`, a duplicate plus a second paper for `spotted wing drosophila`, and an empty page for other terms.

- [ ] **Step 2: Add the test**

The test should call `fetch_drosophila_suzukii_records(... literature_max_works=10 ...)`, then assert that exactly two literature records are present, that one record has an alias-based inclusion path, and that duplicate OpenAlex work id `W123` only appears once.

- [ ] **Step 3: Run the test and verify it fails**

Run:

```bash
python3 -m pytest tests/test_drosophila_suzukii_source.py::DrosophilaSuzukiiSourceTests::test_literature_fetch_uses_swd_aliases_and_deduplicates -q
```

Expected before implementation: FAIL because the current code only calls OpenAlex with the scientific-name search term.

### Task 2: Implement Multi-Term Literature Fetching

**Files:**
- Modify: `askinsects/sources/literature.py`
- Modify: `askinsects/sources/drosophila_suzukii.py`
- Modify: `scripts/ingest_drosophila_suzukii.py`

- [ ] **Step 1: Extend `_works_url`**

Add a `search_term` parameter and use it in `title_and_abstract.search` instead of always using `species`.

- [ ] **Step 2: Extend `fetch_literature_records`**

Add optional `search_terms: list[str] | None = None`. Default to `[species]` so existing Aedes behavior is unchanged. Loop over each search term with its own cursor. Keep a shared `seen_work_keys` set so duplicate OpenAlex works across terms are skipped.

- [ ] **Step 3: Preserve provenance**

Store the active search term in raw page filenames, record payloads, and `inclusion_paths`. Alias-matched title or abstract paths should be visible as `title_alias` or `abstract_alias`; exact species matches should keep existing `title` and `abstract`.

- [ ] **Step 4: Wire SWD aliases**

In `askinsects/sources/drosophila_suzukii.py`, define the SWD OpenAlex search terms and pass them to `fetch_literature_records`. Increase the CLI default `--literature-max-works` in `scripts/ingest_drosophila_suzukii.py` from `100` to `5000`.

- [ ] **Step 5: Run the focused tests**

Run:

```bash
python3 -m pytest tests/test_drosophila_suzukii_source.py tests/test_ingest_drosophila_suzukii.py -q
```

Expected: PASS.

### Task 3: Update Source Docs

**Files:**
- Modify: `README.md`
- Modify: `docs/source-lanes.md`
- Modify: `config/source-map.yaml`

- [ ] **Step 1: Update the SWD core boundary text**

Replace the single-query wording with multi-term OpenAlex discovery wording for post-2020 SWD papers.

- [ ] **Step 2: Update example command**

Show the higher cap:

```bash
python3 -m askinsects ingest-drosophila-suzukii --gbif-occurrence-limit 100 --inaturalist-observation-limit 100 --literature-max-works 5000 --bold-limit 100
```

- [ ] **Step 3: State the supplement ordering**

Add one sentence: increase canonical paper discovery first, then re-run the supplement audit over the expanded paper set.

### Task 4: Verify The Change

**Files:**
- No source edits.

- [ ] **Step 1: Run focused tests**

```bash
python3 -m pytest tests/test_drosophila_suzukii_source.py tests/test_ingest_drosophila_suzukii.py tests/test_drosophila_suzukii_pubmed_literature_source.py tests/test_ingest_drosophila_suzukii_pubmed_literature.py -q
```

- [ ] **Step 2: Run completion gate**

```bash
python3 scripts/verify_complete.py
```

- [ ] **Step 3: Report hosted status honestly**

If the code is not deployed/refreshed to hosted in this turn, say that the code is ready locally but hosted still needs refresh before hosted paper counts can increase.
