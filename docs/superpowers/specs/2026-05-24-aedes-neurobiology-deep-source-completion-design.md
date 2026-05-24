# Aedes Neurobiology Deep Source Completion Design

## Purpose

Finish the parts of the Aedes aegypti neurobiology lane that were still only file-level or gap-level. The lane should expose useful internal source atoms from H5AD/AnnData files, SRA run metadata, MosquitoBrains brain-volume files, and the public Aedes EM/CATMAID connectome-adjacent repository. The full whole-brain connectome remains a future-publication gap unless a public downloadable dataset is found.

## Source Boundaries

- H5AD: downloaded Zenodo `04_H5ADs.zip` members. Parse HDF5 group structure, AnnData matrix shape, `obs` count, `var` count, named `obs` and `var` columns, categorical levels when available, and raw dataset/group inventory. Do not materialize every expression value into SQLite.
- SRA: public runinfo for `SRP290992`, linked from GEO `GSE160740`. Store each SRA run, experiment, BioSample, GSM sample, library layout, spot/base counts, size, and download path. Do not download raw reads in this pass because SRA toolkit is not installed and the run files total tens of GB.
- MosquitoBrains volumes: downloaded reference and segmentation ZIPs. Parse nested ZIPs, MHD/MHA headers, voxel dimensions, spacing, element type, byte order, and ITK-SNAP label files. Do not index every voxel value.
- Connectome: ingest the public `htem/aedes_public` repository metadata, README CATMAID locator, public CATMAID project/stack/annotation/volume API metadata, and CSV inventories for the partial Aedes EM/CO2 circuit dataset. Keep a narrower whole-brain connectome gap record for the Wellcome project because the source says the whole-brain dataset will be made publicly available, not that it is downloadable now.

## Records

All records stay in the existing `neurobiology` lane and `aedes_neurobiology_sources` source id.

New record types:

- `h5ad_summary`
- `h5ad_group`
- `h5ad_dataset`
- `h5ad_obs_column`
- `h5ad_var_column`
- `sra_run`
- `sra_sample_summary`
- `brain_volume_header`
- `brain_region_label`
- `connectome_repository`
- `connectome_repository_readme`
- `catmaid_project`
- `catmaid_stack`
- `catmaid_annotation`
- `catmaid_volume`
- `connectome_csv`

Every record must include a locator that points to the exact archive/member/group/dataset/row source.

## Query Behavior

Questions containing H5AD, AnnData, cell types, cell atlas, SRA, raw reads, reanalysis, MHA, MHD, voxel, volume, segmentation, CATMAID, EM dataset, CO2 circuit, or connectome should route to neurobiology before generic taxonomy/literature.

## Completion

The local and installed `ask-insects` command must answer from the deeper records. The completion gate must keep passing. The remaining gap must be specific: a complete public whole-brain Aedes aegypti connectome download is not mapped yet.
