# Aedes Aegypti GBIF Deep Hosted Ingest Design

## Purpose

Ask Insects should ingest the current GBIF `Aedes aegypti` occurrence set into the hosted server SQLite database, not into a local-only index.

The first deep GBIF target is the GBIF accepted species key `1651891`. A live GBIF count check on May 23, 2026 returned `82,237` occurrence records for `Aedes aegypti`.

## Boundary

This build covers GBIF taxonomy match data and GBIF occurrence search records for `Aedes aegypti`.

It does not claim to ingest every mosquito species, every GBIF species-adjacent endpoint, or a GBIF asynchronous download archive. Those are later source-lane expansions.

## Hosted Shape

The local CLI sends an authenticated request to the Ask Insects VM. The VM fetches GBIF pages and writes to the server artifact directory:

```text
/home/josh/ask-insects/artifacts/mosquito-v1/
```

The SQLite database remains:

```text
/home/josh/ask-insects/artifacts/mosquito-v1/source_index.sqlite
```

## Data Flow

The GBIF source adapter paginates `occurrence/search` with `taxonKey`, `limit`, and `offset`. Hosted deep refreshes use a small worker pool so GBIF pages can be fetched concurrently without changing the source boundary.

It writes raw page JSON files under `raw/gbif/`, normalizes taxonomy and occurrence rows into `records`, and stores raw GBIF match or occurrence payloads in `record_payloads`.

Hosted ingest copies the active artifact directory to staging, refreshes only `gbif_api` rows, updates receipts and status, then swaps staging into place. This preserves existing `inaturalist_api` rows and keeps the active database readable during the long fetch.

## Commands

```bash
python3 -m askinsects ingest-gbif --hosted --species "Aedes aegypti" --occurrence-limit 82237 --occurrence-page-size 300 --occurrence-workers 6 --delay-seconds 0
python3 -m askinsects sql --hosted "select source, lane, count(*) as n from records group by source, lane"
```

## Verification

Verification must prove:

- GBIF pagination works with mocked pages.
- Hosted CLI sends the GBIF ingest request with a long timeout.
- Hosted server refreshes `gbif_api` without deleting `inaturalist_api`.
- Full unit tests pass.
- `python3 scripts/verify_complete.py` passes.
- Hosted health and SQL show `gbif_api` records after deployment.
