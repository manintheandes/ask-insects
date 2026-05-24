# Aedes VectorBase Genomics Lane Design

## Goal

Add an official VectorBase/VEuPathDB genomics lane for `Aedes aegypti` so Ask Insects can answer gene, transcript, protein, and GO annotation questions from the mosquito-specific genomics resource, not only from NCBI package rows.

## Source Boundary

The source is the official VectorBase current-release download tree for `AaegyptiLVP_AGWG`:

- `https://vectorbase.org/common/downloads/Current_Release/AaegyptiLVP_AGWG/gff/data/VectorBase-68_AaegyptiLVP_AGWG.gff`
- `https://vectorbase.org/common/downloads/Current_Release/AaegyptiLVP_AGWG/fasta/data/VectorBase-68_AaegyptiLVP_AGWG_AnnotatedProteins.fasta`
- `https://vectorbase.org/common/downloads/Current_Release/AaegyptiLVP_AGWG/gaf/VectorBase-CURRENT_AaegyptiLVP_AGWG_GO.gaf.gz`

The lane does not mirror raw genome bases by default. It indexes annotation atoms that improve answers: genes, transcripts, proteins, and GO associations. Raw downloaded files are preserved under `raw/vectorbase_genomics/`.

## Records

- `genes`: one record per VectorBase `gene` GFF row.
- `transcripts`: one record per VectorBase transcript-like GFF row.
- `proteins`: one record per annotated protein FASTA header.
- `genome_features`: one record per GO annotation row.

Each record carries `source=vectorbase_aedes_genomics`, `species=Aedes aegypti`, the official file URL, a raw local locator with line/header number, and a payload containing parsed fields.

## Gaps

Malformed GFF rows, malformed protein headers, download failures, or unreadable GAF rows become structured gaps. Missing optional files should not erase other VectorBase records, but the receipt must state the gap.

## Ask Surface

Existing genomics routing should find this lane because it already searches `genes`, `transcripts`, `proteins`, and `genome_features`. Prioritization should prefer VectorBase for queries that name VectorBase, GO, orthology-adjacent annotation, or AAEL identifiers.

## Completion Evidence

- Unit tests parse fixture GFF, FASTA, and GAF files into all expected lanes.
- Ingest test proves the lane updates an existing artifact without removing other source rows.
- CLI and hosted-server tests prove `/ingest/vectorbase-genomics` is wired.
- `python3 scripts/verify_complete.py` includes the new source, script, docs, and tests.
