# Elicit Discovery Source Receipt

Two source-grade lanes that use Elicit (semantic search over 138M+ papers) to
discover papers not already in the hosted Ask Insects corpus.

- `drosophila_suzukii_elicit_discovery`
- `aedes_aegypti_elicit_discovery`

## Boundary

Bounded Elicit semantic-search discovery of candidate papers (repellency,
behavior, olfaction focus, 2020 onward) per species that are **not already in
the hosted corpus**. Records are stored in the `literature` lane as
`elicit_search_candidate` confidence-band records. This is a discovery band, not
a canonical/exact lane and not a paper-depth lane.

## Endpoint and credentials

- `POST https://elicit.com/api/v1/search`, `Authorization: Bearer <key>`.
- Pro plan required (API access). Pro limits: 100 searches/day, 100 results/req.
- Key is read from `ELICIT_API_KEY` or `~/.config/elicit/api_key` (mode 600).
  **The key is never committed to the repo.**

## Discovery queries (focused / moat-first)

SWD: repellent/oviposition-deterrent behavior; olfactory-receptor response to
volatiles; antennal electrophysiology semiochemical.
Aedes: spatial repellent behavioral response; odorant-receptor host-seeking
olfaction; repellent/DEET-alternative efficacy assay.

Each accepted record preserves which query found it (`payload.discovery`).

## Dedup (against hosted)

For each Elicit result DOI, an exact batched lookup runs against the hosted
plane (`ask-insects sql "select url from records where url in (...)"`, 200 DOIs
per batch). Full-table scans time out and are forbidden; exact `IN` is indexed
(<1s). Only DOIs absent from hosted are kept. Within-harvest duplicates collapse
to one record. Papers with no DOI are kept and flagged `no_doi`.

## Provenance grain

One `records` row per new paper (`record_id = <source_id>:<doi|elicitId|title>`),
DOI in `records.url`, structured fields in `record_payloads.payload_json`:
`doi, pmid, elicit_id, year, venue, authors, cited_by_count, abstract,
confidence_band=elicit_search_candidate, depth_outcome=supplement_discovery_not_run,
discovery{query, all_queries, search_mode, corpus, min_year, species}`.

## Depth outcome

Per the `insectsource` paper-completeness contract, each Elicit paper carries a
queryable depth outcome of `supplement_discovery_not_run`. After promoting these
papers, rerun the SWD/Aedes extracted-facts or full-text lanes to give each new
paper a real depth outcome before calling paper coverage complete.

## Safety / freshness

Bounded, opt-in, Pro-API-key fetch. Each query response is raw-saved under
`artifacts/mosquito-v1/raw/<source_id>/`. If every Elicit fetch fails, existing
rows are preserved and the receipt records `refresh_failed: true` (no partial
swap). Not on an automated cron; run on demand.

## Hosted promotion gate

Build and verify locally first. The new-paper list and dry-run counts are shown
to Josh; **records are promoted to the hosted plane only after Josh approves.**
After promotion, verify from outside with
`ask-insects ask --hosted "..." ` against each source.
