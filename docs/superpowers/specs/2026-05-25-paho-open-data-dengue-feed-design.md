# PAHO Open Data Dengue Feed Design

## Goal

Promote PAHO dengue surveillance from dashboard locator evidence to a proven
machine-readable feed wherever PAHO publishes one.

## Source Boundary

The source is PAHO/EIH Open Data Core Indicators:

- download page: `https://opendata.paho.org/en/core-indicators/download-dataset`
- released ZIP linked from that page, currently
  `paho-core-indicators-2026-20260413.zip`

The ZIP contains a CSV with PAHO annual country/territory Core Indicator rows.
Ask Insects indexes rows where `indicator_name` is `Dengue cases`.

## Records

- `public_health`: one record per PAHO Core Indicators dengue case row.

Each record preserves country/territory code, country/territory name, year,
numeric value, PAHO indicator id, source URL, publication date, accessed date,
download page, ZIP URL, raw ZIP path, CSV member name, and row number.

## Remaining Gap

This closes a stable machine-readable annual country/territory feed. It does
not prove country-week PAHO/PLISA dashboard cells. Weekly dashboard cells remain
a source gap until a stable weekly CSV, JSON, API, or authorized endpoint is
proven.

## Completion Evidence

- Unit tests prove ZIP discovery and dengue-row parsing.
- Ingest tests prove records are added without removing other source rows.
- Docs and source map distinguish annual Core Indicator rows from weekly
dashboard cells.
- Hosted query proof returns a `paho_core_indicator_dengue_cases` record.
