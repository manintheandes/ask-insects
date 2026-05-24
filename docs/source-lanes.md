# Source Lanes

V1 is Aedes-first. Other mosquitoes can be indexed as comparison records, but `Aedes aegypti` is the completion boundary for this push.

The comprehensive-source push is Aedes-first: Ask Insects should become the most comprehensive `Aedes aegypti` intelligence system in the world. Other mosquitoes can remain comparison records, but Aedes is the completion boundary for this push. The coverage ledger lives at `config/mosquito-intelligence-coverage.json` and tracks required domains, gate status, next source candidates, and completion evidence.

## Taxonomy

Scientific names, common labels, synonyms, rank, family, genus, and species.

Sources:

- `mosquito_v1_fixtures`: deterministic repo seed records.
- `gbif_api`: live GBIF species match records when explicitly fetched. Hosted deep refreshes are currently focused on `Aedes aegypti`.

## Observations And Images

Observation records with date, region, source URL, media URL, and license when available. Live source lanes also store raw per-record payloads in SQLite so the original API fields remain queryable.

Sources:

- `mosquito_v1_fixtures`: deterministic repo seed records.
- `gbif_api`: GBIF occurrence search records when explicitly fetched. The hosted deep ingest paginates the current `Aedes aegypti` GBIF occurrence set and refreshes only `gbif_api` rows, preserving other hosted lanes. The May 24, 2026 hosted refresh installed 82,237 occurrence records plus the taxonomy row with zero GBIF gaps.
- `inaturalist_api`: bounded iNaturalist observations with licensed photos when explicitly fetched. Local and hosted incremental ingests refresh only `inaturalist_api` rows, preserving literature, genomics, neurobiology, BOLD, and derived facet lanes.
- `mosquito_alert_gbif`: Mosquito Alert Dataset records for `Aedes aegypti`, fetched through GBIF with dataset and taxon pins, preserving expert-validated citizen-science observation fields and still-image metadata.

## Videos And Media

Public moving-image or inspectable media records. V1 reports missing video coverage honestly.

Sources:

- `inaturalist_api`: still-image media URLs from iNaturalist observation photos.
- `pmc_open_access_videos`: curated public PMC article supplementary videos for Aedes behavior, biting, host-seeking, threat avoidance, and photopreference studies.
- `dryad_aedes_behavior_videos`: public Dryad dataset, version, and file manifests for Aedes host-seeking, visual-threat, flight-escape, mating/courtship, male host-attraction, and visual-tracking behavior video archives and source-data files.
- `mendeley_aedes_behavior_media`: public Mendeley Data snapshots, folders, file manifests, and parsed Aedes table rows for mate-recognition, wingbeat, hearing, flight-tone, high-speed video, and locomotory video-analysis datasets.
- `osf_flighttrackai_aedes_videos`: public OSF project `cx762` file manifests for FlightTrackAI `Aedes aegypti` flight-behavior videos, processed/unprocessed video folders, executable bundles, installation instructions, and the trained mosquito model.

Moving-image video coverage is source-grade for the bounded PMC supplementary-video seed set, Dryad file-manifest layer, Mendeley behavior/media file-manifest plus table layer, and OSF FlightTrackAI project file-manifest layer. It is not comprehensive yet; challenge-video datasets and deeper binary/video decoding remain follow-on work.
Deep iNaturalist ingest paginates the public API and saves one raw page artifact per request. Each normalized iNaturalist observation and media row also gets a matching `record_payloads` row with the raw observation and photo payload.
Mosquito Alert ingest saves the GBIF dataset metadata and Aedes occurrence pages under `raw/mosquito_alert/`. It creates one `observations` record per occurrence and one `media` record per still image, with occurrence-level and image-level license fields preserved separately in provenance and payloads.
The PMC video ingest saves one raw article HTML artifact per article, extracts downloadable video links, stores video records in `media`, stores the raw article/video payload per record, and keeps provenance locators pointing back to the saved HTML.
The Dryad behavior/video ingest saves one raw dataset, version, and file-manifest JSON artifact per DOI under `raw/dryad_behavior_videos/`. It indexes one `behavior` record per dataset, file-level `media` records for video/archive files, and file-level `behavior` records for README or source-data files. It preserves DOI, license, size, checksum, behavior labels, download URL, and raw manifest payloads without mirroring multi-gigabyte binary archives by default.
The Mendeley behavior/media ingest saves one raw snapshot JSON, one folder JSON, one combined folder-file manifest JSON per dataset, and public parsed table files under `raw/mendeley_behavior_media/`. It indexes one `behavior` record per dataset, one `behavior` record per folder, file-level `media` records for video, audio, or archive files, file-level `behavior` records for spreadsheet, source-data, README, and code files, parsed sheet records, and parsed table-row records. It preserves DOI, license, folder path, size, content type, SHA-256 hash, download URL, view URL, behavior labels, headers, row values, and raw locators without mirroring large binaries by default.
The OSF FlightTrackAI ingest saves the OSF project JSON, provider JSON, and recursive `osfstorage` folder/file manifests under `raw/osf_flighttrackai_videos/`. It indexes the project and folders as `behavior`, indexes MP4 files as `media`, indexes software, model, and instruction files as `behavior`, and preserves file size, OSF download URL, API locator, raw item payload, and provenance without mirroring multi-gigabyte binaries by default.

## Hosted Boundary

Hosted Ask Insects uses the same source lanes. The difference is location: parsed artifacts live on the Google VM under `/home/josh/ask-insects/artifacts/mosquito-v1/`, and the local CLI asks the hosted API to ingest or query those artifacts.

Hosted GBIF and iNaturalist ingests stage a copy of the active artifact directory, fetch into the staging copy, replace only the matching source rows in SQLite, write receipts, and activate the staged directory only after the refresh succeeds. This keeps the old server database readable during long pulls.

## Genomics

Genome assembly metadata, GFF annotation features, gene rows, transcript rows, and protein FASTA headers.

Sources:

- `ncbi_datasets_genome`: parsed NCBI Datasets package for `Aedes aegypti` assembly `GCF_002204515.2`.
- `ncbi_biosamples`: bounded NCBI BioSample metadata for `Aedes aegypti` samples, strains, isolates, collection dates, geographies, tissues, isolation sources, organizations, and linked SRA identifiers when present.
- `vectorbase_aedes_genomics`: official VectorBase/VEuPathDB `AaegyptiLVP_AGWG` current-release GFF, annotated protein FASTA, GO GAF, codon usage, identifier event history, and NCBI LinkOut downloads parsed into genes, transcripts, proteins, GO annotation, codon usage, ID history, and cross-reference records.

The genomics lane indexes useful atoms, not every DNA base. Raw NCBI package files remain the source artifacts. SQLite rows cite locators such as `assembly_data_report.jsonl#line/1`, `genomic.gff#line/42`, or `protein.faa#protein/XP_001`.

NCBI BioSample rows cite saved ESummary batches under `raw/ncbi_biosamples/`. The ingest is bounded by default; if NCBI reports more `Aedes aegypti` BioSamples than were fetched, Ask Insects writes a structured `biosample_limit_applied` source gap.

VectorBase rows cite saved files under `raw/vectorbase_genomics/`, with locators such as `VectorBase-68_AaegyptiLVP_AGWG.gff#line/42`, `VectorBase-68_AaegyptiLVP_AGWG_AnnotatedProteins.fasta#line/12`, `VectorBase-CURRENT_AaegyptiLVP_AGWG_GO.gaf.gz#line/200`, `VectorBase-68_AaegyptiLVP_AGWG_CodonUsage.txt#line/2`, `VectorBase-68_AaegyptiLVP_AGWG_ids_events.tab#line/1`, or `VectorBase-68_AaegyptiLVP_AGWG_NCBILinkout_Nucleotide.xml#link/1`. VectorBase-specific questions, AAEL IDs, GO annotation, codon usage, identifier-history, and LinkOut questions prefer this source over generic NCBI genome records.

Current genomics lanes:

- `genome_assemblies`
- `genes`
- `transcripts`
- `genome_features`
- `proteins`
- `dna_barcodes`
- `biosamples`

## DNA Barcodes

Public BOLD barcode records for `Aedes aegypti` specimen and marker evidence.

Sources:

- `bold_api`: bounded BOLD public combined TSV records fetched with `scripts/ingest_bold_barcodes.py`.

The barcode lane indexes BOLD process IDs as `dna_barcodes` records with marker code, country/province, collection date, BIN URI, GenBank accession, sequence length, and provenance to the saved TSV row. It is a bounded ingest: if BOLD returns more rows than the configured cap, Ask Insects records a `bold_limit_applied` gap instead of pretending the lane is complete.
When BOLD blocks the runtime IP, the same ingest script accepts `--tsv-path` so a saved public combined TSV can be parsed, copied into `raw/bold/`, receipted, and exposed through the same SQLite rows.

## Neurobiology

Brain atlas, neuroanatomy, brain single-nucleus RNA-seq, cell atlas package artifacts, and sensory-neuron study metadata for `Aedes aegypti`.

Sources:

- `aedes_neurobiology_sources`: source records for mosquitobrains.org, GEO `GSE160740`, SRA `SRP290992` runinfo, the Mosquito Cell Atlas Zenodo record and file package, public Aedes EM/CATMAID repository, CATMAID API metadata including skeleton export metadata, and selected open neurobiology studies.

Current neurobiology lane:

- `neurobiology`

The artifact cache lives at `~/.local/share/ask-insects/sources/neurobiology` by default and is populated with `scripts/ingest_neurobiology_sources.py`. When the cache is supplied to `scripts/build_source_index.py --neurobiology --neurobiology-artifact-dir`, SQLite indexes GEO matrix summaries and feature rows, SRA run and sample metadata, raw SRA access and reanalysis workflow records, Zenodo files and ZIP members, H5AD internal AnnData groups/datasets/obs/var columns, workbook sheets, MosquitoBrains download links/files/ZIP members, MHD/MHA volume headers, coordinate-queryable voxel access locators, ITK-SNAP region labels, public Aedes EM/CATMAID project, stack, annotation, volume, skeleton-manifest, skeleton-filter, and skeleton-ID metadata, public Aedes EM/CATMAID CSV inventories, and an explicit whole-brain connectome source-gap row. Exact voxel values are read on demand with `ask-insects voxel <record_id> --x <x> --y <y> --z <z>` so the index does not need one row per voxel. The source index does not claim compute-heavy raw SRA alignment/count outputs have already been executed. The public CATMAID skeleton export surface is covered, but a future Wellcome complete whole-brain connectome bulk package remains an explicit external availability gap.

## Papers And Literature

Paper metadata, abstracts when available, open access URLs, and source identifiers.

Sources:

- `mosquito_v1_fixtures`: deterministic repo seed records.
- `aedes_literature_openalex`: OpenAlex articles from 2020-01-01 through run date where `Aedes aegypti` is material in title, abstract, or accepted topic metadata.

OpenAlex is the canonical source for discovery and record identity. PubMed E-utilities are enrichment only, used for PMID-backed metadata. Unpaywall is enrichment only, used as the legal open full-text resolver. The lane may write legal direct PDF/XML/text chunks to `literature_fulltext_units`, but it must not use Sci-Hub, private cookies, or institutional scraping.

Legal full-text chunks are an atomic query plane. `search fulltext` reads `literature_fulltext_fts`, returns `literature_fulltext` evidence with provenance to the full-text unit, and literature answers fall back to those chunks when title/abstract metadata does not satisfy the question.

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

## Literature-Derived Intelligence Facets

Behavior, vector competence, resistance, ecology, and public-health records can be derived from source-grade literature records and legal full-text units with:

```bash
python3 scripts/build_literature_facets.py --artifact-dir artifacts/aedes-literature-2020
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 search resistance "pyrethroid"
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 ask "what vector competence data exists for dengue?" --json
```

This lane is source `aedes_literature_facets`. It does not replace dedicated behavior, resistance, vector-competence, ecology, or public-health databases. It creates an immediate source-backed query plane from the indexed Aedes literature while those deeper external lanes are built. The coverage ledger marks these domains as partial source-grade when the facet records are installed and ask-surface wired.

## Pathogen And Vector Competence

Pathogen identity records and vector-competence evidence for `Aedes aegypti`.

Sources:

- `aedes_literature_facets`: literature-derived vector-competence facets while deeper assay extraction is built.
- `aedes_pathogen_taxonomy`: NCBI Taxonomy summary records for dengue, Zika, chikungunya, yellow fever, West Nile, and Mayaro virus as pathogen identity anchors.
- `aedes_vector_competence_assays`: deterministic assay-candidate extraction from indexed Aedes literature records and legal full-text units.

The pathogen taxonomy lane saves NCBI E-utilities taxonomy summary JSON under `raw/pathogen_taxonomy/`, indexes one `vector_competence` row per configured pathogen, preserves the raw taxonomy summary in `record_payloads`, and cites locators such as `raw/pathogen_taxonomy/aedes_pathogen_taxonomy_esummary.json#taxonomy/64320`. It is an identity layer, not a substitute for structured extraction of infection, dissemination, and transmission assay tables.

The assay-candidate lane reads source-grade `aedes_literature_openalex` records and legal `literature_fulltext_units`, then emits `vector_competence` records when a text unit contains an Aedes-relevant pathogen plus assay context such as infection, dissemination, transmission, dose, temperature, tissue, strain, population, or timepoint. Payloads preserve the detected pathogen, matched terms, fields, temperature values, dose values, source paper ID, full-text unit ID, and snippet. This is a structured candidate layer; true table and supplement parsing remains a follow-on requirement.

## Insecticide Resistance

Insecticide susceptibility, resistance phenotype, mechanism, mutation, assay protocol, geography, time, and reference records for `Aedes aegypti`.

Sources:

- `irmapper_aedes`: live IR Mapper Aedes JSON endpoint, filtered by default to `Aedes aegypti` and `Ae. aegypti`.
- `aedes_resistance_markers`: deterministic kdr, VGSC, and metabolic-resistance marker extraction from indexed Aedes literature records and legal full-text units.
- `aedes_literature_facets`: literature-derived resistance facets while deeper source lanes are built.

The IR Mapper lane indexes one SQLite `resistance` row per matching public API row, stores the raw IR Mapper row in `record_payloads`, and cites a provenance locator such as `raw/irmapper/Aedes_aegypti.json#row/1`. It preserves source fields for country, locality, coordinates, collection year, developmental stage, test method, insecticide class, insecticide, dosage, mode of action, mortality, resistance status, mechanism, mutation frequency, reference, and source URL when present.

The resistance-marker lane indexes one SQLite `resistance` row per marker candidate, stores marker ID, marker class, gene or family, matched aliases, context terms, insecticide terms, source paper ID, and full-text unit ID when present in `record_payloads`, and cites provenance back to `records#<paper_id>` plus `literature_fulltext_units#<unit_id>` when legal full text is available. The May 24, 2026 hosted ingest installed 6,449 marker records with zero marker-source gaps. It covers candidate marker evidence such as kdr/VGSC substitutions and metabolic-resistance genes or families; validated genotype-frequency and haplotype table extraction remains follow-on work.

## Ecology

Habitat, seasonality, range, and distribution records for `Aedes aegypti`.

Sources:

- `aedes_occurrence_ecology`: derived country, country-month, seasonality, range, and public habitat summaries from indexed GBIF, iNaturalist, and Mosquito Alert observation payloads.
- `aedes_literature_facets`: literature-derived ecology facets while deeper climate, land-use, suitability, breeding-site, and surveillance lanes are built.

The occurrence ecology lane indexes one SQLite `ecology` row per country summary, country-month summary, and public iNaturalist habitat-field summary. Payloads store aggregation type, country, month when applicable, source counts, observation count, sample input record IDs, sample URLs, coordinate count, bounding box, and observed date range. Provenance points to the derived observation join over `gbif_api`, `inaturalist_api`, and `mosquito_alert_gbif`. The source id is `aedes_occurrence_ecology`, and it is refreshed with `scripts/ingest_occurrence_ecology.py`. The May 24, 2026 hosted ingest installed 1,985 occurrence ecology records from 88,065 Aedes observation inputs. Climate rasters, land-use layers, model outputs, and surveillance completeness remain explicit source gaps.

## Action Notes

Source-backed next steps for scientists, grounded in indexed observations and literature.

GBIF V1 does not create action notes by itself. It strengthens the observation and taxonomy evidence that action answers can cite.

iNaturalist V1 does not create action notes by itself. It strengthens photo-backed observation evidence that action answers can cite.

## Operational Public Health

Operational guidance, vector-control recommendations, disease-prevention pages, and community action messages connected to `Aedes aegypti`.

Sources:

- `aedes_literature_facets`: literature-derived public-health facets while deeper operational lanes are built.
- `aedes_public_health_guidance`: official WHO, PAHO, CDC, and ECDC guidance pages parsed into `public_health` records with raw HTML receipts and source URLs.
- `aedes_paho_dengue_surveillance`: official PAHO dengue situation report and dashboard landing pages parsed at report, subregion, serotype, and figure/table grain with raw HTML receipts and PAHO media locators.

The guidance lane is source-grade at the guidance-page grain: each page is mapped, fetched, raw-saved, indexed, payload-preserved, and queryable through public-health questions. The default set includes official dengue, Zika, Aedes life-cycle, vector-control, travel-medicine, Wolbachia, community prevention, and ECDC Aedes aegypti species-factsheet pages. The PAHO dengue surveillance lane adds report-grain surveillance records for the Region of the Americas, including weekly and year-to-date indicators, subregional case-change notes, serotype circulation notes, and figure/table media locators. PAHO/PLISA dashboard pages are mapped, but country-week Tableau/PHIP rows remain a source gap until a stable unauthenticated CSV, JSON, or API endpoint is available or explicit authorized access is obtained.
