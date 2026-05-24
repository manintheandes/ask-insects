# Aedes Aegypti GBIF Deep Hosted Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a hosted GBIF deep ingest path for `Aedes aegypti` that refreshes GBIF rows in server SQLite while preserving existing hosted lanes.

**Architecture:** Extend the GBIF adapter to paginate occurrence search and store raw payloads. Add a hosted `/ingest/gbif` endpoint and CLI command that stage the active artifact directory, refresh only `gbif_api`, update receipts, and activate after success.

**Tech Stack:** Python standard library, SQLite, GBIF public API, `unittest`, Google Compute Engine systemd deployment.

---

## File Structure

- Modify `askinsects/sources/gbif.py`: occurrence pagination, raw payloads, page receipt metadata.
- Modify `askinsects/index.py`: source delete helper for refreshes.
- Modify `askinsects/server.py`: hosted incremental GBIF ingest endpoint.
- Modify `askinsects/cli.py`: hosted `ingest-gbif` command.
- Modify `scripts/build_source_index.py`: local GBIF page-size and delay options.
- Modify tests for GBIF pagination, hosted CLI, and hosted server preservation.
- Modify docs and source map to document the hosted deep GBIF boundary.

## Tasks

- [x] Add mocked pagination and raw-payload tests for GBIF.
- [x] Implement GBIF `limit` plus `offset` pagination.
- [x] Add raw GBIF match and occurrence payloads to `record_payloads`.
- [x] Add `SourceIndex.delete_source(source)` for lane refreshes.
- [x] Add hosted server `POST /ingest/gbif`.
- [x] Add local CLI `ingest-gbif --hosted`.
- [x] Update docs, source map, and source-lane descriptions.
- [x] Run full tests and completion gate.
- [x] Deploy the hosted API.
- [x] Run the hosted deep GBIF ingest for `Aedes aegypti`.
- [x] Verify hosted health, source counts, and payload counts.
