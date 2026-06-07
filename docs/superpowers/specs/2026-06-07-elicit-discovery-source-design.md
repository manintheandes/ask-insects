# Elicit Discovery Source Design

## Goal

Use Elicit (semantic search over 138M+ papers) to discover papers that Ask
Insects does not already have, for `Drosophila suzukii` (SWD) and
`Aedes aegypti`, and onboard them as source-grade lanes that pass the
`insectsource` Four Gates.

## Boundary

Two new sources, one per species boundary (the repo keeps SWD and Aedes
separate; do not fold them together):

- `drosophila_suzukii_elicit_discovery`
- `aedes_aegypti_elicit_discovery`

Each is a bounded, Elicit-API literature-discovery lane that records **only
papers not already in the hosted corpus**, as a candidate confidence band. It
does NOT claim canonical/exact status, scrape paywalled full text, or assert
paper-depth coverage. Depth (full text, supplement audit, parsed facts) is a
downstream lane and is recorded here as an explicit, queryable gap.

## What this is NOT

- Not a replacement for the OpenAlex/PubMed/Crossref lanes; it is an additional
  discovery band.
- Not an automated nightly cron source. Elicit needs a Pro API key; fetches are
  bounded and run on demand, key kept at the edge (`~/.config/elicit/api_key`,
  never committed).
- Not a paper-depth lane. New papers carry a `supplement_discovery_not_run`
  depth outcome until the extracted-facts/full-text lanes are rerun.

## Source of credentials

Elicit Pro API key at `~/.config/elicit/api_key` (mode 600).
`POST https://elicit.com/api/v1/search`, `Authorization: Bearer <key>`.
Pro limits: 100 searches/day, 100 results/request. Errors handled: 401 (bad
key), 402 (quota), 403 (plan), 429 (rate limit) -> recorded as gaps, not crashes.

## Records

Lane: `literature`. One `records` row per new paper. Provenance preserves:

- `source_id` (the species elicit source), `doi` (also stored in `records.url`
  when present), `pmid`, `elicitId`, `title`, `authors`, `year`, `venue`,
  `citedByCount`, `abstract`.
- `discovery`: the exact Elicit query string, `searchMode`, `corpus`,
  `minYear`, and which species boundary.
- `confidence_band`: `elicit_search_candidate`.
- `depth_outcome`: `supplement_discovery_not_run` (queryable gap atom).
- `raw_locator`: path into the saved raw Elicit response JSON.

Raw responses saved under
`artifacts/mosquito-v1/raw/<source_id>/<query-slug>.json` and receipted.

## Discovery terms (focused / moat-first, 2020+)

SWD and Aedes each get a small set of targeted queries on the repellency /
behavior / olfaction moat (e.g. repellents and oviposition deterrents,
olfactory/odorant receptor behavioral response, antennal electrophysiology,
spatial/topical repellent efficacy). Each accepted record preserves which query
found it. Broad-sweep expansion is a later, separate change.

## Dedup (against hosted, not local)

The hosted plane is the corpus of record; local artifact DBs are stale fixtures.
For each Elicit result DOI, check existence on hosted via batched exact lookups
(`ask-insects sql "select url from records where url in (...)"`). Full-table
scans time out and are forbidden. Keep only DOIs absent from hosted. Also dedup
within the harvest (same DOI from multiple queries -> one record). Papers with no
DOI are kept but flagged `no_doi_dedup_by_title` (normalized-title dedup).

## Data flow

1. `askinsects/sources/elicit_discovery.py` exposes
   `fetch_elicit_discovery_records(species, queries, fetch_json=..., existing_doi_lookup=...)`.
   `fetch_json` and `existing_doi_lookup` are dependency-injected so tests never
   hit the network or the hosted plane.
2. `scripts/ingest_drosophila_suzukii_elicit_discovery.py` and
   `scripts/ingest_aedes_aegypti_elicit_discovery.py` call the fetcher, dedup
   against hosted, and write records via `replace_source_records(source_id, ...)`.
3. Safety contract (same as `mosquito_repellent_external_discovery`): if every
   Elicit fetch fails, existing rows are preserved and the receipt records the
   failed refresh. Only the source's own rows are replaced on success.
4. Update `source_status.json`, `source_receipt.json`, `gaps.json`.

## Four Gates (acceptance)

1. **Mapped:** both sources declared in `config/source-map.yaml` with boundary,
   ingest script, artifact dir, lanes, provenance requirement, fetch policy.
2. **Accessible:** the Elicit fetch path works with the stored key (proven by a
   real bounded fetch, receipted).
3. **Atomically queryable:** records exist with the provenance above; a
   queryable depth-outcome gap atom exists per paper.
4. **Ask-surface wired:** `python3 -m askinsects health|summary|sources|search|
   sql` reach each lane by `--source`, and `verify_complete.py` passes.

## Receipts / enforcement

Receipt fields per source: query list, requested URLs, papers returned,
new (post-dedup) count, dedup-dropped count, gap reasons/count, raw artifacts,
retrieved_at, refresh_failed. Bounded fetches saved. Failed/partial fetches are
gaps, not prose.

## Docs to update before "ready"

`README.md` (lane inventory), `docs/source-lanes.md` (boundary + exclusions),
`docs/querying-ask-insects.md` (example queries), and a per-source receipt doc
under `docs/`.

## Production gate (hosted promotion)

Build and verify LOCALLY first. Then present Josh the actual new-paper list and
dry-run counts. **Nothing is promoted to the hosted plane until Josh approves at
this gate.** Hosted promotion + external verification (`ask-insects ... --hosted
--source <id>`) is the final step, done only after approval.

## Verification

```bash
cd /Users/josh/projects/ask-insects
python3 -m pytest tests/test_elicit_discovery_source.py tests/test_ingest_drosophila_suzukii_elicit_discovery.py tests/test_ingest_aedes_aegypti_elicit_discovery.py -q
python3 scripts/verify_complete.py
# after local build:
python3 -m askinsects sql "select source, count(*) n from records where source like '%elicit_discovery' group by source"
# after approved hosted promotion:
ask-insects ask --hosted "What new Drosophila suzukii repellency papers did Elicit add?"
```
