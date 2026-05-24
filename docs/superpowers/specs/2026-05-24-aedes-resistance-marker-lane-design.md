# Aedes Resistance Marker Lane Design

## Goal

Make kdr, VGSC, and metabolic-resistance marker evidence queryable as first-class `resistance` records for `Aedes aegypti`.

## Source Contract

- Source id: `aedes_resistance_markers`
- Input sources: `aedes_literature_openalex` records and legal `literature_fulltext_units`
- Output lane: `resistance`
- Query grain: one marker candidate per source paper or legal full-text unit
- Provenance: `records#<paper_id>` plus `literature_fulltext_units#<unit_id>` when available
- Payloads: marker ID, marker class, gene or family, matched aliases, context terms, insecticide terms, source paper ID, full-text unit ID, and snippet

## Boundary

This lane is deterministic candidate extraction. It makes marker evidence inspectable and queryable, but it does not claim that genotype-frequency tables, haplotypes, or supplement tables are fully parsed or human validated.

## Completion Evidence

- `askinsects/sources/resistance_markers.py` builds records from the SQLite literature index.
- `scripts/ingest_resistance_markers.py` installs records without deleting other sources.
- Local and hosted CLI expose `ingest-resistance-markers`.
- The hosted server exposes `POST /ingest/resistance-markers`.
- Ask questions mentioning kdr or marker names prefer `aedes_resistance_markers`.
- `python3 scripts/verify_complete.py` passes.
