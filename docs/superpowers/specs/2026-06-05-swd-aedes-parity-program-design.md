# Drosophila Suzukii → Aedes Parity Program Design

Date: 2026-06-05

## Purpose

Bring the `Drosophila suzukii` (spotted wing drosophila, SWD) source plane to structural parity with the `Aedes aegypti` plane: every data category that applies to a crop pest has a SWD source feeding it on the hosted plane, pulling what genuinely exists and recording honest, queryable gaps where it does not.

This completes the program started in `2026-05-28-drosophila-suzukii-source-plane-design.md`, which founded the SWD boundary and explicitly deferred behavior/video, NCBI genomics, crop-damage ecology, pest-management, resistance, and biocontrol as `source_coverage` gaps. Many of those have since been built (25 SWD source modules exist). This spec closes the remaining gaps to parity.

## Parity Definition (decided)

- **Coverage parity, not count parity.** Every *applicable* Aedes category must have a SWD source. Record counts will be smaller where the underlying science is thinner. We never pad or fabricate to match a number; `species.resolve_species` already encodes "never invent a species," and `gaps.py` makes absence queryable. A category with a single honest `source_gap` record ("this barely exists for SWD") counts as covered.
- **Applicable only.** Human-disease categories are out of scope: disease surveillance (CDC/WHO/PAHO/NCVBDC/OpenDataSUS dengue), pathogen transmission (`vector_competence`), `wolbachia_interventions`, and `public_health`. SWD's existing `crop_damage`, `management`, and `biocontrol` lanes are the legitimate crop-pest equivalents and satisfy parity for that branch.
- **Done = built + hosted + verified.** Each category ends with its records live on the hosted plane (`--hosted`, VM artifact dir `/home/josh/ask-insects/artifacts/mosquito-v1/`) and passing the parity completion gate.

## Category Worklist

Baseline gap measured 2026-06-05 against the hosted plane (mosquito count → SWD count). Each category is assigned a bucket.

### Bucket 1 — Run-only (species-aware command already exists)

These CLI commands already accept `--species`; SWD parity is a hosted run with `--species "Drosophila suzukii"`. No new module code.

| Category | Command | Mosq → SWD | Notes |
|---|---|---|---|
| Biosamples | `ingest-ncbi-biosamples` | 20,656 → 50 | Straight NCBI taxon query. |
| Photos / media | `ingest-inaturalist` | (media 31,792 → 620) | Licensed SWD photos exist. |
| Occurrences | `ingest-gbif` | (observations 96,236 → 2,000) | SWD occurrence already partial; deep-refresh. |
| Genome variation | `ingest-ncbi-snp-variation` | — | Expect gap-heavy; SWD dbSNP sparse. |
| Resistance map | `ingest-irmapper` | (resistance) | IR-Mapper is mosquito-scoped; likely gap-only for SWD — record honestly. |

### Bucket 2 — Build new SWD module (curated or mosquito-hardwired)

Each needs `askinsects/sources/drosophila_suzukii_<category>.py` + `scripts/ingest_drosophila_suzukii_<category>.py` + test, on `run_source_ingest` with `gaps.py`, plus its own design doc.

| Category | Mosq → SWD | Difficulty | Note |
|---|---|---|---|
| **Brain / neurobiology** | 100,018 → 0 | Hard | Hand-curated for Aedes (MosquitoBrains atlas, cell atlas, antennal-lobe maps). SWD analogs are sparse; expect substantial honest gaps. **First sub-project.** |
| **Olfaction literature** | (part of smell gap) → ~0 | Medium | OpenAlex/PubMed query for SWD chemosensation; bundled with brain sub-project. |
| Life-history traits | 4,972 → 0 | Medium | VectorByte is mosquito-only; find SWD trait source (literature trait tables / DrosoPhyla-style). |
| Behavior datasets/video | 109,374 → 1,463 | Medium-hard | Expand `drosophila_suzukii_video_atoms`; add structured-assay sources. |
| Image atoms | (media) → thin | Medium | SWD image-atom derivation from available imagery. |
| Resistance markers/tables | 34,952 → 211 | Medium | SWD literature-derived markers; expand existing susceptibility lane. |

### Bucket 3 — Skip (out of scope)

`vector_competence`, `public_health`, `wolbachia_interventions`, all dengue-surveillance lanes. Covered by SWD `crop_damage` / `management` / `biocontrol`.

## Shared Recipe (per Bucket-2 category)

1. Write a per-category design doc (`docs/superpowers/specs/YYYY-MM-DD-swd-<category>-lane-design.md`).
2. Add source module returning `(records, gaps)`; pull only what genuinely names `Drosophila suzukii` / spotted wing drosophila in source metadata.
3. Persist via `run_source_ingest` so a gap-only run preserves existing rows and records honest gaps; for legitimately gap-as-content lanes, follow `docs/source-adapter-runner-exceptions.md`.
4. Add a CLI subcommand `ingest-drosophila-suzukii-<category>` and an ingest script.
5. Tests with fake payloads: prove correct lane/species/source-id, gap behavior, and non-destruction of Aedes rows.
6. Run against `--hosted`; confirm record/gap counts in the run receipt.
7. Pass the parity completion gate.

## Completion Gate (parity enforcement)

The existing `scripts/verify_complete.py` is Aedes-shaped (it enumerates required Aedes spec files and coverage configs). Parity needs an explicit, machine-checked definition for SWD:

- Add `config/swd-source-plane-benchmark.json` mirroring `config/aedes-source-plane-benchmark.json`: the list of applicable categories and, per category, the minimum "covered" condition (≥1 non-gap record OR ≥1 honest `source_gap` record).
- Extend `verify_complete.py` (or add `scripts/verify_swd_parity.py`) to assert every applicable category resolves to "covered" on the hosted/local index and that each new SWD spec file exists in `REQUIRED_FILES`.
- The program is complete when this gate passes with zero uncovered applicable categories.

## Decomposition & Order

This is a program of per-category sub-projects, each its own spec → plan → implementation, mirroring how Aedes was built (one design doc per lane).

1. **SWD brain/smell** (neurobiology + olfaction literature) — built first; see `2026-06-05-swd-neurobiology-olfaction-lane-design.md`.
2. Life-history traits.
3. Behavior datasets/video + image atoms.
4. Resistance markers/tables.
5. Bucket-1 run-only sweep (biosamples, iNaturalist, GBIF, SNP, IR-Mapper) — can run in parallel any time; low risk.
6. Parity gate config + verifier.

## Non-Goals

- No refactor of the working Aedes modules into species-generic form (rejected: high risk, repo is Aedes-focused, curated lanes can't be parameterized).
- No count-matching or filler data.
- No disease/vector categories.
