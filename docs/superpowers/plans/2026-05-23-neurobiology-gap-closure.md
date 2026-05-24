# Neurobiology Gap Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make raw SRA access/workflow and MosquitoBrains voxel values queryable, while preserving the true whole-brain connectome availability boundary.

**Architecture:** Keep normalized evidence in the existing neurobiology source adapter. Store voxel access as payload metadata on volume records and resolve exact values through a focused CLI command.

**Tech Stack:** Python standard library, SQLite payload table, existing `unittest` suite.

---

### Task 1: Exact Voxel Reads

**Files:**
- Modify: `tests/test_neurobiology_source.py`
- Modify: `askinsects/sources/neurobiology.py`
- Create: `askinsects/voxels.py`
- Modify: `askinsects/cli.py`
- Modify: `tests/test_cli.py`

- [x] Write a failing test that creates tiny MHA/MHD fixtures with known voxel values.
- [x] Run the neurobiology test and confirm it fails because `askinsects.voxels` does not exist.
- [x] Add `askinsects/voxels.py` to read exact voxel values from MHA local data and MHD raw sidecar data.
- [x] Add `voxel_access` payloads to MosquitoBrains volume records.
- [x] Add `ask-insects voxel <record_id> --x <x> --y <y> --z <z>`.
- [x] Verify the targeted neurobiology and CLI tests pass.

### Task 2: SRA Raw Access And Reanalysis Workflow

**Files:**
- Modify: `tests/test_neurobiology_source.py`
- Modify: `askinsects/sources/neurobiology.py`
- Modify: `README.md`
- Modify: `docs/source-lanes.md`
- Modify: `docs/querying-ask-insects.md`
- Modify: `config/source-map.yaml`

- [x] Write a failing test that expects `neuro:sra:SRP290992:raw-access` and `neuro:sra:SRP290992:reanalysis-workflow`.
- [x] Run the neurobiology test and confirm those records are missing.
- [x] Emit source records for run download paths, total size, workflow commands, and non-executed alignment status.
- [x] Update docs to distinguish source-grade workflow records from executed compute outputs.

### Task 3: Verification And Installed CLI

**Files:**
- Modify: `/Users/josh/.codex/skills/askinsects/SKILL.md`
- Modify: installed artifact directory under `/Users/josh/.local/share/ask-insects/main`

- [x] Run `python3 -m unittest discover -s tests -v`.
- [x] Run `python3 scripts/verify_complete.py`.
- [x] Rebuild `/Users/josh/.local/share/ask-insects/main/artifacts/mosquito-v1`.
- [x] Refresh the installed code snapshot.
- [x] Verify `ask-insects voxel`, raw SRA workflow search, and connectome answers from `/tmp`.
