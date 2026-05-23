# iNaturalist Deep Aedes Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add polite paginated iNaturalist ingest so Ask Insects can pull all public photo-backed `Aedes aegypti` observations up to an explicit cap.

**Architecture:** Extend the existing iNaturalist source module to fetch many API pages with delay, save each raw page, dedupe records, and return richer receipt metadata. Keep answering unchanged: answers continue to read the local SQLite source index after ingestion.

**Tech Stack:** Python standard library, `urllib.request`, `time.sleep`, `unittest`, JSON artifacts, local SQLite.

---

## File Structure

- Modify `askinsects/sources/inaturalist.py`: pagination, page size, delay, dedupe, total result receipt fields.
- Modify `askinsects/builder.py`: pass `page_size` and `delay_seconds`, write richer iNaturalist receipt.
- Modify `scripts/build_source_index.py`: add `--page-size` and `--delay-seconds`.
- Modify `tests/test_inaturalist_source.py`: fake paginated API responses and no-delay test assertions.
- Modify `tests/test_builder.py`: assert receipt includes page size, delay, total results, and multiple raw pages.
- Modify `README.md`, `docs/querying-ask-insects.md`, `docs/source-lanes.md`: document deep ingest command.
- Modify `scripts/verify_complete.py`: require this design and plan.

## Task 1: Paginated Source Tests

**Files:**
- Modify: `tests/test_inaturalist_source.py`

- [ ] **Step 1: Add failing paginated ingest test**

Add a fake fetcher that returns page 1 with two observations and page 2 with one duplicate plus one new observation. Assert the loader returns three observation records, three media records, two raw page files, deduped ids, and `total_results=4`.

- [ ] **Step 2: Run the test**

```bash
python3 -m unittest tests.test_inaturalist_source -v
```

Expected: fail because `fetch_inaturalist_records` does not accept `page_size` or `delay_seconds` and fetches only one page.

## Task 2: Pagination Implementation

**Files:**
- Modify: `askinsects/sources/inaturalist.py`

- [ ] **Step 1: Implement page parameters**

Add `page_size=200` and `delay_seconds=0.0` to `fetch_inaturalist_records`.

- [ ] **Step 2: Fetch pages until done**

Fetch pages until one of these is true:

- indexed observation count reaches `observation_limit`
- API page returns no results
- fetched results reach `total_results`

- [ ] **Step 3: Save raw page artifacts**

Use filenames like:

```text
Aedes_aegypti_Brazil_page_001.json
```

- [ ] **Step 4: Dedupe records**

Dedupe observation records by observation id and media records by photo id.

- [ ] **Step 5: Run source tests**

```bash
python3 -m unittest tests.test_inaturalist_source -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add askinsects/sources/inaturalist.py tests/test_inaturalist_source.py
git commit -m "feat: paginate iNaturalist source ingest"
```

## Task 3: Builder And CLI Wiring

**Files:**
- Modify: `askinsects/builder.py`
- Modify: `scripts/build_source_index.py`
- Modify: `tests/test_builder.py`

- [ ] **Step 1: Add failing builder test**

Update the iNaturalist builder test to pass `page_size=2` and `delay_seconds=0`, then assert `receipt["inaturalist"]["page_size"] == 2` and `receipt["inaturalist"]["delay_seconds"] == 0`.

- [ ] **Step 2: Run test**

```bash
python3 -m unittest tests.test_builder -v
```

Expected: fail because builder does not accept the new parameters.

- [ ] **Step 3: Implement builder parameters and script flags**

Add:

```text
--page-size
--delay-seconds
```

- [ ] **Step 4: Run builder tests**

```bash
python3 -m unittest tests.test_builder -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add askinsects/builder.py scripts/build_source_index.py tests/test_builder.py
git commit -m "feat: wire deep iNaturalist ingest options"
```

## Task 4: Docs And Completion Gate

**Files:**
- Modify: `README.md`
- Modify: `docs/querying-ask-insects.md`
- Modify: `docs/source-lanes.md`
- Modify: `scripts/verify_complete.py`

- [ ] **Step 1: Document deep ingest**

Add the deep Aedes command with `--observation-limit`, `--page-size`, and `--delay-seconds`.

- [ ] **Step 2: Update completion gate required files**

Require the deep ingest design and plan files.

- [ ] **Step 3: Run deterministic verification**

```bash
python3 -m unittest discover -s tests -v
python3 scripts/verify_complete.py
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/querying-ask-insects.md docs/source-lanes.md scripts/verify_complete.py
git commit -m "docs: document deep iNaturalist ingest"
```

## Task 5: Live Deep Ingest Proof

**Files:**
- No tracked changes expected.

- [ ] **Step 1: Run live deep ingest**

```bash
python3 scripts/build_source_index.py --fixtures --inat --species "Aedes aegypti" --observation-limit 5758 --page-size 200 --delay-seconds 1
```

Expected: runs around 30 API requests, writes many raw page artifacts, and creates thousands of local records.

- [ ] **Step 2: Inspect indexed counts**

```bash
python3 -m askinsects sources
python3 -m askinsects sql "select source, lane, count(*) as records from records group by source, lane"
python3 -m askinsects ask "show mosquito observations with images in Brazil"
```

Expected: iNaturalist source appears with large observation and media counts. The answer uses local indexed records.

- [ ] **Step 3: Final status**

```bash
git status --short --branch
```

Expected: clean because generated artifacts are ignored.
