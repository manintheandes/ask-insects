# Source Map

Open Insects is built from public insect sources. Ask Insects is its first source-backed tool. Each source is a place Ask Insects can read from, such as biodiversity APIs, observation records, licensed photos, public videos, research papers, genomes, cell atlases, or official public-health pages.

This page exists so the interactive graph shows what is actually inside Ask Insects.

## Main Sources

- [[Sources/Observations and Images]] covers GBIF, iNaturalist, Mosquito Alert, taxonomy, occurrence records, licensed still images, and media payloads.
- [[Sources/Genome and BioSample Evidence]] covers NCBI Datasets, NCBI BioSample, VectorBase/VEuPathDB, and BOLD DNA barcode evidence.
- [[Sources/Research Papers]] covers Aedes aegypti literature metadata, legal full-text units, and derived paper facets.
- [[Sources/Behavior Media and Datasets]] covers behavior records, Dryad datasets, Mendeley datasets and parsed tables, PMC videos, and OSF FlightTrackAI manifests.
- [[Sources/Neurobiology and Connectome Evidence]] covers brain atlas, cell atlas, MosquitoBrains, GEO/SRA workflow records, CATMAID metadata, skeleton records, and connectome gaps.
- [[Sources/Vector Competence and Pathogens]] covers pathogen taxonomy anchors and vector-competence assay candidates.
- [[Sources/Resistance and Control Evidence]] covers IR Mapper records and literature-derived resistance markers.
- [[Sources/Ecology and Occurrence Summaries]] covers derived country, country-month, seasonality, range, and habitat records.
- [[Sources/Public Health and Surveillance]] covers official public-health guidance and PAHO dengue surveillance report evidence.
- [[Sources/Source Gaps and Actions]] tracks explicit boundaries where Ask Insects knows a source is missing, partial, or not yet deeply parsed.

## Source IDs

| Ask Insects source | What it covers |
| --- | --- |
| `mosquito_v1_fixtures` | Seed mosquito records for taxonomy, observations, media references, literature, and action notes. |
| `gbif_api` | GBIF Aedes aegypti taxonomy and occurrence records. |
| `inaturalist_api` | iNaturalist public Aedes aegypti observations and licensed still photos. |
| `mosquito_alert_gbif` | Mosquito Alert Aedes aegypti citizen-science occurrence and media records through GBIF. |
| `aedes_occurrence_ecology` | Derived ecology records from GBIF, iNaturalist, and Mosquito Alert observations. |
| `aedes_literature_openalex` | Aedes aegypti literature records, metadata, abstracts, enrichment payloads, and legal full-text units when available. |
| `aedes_literature_facets` | Literature-derived behavior, vector competence, resistance, ecology, and public-health facets. |
| `ncbi_datasets_genome` | NCBI Aedes aegypti assembly, GFF features, genes, transcripts, proteins, and genome metadata. |
| `ncbi_biosamples` | NCBI BioSample sample metadata, strain/isolate fields, geography, collection date, and linked SRA identifiers when exposed. |
| `vectorbase_aedes_genomics` | VectorBase/VEuPathDB genes, transcripts, proteins, genome features, and GO annotations. |
| `bold_api` | BOLD Aedes aegypti DNA barcode specimen records. |
| `pmc_open_access_videos` | Curated open-access article supplementary videos. |
| `dryad_aedes_behavior_videos` | Dryad Aedes behavior and video dataset manifests. |
| `mendeley_aedes_behavior_media` | Mendeley Data Aedes behavior, media, sound, video, and parsed table records. |
| `osf_flighttrackai_aedes_videos` | OSF FlightTrackAI Aedes flight-behavior video, executable, model, and file manifests. |
| `zenodo_aedes_videos` | Zenodo Aedes video search and file-manifest records. |
| `figshare_aedes_videos` | Figshare Aedes article-detail and file-manifest records. |
| `aedes_neurobiology_sources` | Aedes neurobiology records, atlas artifacts, H5AD internals, voxel access, CATMAID metadata, skeleton manifests, and connectome gaps. |
| `irmapper_aedes` | Public IR Mapper Aedes aegypti resistance records. |
| `aedes_resistance_markers` | Literature-derived kdr, VGSC, and metabolic-resistance marker records. |
| `aedes_pathogen_taxonomy` | NCBI Taxonomy records for dengue, Zika, chikungunya, yellow fever, West Nile, and Mayaro virus. |
| `aedes_vector_competence_assays` | Literature-derived vector-competence assay candidate records. |
| `aedes_public_health_guidance` | WHO, PAHO, CDC, and ECDC guidance pages relevant to Aedes aegypti. |
| `aedes_paho_dengue_surveillance` | PAHO dengue situation report evidence and mapped dashboard source gaps. |
