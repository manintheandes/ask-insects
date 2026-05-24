# Aedes Vector-Competence Assay Candidate Lane Plan

1. Add the extractor in `askinsects/sources/vector_competence_assays.py`.
2. Add local ingest in `scripts/ingest_vector_competence_assays.py`.
3. Wire CLI and hosted `/ingest/vector-competence-assays`.
4. Route assay questions to the new lane without breaking pathogen taxonomy questions.
5. Update source map, coverage ledger, README, querying docs, and source-lane docs.
6. Add focused tests and extend `verify_complete.py`.
7. Run focused tests, full tests, local live ingest, hosted ingest, installed sync, and final gate.
