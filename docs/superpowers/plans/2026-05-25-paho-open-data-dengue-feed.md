# PAHO Open Data Dengue Feed Implementation Plan

> For agentic workers: update this checklist as the work proceeds.

**Goal:** Make the official PAHO/EIH Core Indicators dengue cases ZIP/CSV feed
source-grade in Ask Insects.

## Task 1: Parser And Tests

Files:

- Modify: `askinsects/sources/paho_surveillance.py`
- Modify: `tests/test_paho_surveillance_source.py`

- [x] Add fixture ZIP bytes containing Core Indicator dengue and non-dengue rows.
- [x] Test that the download page ZIP link is discovered.
- [x] Test that dengue rows become `public_health` records with ZIP/CSV row provenance.

## Task 2: Ingest And Metadata

Files:

- Modify: `scripts/ingest_paho_dengue_surveillance.py`
- Modify: `askinsects/server.py`
- Modify: `tests/test_ingest_paho_dengue_surveillance.py`

- [x] Add local ingest support for the Core Indicators download page.
- [x] Add hosted ingest support for the Core Indicators download page.
- [x] Receipt counts should include Core Indicator dengue rows.

## Task 3: Docs And Gate

Files:

- Modify: `README.md`
- Modify: `docs/source-lanes.md`
- Modify: `docs/querying-ask-insects.md`
- Modify: `config/source-map.yaml`
- Modify: `config/mosquito-intelligence-coverage.json`
- Modify: `scripts/verify_complete.py`
- Modify: `/Users/josh/.codex/skills/askinsects/SKILL.md`

- [x] Document annual country/territory machine-readable PAHO rows.
- [x] Preserve the weekly dashboard-cell gap.
- [x] Require the new proof terms in `verify_complete.py`.

## Task 4: Ship

- [ ] Run PAHO source and ingest tests.
- [ ] Run full unit tests and `verify_complete.py`.
- [ ] Deploy.
- [ ] Run hosted PAHO ingest.
- [ ] Prove hosted records and hosted answers.
