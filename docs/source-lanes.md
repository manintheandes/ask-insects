# Source Lanes

V1 covers mosquitoes first.

The comprehensive-source push is Aedes-first: Ask Insects should become the most comprehensive `Aedes aegypti` intelligence system in the world. Other mosquitoes can remain comparison records, but Aedes is the completion boundary for this push. The coverage ledger lives at `config/mosquito-intelligence-coverage.json` and tracks required domains, gate status, next source candidates, and completion evidence.

## Taxonomy

Scientific names, common labels, synonyms, rank, family, genus, and species.

Sources:

- `mosquito_v1_fixtures`: deterministic repo seed records.
- `gbif_api`: live GBIF species match records when explicitly fetched. Hosted deep refreshes are currently focused on `Aedes aegypti`.

## Observations And Images

Observation records with date, region, source URL, media URL, and license when available. Live source lanes also store raw per-record payloads in SQLite so the original API fields remain queryable.

Sources:

- `mosquito_v1_fixtures`: deterministic repo seed records.
- `gbif_api`: GBIF occurrence search records when explicitly fetched. The hosted deep ingest paginates the current `Aedes aegypti` GBIF occurrence set and refreshes only `gbif_api` rows, preserving other hosted lanes.
- `inaturalist_api`: bounded iNaturalist observations with licensed photos when explicitly fetched. Local and hosted incremental ingests refresh only `inaturalist_api` rows, preserving literature, genomics, neurobiology, BOLD, and derived facet lanes.

## Videos And Media

Public moving-image or inspectable media records. V1 reports missing video coverage honestly.

Sources:

- `inaturalist_api`: still-image media URLs from iNaturalist observation photos.
- `pmc_open_access_videos`: curated public PMC article supplementary videos for Aedes behavior, biting, host-seeking, threat avoidance, and photopreference studies.

Moving-image video coverage is now source-grade for the bounded PMC supplementary-video seed set. It is not comprehensive yet; larger Dryad, OSF, Mendeley, and challenge-video datasets remain follow-on work.
Deep iNaturalist ingest paginates the public API and saves one raw page artifact per request. Each normalized iNaturalist observation and media row also gets a matching `record_payloads` row with the raw observation and photo payload.
The PMC video ingest saves one raw article HTML artifact per article, extracts downloadable video links, stores video records in `media`, stores the raw article/video payload per record, and keeps provenance locators pointing back to the saved HTML.

## Hosted Boundary

Hosted Ask Insects uses the same source lanes. The difference is location: parsed artifacts live on the Google VM under `/home/josh/ask-insects/artifacts/mosquito-v1/`, and the local CLI asks the hosted API to ingest or query those artifacts.

Hosted GBIF and iNaturalist ingests stage a copy of the active artifact directory, fetch into the staging copy, replace only the matching source rows in SQLite, write receipts, and activate the staged directory only after the refresh succeeds. This keeps the old server database readable during long pulls.

## Genomics

Genome assembly metadata, GFF annotation features, gene rows, transcript rows, and protein FASTA headers.

Sources:

- `ncbi_datasets_genome`: parsed NCBI Datasets package for `Aedes aegypti` assembly `GCF_002204515.2`.

The genomics lane indexes useful atoms, not every DNA base. Raw NCBI package files remain the source artifacts. SQLite rows cite locators such as `assembly_data_report.jsonl#line/1`, `genomic.gff#line/42`, or `protein.faa#protein/XP_001`.

Current genomics lanes:

- `genome_assemblies`
- `genes`
- `transcripts`
- `genome_features`
- `proteins`
- `dna_barcodes`

## DNA Barcodes

Public BOLD barcode records for `Aedes aegypti` specimen and marker evidence.

Sources:

- `bold_api`: bounded BOLD public combined TSV records fetched with `scripts/ingest_bold_barcodes.py`.

The barcode lane indexes BOLD process IDs as `dna_barcodes` records with marker code, country/province, collection date, BIN URI, GenBank accession, sequence length, and provenance to the saved TSV row. It is a bounded ingest: if BOLD returns more rows than the configured cap, Ask Insects records a `bold_limit_applied` gap instead of pretending the lane is complete.
When BOLD blocks the runtime IP, the same ingest script accepts `--tsv-path` so a saved public combined TSV can be parsed, copied into `raw/bold/`, receipted, and exposed through the same SQLite rows.

## Neurobiology

Brain atlas, neuroanatomy, brain single-nucleus RNA-seq, cell atlas package artifacts, and sensory-neuron study metadata for `Aedes aegypti`.

Sources:

- `aedes_neurobiology_sources`: source records for mosquitobrains.org, GEO `GSE160740`, SRA `SRP290992` runinfo, the Mosquito Cell Atlas Zenodo record and file package, public Aedes EM/CATMAID repository, CATMAID API metadata including skeleton export metadata, and selected open neurobiology studies.

Current neurobiology lane:

- `neurobiology`

The artifact cache lives at `~/.local/share/ask-insects/sources/neurobiology` by default and is populated with `scripts/ingest_neurobiology_sources.py`. When the cache is supplied to `scripts/build_source_index.py --neurobiology --neurobiology-artifact-dir`, SQLite indexes GEO matrix summaries and feature rows, SRA run and sample metadata, raw SRA access and reanalysis workflow records, Zenodo files and ZIP members, H5AD internal AnnData groups/datasets/obs/var columns, workbook sheets, MosquitoBrains download links/files/ZIP members, MHD/MHA volume headers, coordinate-queryable voxel access locators, ITK-SNAP region labels, public Aedes EM/CATMAID project, stack, annotation, volume, skeleton-manifest, skeleton-filter, and skeleton-ID metadata, public Aedes EM/CATMAID CSV inventories, and an explicit whole-brain connectome source-gap row. Exact voxel values are read on demand with `ask-insects voxel <record_id> --x <x> --y <y> --z <z>` so the index does not need one row per voxel. The source index does not claim compute-heavy raw SRA alignment/count outputs have already been executed. The public CATMAID skeleton export surface is covered, but a future Wellcome complete whole-brain connectome bulk package remains an explicit external availability gap.

## Papers And Literature

Paper metadata, abstracts when available, open access URLs, and source identifiers.

Sources:

- `mosquito_v1_fixtures`: deterministic repo seed records.
- `aedes_literature_openalex`: OpenAlex articles from 2020-01-01 through run date where `Aedes aegypti` is material in title, abstract, or accepted topic metadata.

OpenAlex is the canonical source for discovery and record identity. PubMed E-utilities are enrichment only, used for PMID-backed metadata. Unpaywall is enrichment only, used as the legal open full-text resolver. The lane may write legal direct PDF/XML/text chunks to `literature_fulltext_units`, but it must not use Sci-Hub, private cookies, or institutional scraping.

Legal full-text chunks are an atomic query plane. `search fulltext` reads `literature_fulltext_fts`, returns `literature_fulltext` evidence with provenance to the full-text unit, and literature answers fall back to those chunks when title/abstract metadata does not satisfy the question.

The canonical artifact directory is `artifacts/aedes-literature-2020/`. It contains the SQLite index, raw OpenAlex cursor JSON artifacts, `source_status.json`, `source_receipt.json`, `literature_enrichment_receipt.json`, and `gaps.json`. PubMed and Unpaywall enrichment payloads are preserved in the SQLite `record_payloads` table rather than duplicated as separate raw JSON files.

Structured literature gaps include:

- `missing_doi`
- `pubmed_missing_pmid`
- `pubmed_fetch_failed`
- `openalex_missing_abstract`
- `openalex_topic_search_empty`
- `openalex_topic_candidate_rejected`
- `unpaywall_fetch_failed`
- `unpaywall_no_fulltext_url`
- `fulltext_landing_page_only`
- `fulltext_fetch_failed`
- `fulltext_parse_failed`

## Literature-Derived Intelligence Facets

Behavior, vector competence, resistance, ecology, and public-health records can be derived from source-grade literature records and legal full-text units with:

```bash
python3 scripts/build_literature_facets.py --artifact-dir artifacts/aedes-literature-2020
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 search resistance "pyrethroid"
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 ask "what vector competence data exists for dengue?" --json
```

This lane is source `aedes_literature_facets`. It does not replace dedicated behavior, resistance, vector-competence, ecology, or public-health databases. It creates an immediate source-backed query plane from the indexed Aedes literature while those deeper external lanes are built.

## Insecticide Resistance

Insecticide susceptibility, resistance phenotype, mechanism, mutation, assay protocol, geography, time, and reference records for `Aedes aegypti`.

Sources:

- `irmapper_aedes`: live IR Mapper Aedes JSON endpoint, filtered by default to `Aedes aegypti` and `Ae. aegypti`.
- `aedes_literature_facets`: literature-derived resistance facets while deeper source lanes are built.

The IR Mapper lane indexes one SQLite `resistance` row per matching public API row, stores the raw IR Mapper row in `record_payloads`, and cites a provenance locator such as `raw/irmapper/Aedes_aegypti.json#row/1`. It preserves source fields for country, locality, coordinates, collection year, developmental stage, test method, insecticide class, insecticide, dosage, mode of action, mortality, resistance status, mechanism, mutation frequency, reference, and source URL when present.

## Action Notes

Source-backed next steps for scientists, grounded in indexed observations and literature.

GBIF V1 does not create action notes by itself. It strengthens the observation and taxonomy evidence that action answers can cite.

iNaturalist V1 does not create action notes by itself. It strengthens photo-backed observation evidence that action answers can cite.
