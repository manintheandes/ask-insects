# Source Adapter Runner Exceptions

These lanes intentionally do NOT use `run_source_ingest`. They maintain bespoke persistence because a run that produces only gap records is a legitimate finding, and the generic runner treats gap-only output as failure and drops the gaps.

## Lanes

**drosophila_suzukii_ncbi_snp_variation** — SNP variation data is sparse for this species; a run returning only gaps (no known variants) is a valid scientific result, not an ingest failure.

**ncbi_snp_variation** — Same reason as drosophila_suzukii_ncbi_snp_variation; sparse SNP coverage for non-model organisms routinely produces gap-only runs.

**drosophila_suzukii_dryad_table_rows** — Dryad table availability depends on upstream deposit state; a gap-only result indicates no accessible rows at query time, which is a reportable finding the generic runner would drop.

**figshare_aedes_videos** — Video asset availability on Figshare varies by embargo and deposit status; gap-only results are valid absence-of-evidence records.

**zenodo_aedes_videos** — Same as figshare_aedes_videos; Zenodo deposit coverage is intermittent and gap-only runs record real absence.

**video_atoms** (source_id: aedes_video_atoms) — Atom-level video records are derived from upstream video lanes; a gap-only run correctly records that no atoms could be derived from available deposits.

**drosophila_suzukii_video_atoms** — Same as video_atoms; gap-only is the expected result when no source videos are available for atomization.

**drosophila_suzukii_biocontrol_outcome_rows** — Derived lane that emits a source_gap EvidenceRecord when no extracted biocontrol fact records pass agent/outcome-context validation; gap-only is a valid scientific finding (no qualifying biocontrol evidence in the indexed literature), not an ingest failure.

**drosophila_suzukii_susceptibility_assay_rows** — Derived lane that emits a source_gap EvidenceRecord when no extracted resistance fact records pass insecticide/metric validation; gap-only is a valid scientific finding (no qualifying susceptibility assay data in the indexed literature), not an ingest failure.

**drosophila_suzukii_literature_fulltext** — Delegates entirely to run_enrichment (scripts/enrich_literature_index.py); does not use the fetch-records/EvidenceRecord/gaps pattern and has no result.records or result.gaps to pass to run_source_ingest.

**observation_climate** (source_id: aedes_observation_climate_join) — Adapter folds gap EvidenceRecords (record_id contains `:gap:`) directly into result.records; a run where all indexed observations lack coordinates emits only a gap record as the valid scientific finding (no coordinate data available for climate join), which the generic runner would treat as refresh failure and discard.

**harvard_dataverse_aedes_suitability** — search-finds-no-rasters emits only a gap EvidenceRecord (valid finding); generic runner would drop it.

**mosquito_repellent_external_discovery** — Adapter unconditionally folds gap EvidenceRecords (record_id contains `:gap:`) for persistent access gaps (patents/CABI/bioRxiv) into result.records on every run. A run where no external candidates are discovered produces only gap EvidenceRecords; the generic runner would treat that as refresh failure and discard them.

**resistance_table_rows** (source_id: aedes_resistance_table_rows) — Derived lane that emits a source_gap EvidenceRecord with `record_id` containing `:gap:` into result.records when no extracted resistance fact records pass insecticide/metric/assay schema validation. Gap-only is a valid scientific finding (no qualifying resistance table data in the indexed literature), not an ingest failure; the generic runner would treat it as refresh failure and drop the gap.

**source_coverage** (source_id: aedes_source_coverage) — Derived lane that reads the coverage ledger and always produces records; it has no fetch step, no fetch-failure mode, and no gaps list. There is nothing for the runner's gap-guard to protect. The lane uses `index.replace_source_records` directly and requires no migration.

**neurobiology_sources** — Standalone binary-download script; does not use the EvidenceRecord / SourceIndex / result.records / result.gaps pattern at all. There is no fetch-records / gaps structure to pass to run_source_ingest.

**drosophila_suzukii_neurobiology_sources** — Gap-capable lane: SWD brain/chemosensory data is genuinely sparse, so a run where NCBI GEO returns zero datasets produces only domain-absence `source_gap` records (whole-brain atlas, connectome, single-nucleus brain RNA-seq, antennal-lobe map). That gap-only result is a valid scientific finding, not an ingest failure. The ingest script keeps `run_source_ingest` (which persists the gaps) but computes `ok` from the absence of a `*_failed` fetch gap, so a genuine search-returns-nothing run reports success while a real fetch error still reports failure.

**drosophila_suzukii_traits** — Gap-capable lane: a run where PubMed returns no SWD trait papers produces only trait-class absence `source_gap` records (development, fecundity, longevity, thermal tolerance, diapause/overwintering, cold hardiness), a valid scientific finding. Same `ok`-from-absence-of-`*_failed`-gap handling as drosophila_suzukii_neurobiology_sources.

**drosophila_suzukii_chemoreceptors** — Gap-capable lane: a run where NCBI Gene returns no chemosensory receptors produces only receptor-family absence `source_gap` records (odorant/ionotropic/gustatory), a valid finding. Same ok-from-absence-of-`*_failed`-gap handling as drosophila_suzukii_neurobiology_sources. Records land in the neurobiology lane as the sensory/receptor layer.
