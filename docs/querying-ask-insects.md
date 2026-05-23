# Querying Ask Insects

Build the local source index first:

```bash
python3 scripts/build_source_index.py --fixtures
```

To add a bounded live GBIF pull:

```bash
python3 scripts/build_source_index.py --fixtures --gbif --species "Aedes aegypti" --occurrence-limit 3
```

To add bounded live iNaturalist observations with photos:

```bash
python3 scripts/build_source_index.py --fixtures --inat --species "Aedes aegypti" --place Brazil --observation-limit 10
```

To deep-ingest all currently reported public licensed-photo `Aedes aegypti` observations up to an explicit cap:

```bash
python3 scripts/build_source_index.py --fixtures --inat --species "Aedes aegypti" --observation-limit 5758 --page-size 200 --delay-seconds 1
```

Then query through the CLI:

```bash
python3 -m askinsects ask "what do we know about Aedes aegypti?"
python3 -m askinsects search observations "Brazil"
python3 -m askinsects search papers "host seeking"
python3 -m askinsects sql "select species, count(*) as records from records group by species"
```

Answers must include source, record id, and provenance locator. If evidence is missing, Ask Insects should say which source lane is missing or thin.

GBIF records use source id `gbif_api`. Raw GBIF responses are saved under `artifacts/mosquito-v1/raw/gbif/` and summarized in `artifacts/mosquito-v1/source_receipt.json`.

iNaturalist records use source id `inaturalist_api`. Raw iNaturalist responses are saved under `artifacts/mosquito-v1/raw/inaturalist/` and summarized in `artifacts/mosquito-v1/source_receipt.json`.
Deep iNaturalist ingests save one raw JSON file per API page, for example `Aedes_aegypti_anywhere_page_001.json`.
