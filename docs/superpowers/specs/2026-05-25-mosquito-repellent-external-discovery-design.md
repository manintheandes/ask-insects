# Mosquito Repellent External Discovery Design

## Goal

Broaden Ask Insects mosquito repellent coverage beyond PubMed and Crossref
journal-article metadata while preserving the source contract: mapped,
accessible, atomically queryable, receipted, and answer-surface wired.

## Boundary

The lane covers bounded public metadata discovery for mosquito repellent research
from 2020 onward across OpenAlex, Europe PMC, AGRICOLA through Europe PMC,
Semantic Scholar, Crossref posted-content preprints, DataCite, Zenodo, and
Figshare.

Native bioRxiv/medRxiv text search, PatentsView/USPTO patent API access, CABI,
and Google Scholar are represented as queryable source-gap records when no
supported public, unauthenticated API is available in this repo.

## Records

Source id: `mosquito_repellent_external_discovery`.

Lanes:

- `literature` for article, preprint, Europe PMC, AGRICOLA, and blocked
  literature-source gap records.
- `datasets` for DataCite, Zenodo, and Figshare repository metadata records.
- `patents` for patent-source gap records until a stable patent API is
  accessible.

Each record stores source family, artifact type, DOI or external ID when
available, title, publication date, venue or repository, source URL, matched
mosquito/repellent terms, raw locator, and raw payload when available.

## Safety

The ingest replaces only `mosquito_repellent_external_discovery` rows after a
successful refresh. If every external fetch fails, existing rows are preserved
and the receipt records the failed refresh.
