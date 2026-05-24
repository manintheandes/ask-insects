# Ask Insects

Ask Insects is a CLI-first local source plane for mosquito evidence.

V1 starts with mosquitoes, then expands to other insect groups. It follows the Ask Monarch pattern:

```text
source artifacts -> mapped lanes -> local parsed indexes -> receipts -> CLI -> answer with provenance or gap
```

## Comprehensive Mosquito Intelligence Goal

The current comprehensive-source strategy is Aedes-first: make Ask Insects the most comprehensive `Aedes aegypti` intelligence system in the world, full stop. Other mosquitoes can still be indexed as comparison records, but they are not the completion boundary for this push.

The machine-readable coverage ledger is `config/mosquito-intelligence-coverage.json`. It is the durable backlog for domains that are not source grade yet. Do not treat a domain as covered unless the ledger, source map, receipts, SQLite records, and Ask Insects CLI all agree.

## Quick Start

```bash
python3 scripts/build_source_index.py --fixtures
python3 -m askinsects health
python3 -m askinsects summary
python3 -m askinsects sources
python3 -m askinsects ask "what do we know about Aedes aegypti?"
python3 -m askinsects ask "show mosquito observations with images in Brazil"
python3 -m askinsects ask "what should a scientist inspect next for Culex pipiens?"
python3 scripts/verify_complete.py
```

## GBIF Source Lane

GBIF is the biodiversity occurrence source lane. Local pulls are opt-in and bounded:

```bash
python3 scripts/build_source_index.py --fixtures --gbif --species "Aedes aegypti" --occurrence-limit 3
python3 -m askinsects sources
python3 -m askinsects search observations "Aedes"
```

This writes raw GBIF API responses under `artifacts/mosquito-v1/raw/gbif/`, normalizes taxonomy and occurrence records into the SQLite index, and records source receipts. Unit tests use fake GBIF responses so the completion gate stays deterministic.

Hosted Ask Insects can deep-refresh GBIF for one species without rebuilding or deleting the existing iNaturalist lane:

```bash
python3 -m askinsects ingest-gbif --hosted --species "Aedes aegypti" --occurrence-limit 82237 --occurrence-page-size 300 --occurrence-workers 6 --delay-seconds 0
```

The hosted ingest paginates GBIF occurrence search with a small worker pool, stores raw page JSON under `/home/josh/ask-insects/artifacts/mosquito-v1/raw/gbif/`, stores raw GBIF match and occurrence payloads in SQLite `record_payloads`, refreshes only `gbif_api` rows, and keeps the active server database available until the staged refresh is ready.

## iNaturalist Source Lane

iNaturalist is the live photo and observation lane. It is opt-in and bounded:

```bash
python3 -m askinsects ingest-inaturalist --species "Aedes aegypti" --place Brazil --observation-limit 10 --page-size 10 --delay-seconds 0
python3 -m askinsects sources
python3 -m askinsects ask "show mosquito observations with images in Brazil"
```

This writes raw iNaturalist API responses under `artifacts/mosquito-v1/raw/inaturalist/`, normalizes observation and still-image media records into the SQLite index, stores the raw per-record payloads in SQLite, and records source receipts. The incremental ingest refreshes only `inaturalist_api` rows, preserving literature, genomics, neurobiology, BOLD, and derived facet lanes. Unit tests use fake iNaturalist responses so the completion gate stays deterministic.

For a deeper `Aedes aegypti` ingest, use paginated API pulls with an explicit cap and delay:

```bash
python3 -m askinsects ingest-inaturalist --species "Aedes aegypti" --observation-limit 5758 --page-size 200 --delay-seconds 1
```

This saves each raw API page separately and records the page size, delay, and total iNaturalist results in the receipt.

SQLite keeps these layers:

- `records`: normalized Ask Insects evidence rows for answers, search, and provenance.
- `record_payloads`: raw per-record source payloads, keyed by `record_id`, for deeper source inspection.
- `literature_fulltext_units`: legal open full-text chunks for literature records when Unpaywall exposes a direct open text or PDF URL that Ask Insects can parse.

## NCBI Genomics Source Lane

NCBI Datasets is the first genomics lane. V1 parses an unpacked `Aedes aegypti` genome package for assembly `GCF_002204515.2`:

```bash
python3 scripts/build_source_index.py --fixtures --ncbi-genome --genome-package-dir /path/to/ncbi-package
python3 -m askinsects search proteins "odorant receptor"
python3 -m askinsects search proteins "gustatory receptor"
python3 -m askinsects ask "show odorant receptor genes in Aedes aegypti"
```

This stores the package files as raw artifacts and indexes useful atoms into SQLite: genome assembly rows, GFF genes, transcripts, other genome features, and protein FASTA headers. It does not index every DNA base as an answer row.

## BOLD DNA Barcode Source Lane

BOLD is the public DNA barcode source lane for `Aedes aegypti` specimen and COI-style marker records:

```bash
python3 scripts/ingest_bold_barcodes.py --artifact-dir artifacts/mosquito-v1 --species "Aedes aegypti" --limit 500
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 search dna_barcodes "COI Aedes aegypti"
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show BOLD COI barcode records for Aedes aegypti" --json
```

The lane writes raw BOLD TSV under `raw/bold/`, normalizes public barcode/specimen atoms into `dna_barcodes`, stores raw row payloads in SQLite, and records bounded-download gaps such as `bold_limit_applied`.
If the public API blocks the runtime IP, use `--tsv-path path/to/Aedes_aegypti_bold_combined.tsv` to ingest a saved BOLD TSV through the same parser and receipt path.

## PMC Video Source Lane

PMC open-access article pages are the first moving-image lane for `Aedes aegypti` videos:

```bash
python3 scripts/ingest_pmc_videos.py --artifact-dir artifacts/mosquito-v1
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "show Aedes aegypti videos" --json
```

The lane stores raw PMC article HTML under `raw/pmc_videos/`, extracts downloadable MP4/WebM/AVI/MOV supplementary links, normalizes them as `media` records from source `pmc_open_access_videos`, stores per-record payloads in SQLite, and records the article URL, video URL, license text, DOI, and raw HTML locator. This is the first source-grade video layer, not the final video corpus. Larger Dryad and OSF motion datasets remain follow-on targets.

## IR Mapper Resistance Source Lane

IR Mapper is the dedicated insecticide-resistance source lane for `Aedes aegypti`:

```bash
python3 -m askinsects ingest-irmapper --species "Aedes aegypti"
python3 -m askinsects ask "what insecticide resistance data exists for Aedes aegypti?" --json
python3 -m askinsects sql "select country, count(*) from (select json_extract(payload_json, '$.raw_row.country') as country from record_payloads where source='irmapper_aedes') group by country order by count(*) desc" --limit 10
```

The lane writes the raw IR Mapper Aedes JSON under `raw/irmapper/`, normalizes `Aedes aegypti` and abbreviated `Ae. aegypti` rows into `resistance` records from source `irmapper_aedes`, stores the raw row payload in SQLite, and records provenance to the saved JSON row. Other Aedes species in the endpoint are comparison material, not installed by default for this Aedes-first push.

## Aedes aegypti Neurobiology Source Lane

The neurobiology lane can run as metadata-only, or from a downloaded raw-artifact cache:

```bash
python3 scripts/build_source_index.py --fixtures --neurobiology
python3 scripts/ingest_neurobiology_sources.py
python3 scripts/build_source_index.py --fixtures --neurobiology --neurobiology-artifact-dir ~/.local/share/ask-insects/sources/neurobiology
python3 -m askinsects search neurobiology "brain atlas"
python3 -m askinsects ask "what neuron data exists for the Aedes aegypti brain?"
```

The full artifact path downloads GEO `GSE160740_RAW.tar`, SRA runinfo for `SRP290992`, the Mosquito Cell Atlas Zenodo record and files, the MosquitoBrains downloads page, Dropbox folder ZIPs when Dropbox permits direct download, and the public `htem/aedes_public` EM/CATMAID analysis repository metadata, README, CSVs, and CATMAID API metadata. SQLite indexes GEO matrix summaries and feature rows, SRA run/sample metadata, raw SRA access and reanalysis workflow records, H5AD internal AnnData groups/datasets/obs/var columns, workbook sheets, MosquitoBrains volume headers and region labels, coordinate-queryable voxel access locators, public EM/CATMAID project, stack, annotation, volume, skeleton-manifest, skeleton-filter, and skeleton-ID records, public EM/CATMAID CSV inventories, study metadata, and a narrowed whole-brain connectome source-gap row. It does not claim the compute-heavy raw SRA alignment has already been executed, and it does not claim the future Wellcome whole-brain connectome has a public bulk package yet.

Exact MosquitoBrains voxel values can be read by coordinate from the local raw artifacts:

```bash
python3 -m askinsects voxel \
  "neuro:mosquitobrains:volume:Segmentation-Files.zip:Brain_border/WholeBrain_Border.mha" \
  --x 0 --y 0 --z 0
```

## Aedes aegypti Literature Lane

The literature lane is an opt-in source lane for `Aedes aegypti` papers since 2020:

```bash
python3 scripts/build_source_index.py \
  --openalex-literature \
  --literature-species "Aedes aegypti" \
  --literature-from-date 2020-01-01 \
  --include-topic-discovery \
  --skip-pubmed \
  --skip-fulltext \
  --literature-page-size 200 \
  --literature-delay-seconds 1 \
  --artifact-dir artifacts/aedes-literature-2020

python3 scripts/enrich_literature_index.py \
  --artifact-dir artifacts/aedes-literature-2020 \
  --email you@example.com

python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 \
  ask "what papers since 2020 discuss Wolbachia and Aedes aegypti?" \
  --json
```

OpenAlex is the canonical discovery source. A paper is in-boundary when `Aedes aegypti` is material in the title, abstract, or accepted OpenAlex topic metadata. PubMed is used only as a cross-check enrichment source, and Unpaywall is used only as a legal open full-text resolver. Ask Insects does not use Sci-Hub, private cookies, or institutional scraping.

The lane writes `source_index.sqlite`, `source_status.json`, `source_receipt.json`, `literature_enrichment_receipt.json`, `gaps.json`, and raw OpenAlex cursor artifacts under `artifacts/aedes-literature-2020/`. PubMed and Unpaywall enrichment payloads are stored per record in `record_payloads`. Structured gaps record missing DOI, missing PMID, missing abstract, rejected topic candidates, unavailable full text, landing-page-only full text, fetch failures, and parse failures.

Literature can also be parsed into mosquito intelligence facets:

```bash
python3 scripts/build_literature_facets.py --artifact-dir artifacts/aedes-literature-2020
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 search behavior "host seeking"
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 search resistance "pyrethroid"
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 ask "what vector competence data exists for dengue?" --json
```

The derived source id is `aedes_literature_facets`. It creates records in `behavior`, `vector_competence`, `resistance`, `ecology`, and `public_health` from indexed Aedes literature and legal full text where available, with provenance back to the source literature record and full-text units.

## Hosted Ask Insects

Hosted V1 follows the Ask Monarch VM pattern. The parsed SQLite index and raw source artifacts live on the Google VM under `/home/josh/ask-insects/artifacts/mosquito-v1/`.

```bash
python3 -m askinsects configure --url http://<vm-ip>:8080 --token "$ASK_INSECTS_TOKEN"
python3 -m askinsects health --hosted
python3 -m askinsects ingest-gbif --hosted --species "Aedes aegypti" --occurrence-limit 82237 --occurrence-page-size 300 --occurrence-workers 6 --delay-seconds 0
python3 -m askinsects ingest-inaturalist --hosted --species "Aedes aegypti" --observation-limit 10 --page-size 10 --delay-seconds 0
python3 -m askinsects ingest-irmapper --hosted --species "Aedes aegypti"
python3 -m askinsects ask --hosted "show mosquito observations with images in Brazil"
```

## Contract

Ask Insects answers from local indexed records. Every answer includes provenance or a clear source gap. V1 does not claim to mirror all mosquito knowledge. It proves bounded source planes end to end.
