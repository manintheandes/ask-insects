# Aedes NCVBDC Dengue Surveillance Lane Design

## Intent

Make official India NCVBDC dengue cases and deaths source-grade for Ask Insects, focused on `Aedes aegypti` public-health intelligence.

## Boundary

Source id: `aedes_ncvbdc_dengue_surveillance`.

The lane covers the public Government of India NCVBDC dengue situation HTML table. It indexes human dengue surveillance as Aedes-relevant public-health evidence, not as mosquito occurrence or abundance evidence.

## Atomic Records

- One source-page record with raw HTML provenance.
- One `public_health` record per state or union territory and year.
- One `public_health` record per national India total and year.
- One `public_health` summary record for the latest two complete calendar years in the table.

## Exclusions

- No district-level India dengue rows unless NCVBDC exposes a stable source that can be fetched and parsed.
- No line-listed case or death data.
- No inference that human dengue cases are mosquito observations.
- Provisional current-year values remain marked provisional and are excluded from the latest-two-complete-years summary.

## Proof

The lane is complete when `python3 -m askinsects ingest-ncvbdc-dengue-surveillance`, `python3 -m askinsects ask "what were dengue deaths in India over the last two years as a result of Aedes?" --json`, and `python3 scripts/verify_complete.py` all pass.
