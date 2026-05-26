# Querying Ask Insects

Build the local source index first:

```bash
python3 scripts/build_source_index.py --fixtures
```

To add a bounded live GBIF pull:

```bash
python3 scripts/build_source_index.py --fixtures --gbif --species "Aedes aegypti" --occurrence-limit 3 --occurrence-page-size 300
```

To add bounded live iNaturalist observations with photos:

```bash
python3 scripts/build_source_index.py --fixtures --inat --species "Aedes aegypti" --place Brazil --observation-limit 10
```

To deep-ingest all currently reported public licensed-photo `Aedes aegypti` observations up to an explicit cap:

```bash
python3 scripts/build_source_index.py --fixtures --inat --species "Aedes aegypti" --observation-limit 5758 --page-size 200 --delay-seconds 1
```

To build the `Aedes aegypti` literature lane from OpenAlex without fetching full text:

```bash
python3 scripts/build_source_index.py \
  --openalex-literature \
  --literature-species "Aedes aegypti" \
  --literature-from-date 2020-01-01 \
  --include-topic-discovery \
  --skip-fulltext \
  --artifact-dir artifacts/aedes-literature-2020
```

To enrich the completed OpenAlex literature artifact with PubMed, Unpaywall, and direct legal full text:

```bash
python3 scripts/enrich_literature_index.py \
  --artifact-dir artifacts/aedes-literature-2020 \
  --email you@example.com
```

To query legal full-text chunks directly:

```bash
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 search fulltext "microbiota Aedes aegypti"
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 ask "what papers since 2020 discuss microbiota and Aedes aegypti?" --json
```

For large full-text runs, use deterministic record-id shards. Each shard owns a stable slice of records, so resume workers do not duplicate each other:

```bash
python3 scripts/enrich_literature_index.py \
  --artifact-dir artifacts/aedes-literature-2020 \
  --email you@example.com \
  --fulltext-only \
  --record-id-shard-count 6 \
  --record-id-shard-index 0
```

To add `Aedes aegypti` genomics from an unpacked NCBI Datasets package:

```bash
python3 scripts/build_source_index.py --fixtures --ncbi-genome --genome-package-dir /path/to/ncbi-package
```

To add official VectorBase/VEuPathDB `Aedes aegypti` gene, transcript, protein, CDS sequence, transcript sequence, GO annotation, codon usage, identifier-history, current-ID resolution, NCBI LinkOut, OrthoMCL current-release pair downloads, and OrthoMCL 6.21 orthogroup membership rows:

```bash
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-vectorbase-genomics
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show VectorBase AAEL000001 gene annotation for Aedes aegypti" --json
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 search genome_features "GO odorant receptor"
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show VectorBase codon usage AUG for Aedes aegypti" --json
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show VectorBase CDS sequence for AAEL000016" --json
```

To add bounded GEO/SRA `Aedes aegypti` expression, RNA-seq, and transcriptome metadata:

```bash
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-expression-omics --geo-limit 120 --sra-limit 300
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show GEO RNA-seq expression data for Aedes aegypti midgut" --json
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 search expression "RNA-seq transcriptome"
```

To add bounded UniProt protein-function and proteome metadata:

```bash
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-uniprot-proteins --protein-limit 250 --proteome-limit 10
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show UniProt protein function for AAEL012345" --json
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 search proteins "UniProt protein"
```

To add bounded VectorByte/VecTraits `Aedes aegypti` trait observations:

```bash
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-vectorbyte-traits --dataset-limit 20 --row-limit 5000
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show VectorByte temperature trait data for Aedes aegypti fecundity" --json
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 search traits "fecundity temperature"
```

To add bounded VectorByte/VecDyn `Aedes aegypti` abundance observations:

```bash
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-vectorbyte-abundance --dataset-limit 5 --row-limit 5000
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-vectorbyte-abundance --dataset-id 27006 --dataset-id 220 --dataset-limit 2 --row-limit 20000 --dataset-page-limit 120
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-vectorbyte-abundance --dataset-id-file config/aedes-vectorbyte-abundance-datasets.txt --dataset-limit 25 --row-limit 100000 --dataset-page-limit 200
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-vectorbyte-abundance --dataset-id 718 --dataset-id 724 --merge-existing --dataset-limit 2 --row-limit 5000 --dataset-page-limit 80
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show VectorByte VecDyn Aedes aegypti abundance trap counts" --json
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 search observations "VecDyn abundance"
```

To add the five Aedes deep source expansions:

```bash
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-aedes-deep-sources --compendium-row-limit 5000 --bioproject-limit 20 --worldclim-sample-limit 100
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show Aedes aegypti taxonomy synonyms from authority sources" --json
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show WorldClim climate context for Aedes aegypti ecology" --json
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show global Aedes aegypti occurrence compendium rows for Brazil" --json
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show Aedes aegypti population genomics BioProject evidence" --json
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show WHO Aedes insecticide resistance bioassay guidance" --json
```

These five source IDs are `aedes_taxonomy_authorities`, `aedes_worldclim_climate`, `aedes_global_compendium_occurrence`, `aedes_population_genomics`, and `aedes_who_resistance_guidance`. Each record cites a raw HTML page, mirrored PDF plus extracted text sidecar, CSV row, NCBI ESummary locator, or WorldClim raster ZIP locator under `raw/aedes_deep_sources/`. Disabled or failed WorldClim raster sampling remains an explicit source gap.

Harvard Dataverse Aedes suitability records use source id `harvard_dataverse_aedes_suitability`. They are separate from the five-lane deep-source ingest because Dataverse file-search freshness is its own source boundary. Raw search and dataset-detail JSON are saved under `artifacts/mosquito-v1/raw/harvard_dataverse_suitability/`. Each ecology record stores dataset DOI, file DOI, file ID, filename, content type, byte size, checksum, scenario terms, license, access URL, and raw locator. If Dataverse metadata says the binary is not public-downloadable, Ask Insects keeps a queryable `dataverse_file_download_not_public` gap.

```bash
python3 -m askinsects ingest-harvard-dataverse-suitability
python3 -m askinsects ask "show Harvard Dataverse suitability rasters for Aedes aegypti dengue transmission" --json
```

To add `Aedes aegypti` brain and neuron source metadata:

```bash
python3 scripts/build_source_index.py --fixtures --neurobiology
```

To add bounded public PMC supplementary videos:

```bash
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-pmc-videos
python3 -m askinsects ingest-pmc-videos --hosted
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show Aedes aegypti videos" --json
```

To derive inspectable video atoms, previews, keyframes, probes, and queryable motion rows from indexed Aedes video sources:

```bash
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-video-atoms --mirror-videos --generate-artifacts --discover-sources --max-video-bytes 750000000 --allowed-licenses "CC0,CC-BY,CC BY,Creative Commons,https://spdx.org/licenses/CC0-1.0.html"
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-video-atoms --discover-sources --discovery-repository dryad --merge-existing --skip-motion-rows --max-discovery-results 1000
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show Aedes aegypti keyframes and previews" --json
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show Aedes aegypti motion trajectory coordinates" --json
```

To derive still-image assets, deterministic source labels, and image-label gaps from indexed iNaturalist and Mosquito Alert media:

```bash
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-image-atoms
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-image-atoms --mirror-images --max-image-mirrors 6000 --max-image-bytes 10000000 --allowed-licenses cc-by,cc-by-nc,cc-by-sa,CC0,Creative Commons
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show Aedes aegypti adult image labels" --json
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "what Aedes image label gaps are missing sex?" --json
```

To add public Dryad `Aedes aegypti` behavior/video dataset manifests:

```bash
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-dryad-behavior-videos
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show Dryad Aedes aegypti behavior videos" --json
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 search behavior "thermal infrared host seeking"
```

To add Mosquito Alert `Aedes aegypti` citizen-science observations and still images:

```bash
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-mosquito-alert --occurrence-limit 1000
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show Mosquito Alert Aedes aegypti images from Brazil" --json
```

To add public IR Mapper `Aedes aegypti` insecticide-resistance records:

```bash
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-irmapper --species "Aedes aegypti"
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "what insecticide resistance data exists for Aedes aegypti?" --json
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 search resistance "deltamethrin Brazil"
```

To extract kdr, VGSC, and metabolic-resistance marker records from indexed Aedes literature and legal full text:

```bash
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-resistance-markers
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show kdr V1016G resistance markers in Aedes aegypti" --json
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 sql "select json_extract(payload_json, '$.marker_id') as marker, count(*) as n from record_payloads where source='aedes_resistance_markers' group by marker order by n desc" --limit 20
```

To promote parsed resistance supplement rows from `aedes_extracted_facts` into table-row resistance records:

```bash
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-resistance-table-rows
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show parsed resistance table V1016G frequency for Aedes aegypti" --json
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 sql "select json_extract(payload_json, '$.confidence') as confidence, count(*) as n from record_payloads where source='aedes_resistance_table_rows' group by confidence"
```

To add NCBI Taxonomy pathogen identity anchors for Aedes-relevant arboviruses:

```bash
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-pathogen-taxonomy
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show Zika pathogen taxonomy for Aedes aegypti" --json
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 search vector_competence "yellow fever pathogen taxonomy"
```

To extract structured vector-competence assay candidates from indexed Aedes literature and legal full text:

```bash
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-vector-competence-assays
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show Zika vector competence assay dose and transmission for Aedes aegypti" --json
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 sql "select json_extract(payload_json, '$.pathogen') as pathogen, count(*) as n from record_payloads where source='aedes_vector_competence_assays' group by pathogen order by n desc" --limit 20
```

To download and index the raw neurobiology artifact cache:

```bash
python3 scripts/ingest_neurobiology_sources.py
python3 scripts/build_source_index.py --fixtures --neurobiology --neurobiology-artifact-dir ~/.local/share/ask-insects/sources/neurobiology
```

Then query through the CLI:

```bash
python3 -m askinsects ask "what do we know about Aedes aegypti?"
python3 -m askinsects search observations "Brazil"
python3 -m askinsects search proteins "odorant receptor"
python3 -m askinsects search proteins "gustatory receptor"
python3 -m askinsects search neurobiology "brain atlas"
python3 -m askinsects ask "what neuron data exists for the Aedes aegypti brain?"
python3 -m askinsects search papers "host seeking"
python3 -m askinsects sql "select species, count(*) as records from records group by species"
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 ask "what papers since 2020 discuss Wolbachia and Aedes aegypti?" --json
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 search literature "Wolbachia dengue"
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 sql "select source, lane, count(*) as records from records group by source, lane"
```

Answers must include source, record id, and provenance locator. If evidence is missing, Ask Insects should say which source lane is missing or thin.

GBIF records use source id `gbif_api`. Raw GBIF responses are saved under `artifacts/mosquito-v1/raw/gbif/` and summarized in `artifacts/mosquito-v1/source_receipt.json`.

For a hosted deep GBIF refresh of the current `Aedes aegypti` occurrence set:

```bash
python3 -m askinsects ingest-gbif --hosted --species "Aedes aegypti" --occurrence-limit 82237 --occurrence-page-size 300 --occurrence-workers 6 --delay-seconds 0
```

This command talks to the hosted API. The server fetches GBIF pages with a small worker pool, writes raw JSON under `/home/josh/ask-insects/artifacts/mosquito-v1/raw/gbif/`, refreshes `gbif_api` rows in `/home/josh/ask-insects/artifacts/mosquito-v1/source_index.sqlite`, and preserves the other hosted lanes. The May 24, 2026 hosted refresh installed 82,237 `Aedes aegypti` occurrence records plus the GBIF taxonomy row with zero GBIF gaps.

iNaturalist records use source id `inaturalist_api`. Raw iNaturalist responses are saved under `artifacts/mosquito-v1/raw/inaturalist/` and summarized in `artifacts/mosquito-v1/source_receipt.json`.
Deep iNaturalist ingests save one raw JSON file per API page, for example `Aedes_aegypti_anywhere_page_001.json`.
Local and hosted iNaturalist ingests are incremental. They replace only `inaturalist_api` rows, preserving the other source lanes already installed in `artifacts/mosquito-v1`.

Mosquito Alert records use source id `mosquito_alert_gbif`. Raw GBIF dataset and occurrence pages are saved under `artifacts/mosquito-v1/raw/mosquito_alert/`. Each observation record stores the raw GBIF occurrence payload and occurrence license. Each media record stores the raw image metadata and media license.

VectorNet surveillance records use source id `vectornet_aedes_surveillance`. Raw IPT Darwin Core Archive files are saved under `artifacts/mosquito-v1/raw/vectornet_surveillance/`, with a filtered TSV for source rows where `scientificName` or `verbatimIdentification` identifies `Aedes aegypti`. Each observation record stores the raw Darwin Core row, detection versus absence-surveillance status, count, life stage, sex, sampling protocol, geography, date range, degree of establishment, and exact row locators. Refresh it with `python3 -m askinsects ingest-vectornet-surveillance`, then ask source-specific questions such as `show VectorNet Aedes aegypti surveillance evidence` or `show VectorNet regional ecology summaries for Aedes aegypti`.

PMC video records use source id `pmc_open_access_videos`. Raw article HTML is saved under `artifacts/mosquito-v1/raw/pmc_videos/`. Each media record stores the article URL, downloadable video URL, parsed article title, DOI when present, license text when present, and a provenance locator into the saved raw HTML.

Zenodo Aedes video records use source id `zenodo_aedes_videos`. Raw Zenodo search JSON is saved under `artifacts/mosquito-v1/raw/zenodo_aedes_videos/`. Each media record stores the Zenodo record ID, file name, download URL, source URL, license, byte size, source-provided hash, raw record/file payloads, and a locator into the saved search JSON. Rejected or empty search outcomes are queryable as `video_gap` records with the original gap reason and locator. The lane only accepts records where source-provided Zenodo metadata materially names `Aedes aegypti`; query terms alone are not evidence.

Figshare Aedes video records use source id `figshare_aedes_videos`. Raw Figshare search and article-detail JSON are saved under `artifacts/mosquito-v1/raw/figshare_aedes_videos/`. Each media record stores the Figshare article ID, file ID, file name, DOI, download URL, source URL, license, byte size, source-provided hash, raw article/file payloads, and a locator into the saved article-detail JSON. Rejected, failed, or empty article outcomes are queryable as `video_gap` records with the original gap reason and locator. The lane only accepts records where source-provided Figshare metadata materially names `Aedes aegypti`; query terms alone are not evidence.

Video atom records use source id `aedes_video_atoms`. They derive video assets, mirrors, probes, inspectable artifacts, motion rows, archive manifests, archive members, and structured gaps from PMC, Dryad, Mendeley, OSF, Zenodo, Figshare, upstream Zenodo/Figshare manifest gaps, repository discovery, and source tables. Discovery records must have `Aedes aegypti` in source-provided material metadata such as title, description, file name, citation, species, or equivalent source text. Search terms alone are not evidence. Queryable sweep receipts must cite the exact query/page/cursor or local scan used for each repository target. Bounded ZIP archives are expanded into member assets when license and size allow; unsupported, huge, unreadable, or unclear-license archives remain structured gaps. Inspectable artifacts distinguish thumbnails from sampled `keyframe_*.jpg` records, and frame manifests must include a non-empty `keyframes` list. Motion rows carry `source_video_asset_id` when the source table names a matching video. When a video is blocked by unclear license, size, download failure, unsupported archive format, archive read failure, or an upstream manifest rejection, the gap payload preserves source download URL, source URL, byte size, source-provided hashes when available, license text, source dataset, repository, original source/reason when available, and locator. Repository-scoped refreshes use `--discovery-repository <target> --merge-existing`; they update the selected repository's records and receipt while preserving the previously installed full video lane. Use `--skip-motion-rows` for these small follow-up passes unless the motion table inputs themselves changed.

Dryad behavior/video records use source id `dryad_aedes_behavior_videos`. Raw dataset, version, and file-manifest JSON is saved under `artifacts/mosquito-v1/raw/dryad_behavior_videos/`. Dataset records use lane `behavior`; video/archive file records use lane `media`; README/source-data files use lane `behavior`. Each record stores the DOI, behavior labels, license, file size, checksum, download URL when present, raw manifest payload, and a provenance locator into the saved Dryad API JSON. The default ingest indexes metadata and download locators only; it does not mirror large video archives.

IR Mapper resistance records use source id `irmapper_aedes`. Raw public API JSON is saved under `artifacts/mosquito-v1/raw/irmapper/`. Each resistance record stores the raw row payload, the installed species filter, and a provenance locator into the saved raw JSON row.

WHO Malaria Threats Map resistance audit records use source id `who_malaria_threats_resistance_audit`. The ingest saves a bounded `FACT_PREVENTION_VIEW` CSV sample from the WHO public data endpoint under `artifacts/mosquito-v1/raw/who_malaria_threats_resistance/`, then queries the endpoint for Aedes species rows. The current public species-filter query returns no Aedes rows, so Ask Insects installs a queryable source-gap record with reason `who_malaria_threats_no_aedes_rows`.

```bash
python3 -m askinsects ingest-who-malaria-threats-resistance
python3 -m askinsects ask "show the WHO insecticide resistance database rows for Aedes aegypti" --json
```

Resistance-marker records use source id `aedes_resistance_markers`. They are derived from source-grade literature rows and legal full-text units already in SQLite. Each record stores marker ID, marker class, gene or family, matched aliases, context terms, insecticide terms, source paper ID, full-text unit ID when present, and snippet. Provenance points back to `records#<paper_id>` and, when available, `literature_fulltext_units#<unit_id>`. The May 24, 2026 hosted ingest installed 6,449 marker records with zero marker-source gaps. This lane is legal full-text only and does not use private cookies, institutional access, or Sci-Hub.

Resistance-table records use source id `aedes_resistance_table_rows`. They are derived from parsed supported-format `aedes_extracted_facts` resistance table rows. Each record stores insecticide terms, marker or mutation terms, assay terms, metric fields, table headers, row values, source extracted-fact ID, source paper ID, and validation status. Provenance points back to the extracted-fact record, source literature record, and raw supplement row locator. These records are schema-validated and not human-validated. If no parsed row passes validation, the lane returns a queryable `source_gap` record that reports how many extracted-fact resistance rows and parsed table rows were checked.

Occurrence ecology records use source id `aedes_occurrence_ecology`. They are derived from indexed GBIF, iNaturalist, and Mosquito Alert observation payloads already in SQLite. Each `ecology` record stores an aggregation type such as country summary, country-month summary, or public habitat summary; source counts; observation counts; sample input record IDs; sample URLs; coordinate count; bounding box when coordinates exist; and first and last observed dates. Provenance points back to the SQLite observation join. The May 24, 2026 hosted ingest installed 1,985 occurrence ecology records from 88,065 Aedes observation inputs. Refresh it with `python3 -m askinsects ingest-occurrence-ecology`, then ask range and seasonality questions such as `what seasonality evidence exists for Aedes aegypti in Brazil by month?`.

Observation climate-join records use source id `aedes_observation_climate_join`. They derive one bounded `ecology` record per coordinate-bearing GBIF, iNaturalist, or Mosquito Alert observation sampled against the local WorldClim v2.1 10-minute bioclim ZIP. Each record stores source observation ID/source, observed date, country/place, coordinates, annual mean temperature, annual precipitation, raster URL, raw ZIP locator, and upstream observation provenance. Refresh it with `python3 -m askinsects ingest-observation-climate-join --limit 1000`, then ask questions such as `show climate-linked Aedes aegypti observation ecology in Brazil` or `show annual mean temperature and precipitation joined to Aedes aegypti observations`.

PAHO dengue surveillance records use source id `aedes_paho_dengue_surveillance`. They parse official PAHO dengue situation report HTML into `public_health` records for regional week summaries, year-to-date indicators, subregional case-change notes, serotype circulation notes, figure/table media locators, and dashboard page or iframe locator records. They also parse PAHO/EIH Core Indicators ZIP/CSV rows where `indicator_name` is `Dengue cases`, making annual country/territory dengue cases machine-readable and provenance-backed. Refresh it with `python3 -m askinsects ingest-paho-dengue-surveillance`, then ask public-health questions such as `show PAHO dengue surveillance evidence for Aedes aegypti`, `show PAHO Open Data annual dengue cases for Brazil`, or `show PAHO PLISA dashboard locator evidence for Aedes aegypti`. PAHO/PLISA country-week dashboard rows remain a source gap until there is stable weekly machine-readable CSV, JSON, or API access.

WHO dengue surveillance records use source id `aedes_who_dengue_surveillance`. They parse official WHO dengue surveillance pages, WER global update pages, WPRO situation-update links, archive links, publication download locators, and WHO Western Pacific Health Data Platform dengue dashboard locators into `public_health` records. Refresh it with `python3 -m askinsects ingest-who-dengue-surveillance`, then ask questions such as `show WHO dengue surveillance evidence for Aedes aegypti`, `show WHO WER dengue global update evidence`, or `show WHO dengue dashboard locator evidence for Aedes aegypti`. WHO dashboard locator records are queryable, but country/time dashboard rows remain a source gap until a stable machine-readable export or API is available.

CDC dengue surveillance records use source id `aedes_cdc_dengue_surveillance`. They parse official CDC dengue current-year and historic pages, CDC WCMS visualization JSON configs, linked CDC CSV datasets, and ArboNET limitation paragraphs into `public_health` records. Refresh it with `python3 -m askinsects ingest-cdc-dengue-surveillance`, then ask questions such as `show CDC ArboNET dengue surveillance current cases`, `show CDC ArboNET county dengue cases`, or `show CDC ArboNET limitations`. CSV-row payloads preserve dimensions such as year, travel status, jurisdiction, county, week, age group, case status, clinical syndrome, serotype, and hospitalization when present, plus numeric or categorical measures from the source row.

India NCVBDC dengue surveillance records use source id `aedes_ncvbdc_dengue_surveillance`. They parse the official Government of India NCVBDC dengue situation table into `public_health` records for each state/UT-year row, each national country-year total, and a latest-two-complete-years summary record. Refresh it with `python3 -m askinsects ingest-ncvbdc-dengue-surveillance`, then ask questions such as `what were dengue deaths in India over the last two years as a result of Aedes?`, `show NCVBDC India dengue deaths for 2024`, or `show India dengue cases and deaths by state`.

Brazil OpenDataSUS dengue surveillance records use source id `aedes_opendatasus_dengue_surveillance`. They parse official Brazil Ministry of Health OpenDataSUS SINAN dengue CSV ZIP files into aggregate `public_health` records at source-file, country-year, residence-state-year, notification-state-year, country epidemiological-week, and residence-state epidemiological-week grain. Refresh it with `python3 -m askinsects ingest-opendatasus-dengue-surveillance`, then ask questions such as `show Brazil OpenDataSUS dengue deaths and notifications for 2025`, `show Brazil SINAN dengue surveillance by state`, or `show OpenDataSUS Brazil dengue epidemiological week records`. Payloads preserve source file URL, raw ZIP locator, SHA-256 checksum, byte size, row count, year, UF code, state name, notifications, EVOLUCAO=2 deaths by disease, severe dengue classifications, hospitalized notifications, and classification/sex/criterion counts. Person-level line records are intentionally not indexed.

World Mosquito Program Wolbachia intervention records use source id `aedes_wolbachia_interventions`. Raw WMP HTML is saved under `artifacts/mosquito-v1/raw/wolbachia_interventions/`. Each `public_health` record stores organization, topic, intervention type, source-mentioned metrics, source URL, and a provenance locator into the saved HTML. Refresh it with `python3 -m askinsects ingest-wolbachia-interventions`, then ask questions such as `show World Mosquito Program Wolbachia intervention evidence from Yogyakarta`.

VectorByte trait records use source id `aedes_vectorbyte_traits`. Raw VBD Hub search JSON and VecTraits dataset JSON are saved under `artifacts/mosquito-v1/raw/vectorbyte_traits/`. Each `traits` record stores dataset ID, row ID, trait name, value, unit, temperature, stage, sex, habitat, lab/field context, location, coordinates when supplied, citation, DOI, and a provenance locator into the saved raw JSON row. Refresh it with `python3 -m askinsects ingest-vectorbyte-traits`, then ask questions such as `show VectorByte temperature trait data for Aedes aegypti fecundity`.

VectorByte abundance records use source id `aedes_vectorbyte_abundance`. Raw VecDyn provider metadata and paginated `vecdyncsv` JSON are saved under `artifacts/mosquito-v1/raw/vectorbyte_abundance/`. Each dataset record stores dataset ID, title, species list, years, collection methods, collections, row count, citation, DOI, and raw metadata locator. Each sample record stores sample value, unit, date/time, stage, sex, sampling method, coordinates, location, dataset title, citation, DOI, and a provenance locator into the saved raw page row. Refresh it with `python3 -m askinsects ingest-vectorbyte-abundance`, or use repeated `--dataset-id` flags or `--dataset-id-file` to make an exact VecDyn dataset receipt without depending on broad provider search ordering. Add `--merge-existing` when doing chunked expansion so only the requested dataset IDs are refreshed and the already installed abundance rows remain available. Then ask questions such as `show VectorByte VecDyn Aedes aegypti abundance trap counts`.

Pathogen taxonomy records use source id `aedes_pathogen_taxonomy`. Raw NCBI E-utilities taxonomy summary JSON is saved under `artifacts/mosquito-v1/raw/pathogen_taxonomy/`. Each `vector_competence` record stores a configured pathogen label, taxid, pathogen group, Aedes relevance note, raw taxonomy summary, and provenance locator into the saved NCBI summary JSON. This lane gives pathogen-specific questions stable identifiers while assay-level table extraction remains a source gap.

Vector-competence assay-candidate records use source id `aedes_vector_competence_assays`. They are derived from source-grade literature rows, legal full-text units, and parsed `aedes_extracted_facts` supplement table rows already in SQLite. Candidate records store a detected pathogen, assay-field map, context terms, temperature values, dose values, source paper ID, full-text unit ID when present, and a snippet. Promoted supplement-table records store `confidence: parsed_table_schema_validated`, `validation_status: schema_validated`, `human_validated: false`, the source extracted-fact record ID, table headers, table row, row index, metric fields, and extracted-fact provenance. Provenance points back to `records#<paper_id>`, `literature_fulltext_units#<unit_id>` when available, and `aedes_extracted_facts#<record_id>` for promoted parsed table rows. This lane is legal full-text and public-supplement only and does not use private cookies, institutional access, or Sci-Hub.

Cross-lane extracted facts use source id `aedes_extracted_facts`. Refresh them with:

```bash
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-extracted-facts
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-extracted-facts --discover-supplements --download-supplements --max-supplement-discovery-records 500 --max-supplement-files 100 --max-supplement-bytes 2000000
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show dengue vector competence supplement table infection rate for Aedes aegypti" --json
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 sql "select lane, count(*) as n from records where source='aedes_extracted_facts' group by lane order by lane"
```

This lane emits supplement manifests plus deterministic candidate facts for vector competence, resistance, behavior, ecology, and public health. With opt-in supplement discovery and download, it also parses supported `.csv`, `.tsv`, `.xlsx`, `.docx`, XML table, and simple HTML table rows into `parsed` fact records with raw-file and row provenance. Metadata discovery covers identifier-backed Europe PMC, PMC, and Figshare records and is separately bounded by `--max-supplement-discovery-records` so production runs do not make unbounded literature-wide lookups. It is not yet human-validated extraction.

Literature records use source id `aedes_literature_openalex`. OpenAlex is the canonical discovery source. The boundary is `Aedes aegypti` material in title, abstract, or accepted topic metadata from 2020-01-01 through the run date. PubMed is an identifier and metadata enrichment. Unpaywall is a legal open full-text resolver. Do not use Sci-Hub, private cookies, or institutional scraping.

The Aedes olfaction audit lane uses source id `aedes_olfaction_literature`. It fetches a bounded PubMed ESearch/ESummary candidate set for Aedes olfaction, odor, chemosensory, antenna, Orco, and receptor terms from 2020 onward, writes one `literature` record per PMID, and annotates each record with `coverage_status`, `matched_record_ids`, and `matched_sources`. When an Unpaywall email is supplied, the same lane fetches legal direct open XML, PDF, HTML, or text files and stores parsed paper chunks plus figure captions in `literature_fulltext_units`:

```bash
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-aedes-olfaction-literature --max-results 500 --page-size 100 --unpaywall-email sources@openinsects.org
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 search literature "Aedes aegypti olfaction coverage_status"
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 search fulltext "Aedes aegypti Orco figure"
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 sql "select json_extract(p.payload_json, '$.coverage_status') as status, count(*) as n from records r join record_payloads p on p.record_id=r.record_id where r.source='aedes_olfaction_literature' group by status"
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-crossref-literature-audit --max-results 500 --page-size 100
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show Crossref DOI audit literature for Aedes aegypti" --json
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-mosquito-repellent-literature --pubmed-max-results 1000 --crossref-max-results 1000 --page-size 100
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ingest-mosquito-repellent-external-discovery --max-results-per-source 50
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "what mosquito repellent papers since 2020 are in the database?" --json
```

OpenAlex raw cursor pages are saved under `artifacts/aedes-literature-2020/raw/literature/` when that artifact directory is used. PubMed and Unpaywall enrichment payloads are stored per record in SQLite `record_payloads.payload_json`. Legal direct PDF/XML/text chunks are stored in `literature_fulltext_units` and mirrored into `literature_fulltext_fts`. Normal `ask` and `search literature` use metadata and abstracts first; literature answers fall back to legal full-text chunks, and `search fulltext` queries those chunks directly. Gaps are structured in `gaps.json`, including missing DOI, missing PMID, missing abstract, topic search gaps, Unpaywall no-full-text cases, landing-page-only cases, fetch failures, and parse failures.

Crossref literature-audit records use source id `aedes_crossref_literature_audit`. Raw Crossref `/works` pages are saved under `artifacts/mosquito-v1/raw/aedes_crossref_literature_audit/`. Each audit record stores DOI, title, publisher, container title, issued date, Crossref member, reference count, license links, `coverage_status`, matched Ask Insects record IDs, and a raw page locator. Structured gaps include `aedes_crossref_fetch_failed`, `aedes_crossref_result_limit_applied`, `aedes_crossref_no_material_aedes_records`, and `aedes_crossref_no_canonical_literature_rows`.

Mosquito repellent literature records use source id `mosquito_repellent_literature`. Raw PubMed and Crossref pages are saved under `artifacts/mosquito-v1/raw/mosquito_repellent_literature/`. Each record stores PMID or DOI when supplied, title, authors, journal or container, publication date, candidate source, matched mosquito terms, matched repellent terms, `coverage_status`, matched Ask Insects record IDs, and raw PubMed/Crossref locators. Structured gaps include `mosquito_repellent_pubmed_search_failed`, `mosquito_repellent_pubmed_summary_failed`, `mosquito_repellent_pubmed_result_limit_applied`, `mosquito_repellent_crossref_fetch_failed`, `mosquito_repellent_crossref_result_limit_applied`, `mosquito_repellent_no_candidates`, and `mosquito_repellent_no_canonical_literature_rows`.

External repellent discovery records use source id `mosquito_repellent_external_discovery`. Raw OpenAlex, Europe PMC, AGRICOLA-through-Europe-PMC, Semantic Scholar, Crossref posted-content preprint, DataCite, Zenodo, and Figshare pages are saved under `artifacts/mosquito-v1/raw/mosquito_repellent_external_discovery/`. Each `literature`, `datasets`, or `patents` record stores source family, artifact type, DOI or external ID when exposed, publication date, venue or repository, source URL, matched mosquito/repellent terms, and raw locator provenance. Queryable gap rows preserve `biorxiv_medrxiv_no_text_search_api`, `patentsview_migrated_or_unavailable_json_api`, `uspto_open_data_portal_requires_api_access`, `cabi_no_public_metadata_api_configured`, and `google_scholar_no_public_api` instead of pretending those sources were fully ingested.

NCBI genomics records use source id `ncbi_datasets_genome`. The parser reads assembly metadata, GFF annotations, and protein FASTA headers from an NCBI Datasets package and writes lanes `genome_assemblies`, `genes`, `transcripts`, `genome_features`, and `proteins`.

VectorBase genomics records use source id `vectorbase_aedes_genomics`. The parser reads official VectorBase/VEuPathDB `AaegyptiLVP_AGWG` GFF, annotated protein FASTA, annotated CDS FASTA, annotated transcript FASTA, GO GAF, codon usage, identifier event history, current-ID resolution rows, NCBI LinkOut, OrthoMCL CURRENT corePairs ortholog, coortholog, and inparalog downloads, and OrthoMCL 6.21 orthogroup membership rows. OrthoMCL pair rows are parsed only when either side starts with `aaeg-old|AAEL`, and stored as first-pass pair `genome_features` records with `relationship_type`, `left_id`, `right_id`, `score`, and raw-file line provenance. Orthogroup rows are parsed when a member starts with `aaeg|AAEL` or `aaeg-old|AAEL`, and preserve orthogroup ID, Aedes member ID, Aedes gene ID, group size, Aedes-member count, sample members, and raw-file line provenance.

Expression-omics records use source id `aedes_expression_omics`. GEO dataset records and SRA run records are queryable metadata atoms. Count-matrix, normalized-expression-matrix, raw SRA reanalysis, and differential-expression-output questions route to queryable expression source-gap records until those computed artifacts are actually onboarded.

NCBI BioSample records use source id `ncbi_biosamples` and lane `biosamples`. The ingest fetches `"Aedes aegypti"[Organism]` BioSample ESearch and ESummary JSON, saves it under `artifacts/mosquito-v1/raw/ncbi_biosamples/`, parses sample XML attributes, and stores accessions, sample names, strain or isolate fields, collection date, geography, tissue, isolation source, organization, and linked SRA identifiers when present. The current hosted receipt is complete for the current NCBI count: 20,656 fetched records out of 20,656 reported, with zero hosted gaps.

```bash
python3 -m askinsects ingest-ncbi-biosamples --limit 20656
python3 -m askinsects ask "show Aedes aegypti BioSamples from China" --json
python3 -m askinsects search biosamples "Rockefeller SRA"
```

NCBI dbSNP variation audit records use source id `aedes_ncbi_snp_variation` and lane `genome_features`. The ingest queries dbSNP with `"Aedes aegypti"[Organism]`, saves raw ESearch and ESummary JSON under `artifacts/mosquito-v1/raw/ncbi_snp_variation/`, and indexes returned SNP summaries when NCBI exposes them. The current NCBI dbSNP organism query returns zero records, so Ask Insects installs a queryable source-gap record with reason `ncbi_snp_no_aedes_records`.

```bash
python3 scripts/ingest_ncbi_snp_variation.py --limit 1000
python3 -m askinsects search genome_features "dbSNP variation source gap"
python3 -m askinsects sql "select source, lane, count(*) as n from records where source='aedes_ncbi_snp_variation' group by source, lane"
```

Neurobiology records use source id `aedes_neurobiology_sources`. Metadata-only builds index source records for mosquitobrains.org, GEO brain snRNA-seq, Mosquito Cell Atlas metadata, and selected open neurobiology studies. Artifact-cache builds additionally index GEO matrix summaries and features, SRA `SRP290992` run/sample metadata, raw SRA access and reanalysis workflow records, Zenodo file and ZIP-member inventory, H5AD AnnData groups/datasets/obs/var columns, workbook sheets, MosquitoBrains volume headers and region labels, coordinate-queryable voxel access locators, public Aedes EM/CATMAID project, stack, annotation, volume, skeleton-manifest, skeleton-filter, and skeleton-ID metadata, public Aedes EM/CATMAID CSV inventories, and a searchable whole-brain connectome source-gap row. Exact voxel values are available on demand:

```bash
python3 -m askinsects voxel "neuro:mosquitobrains:volume:Segmentation-Files.zip:Brain_border/WholeBrain_Border.mha" --x 0 --y 0 --z 0
```

The source index records raw SRA download inputs and a reanalysis workflow, but it does not claim the compute-heavy raw alignment/count outputs have already been generated. The public CATMAID EM project and skeleton export surface are indexed, but the future Wellcome complete whole-brain connectome bulk package is still an external availability gap.

For deeper inspection, query the payload table:

```bash
python3 -m askinsects sql "select record_id, source, lane, json_extract(payload_json, '$.raw_observation.id') as observation_id from record_payloads where source='inaturalist_api' limit 5"
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 sql "select record_id, json_extract(payload_json, '$.inclusion_paths') as paths from record_payloads where source='aedes_literature_openalex' limit 5"
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 sql "select record_id, unit_index, license from literature_fulltext_units limit 5"
```

## Hosted Querying

Hosted Ask Insects follows the Ask Monarch VM shape: the server reads `/home/josh/ask-insects/artifacts/mosquito-v1/source_index.sqlite` and the local CLI talks to the server.

```bash
python3 -m askinsects configure --url http://<vm-ip>:8080 --token "$ASK_INSECTS_TOKEN"
python3 -m askinsects health --hosted
python3 -m askinsects ingest-gbif --hosted --species "Aedes aegypti" --occurrence-limit 82237 --occurrence-page-size 300 --occurrence-workers 6 --delay-seconds 0
python3 -m askinsects ingest-inaturalist --species "Aedes aegypti" --observation-limit 5758 --page-size 200 --delay-seconds 1
python3 -m askinsects ingest-inaturalist --hosted --species "Aedes aegypti" --observation-limit 5758 --page-size 200 --delay-seconds 1
python3 -m askinsects ingest-irmapper --hosted --species "Aedes aegypti"
python3 -m askinsects ingest-dryad-behavior-videos --hosted
python3 -m askinsects ingest-pathogen-taxonomy --hosted
python3 -m askinsects ingest-vector-competence-assays --hosted
python3 -m askinsects ingest-vectorbyte-traits --hosted --dataset-limit 20 --row-limit 5000
python3 -m askinsects ingest-vectorbyte-abundance --hosted --dataset-limit 5 --row-limit 5000
python3 -m askinsects ingest-vectorbyte-abundance --hosted --dataset-id-file config/aedes-vectorbyte-abundance-datasets.txt --dataset-limit 25 --row-limit 100000 --dataset-page-limit 200
python3 -m askinsects ingest-vectorbyte-abundance --hosted --dataset-id 718 --dataset-id 724 --merge-existing --dataset-limit 2 --row-limit 5000 --dataset-page-limit 80
python3 -m askinsects ingest-crossref-literature-audit --hosted --max-results 500 --page-size 100
python3 -m askinsects ingest-mosquito-repellent-literature --hosted --pubmed-max-results 1000 --crossref-max-results 1000 --page-size 100
python3 -m askinsects ingest-mosquito-repellent-external-discovery --hosted --max-results-per-source 50
python3 -m askinsects ingest-extracted-facts --hosted
python3 -m askinsects ask --hosted "show mosquito observations with images in Brazil"
python3 -m askinsects sql --hosted "select source, lane, count(*) as n from records group by source, lane"
python3 -m askinsects search fulltext "microbiota Aedes aegypti" --hosted
```

Use extracted facts when you want table-like cross-domain paper evidence at a candidate grain:

```bash
python3 -m askinsects search vector_competence "extracted dengue transmission" --hosted
python3 -m askinsects search resistance "extracted permethrin mortality" --hosted
python3 -m askinsects sql --hosted "select lane, count(*) as n from records where source='aedes_extracted_facts' group by lane"
```

Those records cite the source paper or legal full-text unit and carry `confidence` as `candidate` or `manifest`. The ingest is bounded by a row-order `--max-fulltext-units` window for legal full-text units and matching record-level text candidates, plus a per-unit text window, and records a gap when any bound is hit. Treat them as source-backed extraction candidates until a later validation lane proves a row or table has been fully parsed and checked.
