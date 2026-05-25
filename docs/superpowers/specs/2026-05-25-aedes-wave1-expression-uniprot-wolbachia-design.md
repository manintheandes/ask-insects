# Aedes Wave 1 Expression, UniProt, And Wolbachia Design

## Goal

Add three high-value `Aedes aegypti` source lanes that deepen the mosquito intelligence plane beyond literature and genome-package rows:

- `aedes_expression_omics`: bounded NCBI GEO/SRA expression, RNA-seq, and transcriptome metadata.
- `aedes_uniprot_proteins`: bounded UniProtKB protein-function and UniProt proteome metadata for taxonomy `7159`.
- `aedes_wolbachia_interventions`: World Mosquito Program Wolbachia intervention evidence at public-page grain.

## Source Boundaries

Expression omics uses NCBI E-utilities `gds` and `sra` searches for `Aedes aegypti` expression/RNA-seq/transcriptome metadata. It indexes GEO dataset summaries and SRA run atoms. It does not claim computed count matrices, differential-expression results, or raw-read reanalysis.

UniProt uses UniProt REST search for NCBI taxonomy `7159`. It indexes bounded protein records and proteome records with accession, reviewed status, protein name, gene names, function comments, GO references, VectorBase references, keywords, proteome IDs, and raw JSON locators.

Wolbachia interventions use public World Mosquito Program pages and releases for Wolbachia method, mechanism, global progress, and Yogyakarta trial evidence. It indexes page-grain public-health records with source-mentioned metrics. It does not replace formal trial-table extraction from publications.

## Records

- `expression`: GEO dataset records and SRA run records from `aedes_expression_omics`.
- `proteins`: UniProtKB protein records and UniProt proteome records from `aedes_uniprot_proteins`.
- `public_health`: WMP intervention evidence pages from `aedes_wolbachia_interventions`.

Every record must carry `species=Aedes aegypti`, a source URL, raw saved artifact locator, payload JSON, and receipt metadata.

## Gaps

Fetch failures, empty searches, missing URLs, and parse gaps become structured `gaps.json` rows scoped to the source id. These are source gaps, not answer prose.

## Ask Surface

Expression/RNA-seq/GEO/SRA questions route to the `expression` lane. UniProt, proteome, and protein-function questions route through genomics but prefer `aedes_uniprot_proteins`. World Mosquito Program, Wolbachia, WMP, and Yogyakarta intervention questions route to public health and prefer `aedes_wolbachia_interventions`.

## Completion Evidence

- Parser tests prove each source normalizes fixture payloads and records gaps.
- Ingest tests prove all three sources update an existing artifact without deleting other rows.
- CLI tests prove hosted commands send bounded options.
- Server tests prove hosted ingest routes call the right scripts.
- `scripts/verify_complete.py` requires files, tests, docs, source-map terms, and coverage-ledger terms.
