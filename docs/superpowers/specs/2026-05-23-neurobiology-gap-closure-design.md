# Neurobiology Gap Closure Design

## Purpose

Close the vague neurobiology expansion gaps by making two source families queryable and one unavailable source boundary explicit.

## Source Boundary

- Raw SRA: Ask Insects indexes public SRP290992 run download paths and a reanalysis workflow. It does not claim the expensive FASTQ conversion, alignment, or count generation has been executed unless a future run writes a receipt for those outputs.
- Voxels: Ask Insects indexes MosquitoBrains MHD/MHA volume headers plus exact `voxel_access` locators. The CLI reads one coordinate value on demand from the raw local artifact instead of creating hundreds of millions of SQLite rows.
- Whole-brain connectome: Ask Insects keeps the complete female `Aedes aegypti` whole-brain connectome as an external availability gap until a public downloadable dataset is found. Public partial EM/CATMAID data remains indexed through `htem/aedes_public`.

## User-Facing Behavior

- `ask-insects search neurobiology "raw SRA reanalysis"` returns raw access and workflow records.
- `ask-insects voxel <record_id> --x <x> --y <y> --z <z>` returns an exact voxel value with the source record id and coordinate.
- Connectome answers must distinguish partial public EM/CATMAID data from the not-yet-downloadable whole-brain connectome.

## Completion

The completion gate must pass, the installed CLI must be rebuilt, and global `ask-insects` must answer from the new records.
