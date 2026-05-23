# iNaturalist Deep Aedes Ingest Design

## Purpose

Deep ingest lets Ask Insects pull a large public iNaturalist observation set for one species without scraping website HTML.

The first target is public, photo-backed `Aedes aegypti` observations. The source lane should fetch all results up to an explicit cap, save every raw API page, normalize observations and still-image media, and keep a receipt that makes the run auditable.

## Boundaries

This is an API ingest, not a website scrape.

V1 uses:

```text
https://api.inaturalist.org/v1/observations
```

It fetches public observation records returned by the API with `photos=true` and `photo_licensed=true`. It does not download image bytes, fetch private data, scrape HTML pages, authenticate, or pull comments and identifications.

## Polite Fetching

The default deep run uses:

- `per_page=200`
- `delay_seconds=1`
- an explicit observation cap
- one source species per run

This follows iNaturalist's recommended API shape: use the API, use high page sizes for larger fetches, avoid unfiltered bulk downloads, and keep request rate around one request per second.

## CLI Shape

The command becomes:

```bash
python3 scripts/build_source_index.py \
  --fixtures \
  --inat \
  --species "Aedes aegypti" \
  --observation-limit 5758 \
  --page-size 200 \
  --delay-seconds 1
```

`--observation-limit` means the maximum number of iNaturalist observations to index for each species. `--page-size` controls API page size. `--delay-seconds` controls the pause between live API page requests.

## Raw Artifacts

Each API page is saved separately:

```text
artifacts/mosquito-v1/raw/inaturalist/Aedes_aegypti_anywhere_page_001.json
artifacts/mosquito-v1/raw/inaturalist/Aedes_aegypti_anywhere_page_002.json
```

The receipt records requested species, place, observation limit, page size, delay, total results reported by iNaturalist, raw page paths, normalized record counts, and gaps.

## Dedupe And Gaps

The source loader dedupes observations by iNaturalist observation id and photos by iNaturalist photo id.

If a page has observations without usable photos, those observations are skipped and a media gap is recorded. If there are no observations for a query, an observation gap is recorded.

## Completion

Unit tests use fake paginated responses. The completion gate remains deterministic and does not call the live iNaturalist API.

The full live ingest is run manually after deterministic verification. It is allowed to take tens of seconds because it is a source refresh, not a normal answer path.
