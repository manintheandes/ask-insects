# Aedes NCBI BioSample Lane Plan

- [x] Inspect existing NCBI and incremental ingest patterns.
- [x] Add `askinsects/sources/ncbi_biosample.py` with ESearch, ESummary, raw JSON receipts, XML parsing, `biosamples` records, and bounded-ingest gaps.
- [x] Add `scripts/ingest_ncbi_biosamples.py` to upsert BioSample records without deleting unrelated source rows.
- [x] Wire CLI command `ingest-ncbi-biosamples` for local and hosted runs.
- [x] Wire hosted route `/ingest/ncbi-biosamples`.
- [x] Route BioSample, sample, strain, isolate, and SRA metadata questions to genomics with `biosamples` preference.
- [x] Update `config/source-map.yaml`, `config/mosquito-intelligence-coverage.json`, README, source-lane docs, querying docs, and the installed `askinsects` skill.
- [x] Add focused tests for source parsing, ingest metadata, CLI hosted payloads, server ingest, and answer routing.
- [x] Run focused tests.
- [x] Run full tests and completion gate.
- [x] Install to local Ask Insects runtime, deploy hosted server, ingest hosted BioSamples, verify hosted query results.
- [ ] Commit and push to `main`.
