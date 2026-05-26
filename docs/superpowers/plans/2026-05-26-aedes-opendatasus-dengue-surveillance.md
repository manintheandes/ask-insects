# Aedes OpenDataSUS Dengue Surveillance Plan

## Steps

1. Add an OpenDataSUS dengue source adapter that fetches annual CSV ZIP files, saves raw ZIP artifacts, computes checksums, streams CSV rows, and emits aggregate public-health records.
2. Add a local ingest script that replaces only `aedes_opendatasus_dengue_surveillance` rows, updates receipts, and preserves unrelated source lanes.
3. Wire the CLI and hosted server route for `ingest-opendatasus-dengue-surveillance`.
4. Teach public-health answer routing to prefer the OpenDataSUS lane for Brazil SINAN/OpenDataSUS dengue questions.
5. Add source-map, docs, coverage-ledger, and third-party-data entries.
6. Verify with focused unit tests, local ingest, real Ask Insects questions, `verify_complete.py`, hosted ingest, and hosted answer checks.

## Acceptance

- `python3 -m unittest tests.test_opendatasus_dengue_surveillance_source tests.test_ingest_opendatasus_dengue_surveillance -v` passes.
- `python3 -m askinsects ingest-opendatasus-dengue-surveillance` creates public-health records with raw ZIP provenance.
- `python3 -m askinsects ask "show Brazil OpenDataSUS dengue deaths and notifications for 2025" --json` returns `aedes_opendatasus_dengue_surveillance`.
- Hosted Ask Insects can ingest and answer from the lane without removing existing sources.
