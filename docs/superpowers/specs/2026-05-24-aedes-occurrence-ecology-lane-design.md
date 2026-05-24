# Aedes Occurrence Ecology Lane Design

## Goal

Make `Aedes aegypti` range, country, month, seasonality, and public habitat signals queryable as source-grade ecology records instead of relying only on literature facets.

## Source Contract

- Source id: `aedes_occurrence_ecology`
- Lane: `ecology`
- Inputs: indexed `observations` records and payloads from `gbif_api`, `inaturalist_api`, and `mosquito_alert_gbif`
- Query plane: `indexed_observation_payloads_to_sqlite_ecology_records`
- Output records:
  - country summaries
  - country-month summaries
  - iNaturalist habitat-field summaries when public habitat fields exist

Each derived record keeps sample input record IDs, source counts, coordinate counts, date range, bounding box when coordinates exist, and provenance locator back to the SQLite observation payload set.

## Boundaries

This lane is an observation-derived ecology layer. It does not claim climate rasters, land-use rasters, mechanistic suitability models, or surveillance completeness. Those remain required next sources.
