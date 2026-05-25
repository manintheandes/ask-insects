# Aedes CDC Dengue Surveillance Lane Design

## Intent

Make official CDC dengue surveillance evidence source-grade for Ask Insects, focused on `Aedes aegypti` public-health intelligence.

## Boundary

Source id: `aedes_cdc_dengue_surveillance`.

The lane covers CDC dengue current-year and historic data pages, their WCMS visualization JSON configs, linked CDC CSV datasets, and ArboNET limitation text. Dengue is indexed here as Aedes-relevant public-health evidence, not as mosquito abundance.

## Atomic Records

- Page records for the CDC current and historic surveillance pages.
- Visualization config records preserving every discovered CDC CSV locator.
- One `public_health` record per CDC CSV row, with row dimensions, measures, source URL, saved CSV path, and row number.
- One `public_health` record per ArboNET limitation paragraph.

## Exclusions

- No private ArboNET data.
- No row-level claims from visualizations unless a CDC CSV row is fetched and saved.
- No inference that human dengue cases are mosquito observations.

## Proof

The lane is complete when `python3 -m askinsects ingest-cdc-dengue-surveillance`, `python3 -m askinsects ask "show CDC ArboNET dengue surveillance current cases" --json`, and `python3 scripts/verify_complete.py` all pass.
