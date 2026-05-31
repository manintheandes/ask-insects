# Source Adapter Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the four recurring source-plane bug classes (non-queryable gaps, wipe-on-failure, species fabrication, undeclared gaps) impossible by construction via a shared ingest runner + species helper, then migrate all ~73 adapters onto them with behavior parity.

**Architecture:** A single `run_source_ingest()` centralizes record persistence, the refresh-failed guard, and gap-queryability for every `ingest_*.py` script. A `resolve_species()` helper removes fabricated species defaults in adapters. A parity harness asserts each migrated lane emits byte-identical `records`/`gaps` for fixed fake fetchers. Migration runs in parity-checked batches; `verify_complete.py` stays green throughout.

**Tech Stack:** Python 3.11+ stdlib, `unittest`, SQLite (`askinsects.index.SourceIndex`), existing `askinsects.gaps.persist_source_gaps`.

**Scope note:** The runner owns the persistence trio + uniform return dict. Each script keeps its existing `source_status.json`/`source_receipt.json` writing (unifying those formats is deferred — it would risk parity for no safety gain). Tests run with system `python3` (which has `openpyxl`); the gate is `python3 scripts/verify_complete.py`.

---

### Task 1: `resolve_species` helper

**Files:**
- Create: `askinsects/species.py`
- Test: `tests/test_species.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_species.py
import unittest
from askinsects.species import resolve_species


class ResolveSpeciesTests(unittest.TestCase):
    def test_returns_cleaned_row_value_when_present(self):
        self.assertEqual(resolve_species("  Aedes aegypti "), "Aedes aegypti")

    def test_returns_none_when_absent_and_no_scope(self):
        self.assertIsNone(resolve_species(""))
        self.assertIsNone(resolve_species(None))

    def test_returns_scope_only_when_absent_and_scope_given(self):
        self.assertEqual(resolve_species(None, scope="Aedes aegypti"), "Aedes aegypti")

    def test_row_value_wins_over_scope(self):
        self.assertEqual(resolve_species("Aedes albopictus", scope="Aedes aegypti"), "Aedes albopictus")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/josh/Documents/ask-insects && python3 -m unittest tests.test_species -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'askinsects.species'`

- [ ] **Step 3: Write minimal implementation**

```python
# askinsects/species.py
from __future__ import annotations

import re


def resolve_species(value: object, *, scope: str | None = None) -> str | None:
    """Return the row's own species, never a fabricated default.

    - Present row value -> cleaned string (wins over scope).
    - Absent + no scope -> None (do not invent a species).
    - Absent + scope given -> scope (only for sources genuinely pinned to one
      species by their query; the caller documents why at the call site).
    """
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if text:
        return text
    return scope
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_species -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add askinsects/species.py tests/test_species.py
git commit -m "feat: resolve_species helper (no fabricated species defaults)"
```

---

### Task 2: `run_source_ingest` runner

**Files:**
- Create: `askinsects/ingest_runner.py`
- Test: `tests/test_ingest_runner.py`

Uses existing `askinsects.gaps.persist_source_gaps(index, source_id, gaps, *, retrieved_at)` and `SourceIndex.replace_source_records(source_id, records)` / `SourceIndex.upsert_records(records)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingest_runner.py
import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.ingest_runner import run_source_ingest

RID = "2026-05-30T00:00:00Z"
SRC = "demo_source"


def _rec(rid, *, atom="row", lane="ecology"):
    return EvidenceRecord(
        record_id=rid, lane=lane, source=SRC, title="t", text="x",
        species="Aedes aegypti", url=None, media_url=None,
        provenance=Provenance(source_id=SRC, locator=rid, retrieved_at=RID),
        payload={"atom_type": atom},
    )


def _index(tmp):
    idx = SourceIndex(Path(tmp) / "i.sqlite")
    idx.initialize()
    return idx


class RunSourceIngestTests(unittest.TestCase):
    def test_success_persists_records_and_gaps_and_reports_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            idx = _index(tmp)
            out = run_source_ingest(
                index=idx, artifact_dir=Path(tmp), source_id=SRC,
                records=[_rec(f"{SRC}:row:1")],
                gaps=[{"lane": "ecology", "reason": "limit_applied"}],
                retrieved_at=RID,
            )
            self.assertTrue(out["ok"])
            self.assertFalse(out["refresh_failed"])
            rows = idx.sql(f"select count(*) as n from records where source='{SRC}'")
            self.assertEqual(int(rows[0]["n"]), 2)  # 1 row + 1 gap record

    def test_total_failure_preserves_existing_and_reports_not_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            idx = _index(tmp)
            # Seed an existing good row via a prior success.
            run_source_ingest(index=idx, artifact_dir=Path(tmp), source_id=SRC,
                              records=[_rec(f"{SRC}:row:1")], gaps=[], retrieved_at=RID)
            # Now a refresh that fetched nothing but a failure gap.
            out = run_source_ingest(
                index=idx, artifact_dir=Path(tmp), source_id=SRC,
                records=[], gaps=[{"lane": "ecology", "reason": "fetch_failed"}],
                retrieved_at=RID,
            )
            self.assertFalse(out["ok"])
            self.assertTrue(out["refresh_failed"])
            self.assertTrue(out["preserved_existing"])
            # The seeded row survived...
            rows = idx.sql(f"select count(*) as n from records where source='{SRC}' and record_id='{SRC}:row:1'")
            self.assertEqual(int(rows[0]["n"]), 1)
            # ...and the failure gap is queryable.
            g = idx.sql(f"select count(*) as n from record_payloads where source='{SRC}' and payload_json like '%fetch_failed%'")
            self.assertGreater(int(g[0]["n"]), 0)

    def test_gap_only_records_count_as_failure(self):
        # Adapter folds its gap into records (no real rows).
        with tempfile.TemporaryDirectory() as tmp:
            idx = _index(tmp)
            run_source_ingest(index=idx, artifact_dir=Path(tmp), source_id=SRC,
                              records=[_rec(f"{SRC}:row:1")], gaps=[], retrieved_at=RID)
            out = run_source_ingest(
                index=idx, artifact_dir=Path(tmp), source_id=SRC,
                records=[_rec(f"{SRC}:gap:fetch_failed", atom="source_gap")],
                gaps=[{"lane": "ecology", "reason": "fetch_failed"}],
                retrieved_at=RID, persist_gap_records=False,
            )
            self.assertTrue(out["refresh_failed"])
            self.assertEqual(int(idx.sql(f"select count(*) as n from records where source='{SRC}' and record_id='{SRC}:row:1'")[0]["n"]), 1)

    def test_no_double_gap_when_persist_gap_records_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            idx = _index(tmp)
            out = run_source_ingest(
                index=idx, artifact_dir=Path(tmp), source_id=SRC,
                records=[_rec(f"{SRC}:row:1"), _rec(f"{SRC}:gap:x", atom="source_gap")],
                gaps=[{"lane": "ecology", "reason": "x"}],
                retrieved_at=RID, persist_gap_records=False,
            )
            self.assertTrue(out["ok"])
            n = int(idx.sql(f"select count(*) as n from records where source='{SRC}' and record_id like '{SRC}:gap:%'")[0]["n"])
            self.assertEqual(n, 1)  # only the adapter's own gap record, not a duplicate


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_ingest_runner -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'askinsects.ingest_runner'`

- [ ] **Step 3: Write minimal implementation**

```python
# askinsects/ingest_runner.py
from __future__ import annotations

from pathlib import Path

from .gaps import persist_source_gaps
from .index import SourceIndex
from .records import EvidenceRecord


def _is_gap_record(record: EvidenceRecord) -> bool:
    payload = record.payload or {}
    atom = str(payload.get("atom_type") or "")
    return atom.endswith("gap") or ":gap:" in record.record_id


def _source_count(index: SourceIndex, source_id: str) -> int:
    with index.connect() as conn:
        row = conn.execute(
            "select count(*) as n from records where source=?", (source_id,)
        ).fetchone()
    return int(row["n"]) if row else 0


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
) -> dict:
    """Single safe persistence path for every ingest script.

    - Preserves existing rows when a refresh produced no real (non-gap) records.
    - Always makes gaps queryable (unless the adapter already emits gap records,
      in which case pass persist_gap_records=False to avoid duplicates).
    """
    non_gap = [r for r in records if not _is_gap_record(r)]
    refresh_failed = not non_gap and bool(gaps)
    if not refresh_failed:
        index.replace_source_records(source_id, records)
    if persist_gap_records:
        persist_source_gaps(index, source_id, gaps, retrieved_at=retrieved_at)
    preserved_existing = refresh_failed and _source_count(index, source_id) > 0
    installed = _source_count(index, source_id)
    return {
        "ok": not refresh_failed,
        "source": source_id,
        "refresh_failed": refresh_failed,
        "preserved_existing": preserved_existing,
        "record_count": installed,
        "refresh_record_count": len(records),
        "source_gap_count": len(gaps),
        "retrieved_at": retrieved_at,
        "raw_artifacts": raw_artifacts or [],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_ingest_runner -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add askinsects/ingest_runner.py tests/test_ingest_runner.py
git commit -m "feat: run_source_ingest centralizes persist/guard/gap-queryability"
```

---

### Task 3: Parity harness + golden-snapshot generator

**Files:**
- Create: `scripts/gen_parity_snapshot.py` (dev tool, not in the gate)
- Create: `tests/parity/__init__.py` (empty)
- Create: `tests/test_ingest_parity.py`
- Create: `tests/parity/fixtures.py` (per-lane fake fetchers + golden JSON paths)

**Concept:** For each migrated lane we capture `(records, gaps)` from the *current* adapter using deterministic fake fetchers, store it as golden JSON under `tests/parity/golden/<source_id>.json`, and the parity test re-runs the same fakes post-migration and asserts equality.

- [ ] **Step 1: Write the snapshot serializer + a self-test (failing)**

```python
# tests/test_ingest_parity.py
import json
import unittest
from pathlib import Path

from tests.parity.fixtures import LANE_CASES  # list of ParityCase

GOLDEN = Path(__file__).parent / "parity" / "golden"


def _serialize(records, gaps):
    return {
        "records": sorted(
            (
                {
                    "record_id": r.record_id, "lane": r.lane, "source": r.source,
                    "title": r.title, "text": r.text, "species": r.species,
                    "url": r.url, "media_url": r.media_url,
                    "payload": r.payload, "provenance": r.provenance.to_dict(),
                }
                for r in records
            ),
            key=lambda d: d["record_id"],
        ),
        "gaps": sorted((dict(g) for g in gaps), key=lambda d: json.dumps(d, sort_keys=True)),
    }


class IngestParityTests(unittest.TestCase):
    def test_each_migrated_lane_matches_golden(self):
        for case in LANE_CASES:
            with self.subTest(source=case.source_id):
                golden_path = GOLDEN / f"{case.source_id}.json"
                self.assertTrue(golden_path.exists(), f"missing golden for {case.source_id}")
                expected = json.loads(golden_path.read_text())
                result = case.run()  # returns (records, gaps) using fake fetchers
                actual = _serialize(*result)
                self.assertEqual(actual, expected, f"parity drift in {case.source_id}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Create the fixtures scaffold (empty case list) and run to confirm green-on-empty**

```python
# tests/parity/fixtures.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ParityCase:
    source_id: str
    run: Callable[[], tuple[list, list]]  # returns (records, gaps)


# Populated one entry per migrated lane (see migration tasks).
LANE_CASES: list[ParityCase] = []
```

Run: `python3 -m unittest tests.test_ingest_parity -v`
Expected: PASS (0 subtests — empty list is a valid no-op until lanes are added)

- [ ] **Step 3: Write the golden generator**

```python
# scripts/gen_parity_snapshot.py
#!/usr/bin/env python3
"""Generate tests/parity/golden/<source_id>.json from the CURRENT adapter.
Run this BEFORE migrating a lane, on a clean checkout of the lane's old code."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tests.parity.fixtures import LANE_CASES  # noqa: E402
from tests.test_ingest_parity import _serialize  # noqa: E402

GOLDEN = REPO / "tests" / "parity" / "golden"


def main(argv=None):
    GOLDEN.mkdir(parents=True, exist_ok=True)
    targets = set(argv or [])
    for case in LANE_CASES:
        if targets and case.source_id not in targets:
            continue
        records, gaps = case.run()
        (GOLDEN / f"{case.source_id}.json").write_text(
            json.dumps(_serialize(records, gaps), indent=2, sort_keys=True) + "\n"
        )
        print(f"wrote golden for {case.source_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: Commit the harness**

```bash
git add scripts/gen_parity_snapshot.py tests/parity/__init__.py tests/parity/fixtures.py tests/test_ingest_parity.py
mkdir -p tests/parity/golden && touch tests/parity/golden/.gitkeep && git add tests/parity/golden/.gitkeep
git commit -m "test: parity harness + golden snapshot generator for adapter migration"
```

- [ ] **Step 5: Add parity test to the gate**

Modify `scripts/verify_complete.py`: add `"tests.test_ingest_parity"` and `"tests.test_species"` and `"tests.test_ingest_runner"` to `UNIT_TEST_MODULES` (before the closing `)`).

```bash
git add scripts/verify_complete.py
git commit -m "test: run framework + parity tests in completion gate"
```

---

### Migration recipe (canonical — applied by every batch task below)

For each lane `<name>` (adapter `askinsects/sources/<name>.py`, script `scripts/ingest_<name>.py`, source id `<SOURCE_ID>`):

**R1.** Add a `ParityCase` to `tests/parity/fixtures.py` whose `run()` calls the adapter's fetch entrypoint with deterministic fake fetchers (reuse the lane's existing `tests/test_<name>_source.py` fakes; import them) and returns `(result.records, result.gaps)`.

**R2.** Generate the golden snapshot from CURRENT code:
`python3 scripts/gen_parity_snapshot.py <SOURCE_ID>` then `git add tests/parity/golden/<SOURCE_ID>.json`.

**R3.** Migrate the script: replace the hand-rolled persistence block (the `refresh_failed = ...` / `if not refresh_failed: index.replace_source_records(...)` / `persist_source_gaps(...)` / `"ok": ...`) with a single call:

```python
from askinsects.ingest_runner import run_source_ingest
...
outcome = run_source_ingest(
    index=index, artifact_dir=artifact_dir, source_id=<SOURCE_ID>,
    records=result.records, gaps=result.gaps, retrieved_at=retrieved,
    raw_artifacts=getattr(result, "raw_artifacts", None),
    persist_gap_records=<False if the adapter already emits gap records else True>,
)
```
Keep the script's existing status/receipt writing, but source `ok`/`refresh_failed`/`preserved_existing`/counts from `outcome`.

**R4.** Migrate the adapter's species: replace each `species = <row> or "Aedes aegypti"` with `species = resolve_species(<row>, scope="Aedes aegypti")` only where the source is query-pinned to aegypti, else `species = resolve_species(<row>)`. (Per the May 2026 review: 5 sites are scoped, the rest must not fabricate.)

**R5.** Reconcile `config/source-map.yaml`: ensure every gap reason the adapter emits is in that source's `structured_gaps`.

**R6.** Verify the batch:
```bash
python3 -m unittest tests.test_ingest_parity tests.test_ingest_<name> tests.test_<name>_source -v   # per lane in batch
python3 scripts/verify_complete.py    # full gate, retry once if "database is locked"
```
Both must pass. Then commit the batch.

**Parity exception rule:** if a lane cannot reach byte-identical parity because the runner's record set legitimately differs (e.g. gaps newly become queryable rows that did not exist before), regenerate the golden AFTER confirming the only delta is added `source_gap` records (never changed/removed real records), and note the lane in the batch commit message.

---

### Task 4: Migrate batch 1 (already-guarded SWD lanes — lowest risk)

**Lanes:** `drosophila_suzukii_dryad_landscape_monitoring`, `drosophila_suzukii_jki_drosomon_trap_captures`, `drosophila_suzukii_osu_trap_reports`, `drosophila_suzukii_umn_flight_assay_rows`, `drosophila_suzukii_genome_files`, `drosophila_suzukii_occurrence_ecology`, `drosophila_suzukii_extension_guidance`, `drosophila_suzukii_dryad_table_rows`, `drosophila_suzukii_biocontrol_outcome_rows`, `drosophila_suzukii_susceptibility_assay_rows`

- [ ] **Step 1:** Apply recipe R1–R2 for each lane (add ParityCase, generate golden from current code). Commit goldens.
- [ ] **Step 2:** Apply R3–R5 for each lane.
- [ ] **Step 3:** Run R6 (parity + per-lane tests + full gate). Expected: all PASS.
- [ ] **Step 4: Commit**
```bash
git add askinsects scripts config tests
git commit -m "refactor: migrate SWD batch onto ingest_runner + resolve_species"
```

---

### Task 5: Migrate batch 2 (Aedes occurrence/observation lanes)

**Lanes:** `gbif` (via build path), `inaturalist`, `mosquito_alert`, `vectornet_surveillance`, `occurrence_ecology`, `observation_climate`, `aedes_deep_sources`, `harvard_dataverse_suitability`, `irmapper`, `who_malaria_threats_resistance`

- [ ] **Step 1:** Recipe R1–R2 per lane; commit goldens.
- [ ] **Step 2:** Recipe R3–R5 per lane. Note: `mosquito_alert`/`inaturalist` species defaults are query-scoped → use `resolve_species(..., scope=...)`. `aedes_deep_sources` compendium is mixed-species → `resolve_species(...)` with no scope (already fixed May 2026; confirm).
- [ ] **Step 3:** Run R6. Expected: all PASS.
- [ ] **Step 4: Commit** `git commit -m "refactor: migrate Aedes occurrence batch onto framework"`

---

### Task 6: Migrate batch 3 (genomics / expression / proteins)

**Lanes:** `vectorbase_genomics`, `expression_omics`, `uniprot_proteins`, `ncbi_biosamples`, `ncbi_snp_variation`, `pathogen_taxonomy`, `vectorbyte_traits`, `vectorbyte_abundance`, `drosophila_suzukii_deep_sources`, `drosophila_suzukii_ncbi_snp_variation`

- [ ] **Step 1:** R1–R2; commit goldens.
- [ ] **Step 2:** R3–R5. Note: `uniprot_proteins`/`expression_omics` species are taxon-pinned → `scope=`. `ncbi_snp_variation`/`drosophila_suzukii_ncbi_snp_variation` fold gaps into records → `persist_gap_records=False`.
- [ ] **Step 3:** Run R6. Expected: all PASS.
- [ ] **Step 4: Commit** `git commit -m "refactor: migrate genomics/expression batch onto framework"`

---

### Task 7: Migrate batch 4 (resistance / vector competence / literature facets)

**Lanes:** `resistance_markers`, `resistance_table_rows`, `vector_competence_assays`, `extracted_facts`, `aedes_crossref_literature_audit`, `aedes_olfaction_literature`, `mosquito_repellent_literature`, `mosquito_repellent_external_discovery`, `source_coverage`, `wolbachia_interventions`

- [ ] **Step 1:** R1–R2; commit goldens. (`source_coverage` has no fetch/gaps — skip runner migration, document; still add a parity case asserting its records are unchanged.)
- [ ] **Step 2:** R3–R5. Note: `resistance_table_rows`/`vector_competence_assays` parsed-table species → `resolve_species(...)` no scope.
- [ ] **Step 3:** Run R6. Expected: all PASS.
- [ ] **Step 4: Commit** `git commit -m "refactor: migrate resistance/literature batch onto framework"`

---

### Task 8: Migrate batch 5 (video / media / surveillance — remaining lanes)

**Lanes:** all remaining `ingest_*.py` not covered above, including `video_atoms`, `drosophila_suzukii_video_atoms`, `image_atoms`, `dryad_behavior_videos`, `osf_flighttrackai_videos`, `zenodo_aedes_videos`, `figshare_aedes_videos`, `mendeley_behavior_media`, `pmc_videos`, the dengue surveillance family (`cdc`, `paho`, `who`, `ncvbdc`, `opendatasus`), `public_health_guidance`, and any others.

- [ ] **Step 1:** Enumerate remaining lanes: `for f in scripts/ingest_*.py; do ...` confirm each is either migrated or in this batch. R1–R2 per lane; commit goldens.
- [ ] **Step 2:** R3–R5. Note: video/image lanes mostly fold gaps into records (`video_gap`/`image_gap`) → `persist_gap_records=False`.
- [ ] **Step 3:** Run R6. Expected: all PASS.
- [ ] **Step 4: Commit** `git commit -m "refactor: migrate video/surveillance batch onto framework"`

---

### Task 9: Final sweep + verification

- [ ] **Step 1:** Confirm every `ingest_*.py` calls `run_source_ingest` (or is a documented exception):
`grep -L "run_source_ingest" scripts/ingest_*.py` — review each printed file; it must be a documented no-gaps/no-fetch exception.
- [ ] **Step 2:** Confirm no fabrication remains: `grep -rn 'or "Aedes aegypti"' askinsects/sources/` — every remaining hit must be a `resolve_species(..., scope=...)` call or a documented scope comment.
- [ ] **Step 3:** Full parity + gate:
```bash
python3 -m unittest tests.test_ingest_parity -v   # all lanes PASS
python3 scripts/verify_complete.py                # green
```
- [ ] **Step 4:** `/verify` — produce Evaluation Pack at `/tmp/verify-ask-insects-adapter-refactor.html` with parity output + gate output + a before/after lane count.
- [ ] **Step 5: Commit + open PR**
```bash
git push -u origin ask-insects-adapter-framework
gh pr create --title "Source adapter framework: honesty-by-construction" --body-file /tmp/ai_framework_pr.txt --base main
```

---

## Self-Review

**Spec coverage:** runner (Task 2) ✓, species helper (Task 1) ✓, parity harness (Task 3) ✓, batched migration with parity+gate per batch (Tasks 4–8) ✓, structured_gaps reconciliation (R5) ✓, unchanged contract/CLI/index (parity enforces) ✓, final verification + `/verify` (Task 9) ✓.

**Placeholder scan:** the migration recipe is referenced by batch tasks rather than repeated 73× — this is a deliberate canonical-procedure pattern, with the full recipe written once (R1–R6) and each batch supplying its concrete lane list and per-lane notes (scope, fold-in). No "TBD"/"handle edge cases" left.

**Type consistency:** `run_source_ingest` signature, `resolve_species` signature, `_serialize`/`ParityCase`/`LANE_CASES`, and `persist_source_gaps` usage are consistent across Tasks 1–3 and the recipe.

**Known risk carried from spec:** parity for fold-in lanes uses `persist_gap_records=False`; lanes where gaps newly become queryable regenerate golden after confirming the only delta is added `source_gap` records (Parity exception rule).
