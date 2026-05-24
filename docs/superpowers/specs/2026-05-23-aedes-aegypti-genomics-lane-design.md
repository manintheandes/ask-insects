# Aedes Aegypti Genomics Lane Design

## Purpose

The genomics lane makes Ask Insects answer source-backed questions about what is inside the mosquito, not only where it has been observed.

The first slice covers the `Aedes aegypti` reference genome and gene products. It should let a user ask about the assembly, genes, transcripts, proteins, and named functional features with row-level provenance.

This lane does not replace the literature lane. Papers explain scientific claims. Genomics records provide structured source atoms: assembly metadata, gene coordinates, transcript identifiers, protein products, and annotation text.

## Source Boundary

The first canonical source is NCBI Datasets for `Aedes aegypti` assembly `GCF_002204515.2`.

Ask Insects will ingest a local NCBI dataset package layout containing:

- `ncbi_dataset/data/assembly_data_report.jsonl`
- `ncbi_dataset/data/GCF_002204515.2/genomic.gff`
- optional `ncbi_dataset/data/GCF_002204515.2/protein.faa`

The implementation is designed so a future live downloader can fetch the same package from NCBI, but V1 parses an already downloaded package path. That keeps deterministic tests offline and avoids making the completion gate depend on a large network download.

## Data Model

Raw package files remain raw artifacts. Ask Insects does not split every DNA base into SQLite rows.

The SQLite index gets useful, queryable atoms:

- `genome_assemblies`: one row per genome assembly.
- `genome_features`: one row per parsed `gene`, `mRNA`, `transcript`, `CDS`, or named sequence feature in GFF.
- `genes`: one row per GFF `gene`.
- `transcripts`: one row per GFF transcript-like feature.
- `proteins`: one row per FASTA protein sequence header.

Every normalized row stores the original source payload in `record_payloads` when useful. GFF rows store raw columns plus parsed attributes. Protein rows store the FASTA header and sequence length, not the full protein sequence in answer text.

## Query Behavior

The normal Ask Insects CLI should work without a special genomics command:

```bash
python3 -m askinsects search genes "odorant receptor"
python3 -m askinsects search proteins "gustatory receptor"
python3 -m askinsects ask "what genome assembly do we have for Aedes aegypti?"
python3 -m askinsects sql "select lane, count(*) from records group by lane"
```

The answer planner should route genome, gene, transcript, protein, receptor, odorant receptor, gustatory receptor, ionotropic receptor, cytochrome P450, sodium channel, and insecticide-resistance wording toward genomics lanes.

## Provenance

Each row must cite:

- source id `ncbi_datasets_genome`
- raw file locator with a stable fragment, such as `genomic.gff#line/42` or `protein.faa#protein/XP_001`
- retrieval or parse time
- source URL for the assembly, when known
- NCBI public data license text or metadata label

The source receipt records the package path, assembly accession, source files parsed, record counts by lane, and structured gaps.

## Error Handling

Missing package paths fail plainly before parsing.

Missing optional protein FASTA creates a structured gap but still allows assembly and GFF records to ingest. Malformed GFF rows create structured gaps and do not become evidence. Missing assembly metadata creates a structured gap and still permits GFF/protein parsing if those files exist.

## Testing

Tests use tiny local fixture files that look like an NCBI Datasets package. They must prove:

- assembly metadata becomes a `genome_assemblies` row
- GFF genes, transcripts, and CDS/features become indexed rows
- protein FASTA headers become `proteins` rows
- payloads are queryable in SQLite
- the build script accepts `--ncbi-genome --genome-package-dir`
- the completion gate remains deterministic and offline

## Future Extensions

After this lane works, a hosted ingest can download the package on the Google VM and activate it with the same staged pattern used by GBIF and iNaturalist. Ensembl/VectorBase can then enrich names, orthology, variants, and vector-specific annotations without replacing the NCBI canonical source.
