# Drosophila Suzukii Source Plane Design

Date: 2026-05-28

## Purpose

Add spotted wing drosophila, `Drosophila suzukii`, as the first explicit non-mosquito Ask Insects expansion boundary.

The goal is to replicate the Aedes source-plane pattern without pretending the species already has Aedes-level depth. The first pass should be source-grade for the core boundary and explicit about deeper gaps.

## Boundary

The source id is `drosophila_suzukii_core`.

It maps:

- GBIF taxonomy and occurrence records.
- iNaturalist licensed-photo observations.
- OpenAlex literature metadata from 2020 onward.
- BOLD DNA barcode rows when available.
- Queryable source-coverage records for completed and missing domains.

It does not yet claim complete behavior/video, NCBI genomics/SRA, crop-damage ecology, pest-management, resistance, or biocontrol coverage. Those become structured `source_coverage` gaps.

## Architecture

The implementation is a composite source module at `askinsects/sources/drosophila_suzukii.py`. It reuses the existing GBIF, iNaturalist, OpenAlex, and BOLD parsers, then retargets the records to one species-specific source id so the ingest can be added to the existing SQLite index without deleting Aedes rows from shared source ids.

The script `scripts/ingest_drosophila_suzukii.py` replaces only `drosophila_suzukii_core` records, updates `gaps.json`, `source_status.json`, and `source_receipt.json`, and leaves all existing Aedes and mosquito lanes intact.

## Query Behavior

Normal Ask Insects search, SQL, and ask flows can reach the new rows because they use the existing `records`, `records_fts`, and `record_payloads` tables. Questions containing `Drosophila suzukii`, `spotted wing drosophila`, or `spotted-wing drosophila` resolve to the scientific name in answer routing.

## Testing

Tests use fake GBIF, iNaturalist, OpenAlex, and BOLD payloads. They prove the source creates taxonomy, observation, media, literature, DNA-barcode, and source-coverage rows, that every row uses the species-specific source id, and that the ingest preserves existing fixture/Aedes rows.
