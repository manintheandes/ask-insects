# Source Adapter Framework Design

Date: 2026-05-30
Status: Approved (brainstorm), pending spec review

## Problem

Ask Insects has ~73 source adapters (`askinsects/sources/*.py`) and their ingest
scripts (`scripts/ingest_*.py`), almost entirely copy-pasted. The same handful
of defects recur across dozens of files because each file re-implements the same
chores by hand:

1. **Non-queryable gaps** — gaps written only as dicts to `gaps.json`, never as
   `source_gap` rows in the queryable index (was ~57 adapters).
2. **Wipe-on-failure** — `replace_source_records` called unconditionally, so a
   total fetch failure deletes existing good rows and still reports `ok: True`
   (was ~43 scripts).
3. **Species fabrication** — `species = <row> or "Aedes aegypti"` stamps the
   target species onto rows whose own data does not name it (was ~14 sites).
4. **Undeclared gaps** — adapters emit gap reasons not listed in the source's
   `structured_gaps` in `config/source-map.yaml`.

The May 2026 review fixed these case-by-case, but conformance to the source
contract is by convention, not by construction: nothing prevents the next lane
from reintroducing them. This design makes the contract enforced by shared,
tested machinery.

## Goals

- Centralize the four bug classes into one tested place each, so a new lane
  cannot reintroduce them.
- **Behavior parity**: migrated lanes produce identical `records` and `gaps` for
  identical inputs. No answer or data change.
- Keep the data contract, sources, CLI, HTTP API, and index schema unchanged.
- Reduce per-lane boilerplate.

## Non-goals

- No new source lanes or scientific data.
- No rewrite of `answer.py`/`planner.py`/`server.py` (separate future work).
- No change to record IDs, lanes, payload shapes, or provenance of existing
  records (parity forbids it).
- Not a declarative/data-driven engine (Approach 3, rejected as overkill).

## Approach (chosen: shared runner + species helper)

The bug classes live on two layers. Persistence, refresh-guard, and
gap-queryability are in the **scripts**; species fabrication is in the
**adapters**. We address each layer with a shared unit, leaving the adapters'
unique fetch/parse logic alone.

### Component 1: `askinsects/ingest_runner.py`

`run_source_ingest(...)` is the single path every `ingest_*.py` calls to persist
a fetch result. It owns:

- `refresh_failed` computed correctly, **using the non-gap subset of records** (a
  result whose only records are gap records, plus a failure gap, counts as failed
  so existing data is preserved; mirrors the deviated guard already used by
  `ingest_ncbi_snp_variation.py` and `ingest_observation_climate.py`). The gap
  subset is detected via `payload["atom_type"]` ending in `gap` or a `:gap:`
  record id.
- Guarded `index.replace_source_records(source_id, records)` only when not
  `refresh_failed`. **Records are persisted exactly as the adapter returned them**
  (including any gap records a fold-in adapter emits) — this is required for
  parity; the non-gap subset is used only to decide `refresh_failed`.
- `persist_source_gaps(index, source_id, gaps, retrieved_at=...)` (the helper
  shipped May 2026) called when `persist_gap_records=True`. This is set `False`
  for the ~16 lanes whose adapters already emit gap records into `records`, so a
  gap is never double-recorded. Default `True` (most lanes only have gap dicts).
- Uniform status/receipt writing and a uniform return dict:
  `{ok, refresh_failed, preserved_existing, source, record_count,
  refresh_record_count, source_gap_count, retrieved_at, source_counts, lanes}`.

Signature (initial):

```python
def run_source_ingest(
    *,
    index: SourceIndex,
    artifact_dir: Path,
    source_id: str,
    records: list[EvidenceRecord],
    gaps: list[dict],
    retrieved_at: str,
    raw_artifacts: list[str] | None = None,
    extra_status: dict | None = None,
    update_status_files: bool = True,
    persist_gap_records: bool = True,
) -> dict: ...
```

A record is "gap-only" when its `payload["atom_type"]` ends in `gap` or its
`record_id` matches `:gap:` — both already-used conventions.

### Component 2: `askinsects/species.py`

`resolve_species(value, *, scope=None)`:

- Returns the cleaned row value if present.
- Returns `None` when absent — never a fabricated default.
- When a source is genuinely species-scoped by its query (e.g. UniProt taxon
  7159, an iNaturalist taxon-pinned search), the caller passes `scope="Aedes
  aegypti"` explicitly; the helper returns the scope only then, documenting the
  decision at the call site. This preserves the legitimate-scope sites the review
  already identified while removing the fabrication ones.

### Component 3: parity harness

`tests/test_ingest_parity.py` plus a one-off dev script. For each migrated lane:

1. Capture a golden snapshot of `(records, gaps)` from the pre-migration adapter
   using fixed fake fetchers (deterministic, no network).
2. After migration, run the same fake fetchers and assert the new output is
   **identical** (record IDs, lanes, payloads, provenance, gaps).

Golden snapshots are generated from the current code before migrating a lane, so
parity is checked against real prior behavior, not a guess.

## Data flow (unchanged for users)

`fetch (adapter) -> (records, gaps) -> run_source_ingest -> index + gaps.json
-> CLI / HTTP answers`. Only the middle persistence step is consolidated.

## Migration plan

1. Build Component 1 + 2 + their unit tests. Gate green.
2. Build the parity harness and golden-snapshot generator.
3. Migrate adapters/scripts onto the runner + species helper in **batches of
   ~10**. After each batch: parity harness passes for that batch AND
   `python3 scripts/verify_complete.py` is green. Commit per batch.
4. Reconcile `structured_gaps` in `source-map.yaml` for any newly-surfaced
   reasons (most already declared in the May 2026 pass).
5. Final full gate + parity run across all lanes.

Lanes that legitimately fold gaps into records or have no fetch (e.g.
`ingest_source_coverage.py`) are migrated only where the runner is a clean fit;
exceptions are documented in the plan, not forced.

## Error handling

- Total fetch failure: `refresh_failed = True`, existing rows preserved,
  `ok: False`, exit code 2, gap recorded and queryable.
- Partial gaps: real records persisted, gaps queryable alongside.
- Runner never raises on empty input; returns `ok: False` with a recorded gap if
  one exists, else a no-op success.

## Testing / verification

- Unit tests for `run_source_ingest` (success, total-failure-preserves,
  gap-only, partial) and `resolve_species` (present, absent, scoped).
- Parity harness per migrated lane.
- `scripts/verify_complete.py` green after every batch.
- `/verify`: Evaluation Pack at `/tmp/verify-ask-insects-adapter-refactor.html`
  with the parity results and final gate output.

## Risks

- **Parity drift**: the runner's uniform status/return dict may differ from a
  lane's bespoke one. Mitigation: parity asserts on `records`+`gaps` (the
  queryable truth); status/receipt dict keys may gain fields but must not lose
  ones existing tests assert. Run each lane's existing test in-batch.
- **Heterogeneous adapters**: ~16 do not follow the `.records/.gaps` convention
  or fold gaps into records. Mitigation: migrate the conforming majority first;
  handle exceptions explicitly with documented per-lane decisions.
- **Scale/regression**: 73 files. Mitigation: batched, parity-gated, committed
  incrementally so any regression is isolated to one small batch.
