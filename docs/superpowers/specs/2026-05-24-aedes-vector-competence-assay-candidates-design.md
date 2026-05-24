# Aedes Vector-Competence Assay Candidate Lane Design

## Goal

Add an Aedes-first source lane that turns indexed `Aedes aegypti` literature and legal full-text units into queryable vector-competence assay candidate records.

## Boundary

- Input sources are existing `aedes_literature_openalex` records and `literature_fulltext_units`.
- The lane is legal full-text only.
- Records are candidates, not validated final assay rows.
- True table and supplement parsing remains future work.

## Record Shape

Each `aedes_vector_competence_assays` record uses lane `vector_competence` and stores:

- pathogen
- matched pathogen terms
- assay fields for infection, dissemination, transmission, dose, temperature, tissue, strain or population, and timepoint when detected
- temperature and dose values when detected
- source paper id
- full-text unit id when available
- snippet
- provenance back to the source record and full-text unit

## Verification

- Unit tests prove extraction and gap behavior.
- Ingest tests prove source replacement preserves other source rows.
- CLI and hosted tests prove the command and route.
- Answer tests prove assay questions prefer assay candidates while taxonomy questions still prefer pathogen identity records.
- `python3 scripts/verify_complete.py` remains the completion gate.
