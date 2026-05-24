# Aedes Aegypti Full Neurobiology Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest every accessible Aedes aegypti neurobiology source family into Ask Insects with raw artifacts, receipts, SQLite queryability, provenance, and explicit source gaps.

**Architecture:** Extend the existing neurobiology source adapter with an optional artifact directory. It will parse local GEO, Zenodo, and MosquitoBrains artifacts into compact records and record unavailable sources as gaps. The builder and CLI keep the existing `--neurobiology` flag and add optional artifact/cache controls.

**Tech Stack:** Python standard library, SQLite FTS through existing `SourceIndex`, `tarfile`, `zipfile`, `csv`, `xml.etree`, `urllib`, `unittest`.

---

## Files

- Modify `askinsects/sources/neurobiology.py`: add artifact discovery, download helpers, parsers, file receipts, and gap records.
- Modify `askinsects/builder.py`: pass optional neurobiology artifact directory and include richer receipt payloads.
- Modify `scripts/build_source_index.py`: add `--neurobiology-artifact-dir`.
- Create `scripts/ingest_neurobiology_sources.py`: fetch public artifacts into the local source cache, then build the SQLite artifact.
- Modify tests for parser, builder, CLI, and completion gate.
- Modify docs and source map with full-ingest boundary and gaps.

## Tasks

1. Add failing parser tests for GEO MTX/TSV, Zenodo inventory JSON, and unavailable connectome gaps.
2. Implement local artifact parsers with deterministic fixtures.
3. Wire `--neurobiology-artifact-dir` through builder and CLI.
4. Add the real ingest script that downloads public artifacts into the local source cache and writes a manifest.
5. Update docs, source map, completion gate, and skill notes.
6. Run full tests and completion gate.
7. Run the real ingest, rebuild the installed artifact, and verify global `ask-insects` answers.
