# Open Insects Public Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Open Insects as the public project identity while keeping Ask Insects as the CLI and hosted query tool.

**Architecture:** This is a documentation and metadata change. The README, Obsidian wiki home, source map, package metadata, and GitHub repo metadata should all express the same naming split, and `scripts/verify_complete.py` should enforce it.

**Tech Stack:** Markdown, TOML, Python standard-library verification, GitHub CLI.

---

### Task 1: Public Identity Copy

**Files:**
- Modify: `README.md`
- Modify: `wiki/Ask Insects.md`
- Modify: `wiki/Source Map.md`
- Modify: `wiki/Guides/Team Setup.md`

- [x] Lead with Open Insects as the project.
- [x] Keep Ask Insects as the CLI and hosted query tool.
- [x] Keep source claims Aedes-first and provenance-backed.

### Task 2: Package And Repo Metadata

**Files:**
- Modify: `pyproject.toml`

- [x] Add `Homepage` as `https://openinsects.org`.
- [x] Add `Source` as the public GitHub repo.
- [x] Keep the package name and command unchanged.

### Task 3: Completion Gate

**Files:**
- Modify: `scripts/verify_complete.py`
- Modify: `tests/test_verify_complete.py`

- [x] Add a verification function for the Open Insects public identity.
- [x] Require the README, wiki home, source map, and `pyproject.toml` to carry the identity split.
- [x] Run the focused verification test and the full completion gate.

### Task 4: Publish Trail

**External metadata:**
- Update GitHub description.
- Update GitHub homepage to `https://openinsects.org`.

- [x] Commit and push the repo changes.
- [x] Update GitHub metadata with `gh repo edit`.
- [x] Read back GitHub metadata.
