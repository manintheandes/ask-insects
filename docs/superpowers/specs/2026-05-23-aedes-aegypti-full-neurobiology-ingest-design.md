# Aedes Aegypti Full Neurobiology Ingest Design

## Purpose

Ask Insects already has a first neurobiology lane. This build moves that lane from metadata-only toward source-grade artifact ingestion for every currently accessible `Aedes aegypti` brain and neuron source family.

## Source Boundary

This ingest covers:

- MosquitoBrains public neuroanatomy pages, downloadable reference brain, and segmentation downloads when the public links are reachable.
- GEO `GSE160740` processed brain snRNA-seq supplementary package.
- Mosquito Cell Atlas Zenodo record `14890013`, including file inventory, checksums, and downloadable package artifacts.
- Wellcome female `Aedes aegypti` connectome grant metadata as an explicit source gap until the promised public dataset exists.

## Ingest Contract

Raw artifacts are stored under:

```text
/Users/josh/.local/share/ask-insects/sources/neurobiology/
```

The SQLite answer index stores useful atoms and receipts, not every matrix count:

- artifact file records
- GEO sample records
- GEO feature/gene records
- GEO barcode/cell-count summaries
- Matrix Market shape and nonzero-count summaries
- Mosquito Cell Atlas package inventory records
- parsed supplementary table sheet names and row/column counts where possible
- explicit source-gap records for unavailable or future-only artifacts

Each record carries source id, URL or local artifact locator, retrieved date, license/access note, and raw payload in `record_payloads`.

## Safety

Large files are downloaded with resumable helpers and size/checksum receipts. If a file is not downloadable without login, JavaScript, or temporary Dropbox state, the ingest records a gap instead of pretending it succeeded.

The build remains fast enough for normal use because SQLite records summarize large matrices rather than copying every expression value into `records`.

## Completion

The build is shipped only when:

- tests prove the artifact parser and builder behavior;
- `python3 scripts/verify_complete.py` passes;
- the installed `ask-insects` command sees the full neurobiology ingest records;
- real questions about brain data, cell atlas data, and source gaps answer from local SQLite with provenance.
