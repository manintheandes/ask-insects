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

## Papers And Literature

Paper metadata, abstracts when available, open access URLs, and source identifiers.

## Action Notes

Source-backed next steps for scientists, grounded in indexed observations and literature.

GBIF V1 does not create action notes by itself. It strengthens the observation and taxonomy evidence that action answers can cite.

iNaturalist V1 does not create action notes by itself. It strengthens photo-backed observation evidence that action answers can cite.
