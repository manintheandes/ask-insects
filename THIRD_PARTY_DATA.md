# Third-Party Data Boundary

Ask Insects is open-source software. The code and project-authored
documentation in this repository are licensed under Apache-2.0.

Third-party data is different. Scientific data, images, videos, papers, API
payloads, database exports, and other upstream artifacts are not relicensed by
Ask Insects. They stay under the licenses, terms, citation rules, and access
rules of the source that published them.

## What This Repository Should Contain

This public repository should contain source code, tests, documentation,
configuration, small deterministic fixtures, and source maps.

This public repository should not contain private credentials, API tokens, raw
artifact mirrors, SQLite database mirrors, downloaded papers, video archives,
audio archives, H5AD matrices, ZIP archives, or other large source payloads.
Generated artifacts belong under ignored `artifacts/` directories or on the
configured hosted Ask Insects server.

## Source Lanes

Each source lane must preserve provenance at the most atomic useful level. That
means a record should keep its source ID, source URL, raw locator, retrieval
metadata, parser grain, and known gaps.

- GBIF records from `gbif_api` preserve GBIF dataset licenses, publisher
  licenses, citation requirements, occurrence locators, and dataset provenance.
- iNaturalist records from `inaturalist_api` preserve observation licenses,
  photo licenses, observer attribution fields when supplied, and observation
  URLs.
- Mosquito Alert records from `mosquito_alert_gbif` preserve GBIF dataset and
  media licenses for the Mosquito Alert slice.
- VectorNet records from `vectornet_aedes_surveillance` preserve the ECDC/EFSA
  VectorNet IPT/GBIF Darwin Core Archive license, archive URL, row locator,
  filtered-row locator, and source surveillance fields.
- NCBI Datasets, BioSample, and Taxonomy records from
  `ncbi_datasets_genome`, `ncbi_biosamples`, and `aedes_pathogen_taxonomy`
  preserve NCBI/public database terms, access metadata, and accession-level
  provenance.
- VectorBase/VEuPathDB records from `vectorbase_aedes_genomics` preserve
  upstream VectorBase/VEuPathDB terms, release identity, file locators, and
  line or header provenance where available.
- VectorByte/VecTraits records from `aedes_vectorbyte_traits` preserve
  upstream VectorByte/VBD Hub terms, dataset IDs, row IDs, source URLs,
  citations, DOIs, and raw JSON row provenance where available.
- ECDC, OECD, Mosquito Taxonomic Inventory or WRBU-style authority pages,
  WorldClim climate pages, Zenodo/Dryad global Aedes occurrence compendium
  files, NCBI BioProject metadata, and WHO Aedes resistance guidance from
  `aedes_taxonomy_authorities`, `aedes_worldclim_climate`,
  `aedes_global_compendium_occurrence`, `aedes_population_genomics`, and
  `aedes_who_resistance_guidance` preserve upstream source URLs, access terms,
  page/file locators, row locators where applicable, and explicit fetch or
  raster-sampling gaps.
- OpenAlex, PubMed, Unpaywall, and PMC Open Access literature and media lanes
  preserve article, publisher, and open-access licenses. Ask Insects should
  only parse legal full text and should keep source gaps for restricted text.
- Dryad, Mendeley Data, OSF, Zenodo, and Figshare behavior or media lanes
  preserve dataset or article licenses, DOI or project locators, file
  manifests, checksums, and download URLs without mirroring multi-gigabyte
  binaries by default.
- WHO, PAHO, CDC, and ECDC public-health lanes preserve official page URLs,
  report locators, agency source identity, machine-readable CSV row locators
  where exposed by the agency, and explicit gaps for row-level surveillance
  data that is not stably machine-readable or authorized.
- BOLD and IR Mapper records from `bold_api` and `irmapper_aedes` preserve
  upstream terms, specimen or resistance locators, and raw row provenance.

## Contribution Rule

New source lanes must document:

- source name and URL
- upstream license or terms
- raw artifact locator
- retrieval time or access date
- parser grain
- SQLite record type
- source gaps and limits

Never commit credentials or ignored raw artifacts to the public repository.
