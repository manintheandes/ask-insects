# Source Map

Open Insects is built from public insect sources. Ask Insects is its first source-backed tool, focused now on mosquito intelligence with Aedes aegypti as the deepest first lane.

Each source is a place Ask Insects can read from, such as biodiversity APIs, observation records, licensed photos, public videos, research papers, genomes, cell atlases, or official public-health pages. The long-term goal is to use the same source-backed pattern for insect intelligence overall.

This page exists so the interactive graph shows what is actually inside Ask Insects.

## Main Sources

- [[Sources/Observations and Images]] covers GBIF, iNaturalist, Mosquito Alert, taxonomy, occurrence records, licensed still images, and media payloads.
- [[Sources/Genome and BioSample Evidence]] covers NCBI Datasets, NCBI BioSample, VectorBase/VEuPathDB, and BOLD DNA barcode evidence.
- [[Sources/Research Papers]] covers Aedes aegypti literature metadata, legal full-text units, olfaction audits, Crossref audit records, and derived paper facets.
- [[Sources/Repellent Discovery]] covers mosquito repellent papers since 2020, external discovery metadata, datasets, preprints, patents, and blocked-source gap rows.
- [[Sources/Behavior Media and Datasets]] covers behavior records, Dryad datasets, Mendeley datasets and parsed tables, PMC videos, and OSF FlightTrackAI manifests.
- [[Sources/Neurobiology and Connectome Evidence]] covers brain atlas, cell atlas, MosquitoBrains, GEO/SRA workflow records, CATMAID metadata, skeleton records, and connectome gaps.
- [[Sources/Vector Competence and Pathogens]] covers pathogen taxonomy anchors and vector-competence assay candidates.
- [[Sources/Resistance and Control Evidence]] covers IR Mapper records and literature-derived resistance markers.
- [[Sources/Ecology and Occurrence Summaries]] covers derived country, country-month, seasonality, range, and habitat records.
- [[Sources/Public Health and Surveillance]] covers official public-health guidance, PAHO, WHO, CDC, India NCVBDC, Brazil OpenDataSUS, VectorNet, and Wolbachia evidence.
- [[Sources/Source Gaps and Actions]] tracks explicit boundaries where Ask Insects knows a source is missing, partial, or not yet deeply parsed.

## Source IDs

| Ask Insects source | What it covers |
| --- | --- |
| `mosquito_v1_fixtures` | Seed mosquito records for taxonomy, observations, media references, literature, and action notes. |
| `gbif_api` | GBIF Aedes aegypti taxonomy and occurrence records. |
| `inaturalist_api` | iNaturalist public Aedes aegypti observations and licensed still photos. |
| `mosquito_alert_gbif` | Mosquito Alert Aedes aegypti citizen-science occurrence and media records through GBIF. |
| `aedes_occurrence_ecology` | Derived ecology records from GBIF, iNaturalist, and Mosquito Alert observations. |
| `aedes_observation_climate_join` | Climate-linked observation sample records. |
| `aedes_global_compendium_occurrence` | Global Aedes occurrence compendium rows filtered to Aedes aegypti. |
| `aedes_worldclim_climate` | WorldClim climate page and bounded bioclim sample records. |
| `harvard_dataverse_aedes_suitability` | Harvard Dataverse suitability/risk raster manifests. |
| `aedes_taxonomy_authorities` | Taxonomy-authority records from public species pages and source documents. |
| `aedes_literature_openalex` | Aedes aegypti literature records, metadata, abstracts, enrichment payloads, and legal full-text units when available. |
| `aedes_literature_facets` | Literature-derived behavior, vector competence, resistance, ecology, and public-health facets. |
| `aedes_olfaction_literature` | PubMed audit records for Aedes aegypti olfaction, odor, chemosensory, antenna, Orco, odorant receptor, and ionotropic receptor papers since 2020. |
| `aedes_crossref_literature_audit` | Crossref publisher metadata audit records for Aedes aegypti literature since 2020. |
| `mosquito_repellent_literature` | PubMed and Crossref public metadata for mosquito repellent research articles since 2020. |
| `mosquito_repellent_external_discovery` | OpenAlex, Europe PMC, AGRICOLA-through-Europe-PMC, Semantic Scholar, Crossref preprint, DataCite, Zenodo, Figshare, patent-gap, CABI-gap, Google-Scholar-gap, and native-preprint-gap records for repellent discovery. |
| `ncbi_datasets_genome` | NCBI Aedes aegypti assembly, GFF features, genes, transcripts, proteins, and genome metadata. |
| `ncbi_biosamples` | NCBI BioSample sample metadata, strain/isolate fields, geography, collection date, and linked SRA identifiers when exposed. |
| `vectorbase_aedes_genomics` | VectorBase/VEuPathDB genes, transcripts, proteins, CDS/transcript sequence summaries, GO annotations, codon usage, identifier history, current-ID resolution, NCBI LinkOut, OrthoMCL pair records, and orthogroup membership records. |
| `aedes_expression_omics` | GEO and SRA expression, RNA-seq, and transcriptome metadata plus source-gap records for unexecuted raw reanalysis and matrix outputs. |
| `aedes_uniprot_proteins` | UniProtKB protein and UniProt proteome metadata for Aedes aegypti. |
| `aedes_vectorbyte_traits` | VectorByte/VecTraits Aedes aegypti trait records with value, unit, stage, sex, habitat, location, citation, DOI, and provenance. |
| `aedes_vectorbyte_abundance` | VectorByte Aedes abundance records. |
| `bold_api` | BOLD Aedes aegypti DNA barcode specimen records. |
| `aedes_ncbi_snp_variation` | dbSNP Aedes organism-query audit, currently a queryable no-record source gap. |
| `aedes_population_genomics` | NCBI BioProject population-genomics metadata. |
| `pmc_open_access_videos` | Curated open-access article supplementary videos. |
| `dryad_aedes_behavior_videos` | Dryad Aedes behavior and video dataset manifests. |
| `mendeley_aedes_behavior_media` | Mendeley Data Aedes behavior, media, sound, video, and parsed table records. |
| `osf_flighttrackai_aedes_videos` | OSF FlightTrackAI Aedes flight-behavior video, executable, model, and file manifests. |
| `zenodo_aedes_videos` | Zenodo Aedes video search and file-manifest records. |
| `figshare_aedes_videos` | Figshare Aedes article-detail and file-manifest records. |
| `aedes_neurobiology_sources` | Aedes neurobiology records, atlas artifacts, H5AD internals, voxel access, CATMAID metadata, skeleton manifests, and connectome gaps. |
| `aedes_image_atoms` | Derived still-image atom records for Aedes aegypti image assets, source provenance, and image metadata. |
| `aedes_video_atoms` | Derived video atom records for Aedes aegypti video assets, manifests, probes, previews, keyframes, frame metadata, and structured video gaps. |
| `irmapper_aedes` | Public IR Mapper Aedes aegypti resistance records. |
| `aedes_resistance_markers` | Literature-derived kdr, VGSC, and metabolic-resistance marker records. |
| `aedes_resistance_table_rows` | Parsed supported-format resistance supplement rows promoted from extracted facts. |
| `aedes_who_resistance_guidance` | WHO Aedes resistance method and discriminating-concentration guidance records. |
| `aedes_pathogen_taxonomy` | NCBI Taxonomy records for dengue, Zika, chikungunya, yellow fever, West Nile, and Mayaro virus. |
| `aedes_vector_competence_assays` | Literature-derived vector-competence assay candidate records. |
| `aedes_public_health_guidance` | WHO, PAHO, CDC, and ECDC guidance pages relevant to Aedes aegypti. |
| `aedes_paho_dengue_surveillance` | PAHO dengue situation report evidence and mapped dashboard source gaps. |
| `aedes_who_dengue_surveillance` | WHO dengue surveillance pages, WER global update pages, WPRO situation updates, archive links, and dashboard locators. |
| `aedes_cdc_dengue_surveillance` | CDC dengue current-year and historic ArboNET pages, CDC visualization JSON configs, linked CSV rows, and ArboNET limitation evidence. |
| `aedes_ncvbdc_dengue_surveillance` | India NCVBDC dengue cases/deaths table at state/UT-year, national-year, and latest-two-complete-year summary grain. |
| `aedes_opendatasus_dengue_surveillance` | Brazil OpenDataSUS SINAN dengue CSV ZIP aggregates by source file, country-year, state-year, and epidemiological week. |
| `aedes_wolbachia_interventions` | World Mosquito Program Wolbachia intervention evidence pages and metrics. |
| `vectornet_aedes_surveillance` | VectorNet Aedes surveillance records. |
| `who_malaria_threats_resistance_audit` | WHO Malaria Threats Map Aedes resistance audit records and explicit no-row gap when the Aedes filter returns no rows. |
| `aedes_source_coverage` | Coverage-ledger domain records and queryable missing-source gaps. |

<!-- publish-bump: 2026-05-28T13:42:00-07:00 -->
