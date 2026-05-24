# Aedes Aegypti Genomics Lane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an NCBI Datasets genomics source lane for `Aedes aegypti` that parses assembly metadata, GFF features, and protein FASTA headers into Ask Insects SQLite records with provenance.

**Architecture:** Add a focused `askinsects/sources/ncbi_genome.py` parser that reads an existing NCBI Datasets package directory and normalizes source atoms into `EvidenceRecord` rows. Wire it through the builder, build script, docs, answer planner, and completion gate without making tests depend on live network downloads.

**Tech Stack:** Python standard library, `argparse`, JSONL, GFF3 parsing, FASTA header parsing, SQLite via existing `SourceIndex`, `unittest`.

---

## File Structure

- Create `askinsects/sources/ncbi_genome.py`: NCBI Datasets package parser and normalizer.
- Create `tests/test_ncbi_genome_source.py`: fixture package tests for assembly, GFF, FASTA, payloads, and gaps.
- Modify `askinsects/builder.py`: accept and receipt `include_ncbi_genome`.
- Modify `scripts/build_source_index.py`: add `--ncbi-genome`, `--genome-package-dir`, and `--genome-assembly-accession`.
- Modify `askinsects/planner.py`: route genome, gene, transcript, protein, receptor, and resistance questions to genomics lanes.
- Modify `tests/test_builder.py`, `tests/test_cli.py`, `tests/test_answer.py`: cover builder, script parser, and planner/answer behavior.
- Modify `config/source-map.yaml`, `docs/source-lanes.md`, `docs/querying-ask-insects.md`, `README.md`: document the source lane and commands.
- Modify `scripts/verify_complete.py`: include the new source file, tests, docs, and deterministic unit test module.

## Task 1: NCBI Genome Source Parser

**Files:**
- Create: `askinsects/sources/ncbi_genome.py`
- Create: `tests/test_ncbi_genome_source.py`

- [ ] **Step 1: Write failing source parser tests**

Create a test fixture package inside a temporary directory with:

```text
ncbi_dataset/data/assembly_data_report.jsonl
ncbi_dataset/data/GCF_002204515.2/genomic.gff
ncbi_dataset/data/GCF_002204515.2/protein.faa
```

The test imports `fetch_ncbi_genome_records`, calls it with the package directory, and asserts records for `genome_assemblies`, `genes`, `transcripts`, `genome_features`, and `proteins`.

- [ ] **Step 2: Verify the tests fail**

Run:

```bash
python3 -m unittest tests.test_ncbi_genome_source -v
```

Expected: failure because `askinsects.sources.ncbi_genome` does not exist.

- [ ] **Step 3: Implement the parser**

Implement:

```python
NCBI_GENOME_SOURCE_ID = "ncbi_datasets_genome"
DEFAULT_ASSEMBLY_ACCESSION = "GCF_002204515.2"
@dataclass(frozen=True)
class NCBIGenomeBuildResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    package_dir: str
    assembly_accession: str
```

Add helpers for JSONL, GFF attributes, GFF rows, FASTA records, and `fetch_ncbi_genome_records(...)`.

- [ ] **Step 4: Verify source parser tests pass**

Run:

```bash
python3 -m unittest tests.test_ncbi_genome_source -v
```

Expected: pass.

## Task 2: Builder And Build Script Wiring

**Files:**
- Modify: `askinsects/builder.py`
- Modify: `scripts/build_source_index.py`
- Modify: `tests/test_builder.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing builder and parser tests**

Add tests that build fixtures plus the fake NCBI genome package and assert:

- `source_status.json` includes `ncbi_datasets_genome`
- source counts include the NCBI records
- lanes include `genome_assemblies`, `genes`, `transcripts`, `genome_features`, and `proteins`
- `scripts/build_source_index.py` accepts `--ncbi-genome --genome-package-dir <path>`

- [ ] **Step 2: Verify failure**

Run:

```bash
python3 -m unittest tests.test_builder tests.test_cli -v
```

Expected: fail because builder and script do not know the NCBI genome lane.

- [ ] **Step 3: Wire builder and script**

Add `include_ncbi_genome`, `genome_package_dir`, and `genome_assembly_accession` parameters to `build_source_index(...)`. Add CLI parser flags and pass them through.

- [ ] **Step 4: Verify builder and parser tests pass**

Run:

```bash
python3 -m unittest tests.test_builder tests.test_cli -v
```

Expected: pass.

## Task 3: Query Routing And Docs

**Files:**
- Modify: `askinsects/planner.py`
- Modify: `tests/test_answer.py`
- Modify: `README.md`
- Modify: `config/source-map.yaml`
- Modify: `docs/source-lanes.md`
- Modify: `docs/querying-ask-insects.md`

- [ ] **Step 1: Write failing answer/planner test**

Add a test that inserts a genomics record and asks about an odorant receptor. Assert the answer returns genomics evidence rather than a generic observation row.

- [ ] **Step 2: Verify failure**

Run:

```bash
python3 -m unittest tests.test_answer -v
```

Expected: fail because genomics wording is not routed yet.

- [ ] **Step 3: Route genomics questions**

Update planner lane terms so genome, gene, transcript, protein, receptor, odorant, gustatory, ionotropic, Orco, cytochrome P450, sodium channel, and insecticide-resistance questions search genomics lanes.

- [ ] **Step 4: Update docs and source map**

Document `ncbi_datasets_genome`, package input, lanes, and example commands.

- [ ] **Step 5: Verify targeted tests pass**

Run:

```bash
python3 -m unittest tests.test_answer -v
```

Expected: pass.

## Task 4: Completion Gate And Final Verification

**Files:**
- Modify: `scripts/verify_complete.py`

- [ ] **Step 1: Update completion gate**

Require:

- `askinsects/sources/ncbi_genome.py`
- `tests/test_ncbi_genome_source.py`
- genomics design doc
- genomics implementation plan
- source-map entry for `ncbi_datasets_genome`

Add `tests.test_ncbi_genome_source` to deterministic unit modules.

- [ ] **Step 2: Run final verification**

Run:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/verify_complete.py
```

Expected: all tests pass and the gate prints `verify_complete ok`.

- [ ] **Step 3: Run a local smoke build with the fixture package from tests**

Run a small temp-package build or use the test helper to create one, then:

```bash
python3 -m askinsects --artifact-dir <tmp-artifact-dir> search genes "odorant receptor"
python3 -m askinsects --artifact-dir <tmp-artifact-dir> search proteins "gustatory receptor"
```

Expected: genomics rows return with `ncbi_datasets_genome` provenance.
