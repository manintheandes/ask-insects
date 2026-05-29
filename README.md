# Open Insects

Open Insects is an open-source effort to make insect knowledge queryable, source-backed, and actionable.

Ask Insects is the first tool in Open Insects: a CLI and hosted source plane for asking evidence-backed questions about insects. The command remains `ask-insects`.

Public home: `https://openinsects.org`

V1 starts with mosquitoes, then expands to other insect groups. It follows a source-plane pattern:

```text
source artifacts -> mapped lanes -> local parsed indexes -> receipts -> CLI -> answer with provenance or gap
```

## License And Open Source Boundary

Ask Insects code and project-authored documentation are licensed under Apache-2.0. See `LICENSE`.

Third-party scientific data, images, videos, papers, API payloads, and database exports are not relicensed by Ask Insects. They remain governed by upstream licenses and terms. See `NOTICE` and `THIRD_PARTY_DATA.md`.

The public repository ships code, docs, tests, source maps, small deterministic fixtures, and provenance rules. Raw artifacts, SQLite mirrors, video archives, paper downloads, API tokens, and credentials stay out of git.

## Comprehensive Mosquito Intelligence Goal

The current comprehensive-source strategy is Aedes-first: build Ask Insects toward the most comprehensive `Aedes aegypti` intelligence system in the world. That is the goal, not a claim the repo is allowed to make blindly. Other mosquitoes can still be indexed as comparison records, but they are not the completion boundary for this push. Open Insects expands outward from that source-backed base.

The machine-readable coverage ledger is `config/mosquito-intelligence-coverage.json`. It is the durable backlog for domains that are not source grade yet. Do not treat a domain as covered unless the ledger, source map, receipts, SQLite records, and Ask Insects CLI all agree.

Ask Insects can also ingest that ledger into queryable source-coverage records:

```bash
python3 -m askinsects ingest-source-coverage
python3 -m askinsects ask "what is missing from Aedes coverage?" --json
```

The derived source `aedes_source_coverage` creates one overview record, one record per coverage domain, and one missing-coverage record per required next source. These records let status and gap questions answer from the same ledger that governs the source contract, rather than falling through to unrelated literature records.

The machine-readable benchmark is `config/aedes-source-plane-benchmark.json`, with the plain-English readout in `docs/aedes-source-plane-benchmark.md`. It currently marks the world-largest/world-deepest claim as not proven. The safe current wording is: Ask Insects is a broad, integrated, provenance-backed `Aedes aegypti` query plane.

## Spotted Wing Drosophila Expansion

Ask Insects now has an explicit expansion boundary for spotted wing drosophila, `Drosophila suzukii`. The first source-grade pass is `drosophila_suzukii_core`: a bounded composite source that can ingest GBIF taxonomy and occurrence rows, iNaturalist licensed still-image observations, OpenAlex literature metadata from 2020 onward, BOLD DNA barcode rows, and queryable coverage/gap records for the deeper lanes that still need work.

```bash
python3 -m askinsects ingest-drosophila-suzukii --gbif-occurrence-limit 100 --inaturalist-observation-limit 100 --literature-max-works 100 --bold-limit 100
python3 -m askinsects ask "what do we know about spotted wing drosophila?" --json
python3 -m askinsects search source_coverage "Drosophila suzukii missing"
```

This does not claim Aedes-level depth yet. It makes `Drosophila suzukii` source-grade at the core boundary. Follow-on lanes now promote SWD genomics, legal direct full-text units, PubMed literature reconciliation, GenBank nucleotide cross-checks, broader mitochondrial/nuclear marker reviews, NCBI Gene orthology plus GeneID-to-GFF mapping, dbSNP availability audits, Dryad population-variant VCF manifests and gaps, extension/IPM guidance, supplement audit, first video atoms, occurrence ecology, and literature-derived crop-damage, pest-management, resistance, and biocontrol records. The remaining gaps are motion-table rows, Ensembl stable-ID history/current-ID mapping, VCF row mirroring/parsing and broader non-dbSNP variant-table review, structured susceptibility assay tables, and human-validated pest-science tables.

The next depth layer is `drosophila_suzukii_deep_sources`. It adds bounded NCBI assembly, BioProject, BioSample, and SRA metadata, UniProt protein and proteome metadata, and repository candidate sweeps across Zenodo, Figshare, and Dryad:

```bash
python3 -m askinsects ingest-drosophila-suzukii-deep-sources --ncbi-limit 50 --protein-limit 100 --repository-limit 50
python3 -m askinsects ask "show Drosophila suzukii SRA and genome evidence" --json
python3 -m askinsects search media "Drosophila suzukii video"
```

Genome-file parsing, legal direct full-text enrichment, per-paper supplement audit, first video atoms, occurrence ecology, extension/IPM guidance, and literature-derived crop-damage, management, resistance, and biocontrol are now promoted through follow-on SWD lanes. Larger full-text coverage, motion-table rows, structured susceptibility assay tables, and human-validated pest-science tables remain follow-on work.

The `drosophila_suzukii_genome_files` lane promotes the genome-file gap into parsed rows for a selected NCBI assembly. It downloads bounded public NCBI GFF and protein FASTA files, then indexes assembly, gene, transcript, functional genome-feature, and protein rows with locators back to the mirrored files.

```bash
python3 -m askinsects ingest-drosophila-suzukii-genome-files --assembly-accession GCF_043229965.1
python3 -m askinsects search genes "Drosophila suzukii orco"
python3 -m askinsects search proteins "Drosophila suzukii odorant receptor"
```

The `drosophila_suzukii_occurrence_ecology` lane turns existing spotted wing observation rows into country, month, seasonality, coordinate, and habitat-style ecology summaries. It does not fetch new observations; it derives queryable ecology rows from the indexed GBIF and iNaturalist payloads.

```bash
python3 -m askinsects ingest-drosophila-suzukii-occurrence-ecology
python3 -m askinsects ask "where is Drosophila suzukii observed by month?" --json
python3 -m askinsects search ecology "Drosophila suzukii seasonality country"
```

The `drosophila_suzukii_literature_fulltext` path enriches indexed SWD papers with legal direct open full-text chunks. It uses OpenAlex direct open-file URLs already in the paper payloads, and can optionally query Unpaywall when an email is supplied. It does not use paywalled PDFs, private cookies, institutional access, or publisher landing pages that do not expose a direct open file.

```bash
python3 -m askinsects ingest-drosophila-suzukii-literature-fulltext --limit 25
python3 -m askinsects search fulltext "Drosophila suzukii oviposition"
python3 -m askinsects sql "select source, count(*) as n from literature_fulltext_units where source='drosophila_suzukii_literature_fulltext' group by source"
```

The `drosophila_suzukii_pubmed_literature` lane reconciles SWD literature with PubMed. It fetches bounded PubMed ESearch/ESummary metadata for `Drosophila suzukii` and spotted wing drosophila papers since 2020, stores one literature audit row per PMID, and marks whether that PubMed paper is already covered by the canonical OpenAlex SWD lane or is currently PubMed-metadata-only.

```bash
python3 -m askinsects ingest-drosophila-suzukii-pubmed-literature --max-results 1000 --page-size 100
python3 -m askinsects search literature "Drosophila suzukii PubMed coverage_status"
python3 -m askinsects sql "select json_extract(payload_json, '$.coverage_status') as status, count(*) as n from record_payloads where source='drosophila_suzukii_pubmed_literature' group by status"
```

The `drosophila_suzukii_ncbi_nucleotide` lane cross-checks SWD barcode coverage against NCBI nuccore/GenBank. It fetches bounded COI/barcode-like nucleotide metadata, stores one `dna_barcodes` row per accession, and marks whether the accession matched an existing BOLD row or is GenBank-only metadata.

```bash
python3 -m askinsects ingest-drosophila-suzukii-ncbi-nucleotide --max-results 1000 --page-size 100
python3 -m askinsects ask "show Drosophila suzukii GenBank COI nucleotide cross-check" --json
python3 -m askinsects sql "select json_extract(payload_json, '$.bold_match_status') as status, count(*) as n from record_payloads where source='drosophila_suzukii_ncbi_nucleotide' group by status"
```

The `drosophila_suzukii_ncbi_marker_review` lane broadens sequence coverage beyond COI/barcode-like records. It fetches bounded NCBI nuccore/GenBank metadata for SWD mitochondrial and nuclear marker accessions, including COII/COX2, NADH/ND loci, cytochrome b, ribosomal 18S/28S, ITS, elongation-factor, and related marker-like records. It is accession metadata evidence, not proof of sequence equivalence or variant interpretation.

```bash
python3 -m askinsects ingest-drosophila-suzukii-ncbi-marker-review --max-results 2000 --page-size 100
python3 -m askinsects ask "show Drosophila suzukii nuclear marker review" --json
python3 -m askinsects sql "select json_extract(payload_json, '$.marker_group') as marker_group, count(*) as n from record_payloads where source='drosophila_suzukii_ncbi_marker_review' group by marker_group"
```

The `drosophila_suzukii_ncbi_snp_variation` lane audits NCBI dbSNP for SWD organism records. Current public dbSNP ESearch returns zero `Drosophila suzukii` records, so Ask Insects stores a queryable source-gap record instead of claiming variant coverage.

```bash
python3 -m askinsects ingest-drosophila-suzukii-ncbi-snp-variation --limit 1000 --page-size 200
python3 -m askinsects ask "show Drosophila suzukii dbSNP variant records" --json
```

The `drosophila_suzukii_ncbi_gene_orthologs` lane closes the first SWD orthology gap. It fetches the public NCBI Gene `gene_orthologs.gz` FTP table, keeps rows where either side is `Drosophila suzukii` taxon 28584, and joins SWD GeneIDs back to indexed GFF gene records when possible. Ensembl stable-ID history remains a separate current-ID source lane.

```bash
python3 -m askinsects ingest-drosophila-suzukii-ncbi-gene-orthologs
python3 -m askinsects ask "show Drosophila suzukii Orco orthologs" --json
python3 -m askinsects sql "select json_extract(payload_json, '$.partner_tax_id') as partner_tax_id, count(*) as n from record_payloads where source='drosophila_suzukii_ncbi_gene_orthologs' group by partner_tax_id order by n desc limit 10"
```

The `drosophila_suzukii_ensembl_metazoa_orthology` lane adds release-pinned Ensembl Metazoa current gene IDs, NCBI GeneID xrefs, and Drosophila melanogaster homolog rows. It also audits Ensembl's stable-ID history tables. In release 62 those history tables exist but are empty, so Ask Insects stores explicit history-empty gaps instead of pretending historical ID mappings are covered.

```bash
python3 -m askinsects ingest-drosophila-suzukii-ensembl-metazoa-orthology
python3 -m askinsects ask "show Drosophila suzukii Ensembl Dmel homologs for Dpit47" --json
python3 -m askinsects sql "select json_extract(payload_json, '$.relationship') as relationship, count(*) as n from record_payloads where source='drosophila_suzukii_ensembl_metazoa_orthology' and json_extract(payload_json, '$.atom_type')='ensembl_metazoa_dmel_homolog' group by relationship order by n desc"
```

The `drosophila_suzukii_extension_guidance` lane promotes the dedicated extension-guidance gap into page-grain management records. It fetches public university extension/IPM and SWD-management guidance pages, saves raw HTML, and indexes organization, region, topic terms, guidance type, source URL, and raw locator.

```bash
python3 -m askinsects ingest-drosophila-suzukii-extension-guidance
python3 -m askinsects ask "show Drosophila suzukii extension IPM guidance" --json
```

The first Aedes-depth literature gate for spotted wing drosophila is `drosophila_suzukii_extracted_facts`. It audits every indexed SWD paper for supplements, preserves supplement manifests, parses supported public supplement tables when opted in, and emits source-backed candidate rows for behavior, crop damage, management, resistance, biocontrol, ecology, and genomics.

```bash
python3 -m askinsects ingest-drosophila-suzukii-extracted-facts --discover-supplements --download-supplements --max-supplement-discovery-records 500 --max-supplement-files 100
python3 -m askinsects ask "what is Drosophila suzukii supplement audit coverage?" --json
python3 -m askinsects sql "select lane, count(*) as n from records where source='drosophila_suzukii_extracted_facts' group by lane"
```

The first moving-image depth layer is `drosophila_suzukii_video_atoms`. It turns indexed SWD repository videos and supplement video locators into queryable video assets, bounded mirrors when license and size allow, checksums, byte sizes, ffprobe duration/fps/resolution/codec metadata, thumbnails, keyframes, preview clips, frame manifests, and explicit gaps when motion rows or binary verification are not available yet.

```bash
python3 -m askinsects ingest-drosophila-suzukii-video-atoms --mirror-videos --generate-artifacts --max-video-bytes 750000000
python3 -m askinsects ask "show Drosophila suzukii videos" --json
python3 -m askinsects ask "show spotted wing drosophila motion evidence" --json
```

## Quick Start

```bash
python3 scripts/build_source_index.py --fixtures
python3 -m askinsects health
python3 -m askinsects summary
python3 -m askinsects sources
python3 -m askinsects ask "what do we know about Aedes aegypti?"
python3 -m askinsects ask "show mosquito observations with images in Brazil"
python3 -m askinsects ask "what should a scientist inspect next for Culex pipiens?"
python3 scripts/verify_complete.py
```

## GBIF Source Lane

GBIF is the biodiversity occurrence source lane. Local pulls are opt-in and bounded:

```bash
python3 scripts/build_source_index.py --fixtures --gbif --species "Aedes aegypti" --occurrence-limit 3
python3 -m askinsects sources
python3 -m askinsects search observations "Aedes"
```

This writes raw GBIF API responses under `artifacts/mosquito-v1/raw/gbif/`, normalizes taxonomy and occurrence records into the SQLite index, and records source receipts. Unit tests use fake GBIF responses so the completion gate stays deterministic.

Hosted Ask Insects can deep-refresh GBIF for one species without rebuilding or deleting the existing iNaturalist lane:

```bash
python3 -m askinsects ingest-gbif --hosted --species "Aedes aegypti" --occurrence-limit 82237 --occurrence-page-size 300 --occurrence-workers 6 --delay-seconds 0
```

The hosted ingest paginates GBIF occurrence search with a small worker pool, stores raw page JSON under `/home/josh/ask-insects/artifacts/mosquito-v1/raw/gbif/`, stores raw GBIF match and occurrence payloads in SQLite `record_payloads`, refreshes only `gbif_api` rows, and keeps the active server database available until the staged refresh is ready. The May 24, 2026 hosted refresh installed 82,237 `Aedes aegypti` occurrence records plus the GBIF taxonomy row with zero GBIF gaps.

## iNaturalist Source Lane

iNaturalist is the live photo and observation lane. It is opt-in and bounded:

```bash
python3 -m askinsects ingest-inaturalist --species "Aedes aegypti" --place Brazil --observation-limit 10 --page-size 10 --delay-seconds 0
python3 -m askinsects sources
python3 -m askinsects ask "show mosquito observations with images in Brazil"
```

This writes raw iNaturalist API responses under `artifacts/mosquito-v1/raw/inaturalist/`, normalizes observation and still-image media records into the SQLite index, stores the raw per-record payloads in SQLite, and records source receipts. The incremental ingest refreshes only `inaturalist_api` rows, preserving literature, genomics, neurobiology, BOLD, and derived facet lanes. Unit tests use fake iNaturalist responses so the completion gate stays deterministic.

For a deeper `Aedes aegypti` ingest, use paginated API pulls with an explicit cap and delay:

```bash
python3 -m askinsects ingest-inaturalist --species "Aedes aegypti" --observation-limit 5758 --page-size 200 --delay-seconds 1
```

This saves each raw API page separately and records the page size, delay, and total iNaturalist results in the receipt.

SQLite keeps these layers:

- `records`: normalized Ask Insects evidence rows for answers, search, and provenance.
- `record_payloads`: raw per-record source payloads, keyed by `record_id`, for deeper source inspection.
- `literature_fulltext_units`: legal open full-text chunks for literature records when Unpaywall exposes a direct open text or PDF URL that Ask Insects can parse.

## Mosquito Alert Source Lane

Mosquito Alert is a citizen-science observation and image lane for `Aedes aegypti`, fetched through its public GBIF dataset:

```bash
python3 -m askinsects ingest-mosquito-alert --occurrence-limit 1000
python3 -m askinsects ask "show Mosquito Alert Aedes aegypti images from Brazil" --json
```

The lane writes GBIF dataset and occurrence pages under `raw/mosquito_alert/`, normalizes one `observations` record per Mosquito Alert occurrence and one `media` record per still image from source `mosquito_alert_gbif`, stores raw occurrence and media payloads in SQLite, and preserves both occurrence-level and image-level license fields. This is a source-specific Aedes slice, not a replacement for the broader GBIF occurrence mirror.

## VectorNet Surveillance Source Lane

`vectornet_aedes_surveillance` is the official VectorNet ECDC/EFSA regional-surveillance lane for `Aedes aegypti` rows in the public Darwin Core Archive:

```bash
python3 -m askinsects ingest-vectornet-surveillance
python3 -m askinsects ask "show VectorNet Aedes aegypti surveillance evidence" --json
```

The lane mirrors the public IPT archive under `raw/vectornet_surveillance/`, writes a filtered TSV of the source `Aedes aegypti` rows, indexes one `observations` record per source row, and adds `ecology` summary records by country and degree of establishment. Records preserve detection versus absence-surveillance status, individual count, life stage, sex, sampling protocol, date range, geography, identification method, CC-BY-4.0 license, and exact archive plus filtered-row locators.

## NCBI Genomics Source Lane

NCBI Datasets is the first genomics lane. V1 parses an unpacked `Aedes aegypti` genome package for assembly `GCF_002204515.2`:

```bash
python3 scripts/build_source_index.py --fixtures --ncbi-genome --genome-package-dir /path/to/ncbi-package
python3 -m askinsects search proteins "odorant receptor"
python3 -m askinsects search proteins "gustatory receptor"
python3 -m askinsects ask "show odorant receptor genes in Aedes aegypti"
```

This stores the package files as raw artifacts and indexes useful atoms into SQLite: genome assembly rows, GFF genes, transcripts, other genome features, and protein FASTA headers. It does not index every DNA base as an answer row.

## VectorBase Genomics Source Lane

`vectorbase_aedes_genomics` is the VectorBase/VEuPathDB Aedes-specific genomics lane for current-release `AaegyptiLVP_AGWG` annotation, cross-reference, and OrthoMCL current-release pair downloads:

```bash
python3 -m askinsects ingest-vectorbase-genomics
python3 -m askinsects search genes "AAEL odorant receptor"
python3 -m askinsects ask "show VectorBase AAEL000001 gene annotation for Aedes aegypti" --json
python3 -m askinsects ask "show VectorBase codon usage AUG for Aedes aegypti" --json
python3 -m askinsects ask "show VectorBase CDS sequence for AAEL000016" --json
```

This writes official GFF, annotated protein FASTA, annotated CDS FASTA, annotated transcript FASTA, GO GAF, codon usage, identifier event history, current-ID resolution rows, NCBI LinkOut, OrthoMCL CURRENT corePairs ortholog, coortholog, and inparalog downloads, and OrthoMCL release 6.21 orthogroups under `artifacts/mosquito-v1/raw/vectorbase_genomics/`. It normalizes records into `genes`, `transcripts`, `proteins`, and `genome_features`, stores parsed payloads in SQLite, and keeps provenance to the saved file line, FASTA header, LinkOut entry, pair row, or orthogroup row. OrthoMCL pair records are parsed when either side starts with the old Aedes namespace prefix `aaeg-old|AAEL`; orthogroup membership records are parsed when a group member starts with `aaeg|AAEL` or `aaeg-old|AAEL`. FASTA sequence records store sequence metadata and observed lengths, not every nucleotide as answer text.

## Expression Omics Source Lane

`aedes_expression_omics` is the bounded GEO/SRA metadata lane for `Aedes aegypti` expression, RNA-seq, and transcriptome studies:

```bash
python3 -m askinsects ingest-expression-omics --geo-limit 120 --sra-limit 300
python3 -m askinsects ask "show GEO RNA-seq expression data for Aedes aegypti midgut" --json
python3 -m askinsects search expression "Yogyakarta"
```

This writes paginated NCBI E-utilities GEO and SRA search/summary JSON under `raw/expression_omics/`, indexes GEO dataset/sample summaries and SRA run atoms into the `expression` lane, stores raw metadata payloads in SQLite, and preserves provenance to the saved ESummary result. ESearch pages and ESummary batches are saved separately when a refresh exceeds one request. The May 25, 2026 hosted refresh installed 420 expression data records: 120 GEO records and 300 SRA run records, with two limit-applied gaps preserving the larger NCBI result frontier. The lane also emits queryable source-gap records for raw SRA reanalysis, count matrices, normalized expression matrices, and differential-expression outputs not yet indexed.

## UniProt Protein Source Lane

`aedes_uniprot_proteins` is the UniProt protein-function and proteome metadata lane for `Aedes aegypti`:

```bash
python3 -m askinsects ingest-uniprot-proteins --protein-limit 250 --proteome-limit 10
python3 -m askinsects ask "show UniProt protein function for AAEL012345" --json
python3 -m askinsects search proteins "UniProt protein"
```

This writes UniProtKB and UniProt proteome JSON under `raw/uniprot_proteins/`, indexes bounded protein and proteome atoms into the `proteins` lane, and preserves accession, reviewed status, protein name, gene names, function comments, GO and VectorBase cross-references, keywords, proteome IDs, and raw JSON locators.

## VectorByte Traits Source Lane

`aedes_vectorbyte_traits` is the VectorByte/VecTraits trait-observation lane for `Aedes aegypti`:

```bash
python3 -m askinsects ingest-vectorbyte-traits --dataset-limit 20 --row-limit 5000
python3 -m askinsects ask "show VectorByte temperature trait data for Aedes aegypti fecundity" --json
python3 -m askinsects search traits "fecundity temperature"
```

This writes VBD Hub search JSON and VecTraits dataset JSON under `raw/vectorbyte_traits/`, indexes one `traits` record per Aedes aegypti source row, and preserves dataset ID, row ID, trait name, value, unit, temperature, stage, sex, habitat, lab/field context, location, citation, DOI, and raw JSON locators.

## VectorByte Abundance Source Lane

`aedes_vectorbyte_abundance` is the VectorByte/VecDyn abundance-observation lane for `Aedes aegypti`:

```bash
python3 -m askinsects ingest-vectorbyte-abundance --dataset-limit 5 --row-limit 5000
python3 -m askinsects ingest-vectorbyte-abundance --dataset-id 27006 --dataset-id 220 --dataset-limit 2 --row-limit 20000 --dataset-page-limit 120
python3 -m askinsects ingest-vectorbyte-abundance --dataset-id-file config/aedes-vectorbyte-abundance-datasets.txt --dataset-limit 25 --row-limit 100000 --dataset-page-limit 200
python3 -m askinsects ingest-vectorbyte-abundance --dataset-id 718 --dataset-id 724 --merge-existing --dataset-limit 2 --row-limit 5000 --dataset-page-limit 80
python3 -m askinsects ask "show VectorByte VecDyn Aedes aegypti abundance trap counts" --json
python3 -m askinsects search observations "VecDyn abundance"
```

This writes VecDyn provider metadata JSON and paginated sample JSON under `raw/vectorbyte_abundance/`, indexes one `ecology` record per Aedes-relevant VecDyn dataset plus one `observations` record per Aedes aegypti abundance sample row, and preserves sample value, unit, date, time, stage, sex, sampling method, coordinates, location, DOI, citation, dataset ID, and raw JSON locators. Use repeated `--dataset-id` flags or `--dataset-id-file` for curated exact-dataset receipts when a broad search frontier is too large or mixed-species. Use `--merge-existing` for chunked expansion: it refreshes only the requested VecDyn dataset IDs and keeps the rest of the existing `aedes_vectorbyte_abundance` source intact. Large VecDyn datasets remain bounded by explicit dataset, search-page, dataset-page, and row limits; skipped frontier rows become structured gaps.

## Aedes Deep Source Expansion Lane

`ingest-aedes-deep-sources` installs five bounded Aedes-specific source expansions at once:

- `aedes_taxonomy_authorities`: ECDC, OECD, MTI/WRBU-style, NCBI Taxonomy, and USDA NAL taxonomy authority pages or PDFs at page/PDF-text grain.
- `aedes_worldclim_climate`: WorldClim climate source pages plus optional bounded 10-minute bioclim raster samples joined to global-compendium occurrence coordinates.
- `aedes_global_compendium_occurrence`: global Aedes occurrence compendium rows filtered to `Aedes aegypti`.
- `aedes_population_genomics`: NCBI BioProject population-genomics metadata in `genome_features`.
- `aedes_who_resistance_guidance`: WHO Aedes insecticide-resistance method and discriminating-concentration pages in `resistance`.

```bash
python3 -m askinsects ingest-aedes-deep-sources --compendium-row-limit 5000 --bioproject-limit 20 --worldclim-sample-limit 100
python3 -m askinsects ask "show Aedes aegypti taxonomy synonyms from authority sources" --json
python3 -m askinsects ask "show WorldClim climate context for Aedes aegypti ecology" --json
python3 -m askinsects ask "show global Aedes aegypti occurrence compendium rows for Brazil" --json
python3 -m askinsects ask "show Aedes aegypti population genomics BioProject evidence" --json
python3 -m askinsects ask "show WHO Aedes insecticide resistance bioassay guidance" --json
```

Raw artifacts are saved under `artifacts/mosquito-v1/raw/aedes_deep_sources/`. The ingest refreshes only those five source IDs, writes source receipts, preserves row, page, or raster-zip locators, and records structured gaps for blocked authority pages or disabled/failed raster sampling.

Harvard Dataverse suitability is a separate ecology lane because it is a live file-search boundary rather than a fixed five-source bundle:

```bash
python3 -m askinsects ingest-harvard-dataverse-suitability
python3 -m askinsects ask "show Harvard Dataverse suitability rasters for Aedes aegypti dengue transmission" --json
python3 -m askinsects sql "select source, lane, count(*) as n from records where source='harvard_dataverse_aedes_suitability' group by source, lane"
```

This lane uses source id `harvard_dataverse_aedes_suitability`. It saves bounded Harvard Dataverse search and dataset-detail JSON under `raw/harvard_dataverse_suitability/`, indexes ecology file manifests with dataset DOI, file DOI, file ID, filename, content type, byte size, checksum, scenario terms, license, and access locator, and keeps explicit `dataverse_file_download_not_public` gaps when Dataverse says a raster binary is not public-downloadable.

## BOLD DNA Barcode Source Lane

BOLD is the public DNA barcode source lane for `Aedes aegypti` specimen and COI-style marker records:

```bash
python3 scripts/ingest_bold_barcodes.py --artifact-dir artifacts/mosquito-v1 --species "Aedes aegypti" --limit 500
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 search dna_barcodes "COI Aedes aegypti"
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show BOLD COI barcode records for Aedes aegypti" --json
```

The lane writes raw BOLD TSV under `raw/bold/`, normalizes public barcode/specimen atoms into `dna_barcodes`, stores raw row payloads in SQLite, and records bounded-download gaps such as `bold_limit_applied`.
If the public API blocks the runtime IP, use `--tsv-path path/to/Aedes_aegypti_bold_combined.tsv` to ingest a saved BOLD TSV through the same parser and receipt path.

## PMC Video Source Lane

PMC open-access article pages are the first moving-image lane for `Aedes aegypti` videos:

```bash
python3 -m askinsects ingest-pmc-videos
python3 -m askinsects ingest-pmc-videos --hosted
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show Aedes aegypti videos" --json
```

The lane stores raw PMC article HTML under `raw/pmc_videos/`, prefers direct NCBI CDN MP4/WebM/AVI/MOV links when article pages expose both CDN and `/articles/instance/.../bin/...` download-page URLs, normalizes them as `media` records from source `pmc_open_access_videos`, stores per-record payloads in SQLite, and records the article URL, video URL, license text, DOI, and raw HTML locator. This is one source-grade video layer, not the final video corpus.

## Dryad Behavior And Video Source Lane

Dryad public datasets add file-grained behavior and video archive manifests for `Aedes aegypti` host-seeking, visual-threat, flight-escape, mating/courtship, male host-attraction, and visual-tracking studies:

```bash
python3 -m askinsects ingest-dryad-behavior-videos
python3 -m askinsects ask "show Dryad Aedes aegypti behavior videos" --json
python3 -m askinsects search behavior "thermal infrared host seeking"
```

The lane uses source id `dryad_aedes_behavior_videos`. It writes Dryad dataset, version, file-manifest API responses, public landing-page HTML, and public table-preview JavaScript under `raw/dryad_behavior_videos/`, normalizes one `behavior` record per dataset plus file-level `media` records for video/archive files, file-level `behavior` records for README/source-data files, and landing-page assay-method records for host-seeking, visual-tracking, repellent, flight, and related behavior descriptions. It stores raw manifest payloads in SQLite and preserves DOI, license, size, checksum, behavior labels, API download URL, browser-facing file-stream URL, and exact provenance. Each video/archive file also gets a queryable `dryad_archive_contents_not_decoded` gap record until the archive is expanded into per-video assets, keyframes, previews, frame manifests, and motion rows. CSV/XLSX source-data files are bounded table-parse candidates; when the Dryad download route blocks row parsing but Dryad exposes a public preview table, Ask Insects parses the preview rows as `table_source=dryad_preview` and keeps a queryable `dryad_table_file_download_blocked_preview_used` audit gap. Files with no parseable download or preview stay queryable table-gap records with filename, DOI, size, checksum, download URL, and error provenance. It indexes manifest and public landing-page metadata by default; it does not mirror multi-gigabyte video archives unless a future repo plan explicitly requires binary mirroring.

## Mendeley Behavior And Media Source Lane

Mendeley Data public datasets add file-grained `Aedes aegypti` behavior and media manifests for high-speed mate-recognition videos, wingbeat sound files, flight-tone hearing data, and locomotory behavior video-analysis spreadsheets:

```bash
python3 -m askinsects ingest-mendeley-behavior-media
python3 -m askinsects ask "show Mendeley Aedes aegypti wing flash videos" --json
python3 -m askinsects search behavior "flight tone mate recognition"
```

The lane uses source id `mendeley_aedes_behavior_media`. It writes public Mendeley snapshot, folder, and file-manifest JSON under `raw/mendeley_behavior_media/`, normalizes one `behavior` record per dataset, one `behavior` record per folder, file-level `media` records for video, audio, or archive files, and file-level `behavior` records for spreadsheets, README, code, or source-data files. It also emits audio/acoustic behavior records for source-provided sound files, preserving folder-context stimulus labels such as frequency and white-noise comparisons when they appear in Mendeley folder names. For bounded public WAV files, it downloads the audio under `raw/mendeley_behavior_media/audio_files/` and emits decoded WAV metadata records with duration, sample rate, channel count, sample width, frame count, byte rate, checksum, and exact locator. It downloads public `.csv`, `.tsv`, and `.xlsx` Aedes table files into `raw/mendeley_behavior_media/table_files/` and emits parsed sheet-level plus row-level `behavior` records with headers, values, row numbers, row-level species truth when source tables contain mixed Aedes species, table behavior type labels such as trajectory, locomotory assay, acoustic wingbeat, phonotaxis, or electrophysiology, licenses, download URLs, and raw-file locators. It preserves DOI, license, folder path, size, content type, SHA-256 hash when supplied, download URL, view URL, behavior labels, and raw manifest payloads. It does not mirror multi-gigabyte binaries, decode video frames, or perform deep acoustic feature extraction beyond bounded WAV file metadata.

## OSF FlightTrackAI Video Source Lane

OSF project `cx762` adds file-grained `Aedes aegypti` FlightTrackAI flight-behavior video manifests:

```bash
python3 -m askinsects ingest-osf-flighttrackai-videos
python3 -m askinsects ask "show OSF FlightTrackAI Aedes aegypti videos" --json
python3 -m askinsects search behavior "FlightTrackAI flight behavior"
```

The lane uses source id `osf_flighttrackai_aedes_videos`. It writes the OSF project JSON, provider JSON, and recursive `osfstorage` manifests under `raw/osf_flighttrackai_videos/`, normalizes the project and folders as `behavior`, MP4 files as `media`, and executable, model, and instruction files as `behavior`. It preserves file size, OSF download URL, API locator, raw file payload, and provenance. It indexes manifest metadata by default; it does not mirror multi-gigabyte binaries unless a future repo plan explicitly requires binary mirroring.

## Zenodo Aedes Video Source Lane

Zenodo search adds bounded `Aedes aegypti` video file manifests:

```bash
python3 -m askinsects ingest-zenodo-aedes-videos --query '"Aedes aegypti" (video OR movie OR mp4 OR tracking)' --size 25
python3 -m askinsects ask "show Zenodo Aedes aegypti videos" --json
```

The lane uses source id `zenodo_aedes_videos`. It writes raw Zenodo search JSON under `raw/zenodo_aedes_videos/` and normalizes materially Aedes video files as `media` rows. It also writes queryable `video_gap` rows when a Zenodo search hit is out of scope, has no video files, or the search returns no usable candidates. It preserves Zenodo record ID, file name, download URL, source URL, license, byte size, source-provided hashes, raw record/file payloads, gap reasons, and exact search-result locators. Search terms alone are not species evidence.

## Figshare Aedes Video Source Lane

Figshare article search adds bounded `Aedes aegypti` video file manifests:

```bash
python3 -m askinsects ingest-figshare-aedes-videos --query "Aedes aegypti video" --page-size 100
python3 -m askinsects ask "show Figshare Aedes aegypti videos" --json
```

The lane uses source id `figshare_aedes_videos`. It writes raw Figshare search and article-detail JSON under `raw/figshare_aedes_videos/` and normalizes materially Aedes video files as `media` rows. It also writes queryable `video_gap` rows when a Figshare hit is out of scope, cannot be fetched, has no video files, or the search returns no usable candidates. It preserves Figshare article ID, file ID, filename, DOI, download URL, source URL, license, byte size, source-provided hashes, raw article/file payloads, gap reasons, and exact article-detail locators. Search terms alone are not species evidence.

## Aedes Video Atoms Source Lane

`aedes_video_atoms` turns video manifests and source tables into inspectable, queryable evidence:

```bash
python3 -m askinsects ingest-video-atoms --hosted --mirror-videos --generate-artifacts --discover-sources --max-video-bytes 750000000 --allowed-licenses "CC0,CC-BY,CC BY,Creative Commons,https://spdx.org/licenses/CC0-1.0.html" --max-discovery-results 1000
python3 -m askinsects ingest-video-atoms --hosted --discover-sources --discovery-repository dryad --merge-existing --skip-motion-rows --max-discovery-results 1000
python3 -m askinsects ask "show Aedes aegypti keyframes and previews" --json
python3 -m askinsects ask "show Aedes aegypti motion trajectory coordinates" --json
```

The lane derives from PMC, Dryad, Mendeley, OSF, Zenodo, Figshare, and repository-discovery candidates. For each downloadable video it stores checksum, byte size, duration, fps, resolution, codec, source paper or dataset, license, and exact locator when mirroring and probing are allowed. Bounded ZIP, TAR, TAR.GZ, and TGZ archives are mirrored, checksummed, expanded into member assets, and paired with archive manifest/member records; huge, unsupported, unreadable, or license-unclear archives become queryable `video_gap` records. If the file is too large, missing a download URL, blocked by license uncertainty, cannot be probed, is not actually video, comes from a repository sweep with no usable candidates, or appears only as a Zenodo/Figshare manifest gap, the ingest writes a queryable `video_gap` record instead of pretending coverage exists. Gap records preserve the source download URL, source URL, byte size, source-provided hashes when available, license text, source dataset, repository, original source, original reason, and locator. Discovery scope is strict: repository search terms do not count as Aedes evidence unless the source title, description, file name, citation, species field, or equivalent material metadata names `Aedes aegypti`. When artifact generation is enabled it emits thumbnails, sampled `keyframe_*.jpg` records, preview clips, and frame manifests with explicit `keyframes` entries under `raw/video_atoms/`; reruns upgrade older thumbnail-only artifact folders instead of preserving fake keyframes. Motion table inputs become `behavior` rows with behavior type, life stage, sex, assay, stimulus, arena, frame/time, track ID, coordinates, confidence when present, and source video asset joins when the table identifies a matching video. `--discover-sources` runs bounded PMC OA, Dryad, Mendeley, OSF, Zenodo, Figshare, institutional Dataverse-style, and indexed paper-supplement discovery. `--discovery-repository` scopes a follow-up pass to one repository and requires `--merge-existing`, so a small refresh replaces that repository's old assets, gaps, and sweep receipt while preserving other repositories and existing motion rows. `--skip-motion-rows` keeps repository follow-ups fast when the existing motion table rows should be preserved. Each repository also gets a `video_sweep` receipt record plus a receipt entry with status, raw candidate count, accepted candidate count, gap count, coverage method, exact query or local scan label, request URL or raw/local input source, page size, page count, page/cursor completeness, candidate limit, and limit status; the completion gate requires these sweep receipts for all eight targets, rejects thumbnail-derived keyframes, frame manifests without keyframe lists, stale unexpanded archive gaps, and broken motion-to-asset references, and keeps unmatched source-video identifiers as queryable gaps. The May 27, 2026 hosted video-atoms refresh plus scoped Dryad follow-up installed 46,252 Aedes video-atom records: 84 video assets, 21 verified mirrored videos, 179 inspectable artifacts including 116 sampled keyframes, 45,574 motion rows, and 407 structured video gaps.

## Aedes Image Atoms Source Lane

`aedes_image_atoms` turns indexed still-image media rows into queryable image assets, source-provided labels, and explicit label gaps:

```bash
python3 -m askinsects ingest-image-atoms
python3 -m askinsects ingest-image-atoms --mirror-images --max-image-mirrors 6000 --max-image-bytes 10000000 --allowed-licenses cc-by,cc-by-nc,cc-by-sa,CC0,Creative Commons
python3 -m askinsects ask "show Aedes aegypti adult image labels" --json
python3 -m askinsects ask "show Aedes image label coverage summary" --json
python3 -m askinsects ask "what Aedes image label gaps are missing sex?" --json
python3 -m askinsects ask "show Aedes aegypti images with checksum and dimensions" --json
```

The lane derives from `inaturalist_api` and `mosquito_alert_gbif` media records. It preserves image URL, source observation, license, source URL, attribution or creator, rights holder, place or country, observed date or event date, coordinates when supplied, iNaturalist quality grade when supplied, image format when supplied, and exact upstream locator. With `--mirror-images`, it also performs bounded licensed image-byte mirrors and stores SHA-256 checksum, byte size, detected dimensions, image format, EXIF presence when detectable, and local raw asset path. Label records are deterministic source metadata only. Coverage records summarize, by upstream source, how many Aedes image assets have or miss source-provided life-stage, sex, anatomy, and body-part labels. Missing life-stage, sex, anatomy, body-part labels, or skipped mirror bytes become queryable `image_gap` records until manual or vision-labeling lanes and larger mirror runs are added.

## IR Mapper Resistance Source Lane

IR Mapper is the dedicated insecticide-resistance source lane for `Aedes aegypti`:

```bash
python3 -m askinsects ingest-irmapper --species "Aedes aegypti"
python3 -m askinsects ask "what insecticide resistance data exists for Aedes aegypti?" --json
python3 -m askinsects sql "select country, count(*) from (select json_extract(payload_json, '$.raw_row.country') as country from record_payloads where source='irmapper_aedes') group by country order by count(*) desc" --limit 10
```

The lane writes the raw IR Mapper Aedes JSON under `raw/irmapper/`, normalizes `Aedes aegypti` and abbreviated `Ae. aegypti` rows into `resistance` records from source `irmapper_aedes`, stores the raw row payload in SQLite, and records provenance to the saved JSON row. Other Aedes species in the endpoint are comparison material, not installed by default for this Aedes-first push.

## WHO Malaria Threats Resistance Audit Lane

WHO's global insecticide-resistance database is audited as a bounded public source:

```bash
python3 -m askinsects ingest-who-malaria-threats-resistance
python3 -m askinsects ask "show the WHO insecticide resistance database rows for Aedes aegypti" --json
python3 -m askinsects sql "select source, lane, count(*) as n from records where source='who_malaria_threats_resistance_audit' group by source, lane"
```

The lane uses source id `who_malaria_threats_resistance_audit`. It saves a bounded `FACT_PREVENTION_VIEW` CSV sample from the WHO Malaria Threats Map public data endpoint, queries the same endpoint for Aedes species rows, and indexes returned resistance rows if present. The current public species-filter query returns no Aedes rows, so Ask Insects installs a queryable `resistance` source-gap record with reason `who_malaria_threats_no_aedes_rows` instead of claiming WHO database Aedes rows are indexed.

## Resistance Marker Source Lane

Indexed Aedes literature and legal full-text chunks can be parsed into kdr, VGSC, and metabolic-resistance marker records:

```bash
python3 -m askinsects ingest-resistance-markers
python3 -m askinsects ask "show kdr V1016G resistance markers in Aedes aegypti" --json
python3 -m askinsects sql "select json_extract(payload_json, '$.marker_id') as marker, count(*) as n from record_payloads where source='aedes_resistance_markers' group by marker order by n desc" --limit 20
```

The lane uses source id `aedes_resistance_markers`. It creates one `resistance` record per detected marker candidate, stores marker class, gene or family, matched aliases, resistance context, insecticide terms, source paper ID, full-text unit ID when present, and snippet in SQLite payloads, and preserves provenance back to `records#<paper_id>` plus `literature_fulltext_units#<unit_id>` when legal full text is available. The May 24, 2026 hosted ingest installed 6,449 marker records with zero marker-source gaps. It is deterministic candidate extraction, not validated genotype or marker-frequency table extraction.

## Resistance Table-Row Source Lane

Parsed Aedes resistance supplement rows from `aedes_extracted_facts` can be promoted into schema-validated resistance table records:

```bash
python3 -m askinsects ingest-resistance-table-rows
python3 -m askinsects ask "show parsed resistance table V1016G frequency for Aedes aegypti" --json
python3 -m askinsects sql "select json_extract(payload_json, '$.confidence') as confidence, count(*) as n from record_payloads where source='aedes_resistance_table_rows' group by confidence"
```

The lane uses source id `aedes_resistance_table_rows`. It creates one `resistance` record per parsed supported-format resistance table row, stores insecticide terms, marker or mutation terms, assay terms, metric fields, table headers, table row values, source extracted-fact record ID, source paper ID, and validation status in SQLite payloads, and preserves provenance back to `aedes_extracted_facts#<record_id>`, `records#<paper_id>`, and the raw supplement row locator. These rows are labeled `parsed_table_schema_validated` with `human_validated: false`; they are inspectable table atoms, not a claim that every resistance table has been parsed or biologically reviewed. When the indexed extracted-fact rows do not contain promotable resistance tables, the lane installs a queryable `source_gap` resistance record instead of silently disappearing.

## Occurrence Ecology Source Lane

Indexed GBIF, iNaturalist, and Mosquito Alert observation payloads can be joined into country, country-month, seasonality, range, and public habitat ecology records:

```bash
python3 -m askinsects ingest-occurrence-ecology
python3 -m askinsects ingest-observation-climate-join --limit 1000
python3 -m askinsects ask "what seasonality evidence exists for Aedes aegypti in Brazil by month?" --json
python3 -m askinsects ask "show climate-linked Aedes aegypti observation ecology in Brazil" --json
python3 -m askinsects sql "select json_extract(payload_json, '$.country') as country, count(*) as n from record_payloads where source='aedes_occurrence_ecology' and json_extract(payload_json, '$.aggregation_type')='country_month_summary' group by country order by n desc" --limit 20
python3 -m askinsects sql "select source, lane, count(*) as n from records where source='aedes_observation_climate_join' group by source, lane"
```

The lane uses source id `aedes_occurrence_ecology`. It creates `ecology` records from existing `gbif_api`, `inaturalist_api`, and `mosquito_alert_gbif` observation payloads, stores input source counts, observation counts, date ranges, coordinate counts, bounding boxes, sample input record IDs, and sample URLs in SQLite payloads, and preserves provenance to the derived observation join. The sibling source id `aedes_observation_climate_join` samples the local WorldClim v2.1 10-minute bioclim ZIP for bounded coordinate-bearing observation rows. Each climate-join record stores the input observation ID and source, observed date, country/place, latitude, longitude, annual mean temperature, annual precipitation, raw WorldClim ZIP locator, and upstream observation provenance. The May 24, 2026 hosted ingest installed 1,985 occurrence ecology records from 88,065 Aedes observation inputs. The May 25, 2026 hosted WorldClim refresh added 500 bounded 10-minute bioclim raster samples with annual mean temperature, annual precipitation, coordinates, occurrence-row provenance, and raw ZIP locators. The Harvard Dataverse suitability lane adds file-grained suitability/risk raster manifests with dataset/file DOI, checksum, byte size, license, and download gaps. This is occurrence-derived, observation-climate, climate-sample, and suitability-manifest ecology coverage; land-use layers, decoded model rasters, and surveillance completeness remain follow-on sources.

## Official Public-Health Guidance Source Lane

WHO, PAHO, CDC, and ECDC guidance pages are the first operational public-health guidance lane for `Aedes aegypti`:

```bash
python3 -m askinsects ingest-public-health
python3 -m askinsects ask "what vector control guidance exists for Aedes aegypti?" --json
```

The lane writes raw official guidance HTML under `raw/public_health_guidance/`, normalizes one `public_health` record per guidance page from source `aedes_public_health_guidance`, stores page metadata in SQLite payloads, and preserves provenance to the saved HTML plus the official source URL. The default set includes official dengue, Zika, Aedes life-cycle, vector-control, travel-medicine, Wolbachia, community prevention, and ECDC species-factsheet pages. This is guidance coverage, not yet a full surveillance dashboard or outbreak time-series lane.

## Wolbachia Intervention Source Lane

`aedes_wolbachia_interventions` is the World Mosquito Program intervention-evidence lane for `Aedes aegypti` Wolbachia replacement:

```bash
python3 -m askinsects ingest-wolbachia-interventions
python3 -m askinsects ask "show World Mosquito Program Wolbachia intervention evidence from Yogyakarta" --json
python3 -m askinsects search public_health "Wolbachia 77% Yogyakarta"
```

This writes WMP public pages and media releases under `raw/wolbachia_interventions/`, indexes one `public_health` evidence record per page, extracts source-mentioned metrics such as percentage reductions, stores page metadata in SQLite payloads, and keeps provenance to the saved HTML and source URL. It complements public-health guidance: guidance explains what to do, while this lane captures intervention evidence and deployment claims at source-page grain.

## PAHO Dengue Surveillance Source Lane

PAHO dengue surveillance is indexed as `Aedes aegypti` public-health intelligence at the official report/page grain:

```bash
python3 -m askinsects ingest-paho-dengue-surveillance
python3 -m askinsects ask "show PAHO dengue surveillance evidence for Aedes aegypti" --json
```

The lane uses source id `aedes_paho_dengue_surveillance`. It writes raw PAHO dengue situation report HTML, dashboard landing HTML, PAHO/EIH Core Indicators download-page HTML, and the released Core Indicators ZIP under `raw/paho_dengue_surveillance/`. It parses regional week, year-to-date, subregion, serotype, figure/table, dashboard page, iframe locator, and annual Core Indicators dengue-case CSV rows into the `public_health` lane, stores metrics and PAHO locators in SQLite payloads, and preserves provenance to the saved raw artifact plus official PAHO URLs. PAHO/EIH Core Indicators annual country/territory dengue rows are now a proven stable machine-readable feed. PAHO/PLISA dashboard pages and iframe URLs remain queryable locator records, but country-week Tableau/PHIP dashboard rows remain a source gap until there is a stable weekly CSV, JSON, or API endpoint or explicit authorized access.

## WHO Dengue Surveillance Source Lane

WHO dengue surveillance is indexed as `Aedes aegypti` public-health intelligence at the official page, report, and dashboard-locator grain:

```bash
python3 -m askinsects ingest-who-dengue-surveillance
python3 -m askinsects ask "show WHO dengue surveillance evidence for Aedes aegypti" --json
python3 -m askinsects ask "show WHO dengue dashboard locator evidence for Aedes aegypti" --json
```

The lane uses source id `aedes_who_dengue_surveillance`. It writes raw WHO dengue surveillance page HTML, WHO WER global update page HTML, WHO Western Pacific situation-update landing HTML, and WHO Western Pacific Health Data Platform dengue dashboard locator HTML under `raw/who_dengue_surveillance/`. It indexes one `public_health` record per WHO page, linked situation-report/update/archive records, publication download locators, parsed headline metrics when present in page HTML, and dashboard locator records. Dashboard locator records are queryable, but country/time dashboard cells remain a source gap until WHO exposes a stable machine-readable CSV, ZIP, XLSX, JSON, or API endpoint or explicit authorized access is obtained.

## CDC Dengue Surveillance Source Lane

CDC dengue ArboNET surveillance is indexed as U.S. `Aedes aegypti` public-health intelligence at page, visualization-config, CSV row, and limitation grain:

```bash
python3 -m askinsects ingest-cdc-dengue-surveillance
python3 -m askinsects ask "show CDC ArboNET dengue surveillance current cases" --json
python3 -m askinsects search public_health "CDC ArboNET county dengue cases"
```

The lane uses source id `aedes_cdc_dengue_surveillance`. It writes raw CDC current-year and historic dengue page HTML, CDC WCMS visualization JSON configs, and linked CDC CSV datasets under `raw/cdc_dengue_surveillance/`. It parses one `public_health` record per page, one record per visualization config, one record per CSV row with dimensions and measures, and one record per ArboNET limitation paragraph. This is human dengue surveillance evidence relevant to Aedes aegypti vector intelligence, not mosquito occurrence evidence.

## India NCVBDC Dengue Surveillance Source Lane

India NCVBDC dengue surveillance is indexed as official `Aedes aegypti` public-health intelligence at state/UT-year and national-year grain:

```bash
python3 -m askinsects ingest-ncvbdc-dengue-surveillance
python3 -m askinsects ask "what were dengue deaths in India over the last two years as a result of Aedes?" --json
python3 -m askinsects search public_health "NCVBDC India dengue deaths 2024 2025"
```

The lane uses source id `aedes_ncvbdc_dengue_surveillance`. It writes the raw Government of India NCVBDC dengue situation HTML under `raw/ncvbdc_dengue_surveillance/`. It parses one `public_health` record per state/UT-year row, one per national country-year total, one source-page record, and one latest-two-complete-year summary record. Payloads preserve country, state or union territory, year, cases, deaths, provisional status, and raw HTML locators. This is human dengue surveillance evidence relevant to Aedes aegypti vector intelligence, not mosquito occurrence evidence.

## Brazil OpenDataSUS Dengue Surveillance Source Lane

Brazil OpenDataSUS dengue surveillance is indexed as official `Aedes aegypti` public-health intelligence at aggregate year, state, and epidemiological-week grain. The default ingest covers the public annual backfiles from 2007 through 2026:

```bash
python3 -m askinsects ingest-opendatasus-dengue-surveillance
python3 -m askinsects ask "show Brazil OpenDataSUS dengue deaths and notifications for 2025" --json
python3 -m askinsects search public_health "OpenDataSUS Brazil dengue epidemiological week"
```

The lane uses source id `aedes_opendatasus_dengue_surveillance`. It writes raw Brazil Ministry of Health OpenDataSUS SINAN dengue CSV ZIP files under `raw/opendatasus_dengue_surveillance/`. It parses aggregate `public_health` records for each source file, each country-year, each residence-state-year, each notification-state-year, each country epidemiological week, and each residence-state epidemiological week. Payloads preserve source file URL, raw ZIP locator, SHA-256 checksum, byte size, row count, year, UF code, state name, notifications, EVOLUCAO=2 deaths by disease, severe dengue classifications, hospitalized notifications, and classification/sex/criterion counts. This is human dengue surveillance evidence relevant to Aedes aegypti vector intelligence, not mosquito occurrence evidence, and it intentionally avoids person-level line records.

## Pathogen Taxonomy Source Lane

NCBI Taxonomy anchors core `Aedes aegypti` arbovirus names to stable pathogen identities for vector-competence and public-health questions:

```bash
python3 -m askinsects ingest-pathogen-taxonomy
python3 -m askinsects ask "show Zika pathogen taxonomy for Aedes aegypti" --json
python3 -m askinsects search vector_competence "dengue pathogen taxonomy"
```

The lane uses source id `aedes_pathogen_taxonomy`. It writes NCBI E-utilities taxonomy summary JSON under `raw/pathogen_taxonomy/`, normalizes one `vector_competence` record per configured pathogen, stores the raw taxonomy summary in SQLite payloads, and preserves provenance to the saved summary plus the NCBI request URL. This is a pathogen identity layer, not yet structured extraction of every vector-competence assay table.

## NCBI BioSample Source Lane

NCBI BioSample gives `Aedes aegypti` sample, strain, collection, geography, tissue, and linked SRA metadata:

```bash
python3 -m askinsects ingest-ncbi-biosamples --limit 20656
python3 -m askinsects ask "show Aedes aegypti BioSamples from China" --json
python3 -m askinsects search biosamples "Rockefeller SRA"
```

The lane uses source id `ncbi_biosamples`. It writes NCBI ESearch and ESummary JSON under `raw/ncbi_biosamples/`, normalizes one `biosamples` record per accession, stores parsed XML attributes and the raw summary in SQLite payloads, and preserves provenance to the saved ESummary batch plus the NCBI request URL. The current hosted receipt is complete for the current NCBI count: 20,656 fetched records out of 20,656 reported, with zero hosted gaps. If NCBI later reports more BioSamples than a bounded refresh fetched, the lane should write a structured `biosample_limit_applied` gap instead of pretending the mirror is complete.

## NCBI dbSNP Variation Audit Lane

NCBI dbSNP is audited as an explicit Aedes variation source boundary:

```bash
python3 scripts/ingest_ncbi_snp_variation.py --limit 1000
python3 -m askinsects search genome_features "dbSNP variation source gap"
python3 -m askinsects sql "select source, lane, count(*) as n from records where source='aedes_ncbi_snp_variation' group by source, lane"
```

The lane uses source id `aedes_ncbi_snp_variation`. It queries NCBI E-utilities dbSNP with `"Aedes aegypti"[Organism]`, writes raw ESearch and ESummary JSON under `raw/ncbi_snp_variation/`, and would normalize returned SNP summaries into `genome_features` records with rsID, position, allele, function, gene, and raw ESummary provenance when NCBI exposes records. The current NCBI dbSNP organism query returns zero records, so the hosted lane installs a queryable `genome_features` source-gap record with reason `ncbi_snp_no_aedes_records` instead of implying that Aedes variant records are indexed.

## Vector-Competence Assay Candidate Lane

Indexed Aedes literature and legal full-text chunks can be parsed into structured vector-competence assay candidates:

```bash
python3 -m askinsects ingest-vector-competence-assays
python3 -m askinsects ask "show Zika vector competence assay dose and transmission for Aedes aegypti" --json
python3 -m askinsects search vector_competence "dissemination saliva 28 C"
```

The lane uses source id `aedes_vector_competence_assays`. It creates one `vector_competence` record per detected pathogen-specific assay candidate, stores structured fields in SQLite payloads, and preserves provenance back to the source paper plus `literature_fulltext_units` when legal full text is available. It also promotes parsed `aedes_extracted_facts` vector-competence supplement table rows when the row passes schema checks for a supported pathogen and infection, dissemination, or transmission evidence. Promoted rows are labeled `parsed_table_schema_validated` with `human_validated: false`; they are inspectable table atoms, not a claim that every table and supplement has been fully parsed or biologically reviewed.

## Aedes aegypti Neurobiology Source Lane

The neurobiology lane can run as metadata-only, or from a downloaded raw-artifact cache:

```bash
python3 scripts/build_source_index.py --fixtures --neurobiology
python3 scripts/ingest_neurobiology_sources.py
python3 scripts/build_source_index.py --fixtures --neurobiology --neurobiology-artifact-dir ~/.local/share/ask-insects/sources/neurobiology
python3 -m askinsects search neurobiology "brain atlas"
python3 -m askinsects ask "what neuron data exists for the Aedes aegypti brain?"
```

The full artifact path downloads GEO `GSE160740_RAW.tar`, SRA runinfo for `SRP290992`, the Mosquito Cell Atlas Zenodo record and files, the MosquitoBrains downloads page, Dropbox folder ZIPs when Dropbox permits direct download, and the public `htem/aedes_public` EM/CATMAID analysis repository metadata, README, CSVs, and CATMAID API metadata. SQLite indexes GEO matrix summaries and feature rows, SRA run/sample metadata, raw SRA access and reanalysis workflow records, H5AD internal AnnData groups/datasets/obs/var columns, workbook sheets, MosquitoBrains volume headers and region labels, coordinate-queryable voxel access locators, public EM/CATMAID project, stack, annotation, volume, skeleton-manifest, skeleton-filter, and skeleton-ID records, public EM/CATMAID CSV inventories, study metadata, and a narrowed whole-brain connectome source-gap row. It does not claim the compute-heavy raw SRA alignment has already been executed, and it does not claim the future Wellcome whole-brain connectome has a public bulk package yet.

Exact MosquitoBrains voxel values can be read by coordinate from the local raw artifacts:

```bash
python3 -m askinsects voxel \
  "neuro:mosquitobrains:volume:Segmentation-Files.zip:Brain_border/WholeBrain_Border.mha" \
  --x 0 --y 0 --z 0
```

## Aedes aegypti Literature Lane

The literature lane is an opt-in source lane for `Aedes aegypti` papers since 2020:

```bash
python3 scripts/build_source_index.py \
  --openalex-literature \
  --literature-species "Aedes aegypti" \
  --literature-from-date 2020-01-01 \
  --include-topic-discovery \
  --skip-pubmed \
  --skip-fulltext \
  --literature-page-size 200 \
  --literature-delay-seconds 1 \
  --artifact-dir artifacts/aedes-literature-2020

python3 scripts/enrich_literature_index.py \
  --artifact-dir artifacts/aedes-literature-2020 \
  --email you@example.com

python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 \
  ask "what papers since 2020 discuss Wolbachia and Aedes aegypti?" \
  --json
```

OpenAlex is the canonical discovery source. A paper is in-boundary when `Aedes aegypti` is material in the title, abstract, or accepted OpenAlex topic metadata. PubMed is used only as a cross-check enrichment source, and Unpaywall is used only as a legal open full-text resolver. Ask Insects does not use Sci-Hub, private cookies, or institutional scraping.

`aedes_olfaction_literature` is a narrower PubMed audit lane for a high-value research question: Aedes aegypti olfaction papers since 2020. It fetches bounded PubMed ESearch and ESummary pages for olfaction, odor, chemosensory, antenna, Orco, and receptor terms, creates one `literature` record per PMID, and marks each with `coverage_status` plus any `matched_record_ids` already present in Ask Insects. It can also ask Unpaywall for legal direct XML, PDF, HTML, or text full text; when a direct open file is available, Ask Insects stores parsed chunks and figure captions in `literature_fulltext_units` with raw-file provenance. Receipts also preserve `canonical_literature_row_count`; if the artifact lacks the canonical OpenAlex literature lane, the audit writes `aedes_olfaction_no_canonical_literature_rows` instead of pretending the coverage comparison was meaningful.

The May 25, 2026 hosted ingest installed 183 PubMed olfaction candidates, compared them against 10,683 canonical OpenAlex literature rows, matched 156 already-indexed papers, added 27 PubMed-metadata-only candidates, and recorded zero hosted gaps.

```bash
python3 -m askinsects ingest-aedes-olfaction-literature --max-results 500 --page-size 100 --unpaywall-email sources@openinsects.org
python3 -m askinsects search literature "Aedes aegypti olfaction coverage_status"
python3 -m askinsects search fulltext "Aedes aegypti Orco antennal neuron figure"
python3 -m askinsects sql "select json_extract(p.payload_json, '$.coverage_status') as status, count(*) as n from records r join record_payloads p on p.record_id=r.record_id where r.source='aedes_olfaction_literature' group by status"
```

The lane writes PubMed raw ESearch pages, ESummary batches, Unpaywall payloads, legal direct full-text files, and `coverage_audit.json` under `artifacts/mosquito-v1/raw/aedes_olfaction_literature/`, then updates `source_index.sqlite`, `source_status.json`, `source_receipt.json`, and `gaps.json` in `artifacts/mosquito-v1/`. Structured gaps record PubMed fetch failures, result-limit frontiers, no-result runs, runs where the current artifact has no canonical `aedes_literature_openalex` rows to compare against, missing Unpaywall email or DOI, no legal direct full-text URL, and full-text fetch or parse failures.

`aedes_crossref_literature_audit` is the Crossref publisher-metadata reconciliation lane for `Aedes aegypti` literature since 2020. It fetches bounded Crossref `/works` cursor pages where source metadata materially names `Aedes aegypti`, saves raw JSON under `artifacts/mosquito-v1/raw/aedes_crossref_literature_audit/`, and writes one `literature` audit record per DOI/work. Each record preserves DOI, title, publisher, container title, issued date, Crossref member, reference count, license links, `coverage_status`, matched Ask Insects record IDs, and raw Crossref page locators.

```bash
python3 -m askinsects ingest-crossref-literature-audit --max-results 500 --page-size 100
python3 -m askinsects ask "show Crossref DOI audit literature for Aedes aegypti" --json
python3 -m askinsects sql "select json_extract(p.payload_json, '$.coverage_status') as status, count(*) as n from records r join record_payloads p on p.record_id=r.record_id where r.source='aedes_crossref_literature_audit' group by status"
```

Structured Crossref audit gaps include `aedes_crossref_fetch_failed`, `aedes_crossref_result_limit_applied`, `aedes_crossref_no_material_aedes_records`, and `aedes_crossref_no_canonical_literature_rows`. Crossref is an audit and enrichment lane, not a replacement for canonical OpenAlex discovery or legal full-text parsing.

`mosquito_repellent_literature` is the mosquito-wide repellent article lane for papers from 2020 onward. It combines PubMed Title/Abstract search with bounded Crossref publisher metadata queries for mosquito repellents, repellency, spatial repellents, topical repellents, DEET, picaridin, icaridin, IR3535, PMD, citronella, essential oils, and plant-extract repellent research. It deduplicates by DOI, PMID, or normalized title, writes one `literature` record per article candidate, preserves raw PubMed/Crossref locators, and marks each record with `coverage_status`, `candidate_sources`, `repellent_terms`, `mosquito_terms`, and matched Ask Insects record IDs when already indexed.

```bash
python3 -m askinsects ingest-mosquito-repellent-literature --pubmed-max-results 1000 --crossref-max-results 1000 --page-size 100
python3 -m askinsects ask "what mosquito repellent papers since 2020 are in the database?" --json
python3 -m askinsects sql "select json_extract(p.payload_json, '$.coverage_status') as status, count(*) as n from records r join record_payloads p on p.record_id=r.record_id where r.source='mosquito_repellent_literature' group by status"
```

Structured repellent-literature gaps include `mosquito_repellent_pubmed_search_failed`, `mosquito_repellent_pubmed_summary_failed`, `mosquito_repellent_pubmed_result_limit_applied`, `mosquito_repellent_crossref_fetch_failed`, `mosquito_repellent_crossref_result_limit_applied`, `mosquito_repellent_no_candidates`, and `mosquito_repellent_no_canonical_literature_rows`. This is a public metadata source plane. It does not use private cookies, institutional access, or Sci-Hub.

`mosquito_repellent_external_discovery` is the external breadth lane for repellent discovery. It adds bounded, raw-receipted metadata candidates from OpenAlex, Europe PMC, AGRICOLA through Europe PMC, Semantic Scholar, Crossref posted-content preprints, DataCite dataset DOI metadata, Zenodo, and Figshare. It also writes queryable source-gap records for native bioRxiv/medRxiv text search, PatentsView/USPTO patent APIs, CABI, and Google Scholar when those surfaces are blocked, migrated, credentialed, or unsupported. Records use `literature`, `datasets`, and `patents` lanes so researchers can ask for papers, preprints, repository data, and patent-source status without leaving Ask Insects.

```bash
python3 -m askinsects ingest-mosquito-repellent-external-discovery --max-results-per-source 50
python3 -m askinsects search datasets "mosquito repellent"
python3 -m askinsects search patents "mosquito repellent patent"
python3 -m askinsects sql "select lane, json_extract(p.payload_json, '$.source_family') as family, count(*) as n from records r join record_payloads p on p.record_id=r.record_id where r.source='mosquito_repellent_external_discovery' group by lane, family order by lane, family"
```

Legal direct full-text units are searchable through the normal CLI and used as a fallback for literature answers when metadata and abstracts are not enough:

```bash
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 search fulltext "microbiota Aedes aegypti"
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 ask "what papers since 2020 discuss microbiota and Aedes aegypti?" --json
```

Literature can also be parsed into mosquito intelligence facets:

```bash
python3 scripts/build_literature_facets.py --artifact-dir artifacts/aedes-literature-2020
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 search behavior "host seeking"
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 search resistance "pyrethroid"
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 ask "what vector competence data exists for dengue?" --json
```

The derived source id is `aedes_literature_facets`. It creates records in `behavior`, `vector_competence`, `resistance`, `ecology`, and `public_health` from indexed Aedes literature and legal full text where available, with provenance back to the source literature record and full-text units. These are partial source-grade lanes: they make the domains queryable now, while deeper structured datasets remain required for world-class coverage.

`aedes_extracted_facts` is the next cross-lane extraction spine. It reads indexed Aedes literature records, record payload supplement metadata, and legal `literature_fulltext_units`, then emits candidate fact records into `vector_competence`, `resistance`, `behavior`, `ecology`, and `public_health`, plus `literature` records for supplement manifests:

```bash
python3 -m askinsects ingest-extracted-facts
python3 -m askinsects ingest-extracted-facts --discover-supplements --download-supplements --max-supplement-discovery-records 500 --max-repository-supplement-discovery-records 100 --max-supplement-files 100 --max-supplement-bytes 2000000 --max-pdf-supplement-files 10
python3 -m askinsects ask "show extracted Aedes aegypti vector competence facts for dengue" --json
python3 -m askinsects search literature "supplement manifest"
```

Extracted-facts payloads preserve `fact_type`, matched fields, source paper ID, full-text unit ID when available, evidence text, supplement metadata, confidence, extraction method, and provenance back to the source record, raw supplement file, row, or legal full-text unit. Confidence is `candidate` for deterministic text facts, `manifest` for supplement pointers, `parsed` for supported supplement table rows, and `audit` for per-paper supplement coverage atoms. The opt-in supplement pass discovers record-payload links, Europe PMC, PMC OA files, Crossref relation metadata, DataCite related identifiers, Unpaywall OA locations, Figshare, Zenodo, publisher landing-page links, and supplement-looking URLs inside legal full-text units where identifiers or landing pages are available. Receipts store `supplement_discovery_route_counts` so each run can show which routes actually produced manifests. `--max-supplement-discovery-records` bounds metadata lookups separately from `--max-supplement-files`, and `--max-repository-supplement-discovery-records` bounds extra Zenodo/Figshare-style records that are allowed to jump beyond the normal limit. The download pass preserves bounded public supplement files under `raw/extracted_facts/supplements/` and parses `.csv`, `.tsv`, `.xlsx`, `.docx`, XML tables, simple HTML tables, plain text-like files, and a bounded number of PDFs. `--max-pdf-supplement-files` keeps PDF extraction explicit and emits queryable gap rows for PDFs left unread by that bound. Every indexed Aedes paper must have a queryable supplement audit atom before literature supplement coverage can be called complete. Audit statuses include promoted rows, parsed rows without a lane match, manifests without supported promoted rows, download not run, no supplement metadata found, missing discovery identifier, and discovery not run. `no_supplement_metadata_found` means the configured bounded routes found no public supplement metadata for that paper in the run, not proof that no supplement exists anywhere. It does not claim human validation or complete parsing of every PDF supplement, workbook variant, image table, or archive.

## Hosted Ask Insects

Hosted V1 follows the Ask Monarch VM pattern. The parsed SQLite index and raw source artifacts live on the Google VM under `/home/josh/ask-insects/artifacts/mosquito-v1/`.

```bash
python3 -m askinsects configure --url http://<vm-ip>:8080 --token "$ASK_INSECTS_TOKEN"
python3 -m askinsects health --hosted
python3 -m askinsects ingest-gbif --hosted --species "Aedes aegypti" --occurrence-limit 82237 --occurrence-page-size 300 --occurrence-workers 6 --delay-seconds 0
python3 -m askinsects ingest-inaturalist --hosted --species "Aedes aegypti" --observation-limit 10 --page-size 10 --delay-seconds 0
python3 -m askinsects ingest-irmapper --hosted --species "Aedes aegypti"
python3 -m askinsects ingest-public-health --hosted
python3 -m askinsects ingest-expression-omics --hosted --geo-limit 120 --sra-limit 300
python3 -m askinsects ingest-uniprot-proteins --hosted --protein-limit 250 --proteome-limit 10
python3 -m askinsects ingest-wolbachia-interventions --hosted
python3 -m askinsects ingest-vectorbyte-traits --hosted --dataset-limit 20 --row-limit 5000
python3 -m askinsects ingest-vectorbyte-abundance --hosted --dataset-limit 5 --row-limit 5000
python3 -m askinsects ingest-vectorbyte-abundance --hosted --dataset-id-file config/aedes-vectorbyte-abundance-datasets.txt --dataset-limit 25 --row-limit 100000 --dataset-page-limit 200
python3 -m askinsects ingest-vectorbyte-abundance --hosted --dataset-id 718 --dataset-id 724 --merge-existing --dataset-limit 2 --row-limit 5000 --dataset-page-limit 80
python3 -m askinsects ingest-pathogen-taxonomy --hosted
python3 -m askinsects ingest-vector-competence-assays --hosted
python3 -m askinsects ingest-extracted-facts --hosted
python3 -m askinsects ingest-mosquito-alert --hosted --occurrence-limit 1000
python3 -m askinsects ingest-vectornet-surveillance --hosted
python3 -m askinsects ingest-who-dengue-surveillance --hosted
python3 -m askinsects ingest-cdc-dengue-surveillance --hosted
python3 -m askinsects ingest-ncvbdc-dengue-surveillance --hosted
python3 -m askinsects ingest-opendatasus-dengue-surveillance --hosted
python3 -m askinsects ingest-crossref-literature-audit --hosted --max-results 500 --page-size 100
python3 -m askinsects ingest-mosquito-repellent-literature --hosted --pubmed-max-results 1000 --crossref-max-results 1000 --page-size 100
python3 -m askinsects ingest-mosquito-repellent-external-discovery --hosted --max-results-per-source 50
python3 -m askinsects ask --hosted "show mosquito observations with images in Brazil"
```

## Contract

Ask Insects answers from local indexed records. Every answer includes provenance or a clear source gap. V1 does not claim to mirror all mosquito knowledge. It proves bounded source planes end to end.
