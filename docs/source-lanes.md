# Source Lanes

V1 covers mosquitoes first.

## Taxonomy

Scientific names, common labels, synonyms, rank, family, genus, and species.

Sources:

- `mosquito_v1_fixtures`: deterministic repo seed records.
- `gbif_api`: live GBIF species match records when explicitly fetched.

## Observations And Images

Observation records with date, region, source URL, media URL, and license when available.

Sources:

- `mosquito_v1_fixtures`: deterministic repo seed records.
- `gbif_api`: bounded GBIF occurrence search records when explicitly fetched.
- `inaturalist_api`: bounded iNaturalist observations with licensed photos when explicitly fetched.

## Videos And Media

Public moving-image or inspectable media records. V1 reports missing video coverage honestly.

Sources:

- `inaturalist_api`: still-image media URLs from iNaturalist observation photos.

Moving-image video coverage is still a source gap unless a future source lane adds video records.
Deep iNaturalist ingest paginates the public API and saves one raw page artifact per request.

## Papers And Literature

Paper metadata, abstracts when available, open access URLs, and source identifiers.

## Action Notes

Source-backed next steps for scientists, grounded in indexed observations and literature.

GBIF V1 does not create action notes by itself. It strengthens the observation and taxonomy evidence that action answers can cite.

iNaturalist V1 does not create action notes by itself. It strengthens photo-backed observation evidence that action answers can cite.
