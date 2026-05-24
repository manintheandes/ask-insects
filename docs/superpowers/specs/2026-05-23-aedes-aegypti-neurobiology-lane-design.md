# Aedes Aegypti Neurobiology Lane Design

## Purpose

Ask Insects needs a first brain and neuron source lane for `Aedes aegypti`. This lane should let the CLI answer initial questions about mosquito brain regions, neuron-related datasets, sensory circuits, and brain transcriptomics without falling back to model memory or web search.

The first build is intentionally narrow. It proves the source contract with small, durable, provenance-rich records. It does not download or parse the full Mosquito Cell Atlas H5AD bundles, raw SRA runs, or large image volumes.

## Source Boundary

The first neurobiology lane covers public `Aedes aegypti` brain and neuron source metadata:

- `mosquitobrains.org` female brain atlas pages and downloadable reference-brain / segmentation links.
- GEO series `GSE160740`, a male and female brain single-nucleus RNA-seq study.
- Mosquito Cell Atlas metadata and Zenodo record metadata for future H5AD and cell annotation ingestion.
- Selected source-backed neurobiology study records for antennal lobe, olfactory sensory neuron, and cell atlas context.

The lane name is `neurobiology`. The source id is `aedes_neurobiology_sources`.

## Atomic Records

The source parser emits one record per useful source atom:

- brain atlas resource
- downloadable brain reference or segmentation artifact
- GEO brain snRNA-seq dataset
- cell atlas data package
- neurobiology study

Each record includes:

- `record_id`
- `lane=neurobiology`
- `source=aedes_neurobiology_sources`
- title and plain-English text
- species
- public URL
- provenance with source id, locator, source URL, retrieved date, and license or access note
- raw payload in SQLite `record_payloads`

## Query Behavior

Questions containing brain, neuron, neurobiology, neural, antennal lobe, olfactory sensory neuron, glia, mushroom body, connectome, snRNA, single nucleus, or cell atlas route to `neurobiology` first.

If the question also contains receptor terms, Ask Insects should still check neurobiology before genomics because Josh is asking about cells, circuits, or brain context, not only protein names.

Answer shape is `neurobiology`. The answer text should say it is coming from the local mosquito neurobiology index.

## Build Behavior

The build script gets a new opt-in flag:

```bash
python3 scripts/build_source_index.py --fixtures --neurobiology
```

The deterministic default uses repo-local source metadata, not live scraping. It writes receipts into the standard mosquito artifact directory and can be combined with NCBI genomics:

```bash
python3 scripts/build_source_index.py \
  --fixtures \
  --ncbi-genome \
  --genome-package-dir /path/to/GCF_002204515.2 \
  --neurobiology
```

## Completion Criteria

- Neurobiology source is mapped in `config/source-map.yaml`.
- The parser has deterministic unit tests.
- The builder can combine fixture and neurobiology records.
- Brain and neuron questions route to `neurobiology`.
- Answers include neurobiology evidence and provenance.
- The completion gate requires the source file, tests, spec, and plan.
- The installed `ask-insects` command can answer at least:

```bash
ask-insects ask "what neuron data exists for the Aedes aegypti brain?" --json
ask-insects search neurobiology "brain atlas" --limit 3
```

## Explicit Gaps

- Full H5AD / cell matrix ingest is not in this slice.
- Raw SRA download and reanalysis is not in this slice.
- A complete mosquito connectome is not claimed.
- Brain image volume parsing is not in this slice.
- Cross-linking cell types to NCBI genes is future work after this lane exists.
