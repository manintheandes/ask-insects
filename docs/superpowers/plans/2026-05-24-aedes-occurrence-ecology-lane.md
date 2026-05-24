# Aedes Occurrence Ecology Lane Plan

- [x] Inspect hosted GBIF, iNaturalist, and Mosquito Alert observation payload fields for country, date, coordinates, quality, and habitat annotations.
- [x] Add `askinsects/sources/occurrence_ecology.py` to derive country, country-month, and habitat ecology records from indexed observation payloads.
- [x] Add `scripts/ingest_occurrence_ecology.py` and CLI/server hosted ingest hooks.
- [x] Route range, distribution, country, month, and seasonality questions toward ecology and prefer `aedes_occurrence_ecology`.
- [x] Add source, ingest, hosted CLI, server, and answer-ranking tests.
- [x] Update source map, coverage ledger, README, source-lane docs, querying docs, and installed skill.
- [x] Deploy hosted server, ingest hosted `aedes_occurrence_ecology`, and verify hosted answers.
- [ ] Sync installed runtime, commit, and push.
