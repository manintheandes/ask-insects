# Aedes Mendeley Behavior Table Deep Parse Plan

## Outcome

Ask Insects should parse public Mendeley `Aedes aegypti` behavior tables into queryable sheet and row records while preserving the existing dataset, folder, file, media, and hosted ingest behavior.

## Tasks

1. Add deterministic parser tests for downloaded CSV and XLSX table files.
2. Extend `askinsects/sources/mendeley_behavior_media.py` to download table files, parse workbook sheets or delimited rows, and emit sheet and row records.
3. Keep comparison-only files out of row-level `Aedes aegypti` evidence.
4. Add table counts to local and hosted ingest receipts.
5. Update README, source lanes, source map, coverage ledger, and completion gate.
6. Run targeted tests, full unit tests, and `python3 scripts/verify_complete.py`.
7. Run local and hosted Mendeley ingest, then verify hosted table counts and table-row answers.
