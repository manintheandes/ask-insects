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

GBIF is the first live public source lane. It is opt-in and bounded:

```bash
python3 scripts/build_source_index.py --fixtures --gbif --species "Aedes aegypti" --occurrence-limit 3
python3 -m askinsects sources
python3 -m askinsects search observations "Aedes"
```

This writes raw GBIF API responses under `artifacts/mosquito-v1/raw/gbif/`, normalizes taxonomy and occurrence records into the SQLite index, and records source receipts. Unit tests use fake GBIF responses so the completion gate stays deterministic.

## iNaturalist Source Lane

iNaturalist is the live photo and observation lane. It is opt-in and bounded:

```bash
python3 scripts/build_source_index.py --fixtures --inat --species "Aedes aegypti" --place Brazil --observation-limit 10
python3 -m askinsects sources
python3 -m askinsects ask "show mosquito observations with images in Brazil"
```

This writes raw iNaturalist API responses under `artifacts/mosquito-v1/raw/inaturalist/`, normalizes observation and still-image media records into the SQLite index, stores the raw per-record payloads in SQLite, and records source receipts. Unit tests use fake iNaturalist responses so the completion gate stays deterministic.

For a deeper `Aedes aegypti` ingest, use paginated API pulls with an explicit cap and delay:

```bash
python3 scripts/build_source_index.py --fixtures --inat --species "Aedes aegypti" --observation-limit 5758 --page-size 200 --delay-seconds 1
```

This saves each raw API page separately and records the page size, delay, and total iNaturalist results in the receipt.

SQLite keeps these layers:

- `records`: normalized Ask Insects evidence rows for answers, search, and provenance.
- `record_payloads`: raw per-record source payloads, keyed by `record_id`, for deeper source inspection.
- `literature_fulltext_units`: legal open full-text chunks for literature records when Unpaywall exposes a direct open text or PDF URL that Ask Insects can parse.

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

## Contract

Ask Insects answers from local indexed records. Every answer includes provenance or a clear source gap. V1 does not claim to mirror all mosquito knowledge. It proves bounded source planes end to end.
