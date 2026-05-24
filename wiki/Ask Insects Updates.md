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

Latest Ask Insects source-plane update: 2026-05-24.

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

<!-- publish-bump: 2026-05-24T06:51:53-07:00 -->
