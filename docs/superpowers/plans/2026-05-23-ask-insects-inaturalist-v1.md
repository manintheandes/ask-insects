# Ask Insects iNaturalist V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in iNaturalist source lane that indexes mosquito observations and image media with provenance.

**Architecture:** Add a focused source module for iNaturalist API fetch and normalization. Extend the existing builder to combine fixture, GBIF, and iNaturalist records into the same SQLite index, status, receipt, and gap artifacts.

**Tech Stack:** Python standard library, `urllib.request`, `unittest`, JSON artifacts, local SQLite.

---

## File Structure

- Create `askinsects/sources/inaturalist.py`: iNaturalist client, raw artifact writer, observation and media normalization.
- Create `tests/test_inaturalist_source.py`: mocked iNaturalist source tests.
- Modify `askinsects/builder.py`: add `include_inaturalist`, species, place, observation limit, and injected fake fetcher.
- Modify `scripts/build_source_index.py`: add `--inat`, `--place`, and `--observation-limit`.
- Modify `askinsects/answer.py`: let image observation questions prefer media records when available, while video questions still report a moving-image gap.
- Modify `config/source-map.yaml`, `README.md`, `docs/source-lanes.md`, and `docs/querying-ask-insects.md`: document source contract and commands.
- Modify `scripts/verify_complete.py`: require iNaturalist source files and run mocked tests.

## Task 1: iNaturalist Source Module

**Files:**
- Create: `askinsects/sources/inaturalist.py`
- Create: `tests/test_inaturalist_source.py`

- [ ] **Step 1: Write failing tests**

Create fake iNaturalist responses with one observation containing one licensed photo. Assert that `fetch_inaturalist_records(...)` returns an `observations` record and a `media` record with source id `inaturalist_api`, observation URL, media URL, license, and raw locator.

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
python3 -m unittest tests.test_inaturalist_source -v
```

Expected: fail because `askinsects.sources.inaturalist` does not exist.

- [ ] **Step 3: Implement source module**

Implement:

- `INATURALIST_SOURCE_ID = "inaturalist_api"`
- `DEFAULT_INATURALIST_SPECIES = ("Aedes aegypti",)`
- `INaturalistBuildResult`
- `INaturalistClient`
- `fetch_inaturalist_records(...)`

Use `https://api.inaturalist.org/v1/observations` with `taxon_name`, `per_page`, `photos=true`, and `photo_licensed=true`.

- [ ] **Step 4: Run source tests**

Run:

```bash
python3 -m unittest tests.test_inaturalist_source -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add askinsects/sources/inaturalist.py tests/test_inaturalist_source.py
git commit -m "feat: add iNaturalist source loader"
```

## Task 2: Builder, Script, And Answer Wiring

**Files:**
- Modify: `askinsects/builder.py`
- Modify: `scripts/build_source_index.py`
- Modify: `askinsects/answer.py`
- Modify: `tests/test_builder.py`
- Modify: `tests/test_answer.py`

- [ ] **Step 1: Write failing tests**

Add tests that:

- Build fixture plus fake iNaturalist records.
- Assert source status includes `inaturalist_api`.
- Assert source counts include two iNaturalist records.
- Assert image-backed observation questions can return media evidence when media records exist.
- Assert video questions still produce a media gap when only still images are indexed.

- [ ] **Step 2: Run targeted tests and verify failure**

Run:

```bash
python3 -m unittest tests.test_builder tests.test_answer -v
```

Expected: fail because builder and answer layer do not know iNaturalist media records yet.

- [ ] **Step 3: Implement builder and script flags**

Add:

- `include_inaturalist`
- `inaturalist_species`
- `inaturalist_place`
- `observation_limit`
- `inaturalist_fetch_json`

Add build script flags:

```bash
--inat
--place Brazil
--observation-limit 10
```

- [ ] **Step 4: Implement answer behavior**

Image questions should check media records. Video questions should keep requiring moving-image media and should still report a source gap when only still photos exist.

- [ ] **Step 5: Run targeted tests**

Run:

```bash
python3 -m unittest tests.test_builder tests.test_answer -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add askinsects/builder.py scripts/build_source_index.py askinsects/answer.py tests/test_builder.py tests/test_answer.py
git commit -m "feat: wire iNaturalist media into source builds"
```

## Task 3: Docs And Completion Gate

**Files:**
- Modify: `README.md`
- Modify: `config/source-map.yaml`
- Modify: `docs/source-lanes.md`
- Modify: `docs/querying-ask-insects.md`
- Modify: `scripts/verify_complete.py`

- [ ] **Step 1: Update docs and source map**

Document `inaturalist_api`, the raw artifact path, opt-in live behavior, and example command.

- [ ] **Step 2: Update completion gate**

Require:

- `askinsects/sources/inaturalist.py`
- `tests/test_inaturalist_source.py`
- iNaturalist design and plan files

Add `tests.test_inaturalist_source` to `UNIT_TEST_MODULES`.

- [ ] **Step 3: Run deterministic verification**

Run:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/verify_complete.py
```

Expected: pass.

- [ ] **Step 4: Commit docs and gate**

```bash
git add README.md config/source-map.yaml docs/source-lanes.md docs/querying-ask-insects.md scripts/verify_complete.py
git commit -m "docs: document iNaturalist source lane"
```

## Task 4: Final Verification And Live Smoke

**Files:**
- No expected changes unless verification exposes a defect.

- [ ] **Step 1: Run final deterministic verification**

```bash
python3 -m unittest discover -s tests -v
python3 scripts/verify_complete.py
git status --short --branch
```

Expected: tests pass, completion gate prints `verify_complete ok`, and git status is clean.

- [ ] **Step 2: Run live smoke check**

```bash
python3 scripts/build_source_index.py --fixtures --inat --species "Aedes aegypti" --place Brazil --observation-limit 3
python3 -m askinsects sources
python3 -m askinsects sql "select source, lane, count(*) as records from records group by source, lane"
python3 -m askinsects ask "show mosquito observations with images in Brazil"
```

Expected: live iNaturalist records appear if the API returns licensed photo observations. If no observations are returned, source gaps are recorded and deterministic verification remains the completion proof.
