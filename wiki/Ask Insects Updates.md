---
title: Ask Insects Updates
type: updates
status: active
publish: true
tags:
  - insects-wiki
  - ask-insects
  - updates
  - release-notes
---
# Ask Insects Updates

This page tracks meaningful Ask Insects changes. Most updates do not require user action.

Latest Ask Insects source-plane update: 2026-07-22.

## 2026-07-22

### Anopheles Development
- Added eleven Anopheles development lanes: a 16-domain coverage ledger, bounded OpenAlex literature, bounded GBIF taxonomy and occurrence records, accession-level NCBI BioSample metadata, bounded UniProt protein and proteome metadata, run-level NCBI SRA metadata, NCBI assembly metadata, parsed NCBI reference-genome features, WHO malaria-vector resistance assay rows, NCBI Taxonomy anchors for Plasmodium pathogens, and 90 exact abstract-level numeric infection or transmission endpoint records.
- The NCBI BioSample lane parses geography, collection date, tissue, isolation source, isolate, strain, and linked SRA identifiers with exact raw-response locators and per-species receipts.
- Added Anopheles-specific answer behavior that keeps Aedes samples out of Anopheles answers and reports an explicit source gap when a requested species or place is absent from the bounded index.
- Added verified NCBI taxonomy identifiers for all eight UniProt target species and kept Aedes protein records in a separate source lane.
- Added run-level SRA parsing with experiment, BioProject, BioSample, platform, library, spots, bases, and size fields while keeping raw-read downloads and reanalysis as explicit gaps.
- Expanded NCBI Assembly, BioSample, SRA, and GBIF searches to twenty priority species. The local build contains 122 assembly records plus four zero-result gaps, 2,688 BioSamples plus seven gaps, 1,444 SRA runs plus thirteen gaps, and 520 GBIF taxonomy or occurrence records.
- Parsed the Anopheles gambiae reference GFF, protein FASTA, Gene Ontology GAF, and raw and normalized expression tables into 141,777 atomic source entries: 14,803 genes, 33,662 transcripts, 6,160 functional coding segments, 30,505 proteins, 41,482 GO assertions, and 15,165 gene-expression profiles. Each entry cites an exact source-file line or FASTA record, and the receipt preserves SHA-256 hashes for all five source files.
- Added 125,160 Anopheles stephensi reference-genome entries from `GCF_013141755.1`: 15,187 genes, 33,324 transcripts, 29,660 proteins, and 46,989 functional or GO records. NCBI exposes no expression-count tables in that assembly directory, so the missing Stephensi expression file is queryable as a source gap.
- Made genome refreshes assembly-scoped and per-assembly receipted. Thirteen parsed reference genomes now coexist as 1,427,103 genome-source records without one species refresh erasing another. The parsed species are Gambiae, Stephensi, Coluzzii, Funestus, Arabiensis, Minimus, Sinensis, Albimanus, Darlingi, Aquasalis, Merus, Nili, and Moucheti; unusable or absent annotation files for other targets are explicit source gaps.
- Added 10,000 distinct WHO MAL_THREATS Anopheles rows with named insecticides, spanning more than 60 Anopheles labels. Structured question filters use the WHO species, insecticide, year, country, and locality fields, so a chemical mentioned only in a citation cannot satisfy an assay query.
- Added ten NCBI Taxonomy identity anchors for major human malaria parasites and laboratory Plasmodium models. The answer path explicitly separates pathogen identity from evidence that a mosquito supports infection or transmission.
- Expanded OpenAlex discovery from a 2020-to-current, five-species, 250-work design to historical-to-current searches across twenty priority species, the Gambiae complex, and thirteen scientific topics. The refreshed lane contains 3,457 works plus 5,482 explicit missing-abstract, missing-DOI, or skipped-PubMed gaps.
- Added species-locked Anopheles domain routing so host-seeking, oviposition, ecology, and neurobiology questions cannot fall through to Aedes records or a different Anopheles species.
- The current local Anopheles plane contains 1,455,002 records across eleven source lanes. This exceeds the May 28 hosted Aedes record count numerically, but depth, breadth, hosted parity, and the Anopheles black-box evaluation are not yet proven.
- Added [[Anopheles Intelligence]] with current evidence lanes and remaining gaps. This work remains a local development build until hosted deployment and black-box evaluation are proven.

### Public Overview Refresh
- Updated [[Ask Insects]] from the older mosquito-first description to the current Open Insects direction: SWD crop repellent, human mosquito repellent, and diamondback moth expansion.
- Clarified that Ask Insects is a public evidence system. Private Monarch experiments can use Ask Insects as public context, but private R&D data does not flow into Ask Insects and cannot fill public evidence gaps.
- Added the shared biology-domain model: sensory systems, brain and neurobiology, genes and proteins, physiology, behavior, egg laying, feeding, movement, ecology, chemical response, learning and internal state, development, and adaptation or resistance.
- Added current product-program sections for SWD, Aedes human mosquito repellency, and diamondback moth.
- Added an `Ask+Insects.md` alias note so the published URL that resolves to `Ask+Insects.md` has a source file instead of showing a missing-note page.

### Shipped Route Hardening
- Shipped Ask Insects commit `712aa0d` end to end: merged to `main`, deployed to the hosted Ask Insects VM, installed runtime and skill refreshed, and a fresh Codex app canary completed with a full sourced answer in 18.481 seconds.
- The saved Codex project now keeps the reliable low-reasoning normal route and explicitly uses the fast service tier. The repo-owned skill metadata now says not to emit commentary, status updates, or preambles before the hosted answer command.
- `python3 scripts/verify_complete.py` now checks the normal-question project config, including the fast service tier. This repository check does not replace the private 50-question Reality Eval pass and recording.

## 2026-05-28

### Hosted Source Plane
- Hosted Ask Insects health reports 1,388,102 source records.
- Current hosted lanes include 585,275 genome-feature records, 109,374 behavior records, 102,915 transcript records, 100,018 neurobiology records, 96,236 observation records, 65,423 public-health records, 56,960 protein records, 52,950 literature records, 44,121 expression records, 39,045 gene records, 34,952 resistance records, 31,792 media records, 23,273 vector-competence records, 20,656 BioSample records, 16,382 ecology records, 4,972 trait records, 3,561 DNA-barcode records, 142 dataset records, 41 source-coverage records, and 2 patent records.
- The current coverage ledger is honest about incompleteness: 11 tracked Aedes domains are partial source-grade, with 29 queryable missing-source gaps.

### Shipped Behavior And Video Fix
- Shipped Ask Insects commit `55aec35` end to end: merged to `main`, pushed, deployed to the hosted Ask Insects VM, service restarted, local installed `ask-insects` refreshed, and live hosted behavior verified.
- Ask Insects now answers `show Dryad Figure_S7 archive gap` with the exact Dryad missing-source row first: `dryad:gap:10_5061_dryad_qz612jmrb:figure_s7_zip:archive_contents_not_decoded`.
- Video archive downloads now preserve attempted locators and can fall back to Dryad file-stream URLs when the primary API download route is blocked.

### Known Boundaries
- The public site should not claim Ask Insects is complete. The largest remaining Aedes behavior gaps are decoded Dryad trajectory tables, deeper acoustic features, high-speed video/archive parsing, repellent and attractant assay datasets, and host-seeking or oviposition experiment metadata.

## 2026-05-27

### Hosted Source Plane
- Hosted Ask Insects health reports 1,463,819 source records.
- Current hosted lanes include 767,732 genome-feature records, 106,930 behavior records, 102,915 transcript records, 100,736 observation records, 100,018 neurobiology records, 59,422 public-health records, 56,960 protein records, 39,045 gene records, 28,094 resistance records, 26,208 media records, 23,494 literature records, 11,525 vector-competence records, 11,005 ecology records, 4,972 trait records, 3,561 DNA-barcode records, 422 expression records, 110 dataset records, and 2 patent-source-status records.

### New And Expanded Sources
- Expanded official Brazil OpenDataSUS SINAN dengue surveillance to the full default public annual backfile span from 2007 through 2026.
- Hosted OpenDataSUS now has 29,402 aggregate public-health records from 30,767,966 source CSV rows across 20 public annual ZIP files.
- Ask Insects now answers hosted Brazil OpenDataSUS dengue questions for historical years such as 2007 and 2015 from OpenDataSUS records, with year-specific source file locators.

## 2026-05-26

### Hosted Source Plane
- Hosted Ask Insects health reports 1,425,639 source records.
- Current hosted lanes include 767,732 genome-feature records, 106,917 behavior records, 102,915 transcript records, 100,736 observation records, 100,018 neurobiology records, 56,960 protein records, 39,045 gene records, 31,964 public-health records, 28,365 resistance records, 26,208 media records, 12,802 literature records, 11,344 vector-competence records, 10,898 ecology records, 4,972 trait records, 3,561 DNA-barcode records, 422 expression records, 110 dataset records, and 2 patent-source-status records.

### New And Expanded Sources
- Expanded VectorBase/VEuPathDB to include codon usage, identifier events, current-ID resolution, NCBI LinkOut, OrthoMCL pair records, and orthogroup membership.
- Added mosquito repellent literature since 2020 from PubMed and Crossref public metadata.
- Added external repellent discovery across OpenAlex, Europe PMC, AGRICOLA-through-Europe-PMC, Semantic Scholar, Crossref posted-content preprints, DataCite, Zenodo, and Figshare.
- Added queryable gap rows for native bioRxiv/medRxiv text search, PatentsView, USPTO Open Data Portal, CABI, and Google Scholar.
- Added or expanded expression metadata, UniProt proteins, VectorByte traits and abundance, image atoms, video atoms, VectorNet surveillance, CDC dengue surveillance, WHO dengue surveillance, resistance-table rows, and extracted-fact records.
- Shipped the safe incremental extracted-facts refresh path so a one-paper refresh no longer shrinks the full Aedes extracted-facts lane.
- Shipped the video-atom cleanup pass that filters non-video data files, keeps queryable video gaps, and preserves verified mirrored video artifacts.
- Hosted video atoms now include 46,252 queryable records, including 84 video assets, 21 verified video assets, 407 structured video gaps, 116 keyframes, 21 thumbnails, 21 preview clips, 21 frame manifests, and 45,574 motion rows.
- Shipped safe repository-scoped video refreshes, proven with a Dryad-only hosted pass that accepted 29 candidates from 71 raw Dryad discovery candidates and cleared stale Dryad candidate rows without shrinking the other video repositories.
- Shipped official India NCVBDC dengue surveillance with 221 hosted public-health records and a queryable latest-two-complete-year summary for India dengue deaths.
- Shipped official Brazil OpenDataSUS SINAN dengue surveillance with 2,177 hosted aggregate public-health records from 1,956,578 source CSV rows, including country-year, state-year, country-week, and residence-state-week records.
- Hosted extracted facts now include 7,653 queryable records, with promoted vector-competence and resistance table rows still available through their dedicated answer lanes.

### Documentation
- Updated the public Open Insects vault source map and source pages to reflect the current hosted source plane.
- Added a dedicated [[Sources/Repellent Discovery]] page.

## 2026-05-24

### New Sources
- Added hosted Aedes aegypti source coverage for GBIF, iNaturalist, Mosquito Alert, NCBI genome and BioSample records, VectorBase/VEuPathDB, BOLD, OpenAlex literature, Dryad, Mendeley, OSF FlightTrackAI, PMC videos, IR Mapper, PAHO, WHO, CDC, ECDC, and neurobiology artifacts.
- Added CATMAID skeleton metadata and explicit whole-brain connectome source-gap records.
- Added neurobiology records for brain atlas, cell atlas, MosquitoBrains, SRA workflow metadata, H5AD internals, and coordinate-queryable voxel access.

### Hosted Source Plane
- Hosted Ask Insects is running on the Ask Insects server with SQLite at `/home/josh/ask-insects/artifacts/mosquito-v1/source_index.sqlite`.
- Current hosted health reports 436,182 source records.
- The source plane is Aedes aegypti first.

### Documentation
- Added this Obsidian vault using the same page family as Ask Monarch and Ask Just.
- Added source pages, a source map, question cookbook, skills page, deep research guide, and setup page.
- Added a real `ask-insects setup --url ... --token ...` command so the public setup flow can end with `status: ready`.
- Updated the setup, team setup, and skills pages to match the Ask Monarch wiki shape more closely.
- Added a hosted CATMAID skeleton manifest proof image to the Insects Skills page.
- Restarted the hosted Ask Insects service after a stale SQLite lock and re-verified hosted health plus a source-backed CATMAID query.

### Known Boundaries
- Ask Insects does not yet claim a complete public whole-brain Aedes connectome bulk package.
- Large video archives are mostly manifest-level unless a receipt proves binary mirroring and deep parsing.
- PAHO/PLISA country-week dashboard rows remain a source gap until stable machine-readable access or authorized access exists.
- Compute-heavy raw SRA alignment/count reanalysis is not claimed unless future receipts prove it was executed.

## Future Updates

Future notes should be concrete. If there is no user-facing source, routing, setup, or documentation change, no note is needed.

<!-- publish-bump: 2026-05-28T12:54:25-07:00 -->
