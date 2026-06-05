# Drosophila Suzukii Neurobiology + Olfaction Lane Design

Date: 2026-06-05

First sub-project of `2026-06-05-swd-aedes-parity-program-design.md`. Chosen first because it is the highest-value (repellency-relevant) and hardest category: the Aedes neurobiology lane (100,018 records) is hand-curated and has no SWD equivalent (0 records). Building it first surfaces early how much SWD brain/chemosensory data genuinely exists.

## Purpose

Give Ask Insects a first brain / neuron / chemosensation source lane for `Drosophila suzukii`, so the CLI can answer questions about SWD brain regions, sensory circuits, antennal/olfactory transcriptomics, and chemoreceptor biology from the local source index instead of model memory or web search.

The build is intentionally narrow and source-grade. It is explicit that SWD is far less studied at the brain level than Aedes, and far less than its relative *Drosophila melanogaster*. Where only out-of-species (D. melanogaster) analogs exist, they are recorded as honest gaps, not as SWD coverage.

## Source Boundary

Covers public `Drosophila suzukii` brain, neuron, and chemosensory source metadata that genuinely names the species:

- SWD antennal / chemosensory transcriptome datasets in GEO/SRA (e.g. olfactory receptor [Or], ionotropic receptor [Ir], gustatory receptor [Gr] expression studies in SWD antennae and ovipositor).
- Published SWD chemosensation / neuroethology literature (host-seeking, oviposition cue, CO2/odor response) from OpenAlex and PubMed.
- SWD reference-genome chemoreceptor gene annotations already in the plane, cross-referenced (read-only) for context.
- Queryable `source_gap` records for every brain/chemosensory domain that exists for Aedes/D. melanogaster but not for SWD (e.g. whole-brain atlas, connectome, single-nucleus brain RNA-seq, antennal-lobe map).

The lane name is `neurobiology`. The source id is `drosophila_suzukii_neurobiology_sources`.

A sibling olfaction-literature pass uses source id `drosophila_suzukii_olfaction_literature` (lane `literature`), mirroring `aedes_olfaction_literature`: it queries SWD chemosensation papers, matches against already-indexed SWD OpenAlex rows, and adds metadata-only candidates with honest match counts.

## Atomic Records

One record per useful source atom:

- SWD antennal/chemosensory transcriptome dataset (GEO/SRA)
- SWD chemoreceptor study (Or/Ir/Gr biology)
- SWD neuroethology / host-seeking / oviposition-cue study
- chemosensory gene-annotation context record (derived, read-only join to existing genome features)
- `source_gap` record for each absent brain/chemosensory domain

Each non-gap record includes: `record_id`; `lane`; `source`; title and plain-English text; `species="Drosophila suzukii"` via `resolve_species` (never a fabricated default); public URL; provenance (source id, locator, source URL, retrieved date, license/access note); raw payload in `record_payloads`.

## Query Behavior

Questions containing brain, neuron, neurobiology, neural, antennal, antennae, olfactory, olfaction, chemosensory, chemoreceptor, odorant receptor, Or/Ir/Gr, gustatory, oviposition cue, host-seeking, or sensory route to `neurobiology` first, then `literature`. Receptor-term questions still check neurobiology before genomics (the user is asking about circuits/cells, not only protein names). Answer text states it is coming from the local SWD neurobiology index, and surfaces the relevant gap record when coverage is thin.

## Build Behavior

New CLI subcommands following the adapter-framework pattern:

```bash
python3 -m askinsects ingest-drosophila-suzukii-neurobiology --hosted
python3 -m askinsects ingest-drosophila-suzukii-olfaction-literature --hosted
```

Both return `(records, gaps)` and persist via `run_source_ingest` with `persist_source_gaps`, so a gap-only run preserves existing rows and still records honest gaps. Deterministic default uses repo-local/curated source metadata plus bounded API queries (OpenAlex/PubMed/NCBI E-utilities), not unbounded scraping. Raw payloads land under `raw/drosophila_suzukii_neurobiology/` and `raw/drosophila_suzukii_olfaction_literature/`.

Because gap-only output is a legitimate scientific result for SWD brain data, if `run_source_ingest`'s gap-guard would drop a gap-only run, the lane is added to `docs/source-adapter-runner-exceptions.md` and folds gap EvidenceRecords (`:gap:` in `record_id`) into `result.records`, matching the documented pattern used by `drosophila_suzukii_susceptibility_assay_rows` and others.

## Completion Criteria

- Both sources mapped in `config/source-map.yaml`.
- Deterministic unit tests with fake GEO/SRA/OpenAlex/PubMed payloads prove: correct lane/species/source-id; gap records emitted for absent domains; Aedes and existing SWD rows untouched.
- Brain/neuron/chemosensory questions route to `neurobiology`.
- Records (or honest gaps) live on the hosted plane; run receipt reports record and gap counts.
- New spec file added to `verify_complete.py` `REQUIRED_FILES`; SWD parity benchmark marks the neurobiology and olfaction categories as covered.
- The installed `ask-insects` command can answer at least:

```bash
ask-insects ask "what chemosensory or brain data exists for Drosophila suzukii?" --hosted --json
ask-insects search neurobiology "antennal transcriptome" --hosted --limit 3
```

## Explicit Gaps

- No SWD whole-brain atlas, connectome, or single-nucleus brain RNA-seq is claimed; each is recorded as a `source_gap` if absent.
- *Drosophila melanogaster* brain/connectome resources are out-of-species comparison material only; they are NOT installed as SWD coverage.
- Full H5AD / cell-matrix and raw SRA reanalysis are out of this slice.
- Cross-linking chemoreceptor cell types to SWD genes beyond simple annotation context is future work.
