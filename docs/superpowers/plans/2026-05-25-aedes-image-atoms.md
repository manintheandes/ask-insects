# Aedes Image Atoms

Date: 2026-05-25

## Goal

Promote Aedes aegypti still-image coverage from raw media records into queryable image assets, deterministic source-provided labels, and structured label gaps.

## Source Contract

The derived source is `aedes_image_atoms`.

Inputs:

- `inaturalist_api` media records and payloads.
- `mosquito_alert_gbif` media records and payloads.

Outputs:

- `image_asset` records with image URL, source observation, license, retrieved time, place/date, attribution, quality grade, coordinates, and exact upstream locator when available.
- `image_label` records for deterministic source metadata such as iNaturalist quality grade, iNaturalist annotations, Mosquito Alert life stage, occurrence status, media format, media type, and basis of record.
- `image_gap` records for missing source-provided life stage, sex, anatomy, or body-part labels.

No model vision claims are made in this pass. Labels are source metadata only.

## Implementation Steps

1. Add `askinsects/sources/image_atoms.py`.
2. Add `scripts/ingest_image_atoms.py`.
3. Add CLI and hosted server ingest wiring.
4. Prefer `aedes_image_atoms` for image, photo, quality, life-stage, sex, anatomy, and body-part image questions.
5. Document the lane in source map, source-lanes docs, querying docs, README, and the coverage ledger.
6. Add verifier coverage for source-map terms and installed image-atom artifact consistency.
7. Deploy and refresh hosted Ask Insects.

## Verification

Run:

```bash
python3 -m unittest tests.test_image_atoms_source tests.test_ingest_image_atoms tests.test_answer tests.test_cli_hosted tests.test_server tests.test_verify_complete -v
python3 -m unittest discover -s tests -v
python3 scripts/verify_complete.py
python3 -m askinsects ingest-image-atoms --hosted
python3 -m askinsects ask --hosted "show Aedes aegypti adult image labels" --json
```
