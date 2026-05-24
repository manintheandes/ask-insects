# Aedes Aegypti World Intelligence Source Plane Design

## Goal

Make Ask Insects the most comprehensive `Aedes aegypti` intelligence system in the world, full stop.

That means Aedes coverage across literature, genomics, behavior, observations, images, video, neurobiology, vector competence, resistance, ecology, and operational public-health evidence. Other mosquitoes can still be represented as fixture or comparison records, but they are not the completion boundary for this push.

## Source Contract

An Aedes source is real only when it is:

- mapped in repo-local source records or coverage ledgers;
- accessible through a current fetcher, artifact cache, or documented external availability gap;
- atomically queryable at the useful grain with provenance;
- receipted with counts, boundaries, failures, and refresh time;
- wired through the local or hosted Ask Insects query surface.

The system must not claim coverage from a URL, paper, database name, raw folder, or public API until those gates pass.

## Required Intelligence Domains

The comprehensive Aedes system must cover:

- literature;
- genomics;
- behavior;
- observations;
- images;
- video;
- neurobiology;
- vector competence;
- resistance;
- ecology;
- public health and operations.

The durable coverage ledger is:

```text
config/mosquito-intelligence-coverage.json
```

That ledger is a source-contract backlog, not a marketing roadmap. It names what is source grade, what is thin, what is planned, and what is a source gap.

## Current State

Ask Insects already has strong foundations:

- Aedes literature since 2020 from OpenAlex, enriched by PubMed and Unpaywall when available.
- Aedes NCBI genome package parsing for assembly, genes, transcripts, genome features, and proteins.
- Aedes neurobiology records from MosquitoBrains, GEO/SRA metadata, Mosquito Cell Atlas, CATMAID metadata, skeleton export metadata, and explicit whole-brain connectome gaps.
- Fixture-backed taxonomy, observations, media references, and action notes.

Those are foundations, not completion. The major missing Aedes lanes are video, vector competence, insecticide resistance, operational public health, behavior, ecology, and broader Aedes genomics.

## Target Architecture

Each new domain follows the existing lane pattern:

```text
source registry -> bounded fetch or artifact cache -> parser -> SQLite records/payloads -> receipts/gaps -> CLI/hosted query -> tests
```

Use these lane families:

- `behavior`: curated Aedes behavior papers, trajectory datasets, assay metadata, host-seeking, biting, oviposition, mating, flight, circadian behavior, and larval behavior.
- `media`: Aedes still images, videos, acoustic records, labels, licenses, source URLs, and inspectable media locators.
- `observations`: GBIF, iNaturalist, Mosquito Alert, surveillance occurrence records, collection metadata, and trap context for Aedes.
- `genomics`: NCBI, VectorBase or successor resources, BOLD barcode data, orthology, variants, expression, microbiome, and resistance markers for Aedes.
- `neurobiology`: current Aedes brain atlas and CATMAID work plus any additional public Aedes neurobiology sources.
- `vector_competence`: pathogen, strain, assay, mosquito population, infection, dissemination, transmission, and experimental conditions.
- `resistance`: insecticide susceptibility, mechanism, mutation, assay protocol, geography, and time.
- `ecology`: climate, habitat, breeding sites, land use, seasonality, and range models.
- `public_health`: surveillance, outbreak, intervention, disease, and operational-control records.

## Query Behavior

Ask Insects should answer from indexed source records first. If a user asks for a domain that is not source grade, the answer should name the missing domain and source gap. It should not substitute model memory or nearby domains.

Examples:

- "show mosquito videos from Brazil" should return video evidence or a video source gap.
- "what resistance mutations are mapped for Aedes aegypti?" should return resistance records or a resistance source gap.
- "what vector competence data exists for dengue and Aedes albopictus?" should return assay records or a vector-competence source gap.
- "what behavior data do we have?" should distinguish literature mentions from source-grade behavior datasets.

## Validation

The completion gate must verify:

- the coverage ledger exists;
- the Aedes aegypti scope is explicit;
- every required intelligence domain is present;
- every domain declares the five source-contract gates;
- incomplete domains declare next sources and completion evidence;
- docs link to the ledger;
- existing deterministic fixture tests still pass.

This spec does not complete the world-comprehensive Aedes goal. It makes the real target mechanically visible so each next source lane can be built, parsed through `@insectsource`, shipped to Ask Insects, and verified end to end.
