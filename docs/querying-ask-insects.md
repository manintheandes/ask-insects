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

To add `Aedes aegypti` genomics from an unpacked NCBI Datasets package:

```bash
python3 scripts/build_source_index.py --fixtures --ncbi-genome --genome-package-dir /path/to/ncbi-package
```

To add first-pass `Aedes aegypti` brain and neuron source metadata:

```bash
python3 scripts/build_source_index.py --fixtures --neurobiology
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

NCBI genomics records use source id `ncbi_datasets_genome`. The parser reads assembly metadata, GFF annotations, and protein FASTA headers from an NCBI Datasets package and writes lanes `genome_assemblies`, `genes`, `transcripts`, `genome_features`, and `proteins`.

Neurobiology records use source id `aedes_neurobiology_sources`. The first pass indexes source metadata for mosquitobrains.org, GEO brain snRNA-seq, Mosquito Cell Atlas metadata, and selected open neurobiology studies into lane `neurobiology`. It does not claim full H5AD, SRA, connectome, or brain image-volume ingestion yet.

For deeper inspection, query the payload table:

```bash
python3 -m askinsects sql "select record_id, source, lane, json_extract(payload_json, '$.raw_observation.id') as observation_id from record_payloads where source='inaturalist_api' limit 5"
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
