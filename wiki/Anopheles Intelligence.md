---
title: Anopheles Intelligence
type: source-program
status: development
publish: true
tags:
  - ask-insects
  - anopheles
  - malaria-vectors
sources:
  - ../config/anopheles-intelligence-coverage.json
  - ../config/source-map.yaml
  - ../docs/source-lanes.md
---

# Anopheles Intelligence

Ask Insects is building a source-backed Anopheles intelligence system for the `Anopheles gambiae` complex, `Anopheles gambiae`, `Anopheles coluzzii`, `Anopheles funestus`, `Anopheles stephensi`, and other major regional malaria vectors.

The goal is to make Anopheles evidence deeper and more useful than the current Aedes evidence plane. That has not been proven yet.

## Current Development Lanes

- `anopheles_source_coverage`: a queryable ledger covering 16 scientific domains and the sources still needed.
- `anopheles_literature_openalex`: 3,457 historical-to-current literature records across twenty priority species, the Gambiae complex, and thirteen R&D topics, plus 5,482 explicit metadata/enrichment gaps, with exact OpenAlex and saved raw-page provenance.
- `anopheles_gbif_occurrences`: 520 bounded GBIF taxonomy and occurrence records across twenty priority species.
- `anopheles_ncbi_biosamples`: 2,688 accession-level NCBI BioSample records across twenty priority species, plus explicit gaps, including geography, collection date, tissue, isolation source, isolate, strain, and linked SRA identifiers when present.
- `anopheles_uniprot_proteins`: bounded UniProtKB protein and proteome metadata for eight priority species, using NCBI-verified taxonomy identifiers and preserving function, GO, VectorBase cross-references, and exact API locators.
- `anopheles_ncbi_sra_runs`: 1,444 run-level NCBI SRA records across twenty priority species, plus explicit gaps, with linked experiments, BioProjects, BioSamples, platforms, library strategies, run sizes, and exact raw summary locators.
- `anopheles_ncbi_assemblies`: 122 accession-level NCBI Assembly records across twenty searched species, plus four explicit zero-result gaps, including assembly level, linked BioProject and BioSample, release and quality fields, download paths, and exact raw summary locators.
- `anopheles_ncbi_genome_features`: 1,427,103 assembly-scoped records across thirteen parsed reference genomes: Gambiae, Stephensi, Coluzzii, Funestus, Arabiensis, Minimus, Sinensis, Albimanus, Darlingi, Aquasalis, Merus, Nili, and Moucheti. Records include genes, transcripts, selected functional annotations, proteins, GO assertions, available gene-expression profiles, and explicit source-file gaps with exact provenance.
- `anopheles_who_malaria_resistance`: WHO malaria-vector insecticide-resistance assay rows with species, place, time, test, chemical, mortality, status, mechanism, and citation fields when supplied.
- `anopheles_pathogen_taxonomy`: ten NCBI Taxonomy identity anchors for major human malaria parasites and laboratory Plasmodium models. These identify pathogens but do not by themselves establish vector competence or transmission.
- `anopheles_vector_competence_evidence`: 90 exact abstract-level numeric endpoint rows derived from the 3,457 real Anopheles literature works. The current local rows comprise 34 field-surveillance results, 3 controlled experimental results, and 53 results with unclear abstract context. Each retains the exact result sentence and original raw OpenAlex locator; modeled projections and methods-only numeric sentences are excluded, and full-text-table validation remains a gap.

Each real source lane preserves the upstream source URL, a saved raw-response locator, the retrieval time, and a receipt describing what was fetched, bounded, skipped, or incomplete.

## Current Boundaries

These lanes do not yet prove complete Anopheles coverage. The literature lane still needs PubMed and Crossref reconciliation, legal full text, supplement audits, and parsed scientific tables. GBIF is a bounded occurrence sample, not complete surveillance or range modelling. BioSample and SRA run metadata do not mean raw reads were downloaded, aligned, or analysed. The NCBI expression profiles preserve supplied count-table values but are not new differential-expression analyses. Several target assemblies lack usable NCBI annotation or expression files, and VectorBase or VEuPathDB annotations remain gaps.

Major work remains in VectorBase and VEuPathDB genome features and sequences, expression and population genomics, insecticide resistance, vector competence, pathogen interactions, host seeking, sensory biology, neurobiology, oviposition, larval ecology, microbiome and symbionts, control methods, repellents, public-health guidance, images, videos, and field surveillance.

The Anopheles program is not complete or hosted until deployment and a realistic black-box evaluation through normal Codex prove accurate, source-based answers under 60 seconds.
