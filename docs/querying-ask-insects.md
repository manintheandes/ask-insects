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

To add `Aedes aegypti` brain and neuron source metadata:

```bash
python3 scripts/build_source_index.py --fixtures --neurobiology
```

To add bounded public PMC supplementary videos:

```bash
python3 scripts/ingest_pmc_videos.py --artifact-dir artifacts/mosquito-v1
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show Aedes aegypti videos" --json
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

PMC video records use source id `pmc_open_access_videos`. Raw article HTML is saved under `artifacts/mosquito-v1/raw/pmc_videos/`. Each media record stores the article URL, downloadable video URL, parsed article title, DOI when present, license text when present, and a provenance locator into the saved raw HTML.

Dryad behavior/video records use source id `dryad_aedes_behavior_videos`. Raw dataset, version, and file-manifest JSON is saved under `artifacts/mosquito-v1/raw/dryad_behavior_videos/`. Dataset records use lane `behavior`; video/archive file records use lane `media`; README/source-data files use lane `behavior`. Each record stores the DOI, behavior labels, license, file size, checksum, download URL when present, raw manifest payload, and a provenance locator into the saved Dryad API JSON. The default ingest indexes metadata and download locators only; it does not mirror large video archives.

IR Mapper resistance records use source id `irmapper_aedes`. Raw public API JSON is saved under `artifacts/mosquito-v1/raw/irmapper/`. Each resistance record stores the raw row payload, the installed species filter, and a provenance locator into the saved raw JSON row.

Pathogen taxonomy records use source id `aedes_pathogen_taxonomy`. Raw NCBI E-utilities taxonomy summary JSON is saved under `artifacts/mosquito-v1/raw/pathogen_taxonomy/`. Each `vector_competence` record stores a configured pathogen label, taxid, pathogen group, Aedes relevance note, raw taxonomy summary, and provenance locator into the saved NCBI summary JSON. This lane gives pathogen-specific questions stable identifiers while assay-level table extraction remains a source gap.

Vector-competence assay-candidate records use source id `aedes_vector_competence_assays`. They are derived from source-grade literature rows and legal full-text units already in SQLite. Each record stores a detected pathogen, assay-field map, context terms, temperature values, dose values, source paper ID, full-text unit ID when present, and a snippet. Provenance points back to `records#<paper_id>` and, when available, `literature_fulltext_units#<unit_id>`. This lane is legal full-text only and does not use private cookies, institutional access, or Sci-Hub.

Literature records use source id `aedes_literature_openalex`. OpenAlex is the canonical discovery source. The boundary is `Aedes aegypti` material in title, abstract, or accepted topic metadata from 2020-01-01 through the run date. PubMed is an identifier and metadata enrichment. Unpaywall is a legal open full-text resolver. Do not use Sci-Hub, private cookies, or institutional scraping.

OpenAlex raw cursor pages are saved under `artifacts/aedes-literature-2020/raw/literature/` when that artifact directory is used. PubMed and Unpaywall enrichment payloads are stored per record in SQLite `record_payloads.payload_json`. Legal direct PDF/XML/text chunks are stored in `literature_fulltext_units` and mirrored into `literature_fulltext_fts`. Normal `ask` and `search literature` use metadata and abstracts first; literature answers fall back to legal full-text chunks, and `search fulltext` queries those chunks directly. Gaps are structured in `gaps.json`, including missing DOI, missing PMID, missing abstract, topic search gaps, Unpaywall no-full-text cases, landing-page-only cases, fetch failures, and parse failures.

NCBI genomics records use source id `ncbi_datasets_genome`. The parser reads assembly metadata, GFF annotations, and protein FASTA headers from an NCBI Datasets package and writes lanes `genome_assemblies`, `genes`, `transcripts`, `genome_features`, and `proteins`.

NCBI BioSample records use source id `ncbi_biosamples` and lane `biosamples`. The ingest fetches bounded `"Aedes aegypti"[Organism]` BioSample ESearch and ESummary JSON, saves it under `artifacts/mosquito-v1/raw/ncbi_biosamples/`, parses sample XML attributes, and stores accessions, sample names, strain or isolate fields, collection date, geography, tissue, isolation source, organization, and linked SRA identifiers when present.

```bash
python3 -m askinsects ingest-ncbi-biosamples --limit 1000
python3 -m askinsects ask "show Aedes aegypti BioSamples from China" --json
python3 -m askinsects search biosamples "Rockefeller SRA"
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
python3 -m askinsects ask --hosted "show mosquito observations with images in Brazil"
python3 -m askinsects sql --hosted "select source, lane, count(*) as n from records group by source, lane"
python3 -m askinsects search fulltext "microbiota Aedes aegypti" --hosted
```
