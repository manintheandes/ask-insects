# Aedes Supplement Table Expansion Design

## Goal

Expand `aedes_extracted_facts` from paper text candidates into a real supplement-discovery and parseable table-row lane for `Aedes aegypti`.

## Source Contract

- Source id: `aedes_extracted_facts`
- Input sources: `aedes_literature_openalex`, `record_payloads`, `literature_fulltext_units`, Europe PMC metadata, PMC OA metadata, and downloaded public supplement files
- Output lanes: `literature` for supplement manifests, plus `vector_competence`, `resistance`, `behavior`, `ecology`, and `public_health` for parsed table rows
- Query grain: one parsed fact per supported supplement row
- Raw artifacts: downloaded supported supplements under `artifacts/mosquito-v1/raw/extracted_facts/supplements/`
- Provenance: `records#<paper_id>;supplement#<n>;row#<n>` plus raw-file locator when downloaded
- Confidence: `manifest` for discovered supplement pointers, `parsed` for supported deterministic row parsing, and `candidate` for text-unit extraction

## Discovery

The lane should discover supplement candidates from:

- Existing record payload supplement metadata
- Europe PMC result payload structures with supplementary material lists or full-text links
- PMC OA metadata payloads or compatible records that expose file locations

The implementation must be injectable for tests and offline operation. Network fetches are opt-in through the ingest script.

## Supported Parsing

Wave 1.1 supports deterministic parsing for:

- `.csv`
- `.tsv`
- `.xlsx`
- Simple XML tables
- Simple HTML tables

Unsupported, missing, oversized, or failed downloads become structured gaps.

## Boundary

This is still deterministic source-plane extraction. It makes row-level supplement evidence queryable with provenance, but it does not claim that every supplement has been parsed or that extracted rows are human validated.

## Completion Evidence

- Source tests prove injectable Europe PMC / PMC supplement discovery.
- Source tests prove parseable CSV, TSV, XLSX, XML, and HTML rows become `parsed` fact records.
- Ingest tests prove raw downloaded supplements are preserved and unrelated sources survive.
- CLI exposes opt-in discovery/download controls.
- Docs and coverage ledger distinguish parsed row facts from validated facts.
- `python3 scripts/verify_complete.py` passes.
