# Generic Insect Evidence Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the consumer-specific v1 context export with a generic, public-safe v2 insect evidence package that includes direct taxon and context assertions.

**Architecture:** Keep the existing bounded hosted export surface, but make its config and schema consumer-neutral. Select records only from trusted semantic fields, attach machine-verifiable eligibility assertions, convert provenance to stable public locators, and report every rejection as a receipt or gap.

**Tech Stack:** Python 3, SQLite, JSON, `unittest`/`pytest`, existing Ask Insects CLI and HTTP server.

---

## File Structure

- `config/insect-evidence-package.json`: generic public contexts, aliases, trusted fields, selectors, and limits.
- `askinsects/context_package.py`: v2 config loading, semantic assertions, public provenance, deterministic selection, package validation.
- `tests/test_context_package.py`: focused red-green tests for contamination, assertions, gaps, privacy, and determinism.
- `tests/test_server.py` and `tests/test_cli_hosted.py`: hosted v2 contract tests.
- `README.md`, `AGENTS.md`, `docs/source-lanes.md`, `docs/querying-ask-insects.md`, `config/source-map.yaml`, `skills/askinsects/SKILL.md`: active generic product contract.
- `askinsects/answer.py`, `askinsects/planner.py`, `config/insect-intelligence-programs.json`: generic public/private boundary wording.
- `askinsects/sources/drosophila_suzukii.py` and its tests: rename consumer-specific topic symbols without changing source behavior.
- `scripts/verify_complete.py` and `tests/test_verify_complete.py`: mechanical v2 and independence gates.
- `evals/ask_insects_production_path_v1.json`, `scripts/eval_production_path.py`, and tests: consumer-neutral boundary questions and command allowlisting.

### Task 1: Rename And Validate The Generic Config

**Files:**
- Create: `config/insect-evidence-package.json`
- Modify: `askinsects/context_package.py`
- Modify: `tests/test_context_package.py`
- Delete: `config/ask-monarch-context-package.json`

- [ ] **Step 1: Write failing path and schema tests**

Add tests that require `DEFAULT_CONTEXT_CONFIG.name == "insect-evidence-package.json"`, require schema `ask-insects-evidence-package-config.v2`, reject `private_assay_families` and `private_assay_modes`, and accept generic fields `endpoint_family` and `exposure_routes`.

- [ ] **Step 2: Run the focused tests and verify the expected failure**

Run: `python3 -m pytest tests/test_context_package.py -q`

Expected: failures name the old config path and missing v2 generic fields.

- [ ] **Step 3: Create the generic config and minimal loader**

Use these constants and context shape:

```python
PACKAGE_SCHEMA_VERSION = "ask-insects-evidence-package.v2"
CONFIG_SCHEMA_VERSION = "ask-insects-evidence-package-config.v2"
ELIGIBILITY_RULESET_VERSION = "direct-semantic-evidence.v1"
DEFAULT_CONTEXT_CONFIG = REPO_ROOT / "config/insect-evidence-package.json"
```

Each config context must contain exactly:

```json
{
  "id": "treated_area_contact_avoidance",
  "endpoint_family": "treated_area_occupancy",
  "exposure_routes": ["contact"],
  "species_ids": ["drosophila_suzukii", "aedes_aegypti"],
  "required_domains": ["sensory_world", "behavior"],
  "measures": ["occupancy or avoidance relative to a treated area"],
  "does_not_establish": ["a proven receptor or product claim"],
  "plausible_explanations": ["sensory avoidance", "irritation", "movement change"],
  "discriminating_evidence": ["matched controls and dose-response replication"],
  "selectors": []
}
```

Split the old combined contact context into contact and non-contact contexts. Keep choice, oviposition, landing, spatial behavior, and post-exposure as generic concepts.

- [ ] **Step 4: Run focused tests**

Run: `python3 -m pytest tests/test_context_package.py -q`

Expected: path and config tests pass; semantic assertion tests added later remain absent.

- [ ] **Step 5: Commit**

```bash
git add config/insect-evidence-package.json config/ask-monarch-context-package.json askinsects/context_package.py tests/test_context_package.py
git commit -m "refactor: make insect evidence config generic"
```

### Task 2: Prove Direct Taxon And Context Eligibility

**Files:**
- Modify: `config/insect-evidence-package.json`
- Modify: `askinsects/context_package.py`
- Modify: `tests/test_context_package.py`

- [ ] **Step 1: Add contamination fixtures and failing tests**

Add records whose database species is `Drosophila suzukii` but trusted evidence text is about:

```text
Haemaphysalis longicornis tick repellency
Tribolium castaneum Y-tube repellency
Drosophila melanogaster TRPA1 avoidance
generic insect oviposition without Drosophila suzukii
```

Assert none are exported. Add direct SWD, Aedes, and DBM records and assert each exported record has:

```python
record["eligibility"]["taxon"]["status"] == "direct_focal_taxon"
record["eligibility"]["context"]["status"] == "direct_context"
record["eligibility"]["ruleset_version"] == "direct-semantic-evidence.v1"
```

Also assert each basis includes `field_path`, `matched_term`, and `excerpt`.

Each selector must declare the trusted field paths used for its taxon and
context assertions. For derived facts, it must also declare the parent-record
id path and trusted parent fields. Do not infer a trusted profile from the
source id at runtime.

- [ ] **Step 2: Verify RED**

Run: `python3 -m pytest tests/test_context_package.py -q`

Expected: contaminated rows are selected and `eligibility` is missing.

- [ ] **Step 3: Implement trusted field extraction**

Implement focused helpers:

```python
def _value_at_path(record: dict[str, object], path: str) -> list[str]: ...

def _trusted_semantic_values(
    record: dict[str, object], field_paths: list[str]
) -> list[tuple[str, str]]: ...

def _direct_assertion(
    values: list[tuple[str, str]], terms: list[str], *, status: str
) -> dict[str, object] | None: ...
```

Only configured paths may be read. Do not include `query`, `search_term`, `scope`, `inclusion_paths`, generated species labels, or the database `species` column in the allowlist.

The retained source shapes have these additional constraints:

- extracted facts require `payload.source_record_id`; taxon confirmation comes
  from the loaded parent paper title or raw OpenAlex abstract, while context
  confirmation comes from retained source text or a structured source row
- olfaction literature may use its retained source title; a matched-record id
  is usable only after the matched record independently passes the same checks
- flight table rows without a species-bearing parent link, hard-coded
  neurobiology atoms without retained raw species text, and the not-yet-mapped
  DBM selector must be rejected and reported as direct-evidence gaps

- [ ] **Step 4: Implement derived-record upstream checks**

When `payload.source_record_id` exists, load that record in the same read-only SQLite connection. Require a direct taxon assertion from the upstream title or abstract and a direct context assertion from the current evidence passage or structured assay fields. Missing upstream rows reject the candidate.

- [ ] **Step 5: Attach assertions and rejection receipts**

Each selector result must include:

```json
{
  "candidate_count": 4,
  "selected_count": 1,
  "rejection_counts": {
    "taxon_not_directly_confirmed": 2,
    "context_not_directly_confirmed": 1
  }
}
```

If no row remains, emit `selector_no_direct_evidence` with the same receipt.

- [ ] **Step 6: Verify GREEN**

Run: `python3 -m pytest tests/test_context_package.py -q`

Expected: all focused tests pass and known cross-species fixtures are excluded.

- [ ] **Step 7: Commit**

```bash
git add config/insect-evidence-package.json askinsects/context_package.py tests/test_context_package.py
git commit -m "fix: require direct species and context evidence"
```

### Task 3: Export Public-Safe Provenance

**Files:**
- Modify: `askinsects/context_package.py`
- Modify: `tests/test_context_package.py`

- [ ] **Step 1: Write failing privacy and locator tests**

Cover `/home/josh/...#row/100`, `file:///tmp/x`, `gs://private-bucket/x`, token-like keys, an unknown top-level field, a 1 MB string, and nesting beyond the allowed depth. Assert local paths never appear in serialized output and a public `source_url` becomes the locator while preserving `#row/100`.

- [ ] **Step 2: Verify RED**

Run: `python3 -m pytest tests/test_context_package.py -q`

Expected: current package leaks local paths and accepts unsafe shapes.

- [ ] **Step 3: Implement public provenance normalization**

Add:

```python
def _public_provenance(record: dict[str, object]) -> dict[str, object]:
    """Return source id, stable public locator, record id, retrieval time, and license."""
```

Use `source_url` as the base. Preserve a useful fragment from the indexed locator only when it starts with `row`, `page`, `cell`, `sheet`, `result`, `works`, or `jsonpath`. Add `index_record_id` separately.

- [ ] **Step 4: Add structural limits and generic boundary validation**

Set explicit limits for package bytes, list lengths, string length, and nesting depth. Reject absolute paths, `file:`, non-public cloud locators, credential-shaped keys, and consumer fields. Do not hard-code one consumer name as the privacy model.

- [ ] **Step 5: Verify GREEN**

Run: `python3 -m pytest tests/test_context_package.py -q`

Expected: all privacy, locator, hash, and determinism tests pass.

- [ ] **Step 6: Commit**

```bash
git add askinsects/context_package.py tests/test_context_package.py
git commit -m "fix: publish stable public-only provenance"
```

### Task 4: Wire V2 Through CLI And Hosted HTTP

**Files:**
- Modify: `askinsects/cli.py`
- Modify: `askinsects/server.py`
- Modify: `tests/test_cli_hosted.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write failing hosted contract tests**

Assert both CLI and `/context-package` return schema v2, generic contexts, assertions, selector rejection receipts, and no private request parameters. Assert generation errors return a bounded JSON error without falling back to a local index.

- [ ] **Step 2: Verify RED**

Run: `python3 -m pytest tests/test_cli_hosted.py tests/test_server.py -q`

Expected: schema and field assertions fail against v1.

- [ ] **Step 3: Update the CLI and server adapters**

Keep the command and path stable, but update help and response handling to name a generic public evidence package. Do not add consumer parameters.

- [ ] **Step 4: Verify GREEN**

Run: `python3 -m pytest tests/test_cli_hosted.py tests/test_server.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add askinsects/cli.py askinsects/server.py tests/test_cli_hosted.py tests/test_server.py
git commit -m "feat: serve generic evidence package v2"
```

### Task 5: Remove Consumer Coupling From Active Product Surfaces

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/source-lanes.md`
- Modify: `docs/querying-ask-insects.md`
- Modify: `config/source-map.yaml`
- Modify: `config/insect-intelligence-programs.json`
- Modify: `skills/askinsects/SKILL.md`
- Modify: `askinsects/answer.py`
- Modify: `askinsects/planner.py`
- Modify: `askinsects/sources/drosophila_suzukii.py`
- Modify: `tests/test_drosophila_suzukii_source.py`
- Modify: `tests/test_insect_intelligence_programs.py`

- [ ] **Step 1: Add failing generic-boundary tests**

Assert active config, runtime modules, README, source docs, and installed skill do not describe one private consumer as the owner or target. Assert the public answer says private evidence belongs in a separate private system and cannot fill public gaps.

- [ ] **Step 2: Verify RED**

Run: `python3 -m pytest tests/test_drosophila_suzukii_source.py tests/test_insect_intelligence_programs.py -q`

Expected: old consumer-specific constants and answer wording fail.

- [ ] **Step 3: Genericize active surfaces without changing science behavior**

Rename the SWD topic constant to `DROSOPHILA_SUZUKII_PRODUCT_TOPIC_SEARCH_TERMS`. Rewrite public objectives around protecting people and crops. Describe downstream consumers generically. Preserve source lane ids and scientific scope.

- [ ] **Step 4: Verify GREEN**

Run: `python3 -m pytest tests/test_drosophila_suzukii_source.py tests/test_insect_intelligence_programs.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md README.md docs/source-lanes.md docs/querying-ask-insects.md config/source-map.yaml config/insect-intelligence-programs.json skills/askinsects/SKILL.md askinsects/answer.py askinsects/planner.py askinsects/sources/drosophila_suzukii.py tests/test_drosophila_suzukii_source.py tests/test_insect_intelligence_programs.py
git commit -m "docs: make Ask Insects consumer independent"
```

### Task 6: Enforce Public Clone Independence

**Files:**
- Modify: `scripts/verify_complete.py`
- Modify: `tests/test_verify_complete.py`
- Modify: `scripts/eval_production_path.py`
- Modify: `tests/test_production_path_eval.py`
- Modify: `evals/ask_insects_production_path_v1.json`

- [ ] **Step 1: Write failing completion-gate tests**

Require the generic config and v2 design, forbid the deleted config, validate semantic assertions and public locators, and scan active runtime/config/skill files for consumer-specific imports or private locators.

- [ ] **Step 2: Write failing evaluator allowlist tests**

Replace explicit alternate-product command markers with a rule that allows exactly one installed skill read and exactly one `ask-insects ask --compact` command. Any other command fails regardless of its name. Rewrite the three private-boundary questions to refer to a separate private R&D system.

- [ ] **Step 3: Verify RED**

Run: `python3 -m pytest tests/test_verify_complete.py tests/test_production_path_eval.py -q`

Expected: old required files and explicit consumer wording fail.

- [ ] **Step 4: Implement the gates**

Make `verify_complete.py` load and validate a real v2 package fixture or hosted package when configured. Add a clean-clone static check proving no private repository path, token, or package is required to import `askinsects`, load the config, or run fixture-backed package tests.

- [ ] **Step 5: Verify GREEN**

Run: `python3 -m pytest tests/test_verify_complete.py tests/test_production_path_eval.py -q`

Expected: all tests pass and the production corpus still has 200 unique cases.

- [ ] **Step 6: Commit**

```bash
git add scripts/verify_complete.py tests/test_verify_complete.py scripts/eval_production_path.py tests/test_production_path_eval.py evals/ask_insects_production_path_v1.json
git commit -m "test: enforce public package independence"
```

### Task 7: Full Local Verification

**Files:**
- No production edits expected.

- [ ] **Step 1: Run focused contamination proof**

Run: `python3 -m pytest tests/test_context_package.py -q`

Expected: all tests pass, including named tick and beetle regression cases.

- [ ] **Step 2: Run the complete test suite**

Run: `python3 -m pytest -q`

Expected: zero failures.

- [ ] **Step 3: Run the repository completion gate**

Run: `python3 scripts/verify_complete.py`

Expected: exit 0 and every required subcheck reports pass.

- [ ] **Step 4: Inspect the generated package**

Run a fixture-backed package build and assert with `jq` that schema is v2, every evidence record has two assertions, no serialized local path exists, and SWD output excludes the known unrelated DOIs.

- [ ] **Step 5: Review the diff**

Run: `git diff origin/main...HEAD --check && git status --short && git log --oneline origin/main..HEAD`

Expected: clean diff check, only intended files, and focused commits.
