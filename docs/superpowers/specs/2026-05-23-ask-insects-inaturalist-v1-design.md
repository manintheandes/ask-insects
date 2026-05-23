# Ask Insects iNaturalist V1 Design

## Purpose

iNaturalist V1 adds inspectable real-world mosquito photos to Ask Insects.

GBIF tells Ask Insects which taxa exist and where records have been indexed. iNaturalist adds observation records with human-submitted photos, licenses, dates, places, and observation URLs.

## Source Boundary

iNaturalist is an opt-in live source lane for observations and media.

Ask Insects will use the public observations API:

```text
https://api.inaturalist.org/v1/observations
```

V1 will fetch bounded pages only. It will not authenticate, identify images, sync all iNaturalist data, or download image files. It stores image URLs and raw API JSON.

## Query Shape

The build command will accept:

```bash
python3 scripts/build_source_index.py --fixtures --inat --species "Aedes aegypti" --place Brazil --observation-limit 10
```

The source loader sends public API parameters for taxon name, place query when available, photo presence, license preference, and per-page limit. The default is one mosquito species and a small limit so local runs stay fast.

## Data Flow

The iNaturalist source loader fetches raw JSON and saves it under:

```text
artifacts/mosquito-v1/raw/inaturalist/
```

Each observation with a usable photo becomes:

- an `observations` record for the observation itself
- a `media` record for the first usable photo

Both records include source id `inaturalist_api`, observation URL, image URL when available, license, date, location text, taxon name, and a raw-response locator.

## Gaps

If iNaturalist returns no observations, Ask Insects records an observation source gap.

If observations exist but no usable photos are present, Ask Insects records a media source gap. It must not pretend the photo lane is covered.

## CLI Behavior

Users do not need a separate query command. After a build with `--inat`, existing commands should work:

```bash
python3 -m askinsects sources
python3 -m askinsects search observations "Brazil"
python3 -m askinsects ask "show mosquito observations with images in Brazil"
```

The media answer should use real `media` lane records when present. The old video source gap still remains true for moving-image requests.

## Testing

Unit tests use fake iNaturalist responses and never require the live service.

The completion gate proves the deterministic fixture path and mocked iNaturalist normalization. A live iNaturalist smoke check is allowed after deterministic verification, but live results are not required for completion.

## References

- iNaturalist API: `https://www.inaturalist.org/api`
- iNaturalist v2 docs landing page: `https://api.inaturalist.org/v2/docs/`
