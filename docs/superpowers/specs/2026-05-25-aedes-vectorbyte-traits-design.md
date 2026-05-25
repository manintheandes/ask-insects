# Aedes VectorByte Traits Design

## Goal

Add a source-grade Ask Insects lane for Aedes aegypti trait observations from VectorByte VecTraits, starting with bounded AedesTraits-style temperature and biology rows.

## Boundary

This lane covers public VecTraits datasets returned by the VBD Hub search API for `Aedes aegypti` in database `vt`. It fetches a bounded number of dataset IDs and indexes row-level trait observations where `Interactor1` is `Aedes aegypti` or the genus/species fields resolve to `Aedes aegypti`.

It does not cover VecDyn abundance data, VectorBase PopBio, or all VectorByte taxa. Those remain future lanes.

## Source Contract

- Source id: `aedes_vectorbyte_traits`
- Primary lane: `traits`
- Secondary routing: trait questions should also be reachable from ecology, behavior, public-health, and vector-competence style questions when they mention temperature, development, fecundity, survival, body size, infection, or transmission traits.
- Raw files: `artifacts/mosquito-v1/raw/vectorbyte_traits/`
- Atomic unit: one VecTraits observation row.
- Provenance: each row stores the dataset id, row id, raw JSON locator, DOI/citation when present, retrieved timestamp, source URL, and VectorByte/VBD Hub public-source license note.

## Data Flow

1. Search `https://api.vbdhub.org/search` with query `Aedes aegypti`, database `vt`, and bounded page/limit options.
2. Save the search response as raw JSON.
3. Fetch each selected dataset from `https://vectorbyte.crc.nd.edu/portal/api/vectraits-dataset/{id}/?format=json`.
4. Save each dataset response as raw JSON.
5. Convert each matching row to an `EvidenceRecord` with trait name, value, unit, temperature, stage, sex, location, citation, DOI, and experiment context in searchable text.
6. Replace only `aedes_vectorbyte_traits` records in the SQLite index after a successful non-empty refresh.
7. Update status, receipt, and gaps without deleting unrelated sources.

## Ask Behavior

Questions about Aedes traits, thermal response, temperature-dependent development, fecundity, longevity, body size, infection, or transmission potential should prefer this lane when matching records exist.

Example questions:

- `show VectorByte temperature trait data for Aedes aegypti fecundity`
- `how does temperature affect Aedes aegypti transmission potential?`
- `show Aedes aegypti development time trait observations from VecTraits`

## Failure Behavior

If the search or all dataset fetches fail, the ingest records structured gaps and preserves any previously indexed rows for this source. Partial fetch failures become gaps, while successfully fetched datasets still index.

## Verification

The lane is complete only when these pass:

- Parser tests for search response, dataset rows, non-Aedes filtering, and fetch gaps.
- Ingest tests proving unrelated source rows survive refresh and failed refresh.
- Hosted CLI and server route tests.
- Source-map, docs, coverage ledger, and `verify_complete.py`.
- Local ingest plus hosted ingest.
- Hosted health, SQL count, and real answer proof.
