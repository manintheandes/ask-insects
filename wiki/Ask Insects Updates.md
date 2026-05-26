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

Latest Ask Insects source-plane update: 2026-05-26.

## 2026-05-26

### Hosted Source Plane
- Hosted Ask Insects health reports 1,423,241 source records.
- Current hosted lanes include 767,732 genome-feature records, 106,917 behavior records, 102,915 transcript records, 100,736 observation records, 100,018 neurobiology records, 56,960 protein records, 39,045 gene records, 29,566 public-health records, 28,365 resistance records, 26,208 media records, 12,802 literature records, 11,344 vector-competence records, 10,898 ecology records, 4,972 trait records, 3,561 DNA-barcode records, 422 expression records, 110 dataset records, and 2 patent-source-status records.

### New And Expanded Sources
- Expanded VectorBase/VEuPathDB to include codon usage, identifier events, current-ID resolution, NCBI LinkOut, OrthoMCL pair records, and orthogroup membership.
- Added mosquito repellent literature since 2020 from PubMed and Crossref public metadata.
- Added external repellent discovery across OpenAlex, Europe PMC, AGRICOLA-through-Europe-PMC, Semantic Scholar, Crossref posted-content preprints, DataCite, Zenodo, and Figshare.
- Added queryable gap rows for native bioRxiv/medRxiv text search, PatentsView, USPTO Open Data Portal, CABI, and Google Scholar.
- Added or expanded expression metadata, UniProt proteins, VectorByte traits and abundance, image atoms, video atoms, VectorNet surveillance, CDC dengue surveillance, WHO dengue surveillance, resistance-table rows, and extracted-fact records.
- Shipped the safe incremental extracted-facts refresh path so a one-paper refresh no longer shrinks the full Aedes extracted-facts lane.
- Shipped the video-atom cleanup pass that filters non-video data files, keeps queryable video gaps, and preserves verified mirrored video artifacts.
- Hosted video atoms now include 46,293 queryable records, including 125 video assets, 21 verified video assets, 116 keyframes, 21 thumbnails, 21 preview clips, 21 frame manifests, and 45,574 motion rows.
- Shipped safe repository-scoped video refreshes, proven with a Dryad-only hosted pass that accepted 29 candidates from 71 raw Dryad discovery candidates without shrinking the full video lane.
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

<!-- publish-bump: 2026-05-26T12:05:00-07:00 -->
