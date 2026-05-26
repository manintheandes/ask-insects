# Aedes OpenDataSUS Dengue Surveillance Design

## Goal

Add Brazil Ministry of Health OpenDataSUS SINAN dengue evidence as an Ask Insects public-health source lane for `Aedes aegypti` intelligence.

## Boundary

The lane covers official annual OpenDataSUS dengue CSV ZIP files from the public arboviruses dengue dataset. The default run mirrors the current configured years, currently 2025 and 2026. Older annual backfiles can be passed explicitly by year, but are not claimed by the default receipt.

The lane indexes aggregate surveillance atoms only:

- source-file records with URL, raw ZIP locator, SHA-256 checksum, byte size, and CSV row count
- country-year summaries for Brazil
- residence-state-year summaries
- notification-state-year summaries
- country epidemiological-week summaries
- residence-state epidemiological-week summaries

It intentionally does not index person-level line records.

## Source Contract

Each record must preserve source id `aedes_opendatasus_dengue_surveillance`, species `Aedes aegypti`, lane `public_health`, official source URL, raw ZIP locator, retrieval time, upstream license or terms, and payload fields for the aggregate.

Deaths are represented conservatively as rows where `EVOLUCAO=2`, described as deaths coded as death by disease. The parser must not silently relabel that code as all-cause mortality or confirmed dengue deaths beyond the source code meaning.

## Verification

The lane is source-grade only when it is mapped in `config/source-map.yaml`, parsed into SQLite records with payloads and provenance, exposed through local and hosted CLI ingestion paths, documented in source docs, covered by tests, and accepted by `python3 scripts/verify_complete.py`.
