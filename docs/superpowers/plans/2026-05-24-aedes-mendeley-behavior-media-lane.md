# Aedes Mendeley Behavior And Media Lane Plan

## Outcome

Ask Insects should be able to source public Mendeley Data behavior and media datasets for `Aedes aegypti`, with dataset, folder, and file atoms queryable from SQLite and hosted Ask Insects.

## Tasks

1. Add tests for Mendeley snapshot, folder, and file manifest normalization.
2. Add tests for the local ingest script preserving existing sources and writing payload rows.
3. Add hosted CLI and server route tests for `/ingest/mendeley-behavior-media`.
4. Implement `askinsects/sources/mendeley_behavior_media.py`.
5. Implement `scripts/ingest_mendeley_behavior_media.py`.
6. Wire CLI and server ingest routes.
7. Prefer `mendeley_aedes_behavior_media` for Mendeley, flight-tone, mate-recognition, locomotion, and temperature-behavior questions.
8. Update README, source lanes, source map, coverage ledger, and completion gate.
9. Run targeted tests, full unit tests, and `python3 scripts/verify_complete.py`.
10. Run local ingest, deploy server, run hosted ingest, verify hosted counts and sample answers.
