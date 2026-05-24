# Aedes Neurobiology Deep Source Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish source-grade neurobiology parsing beyond file/member inventory.

**Architecture:** Keep one source adapter, `askinsects/sources/neurobiology.py`, but split new helpers by artifact class: H5AD/HDF5, SRA runinfo, MosquitoBrains volumes, and public EM/connectome repository metadata. All outputs remain ordinary `EvidenceRecord` rows so the existing CLI and SQLite payload table keep working.

**Tech Stack:** Python standard library, optional `h5py` for H5AD/HDF5 introspection, SQLite through existing `SourceIndex`, current `unittest` test suite.

---

### Task 1: H5AD Internal Records

**Files:**
- Modify: `tests/test_neurobiology_source.py`
- Modify: `askinsects/sources/neurobiology.py`
- Modify: `askinsects/answer.py`
- Modify: `askinsects/planner.py`

- [x] Add a test fixture that creates a minimal valid H5AD file inside `04_H5ADs.zip`.
- [x] Assert `fetch_neurobiology_records(... artifact_dir=...)` emits `h5ad_summary`, `h5ad_group`, `h5ad_dataset`, `h5ad_obs_column`, and `h5ad_var_column` records.
- [x] Run `python3 -m unittest tests.test_neurobiology_source -v` and confirm it fails because those records do not exist.
- [x] Implement H5AD extraction to a temporary file, parse with `h5py`, emit summary/group/dataset/column records, and remove the old `h5ad_internal_matrix_not_parsed` gap when parsing succeeds.
- [x] Add H5AD/AnnData search routing tests and make them pass.

### Task 2: SRA Run Metadata

**Files:**
- Modify: `tests/test_neurobiology_source.py`
- Modify: `askinsects/sources/neurobiology.py`
- Modify: `scripts/ingest_neurobiology_sources.py`

- [x] Add fake `geo/SRP290992_runinfo.csv` to the neurobiology fixture.
- [x] Assert the parser emits one `sra_run` record and one `sra_sample_summary` record.
- [x] Run the neurobiology tests and confirm failure.
- [x] Update the ingest script to download `https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/runinfo?acc=SRP290992`.
- [x] Implement CSV parsing into SRA run and sample summary records.

### Task 3: MosquitoBrains Volume Metadata

**Files:**
- Modify: `tests/test_neurobiology_source.py`
- Modify: `askinsects/sources/neurobiology.py`

- [x] Extend the fixture with nested reference-brain ZIPs, MHD/MHA headers, and ITK-SNAP label text.
- [x] Assert `brain_volume_header` and `brain_region_label` records are emitted.
- [x] Run the neurobiology tests and confirm failure.
- [x] Implement nested ZIP traversal, MHD/MHA header parsing, and label parsing.

### Task 4: Public EM/Connectome-Adjacent Source

**Files:**
- Modify: `tests/test_neurobiology_source.py`
- Modify: `scripts/ingest_neurobiology_sources.py`
- Modify: `askinsects/sources/neurobiology.py`
- Modify: `config/source-map.yaml`

- [x] Add fake `connectome/aedes_public/repo.json` and one CSV fixture.
- [x] Assert `connectome_repository` and `connectome_csv` records are emitted.
- [x] Run the neurobiology tests and confirm failure.
- [x] Download GitHub repository metadata and CSV files from `htem/aedes_public` in the ingest script.
- [x] Parse repository metadata and CSV inventories into records.
- [x] Keep the whole-brain Wellcome gap as `whole_brain_connectome_download_not_public`.
- [x] Add the public README CATMAID locator plus CATMAID project, stack, annotation, and volume API metadata.

### Task 5: Verification And Install

**Files:**
- Modify: `README.md`
- Modify: `docs/source-lanes.md`
- Modify: `docs/querying-ask-insects.md`
- Modify: `/Users/josh/.codex/skills/askinsects/SKILL.md`

- [x] Update docs to describe the deeper source atoms and the narrower remaining whole-brain connectome gap.
- [x] Run `python3 -m unittest discover -s tests -v`.
- [x] Run `python3 scripts/verify_complete.py`.
- [x] Run `python3 scripts/ingest_neurobiology_sources.py` to refresh raw artifacts.
- [x] Rebuild `/Users/josh/.local/share/ask-insects/main/artifacts/mosquito-v1` with fixtures, NCBI genome, literature if needed, and neurobiology artifact dir.
- [x] Refresh `/Users/josh/.local/share/ask-insects/main` from `main`.
- [x] Verify from `/tmp`: `ask-insects summary`, `ask-insects search neurobiology "AnnData obs cell type"`, `ask-insects search neurobiology "SRA SRR12972760"`, `ask-insects search neurobiology "DimSize 646 649 275"`, and `ask-insects ask "what public connectome data exists for Aedes aegypti?" --json`.
