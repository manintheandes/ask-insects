# Aedes Mendeley Behavior Table Deep Parse Design

## Goal

Upgrade `mendeley_aedes_behavior_media` from file-manifest coverage to table-level Aedes behavior evidence where public Mendeley files are small enough and licensed for direct parsing.

The focus is `Aedes aegypti`. Mixed datasets can stay in scope when `Aedes aegypti` is materially present, but comparison-only files should not become Aedes row evidence.

## Source Boundary

The deep parse uses the existing Mendeley source id:

```text
mendeley_aedes_behavior_media
```

It parses public `.csv`, `.tsv`, and `.xlsx` files from the already mapped Mendeley dataset manifests. It keeps video, audio, archive, code, README, and comparison-only files as file-level records unless a later plan adds a source-grade parser for those formats.

## Atomic Query Grain

The parser emits:

- one existing file-level behavior record per source table file;
- one `behavior` record per parsed table or workbook sheet;
- one `behavior` record per non-empty table row.

Each parsed table record preserves dataset id, version, DOI, filename, folder path, sheet name, headers, sample rows, row count, column count, download URL, license, and raw-file locator.

Each parsed row record preserves dataset id, version, DOI, filename, sheet name, row number, key-value row payload, download URL, license, and raw-file row locator.

## Aedes Scope

Dataset-level Aedes scope is inherited from the manifest lane. File-level row parsing is stricter:

- `Aedes aegypti` and mixed Aedes files are parsed;
- `Ae. japonicus` comparison-only workbooks in the locomotory behavior dataset remain manifest file records but are skipped for row-level Aedes evidence.

## Source Contract

- Mapped: source map and docs state that Mendeley table files are parsed into sheet and row atoms.
- Accessible: ingest downloads public table files through Mendeley public file URLs.
- Atomically queryable: SQLite `records` and `record_payloads` expose file, sheet, and row records.
- Receipted: metadata includes table file, parsed file, skipped file, sheet, and row counts.
- Ask surface wired: behavior searches and questions can retrieve parsed row evidence with provenance.

## Explicit Limits

This does not decode video frames, acoustic waveforms, or compressed archives. It also does not claim comparison-only rows as `Aedes aegypti` evidence. Those remain explicit future source gaps.
