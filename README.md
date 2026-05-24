# Ask Insects

Ask Insects is a CLI-first local source plane for mosquito evidence.

V1 starts with mosquitoes, then expands to other insect groups. It follows the Ask Monarch pattern:

```text
source artifacts -> mapped lanes -> local parsed indexes -> receipts -> CLI -> answer with provenance or gap
```

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
python3 scripts/build_source_index.py --fixtures --inat --species "Aedes aegypti" --place Brazil --observation-limit 10
python3 -m askinsects sources
python3 -m askinsects ask "show mosquito observations with images in Brazil"
```

This writes raw iNaturalist API responses under `artifacts/mosquito-v1/raw/inaturalist/`, normalizes observation and still-image media records into the SQLite index, and records source receipts. Unit tests use fake iNaturalist responses so the completion gate stays deterministic.

For a deeper `Aedes aegypti` ingest, use paginated API pulls with an explicit cap and delay:

```bash
python3 scripts/build_source_index.py --fixtures --inat --species "Aedes aegypti" --observation-limit 5758 --page-size 200 --delay-seconds 1
```

This saves each raw API page separately and records the page size, delay, and total iNaturalist results in the receipt.

SQLite keeps two layers:

- `records`: normalized Ask Insects evidence rows for answers, search, and provenance.
- `record_payloads`: raw per-record source payloads, keyed by `record_id`, for deeper source inspection.

## NCBI Genomics Source Lane

NCBI Datasets is the first genomics lane. V1 parses an unpacked `Aedes aegypti` genome package for assembly `GCF_002204515.2`:

```bash
python3 scripts/build_source_index.py --fixtures --ncbi-genome --genome-package-dir /path/to/ncbi-package
python3 -m askinsects search proteins "odorant receptor"
python3 -m askinsects search proteins "gustatory receptor"
python3 -m askinsects ask "show odorant receptor genes in Aedes aegypti"
```

This stores the package files as raw artifacts and indexes useful atoms into SQLite: genome assembly rows, GFF genes, transcripts, other genome features, and protein FASTA headers. It does not index every DNA base as an answer row.

## Aedes aegypti Neurobiology Source Lane

The neurobiology lane is an opt-in first pass for mosquito brain and neuron evidence:

```bash
python3 scripts/build_source_index.py --fixtures --neurobiology
python3 -m askinsects search neurobiology "brain atlas"
python3 -m askinsects ask "what neuron data exists for the Aedes aegypti brain?"
```

V1 indexes source atoms from mosquitobrains.org, GEO `GSE160740`, Mosquito Cell Atlas metadata, and selected open neurobiology study metadata. It proves queryability for brain atlas, reference brain, segmentation, brain snRNA-seq, cell atlas, antennal lobe, olfactory sensory neuron, and odor-encoding questions. It does not yet parse full H5AD matrices, raw SRA reads, connectomes, or brain image volumes.

## Hosted Ask Insects

Hosted V1 follows the Ask Monarch VM pattern. The parsed SQLite index and raw source artifacts live on the Google VM under `/home/josh/ask-insects/artifacts/mosquito-v1/`.

```bash
python3 -m askinsects configure --url http://<vm-ip>:8080 --token "$ASK_INSECTS_TOKEN"
python3 -m askinsects health --hosted
python3 -m askinsects ingest-gbif --hosted --species "Aedes aegypti" --occurrence-limit 82237 --occurrence-page-size 300 --occurrence-workers 6 --delay-seconds 0
python3 -m askinsects ingest-inaturalist --hosted --species "Aedes aegypti" --observation-limit 10 --page-size 10 --delay-seconds 0
python3 -m askinsects ask --hosted "show mosquito observations with images in Brazil"
```

## Contract

Ask Insects answers from local indexed records. Every answer includes provenance or a clear source gap. V1 does not claim to mirror all mosquito knowledge. It proves a bounded mosquito seed source plane end to end.
