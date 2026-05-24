# Aedes Aegypti Neurobiology Lane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a first Ask Insects neurobiology source lane for `Aedes aegypti` brain and neuron evidence.

**Architecture:** Add one deterministic source parser that emits provenance-rich `neurobiology` records from repo-local source metadata. Wire the parser into the existing builder, CLI build flags, planner, answer text, source map, docs, and completion gate.

**Tech Stack:** Python standard library, SQLite FTS via existing `SourceIndex`, `unittest`, existing Ask Insects CLI.

---

## File Structure

- Create `askinsects/sources/neurobiology.py`: deterministic neurobiology source records and `fetch_neurobiology_records`.
- Create `tests/test_neurobiology_source.py`: parser and SQLite payload tests.
- Modify `askinsects/builder.py`: include `include_neurobiology`, call source parser, add receipts.
- Modify `scripts/build_source_index.py`: add `--neurobiology`.
- Modify `askinsects/planner.py`: route brain/neuron questions to neurobiology.
- Modify `askinsects/answer.py`: add neurobiology answer text and query phrases.
- Modify `tests/test_builder.py`, `tests/test_cli.py`, `tests/test_answer.py`, `tests/test_verify_complete.py`.
- Modify `README.md`, `docs/source-lanes.md`, `docs/querying-ask-insects.md`, `config/source-map.yaml`.
- Modify `scripts/verify_complete.py`: require source, tests, spec, and plan.

## Task 1: Source Parser

- [ ] Write failing tests in `tests/test_neurobiology_source.py`.
- [ ] Run `python3 -m unittest tests.test_neurobiology_source -v` and confirm it fails because the source module is missing.
- [ ] Create `askinsects/sources/neurobiology.py` with deterministic source atoms.
- [ ] Run `python3 -m unittest tests.test_neurobiology_source -v` and confirm it passes.
- [ ] Commit with `feat: add neurobiology source parser`.

## Task 2: Builder And CLI Wiring

- [ ] Add failing builder and CLI tests for `--neurobiology`.
- [ ] Run `python3 -m unittest tests.test_builder tests.test_cli -v` and confirm failure.
- [ ] Wire `include_neurobiology` through `askinsects/builder.py`.
- [ ] Add `--neurobiology` to `scripts/build_source_index.py`.
- [ ] Run `python3 -m unittest tests.test_builder tests.test_cli -v` and confirm pass.
- [ ] Commit with `feat: wire neurobiology source builds`.

## Task 3: Query Routing And Answers

- [ ] Add failing answer tests for brain/neuron routing and neurobiology evidence.
- [ ] Run `python3 -m unittest tests.test_answer -v` and confirm failure.
- [ ] Update `askinsects/planner.py` and `askinsects/answer.py`.
- [ ] Run `python3 -m unittest tests.test_answer -v` and confirm pass.
- [ ] Commit with `feat: answer neurobiology questions from source lane`.

## Task 4: Docs, Source Map, Completion Gate

- [ ] Update source map and docs with the neurobiology lane.
- [ ] Update `scripts/verify_complete.py` and `tests/test_verify_complete.py`.
- [ ] Run `python3 -m unittest tests.test_verify_complete -v`.
- [ ] Run `python3 scripts/verify_complete.py`.
- [ ] Commit with `test: require neurobiology source gate`.

## Task 5: Install And Prove

- [ ] Run full tests: `python3 -m unittest discover -s tests -v`.
- [ ] Run completion gate: `python3 scripts/verify_complete.py`.
- [ ] Merge the branch into `main`.
- [ ] Refresh `/Users/josh/.local/share/ask-insects/main` from `main`.
- [ ] Build the installed artifact with fixtures, NCBI genomics, and neurobiology.
- [ ] Verify global command from `/tmp`:

```bash
ask-insects sources
ask-insects summary
ask-insects search neurobiology "brain atlas" --limit 3
ask-insects ask "what neuron data exists for the Aedes aegypti brain?" --json
```
