# Aedes CDC Dengue Surveillance Plan

## Steps

1. Map CDC dengue current and historic pages and inspect whether downloadable data exists.
2. Parse CDC page HTML, WCMS visualization config JSON, linked CSV datasets, and ArboNET limitations.
3. Ingest the records into SQLite under source id `aedes_cdc_dengue_surveillance`.
4. Wire CLI, hosted server endpoint, answer routing, source map, docs, and completion checks.
5. Run local ingest and query proof.
6. Push and deploy the lane to the hosted Ask Insects server.

## Validation

- Focused unit tests for parser, ingest, CLI hosted request, server route, and answer routing.
- `python3 scripts/verify_complete.py`
- `python3 scripts/verify_mosquito_intelligence_coverage.py`
- `python3 -m unittest discover -s tests -v`
- Hosted ingest plus hosted ask/SQL proof.
