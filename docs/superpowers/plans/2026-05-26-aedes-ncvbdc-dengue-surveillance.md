# Aedes NCVBDC Dengue Surveillance Plan

## Steps

1. Map the official NCVBDC India dengue situation page and identify its table grain.
2. Parse the raw HTML table into source-page, state/UT-year, national country-year, and latest-two-complete-year summary records.
3. Ingest the records into SQLite under source id `aedes_ncvbdc_dengue_surveillance` without removing other sources.
4. Wire CLI, hosted server endpoint, answer routing, source map, docs, coverage ledger, and completion checks.
5. Run local ingest and query proof.
6. Push and deploy the lane to the hosted Ask Insects server.

## Validation

- Focused unit tests for parser, ingest, CLI hosted request, server route, and answer routing.
- `python3 scripts/verify_complete.py`
- `python3 scripts/verify_mosquito_intelligence_coverage.py`
- `python3 -m unittest discover -s tests -v`
- Hosted ingest plus hosted ask/SQL proof.
