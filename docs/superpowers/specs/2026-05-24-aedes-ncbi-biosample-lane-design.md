# Aedes NCBI BioSample Lane Design

## Goal

Add a source-grade `Aedes aegypti` BioSample lane so Ask Insects can answer sample, strain, isolate, collection, geography, tissue, and linked SRA questions from local SQLite records with provenance.

## Source Boundary

The lane uses NCBI E-utilities:

- ESearch against `db=biosample` with term `"Aedes aegypti"[Organism]`
- ESummary against the returned BioSample UIDs

It is a bounded live ingest, not a complete mirror unless the configured limit reaches the reported NCBI count. If NCBI reports more matching BioSamples than the ingest fetched, the lane must record a structured `biosample_limit_applied` gap.

## Records

Each BioSample summary becomes one `EvidenceRecord`:

- source: `ncbi_biosamples`
- lane: `biosamples`
- record id: `ncbi:biosample:<accession>`
- species: the NCBI organism, normally `Aedes aegypti`
- URL: the public NCBI BioSample page
- provenance locator: saved ESummary JSON batch plus UID

Payloads preserve the raw ESummary record and parsed BioSample XML attributes and IDs.

## Ask Surface

Questions mentioning BioSample, sample, strain, isolate, or linked SRA metadata should route to the genomics answer shape and prefer the `biosamples` lane before gene, protein, or assembly records.

## Verification

Completion requires:

- unit tests for source parsing and limit gaps
- ingest tests proving existing source rows are preserved
- CLI hosted request tests
- server route tests
- answer routing tests
- docs, source map, coverage ledger, and skill updates
- `python3 -m unittest discover -s tests -v`
- `python3 scripts/verify_complete.py`
