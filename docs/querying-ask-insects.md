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

Then query through the CLI:

```bash
python3 -m askinsects ask "what do we know about Aedes aegypti?"
python3 -m askinsects search observations "Brazil"
python3 -m askinsects search proteins "odorant receptor"
python3 -m askinsects search proteins "gustatory receptor"
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

This command talks to the hosted API. The server fetches GBIF pages with a small worker pool, writes raw JSON under `/home/josh/ask-insects/artifacts/mosquito-v1/raw/gbif/`, refreshes `gbif_api` rows in `/home/josh/ask-insects/artifacts/mosquito-v1/source_index.sqlite`, and preserves the other hosted lanes.

iNaturalist records use source id `inaturalist_api`. Raw iNaturalist responses are saved under `artifacts/mosquito-v1/raw/inaturalist/` and summarized in `artifacts/mosquito-v1/source_receipt.json`.
Deep iNaturalist ingests save one raw JSON file per API page, for example `Aedes_aegypti_anywhere_page_001.json`.

Literature records use source id `aedes_literature_openalex`. OpenAlex is the canonical discovery source. The boundary is `Aedes aegypti` material in title, abstract, or accepted topic metadata from 2020-01-01 through the run date. PubMed is an identifier and metadata enrichment. Unpaywall is a legal open full-text resolver. Do not use Sci-Hub, private cookies, or institutional scraping.

OpenAlex raw cursor pages are saved under `artifacts/aedes-literature-2020/raw/literature/` when that artifact directory is used. PubMed and Unpaywall enrichment payloads are stored per record in SQLite `record_payloads.payload_json`. Legal direct PDF/XML/text chunks are stored in `literature_fulltext_units` and mirrored into `literature_fulltext_fts`. Normal `ask` and `search literature` use metadata and abstracts; query full-text chunks through read-only SQL until a dedicated full-text search command is added. Gaps are structured in `gaps.json`, including missing DOI, missing PMID, missing abstract, topic search gaps, Unpaywall no-full-text cases, landing-page-only cases, fetch failures, and parse failures.

NCBI genomics records use source id `ncbi_datasets_genome`. The parser reads assembly metadata, GFF annotations, and protein FASTA headers from an NCBI Datasets package and writes lanes `genome_assemblies`, `genes`, `transcripts`, `genome_features`, and `proteins`.

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
python3 -m askinsects ingest-inaturalist --hosted --species "Aedes aegypti" --observation-limit 10 --page-size 10 --delay-seconds 0
python3 -m askinsects ask --hosted "show mosquito observations with images in Brazil"
python3 -m askinsects sql --hosted "select source, lane, count(*) as n from records group by source, lane"
```
