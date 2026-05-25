# Mosquito Repellent Literature Design

## Goal

Add a source-grade public metadata lane for mosquito repellent research articles from 2020 onward so Ask Insects can answer repellent-literature questions from queryable records with provenance.

## Boundary

The lane covers public PubMed and Crossref article metadata where source metadata indicates mosquito repellent, repellency, spatial repellent, topical repellent, DEET, picaridin, icaridin, IR3535, PMD, citronella, essential oil, or plant-extract repellent research from 2020-01-01 through run date.

The lane does not scrape publisher pages, use private cookies, use institutional access, use Sci-Hub, or claim publisher full text has been parsed. It produces metadata atoms:

- one deduplicated article candidate per record
- PMID or DOI when supplied
- title, authors, journal or container, publication date, and URL when supplied
- PubMed or Crossref candidate source membership
- matched mosquito and repellent terms
- `coverage_status` showing whether an existing Ask Insects literature row already matches by DOI or normalized title
- structured gaps for failed fetches, result-limit frontiers, no-candidate runs, and missing canonical literature rows

## Data Flow

1. Fetch bounded PubMed ESearch pages using a Title/Abstract query over mosquito taxa and repellent terms.
2. Fetch PubMed ESummary batches for candidate PMIDs.
3. Fetch bounded Crossref `/works` cursor pages across targeted repellent queries.
4. Save raw JSON under `artifacts/mosquito-v1/raw/mosquito_repellent_literature/`.
5. Filter Crossref items to records that contain both mosquito and repellent terms in source metadata.
6. Deduplicate by DOI, PMID, then normalized title.
7. Compare candidates against current literature rows, excluding this lane.
8. Replace only `mosquito_repellent_literature` rows after a successful refresh.
9. Update source status, receipt, and gaps without removing other source lanes.

## Ask Surface

Add `ingest-mosquito-repellent-literature` locally and hosted. Literature questions mentioning mosquito repellents, DEET, picaridin, icaridin, IR3535, PMD, citronella, essential oils, plant extracts, spatial repellents, or topical repellents should prefer this lane when it is installed.

## Verification

Tests cover source parsing, PubMed and Crossref deduplication, preservation on failed refresh, CLI/hosted routing, server endpoint wiring, answer preference, source-map/doc coverage, and the repo completion gate.
