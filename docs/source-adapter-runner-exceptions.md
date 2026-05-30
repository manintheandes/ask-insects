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
