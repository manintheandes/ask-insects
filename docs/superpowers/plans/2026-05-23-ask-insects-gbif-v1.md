# Ask Insects GBIF V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded GBIF source lane that fetches mosquito taxonomy and occurrence records into the local Ask Insects index with provenance and receipts.

**Architecture:** Add a focused GBIF source module that fetches species matches and occurrence search results, stores raw JSON artifacts, and normalizes them to existing `EvidenceRecord` rows. Extend the builder so fixture records and GBIF records can share one SQLite index and one receipt/status/gap set.

**Tech Stack:** Python standard library, `urllib.request`, `unittest`, local SQLite, JSON artifacts.

---

## File Structure

- Create `askinsects/sources/gbif.py`: GBIF API client, raw artifact writer, species match and occurrence normalization.
- Create `tests/test_gbif_source.py`: mocked GBIF unit tests.
- Modify `askinsects/builder.py`: support combined fixture and GBIF builds.
- Modify `scripts/build_source_index.py`: add `--gbif`, repeatable `--species`, and `--occurrence-limit`.
- Modify `askinsects/cli.py`: include sources discovered from source status when available.
- Modify `config/source-map.yaml`: add `gbif_api` source mapping.
- Modify `docs/source-lanes.md`, `docs/querying-ask-insects.md`, `README.md`: document GBIF lane and commands.
- Modify `scripts/verify_complete.py`: require GBIF files and run GBIF tests while keeping live GBIF optional.

## Task 1: GBIF Source Module

**Files:**
- Create: `askinsects/sources/gbif.py`
- Create: `tests/test_gbif_source.py`

- [ ] **Step 1: Write failing tests for GBIF normalization**

Create tests that use a fake fetcher returning GBIF species match and occurrence payloads. Assert that taxonomy and observation records include `source="gbif_api"`, GBIF URLs, and provenance locators.

- [ ] **Step 2: Run the tests and verify failure**

Run:

```bash
python3 -m unittest tests.test_gbif_source -v
```

Expected: fail because `askinsects.sources.gbif` does not exist.

- [ ] **Step 3: Implement `askinsects/sources/gbif.py`**

Implement:

- `GBIF_SOURCE_ID = "gbif_api"`
- `DEFAULT_GBIF_SPECIES`
- `GBIFClient`
- `GBIFBuildResult`
- `fetch_gbif_records(...)`

Use `https://api.gbif.org/v1/species/match` for species matching and `https://api.gbif.org/v1/occurrence/search` for occurrences.

- [ ] **Step 4: Run tests**

Run:

```bash
python3 -m unittest tests.test_gbif_source -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add askinsects/sources/gbif.py tests/test_gbif_source.py
git commit -m "feat: add GBIF source loader"
```

## Task 2: Builder And CLI Wiring

**Files:**
- Modify: `askinsects/builder.py`
- Modify: `scripts/build_source_index.py`
- Modify: `askinsects/cli.py`
- Modify: `tests/test_builder.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing builder and CLI tests**

Add tests that:

- Build an index from fixture records plus fake GBIF records.
- Assert status includes both `mosquito_v1_fixtures` and `gbif_api`.
- Assert `python3 -m askinsects sources` includes `gbif_api` when source status contains it.
- Assert the build script accepts `--fixtures --gbif --species "Aedes aegypti" --occurrence-limit 1` with a mocked builder function where practical.

- [ ] **Step 2: Run targeted tests and verify failure**

Run:

```bash
python3 -m unittest tests.test_builder tests.test_cli -v
```

Expected: fail because builder and CLI do not yet know GBIF.

- [ ] **Step 3: Implement combined builds**

Add `build_source_index(...)` that accepts fixture and GBIF options. Keep `build_fixture_index(...)` as a compatibility wrapper.

- [ ] **Step 4: Implement CLI and script wiring**

Add build script flags:

```bash
--gbif
--species "Aedes aegypti"
--occurrence-limit 3
```

Update `sources` command to read `source_status.json` and include real indexed sources.

- [ ] **Step 5: Run targeted tests**

Run:

```bash
python3 -m unittest tests.test_builder tests.test_cli -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add askinsects/builder.py scripts/build_source_index.py askinsects/cli.py tests/test_builder.py tests/test_cli.py
git commit -m "feat: wire GBIF into source builds"
```

## Task 3: Docs, Source Map, And Completion Gate

**Files:**
- Modify: `README.md`
- Modify: `config/source-map.yaml`
- Modify: `docs/source-lanes.md`
- Modify: `docs/querying-ask-insects.md`
- Modify: `scripts/verify_complete.py`

- [ ] **Step 1: Update docs and source map**

Document GBIF as the taxonomy and occurrence lane, including that live GBIF pulls are opt-in and bounded.

- [ ] **Step 2: Update completion gate**

Require `askinsects/sources/gbif.py`, `tests/test_gbif_source.py`, and this GBIF design/plan. Add `tests.test_gbif_source` to `UNIT_TEST_MODULES`.

- [ ] **Step 3: Run verification**

Run:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/verify_complete.py
```

Expected: pass.

- [ ] **Step 4: Optional live smoke check**

Run:

```bash
python3 scripts/build_source_index.py --fixtures --gbif --species "Aedes aegypti" --occurrence-limit 1
python3 -m askinsects sources
python3 -m askinsects search observations "Aedes"
```

Expected: command succeeds if GBIF is reachable. If GBIF is unavailable, report the live source gap and keep deterministic tests as the completion proof.

- [ ] **Step 5: Commit**

```bash
git add README.md config/source-map.yaml docs/source-lanes.md docs/querying-ask-insects.md scripts/verify_complete.py
git commit -m "docs: document GBIF source lane"
```

## Task 4: Final Verification

**Files:**
- No expected changes unless verification exposes a defect.

- [ ] **Step 1: Run final tests**

```bash
python3 -m unittest discover -s tests -v
python3 scripts/verify_complete.py
git status --short --branch
```

Expected: tests pass, completion gate prints `verify_complete ok`, and git status is clean.

- [ ] **Step 2: Review final behavior**

Run:

```bash
python3 -m askinsects sources
python3 -m askinsects sql "select source, lane, count(*) as records from records group by source, lane"
```

Expected: fixture source appears after deterministic build. GBIF source appears after an explicit GBIF build.
