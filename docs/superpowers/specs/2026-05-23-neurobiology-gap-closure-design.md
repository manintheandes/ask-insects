# Neurobiology Gap Closure Design

## Purpose

Close the vague neurobiology source-status gaps by making raw SRA access/workflow, exact voxel reads, and public CATMAID EM metadata queryable, while keeping the unavailable whole-brain bulk-download boundary explicit.

## Source Boundary

- Raw SRA: Ask Insects indexes public SRP290992 run download paths and a reanalysis workflow. It does not claim the expensive FASTQ conversion, alignment, or count generation has been executed unless a future run writes a receipt for those outputs.
- Voxels: Ask Insects indexes MosquitoBrains MHD/MHA volume headers plus exact `voxel_access` locators. The CLI reads one coordinate value on demand from the raw local artifact instead of creating hundreds of millions of SQLite rows.
- Public EM/CATMAID: Ask Insects indexes `htem/aedes_public`, its README CATMAID locator, public CATMAID project/stack/annotation/volume metadata, and public CSV inventories.
- Whole-brain connectome: Ask Insects keeps the complete female `Aedes aegypti` whole-brain connectome bulk download as an external availability gap until a public downloadable dataset is found.

## User-Facing Behavior

- `ask-insects search neurobiology "raw SRA reanalysis"` returns raw access and workflow records.
- `ask-insects voxel <record_id> --x <x> --y <y> --z <z>` returns an exact voxel value with the source record id and coordinate.
- Connectome answers must distinguish indexed public EM/CATMAID project metadata from the not-yet-downloadable whole-brain bulk connectome.

## Completion

The completion gate must pass, the installed CLI must be rebuilt, and global `ask-insects` must answer from the new records.
