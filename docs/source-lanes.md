# Source Lanes

V1 covers mosquitoes first.

## Taxonomy

Scientific names, common labels, synonyms, rank, family, genus, and species.

Sources:

- `mosquito_v1_fixtures`: deterministic repo seed records.
- `gbif_api`: live GBIF species match records when explicitly fetched. Hosted deep refreshes are currently focused on `Aedes aegypti`.

## Observations And Images

Observation records with date, region, source URL, media URL, and license when available. Live source lanes also store raw per-record payloads in SQLite so the original API fields remain queryable.

Sources:

- `mosquito_v1_fixtures`: deterministic repo seed records.
- `gbif_api`: GBIF occurrence search records when explicitly fetched. The hosted deep ingest paginates the current `Aedes aegypti` GBIF occurrence set and refreshes only `gbif_api` rows, preserving other hosted lanes.
- `inaturalist_api`: bounded iNaturalist observations with licensed photos when explicitly fetched.

## Videos And Media

Public moving-image or inspectable media records. V1 reports missing video coverage honestly.

Sources:

- `inaturalist_api`: still-image media URLs from iNaturalist observation photos.

Moving-image video coverage is still a source gap unless a future source lane adds video records.
Deep iNaturalist ingest paginates the public API and saves one raw page artifact per request. Each normalized iNaturalist observation and media row also gets a matching `record_payloads` row with the raw observation and photo payload.

## Hosted Boundary

Hosted Ask Insects uses the same source lanes. The difference is location: parsed artifacts live on the Google VM under `/home/josh/ask-insects/artifacts/mosquito-v1/`, and the local CLI asks the hosted API to ingest or query those artifacts.

Hosted GBIF ingest stages a copy of the active artifact directory, fetches GBIF into the staging copy, replaces existing `gbif_api` rows in SQLite, writes receipts, and activates the staged directory only after the refresh succeeds. This keeps the old server database readable during long GBIF pulls.

## Genomics

Genome assembly metadata, GFF annotation features, gene rows, transcript rows, and protein FASTA headers.

Sources:

- `ncbi_datasets_genome`: parsed NCBI Datasets package for `Aedes aegypti` assembly `GCF_002204515.2`.

The genomics lane indexes useful atoms, not every DNA base. Raw NCBI package files remain the source artifacts. SQLite rows cite locators such as `assembly_data_report.jsonl#line/1`, `genomic.gff#line/42`, or `protein.faa#protein/XP_001`.

Current genomics lanes:

- `genome_assemblies`
- `genes`
- `transcripts`
- `genome_features`
- `proteins`

## Neurobiology

Brain atlas, neuroanatomy, brain single-nucleus RNA-seq metadata, cell atlas package metadata, and sensory-neuron study metadata for `Aedes aegypti`.

Sources:

- `aedes_neurobiology_sources`: deterministic metadata records for mosquitobrains.org, GEO `GSE160740`, the Mosquito Cell Atlas Zenodo record, and selected open neurobiology studies.

Current neurobiology lane:

- `neurobiology`

This lane is a first source-contract slice. It indexes useful source atoms and provenance, not full image volumes, H5AD matrices, raw SRA runs, or a complete connectome. Those remain explicit expansion gaps.

## Papers And Literature

Paper metadata, abstracts when available, open access URLs, and source identifiers.

Sources:

- `mosquito_v1_fixtures`: deterministic repo seed records.
- `aedes_literature_openalex`: OpenAlex articles from 2020-01-01 through run date where `Aedes aegypti` is material in title, abstract, or accepted topic metadata.

OpenAlex is the canonical source for discovery and record identity. PubMed E-utilities are enrichment only, used for PMID-backed metadata. Unpaywall is enrichment only, used as the legal open full-text resolver. The lane may write legal direct PDF/XML/text chunks to `literature_fulltext_units`, but it must not use Sci-Hub, private cookies, or institutional scraping.

The canonical artifact directory is `artifacts/aedes-literature-2020/`. It contains the SQLite index, raw OpenAlex cursor JSON artifacts, `source_status.json`, `source_receipt.json`, `literature_enrichment_receipt.json`, and `gaps.json`. PubMed and Unpaywall enrichment payloads are preserved in the SQLite `record_payloads` table rather than duplicated as separate raw JSON files.

Structured literature gaps include:

- `missing_doi`
- `pubmed_missing_pmid`
- `pubmed_fetch_failed`
- `openalex_missing_abstract`
- `openalex_topic_search_empty`
- `openalex_topic_candidate_rejected`
- `unpaywall_fetch_failed`
- `unpaywall_no_fulltext_url`
- `fulltext_landing_page_only`
- `fulltext_fetch_failed`
- `fulltext_parse_failed`

## Action Notes

Source-backed next steps for scientists, grounded in indexed observations and literature.

GBIF V1 does not create action notes by itself. It strengthens the observation and taxonomy evidence that action answers can cite.

iNaturalist V1 does not create action notes by itself. It strengthens photo-backed observation evidence that action answers can cite.
