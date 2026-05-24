# Aedes Extracted Facts Design

## Goal

Make table-like and supplement-like facts from `Aedes aegypti` literature queryable across vector competence, resistance, behavior, ecology, and public-health lanes.

## Source Contract

- Source id: `aedes_extracted_facts`
- Input sources: `aedes_literature_openalex` records, `record_payloads`, and legal `literature_fulltext_units`
- Supplement discovery inputs: DOI, PMID, PMCID, PMC or Europe PMC metadata already present in payloads, plus optional injectable metadata fetchers
- Output lanes: `vector_competence`, `resistance`, `behavior`, `ecology`, `public_health`, and `literature` for supplement manifests
- Query grain: one extracted fact per source paper, legal full-text unit, or parseable supplement locator
- Provenance: `records#<paper_id>`, `literature_fulltext_units#<unit_id>` when available, and supplement locator when available
- Payloads: `fact_type`, `schema_version`, `fields`, `source_record_id`, `fulltext_unit_id`, `supplement`, `evidence_text`, `confidence`, `extraction_method`, and source provenance

## Fact Families

- `vector_competence`: pathogen, infection, dissemination, transmission, dose, temperature, tissue, strain, and timepoint evidence
- `resistance`: insecticide, assay, mortality, knockdown, LC50 or LC90, mutation, genotype frequency, and country evidence
- `behavior`: assay, stimulus, sex, age, strain, and response metric evidence
- `ecology`: habitat, breeding site, climate, seasonality, range, and location evidence
- `public_health`: cases, deaths, intervention, location, date, serotype, and source evidence

## Boundary

This lane is deterministic extraction. It creates inspectable candidates and supplement manifests, but it does not claim human validation or complete parsing of every table, PDF supplement, or workbook.

## Completion Evidence

- `askinsects/sources/extracted_facts.py` builds structured fact records from the SQLite source plane.
- `scripts/ingest_extracted_facts.py` installs extracted facts without deleting other sources.
- Local and hosted CLI expose `ingest-extracted-facts`.
- The hosted server exposes `POST /ingest/extracted-facts`.
- Source map, coverage, and query docs name this as Wave 1 cross-lane table and supplement extraction.
- `python3 scripts/verify_complete.py` passes.
