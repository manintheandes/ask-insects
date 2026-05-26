# Source Lanes

V1 is Aedes-first. Other mosquitoes can be indexed as comparison records, but `Aedes aegypti` is the completion boundary for this push.

The comprehensive-source push is Aedes-first: Ask Insects is building toward the most comprehensive `Aedes aegypti` intelligence system in the world. Other mosquitoes can remain comparison records, but Aedes is the completion boundary for this push. The coverage ledger lives at `config/mosquito-intelligence-coverage.json` and tracks required domains, gate status, next source candidates, and completion evidence. The benchmark ledger lives at `config/aedes-source-plane-benchmark.json` and currently marks the world-largest/world-deepest claim as not proven.

## Taxonomy

Scientific names, common labels, synonyms, rank, family, genus, and species.

Sources:

- `mosquito_v1_fixtures`: deterministic repo seed records.
- `gbif_api`: live GBIF species match records when explicitly fetched. Hosted deep refreshes are currently focused on `Aedes aegypti`.
- `aedes_taxonomy_authorities`: ECDC, OECD, Mosquito Taxonomic Inventory or WRBU-style, NCBI Taxonomy, and USDA NAL authority pages or PDFs for `Aedes aegypti`, indexed at page/PDF-text grain with classification and synonym/name evidence when source text exposes it.

Taxonomy-authority rows cite saved raw HTML or mirrored PDFs under `raw/aedes_deep_sources/taxonomy_authorities/`. For protected authority pages, Ask Insects uses accessible authority PDF fallbacks when available and stores an extracted text sidecar beside the PDF. Only source families with no accessible substitute become structured `taxonomy_authority_fetch_failed` gaps.

## Observations And Images

Observation records with date, region, source URL, media URL, and license when available. Live source lanes also store raw per-record payloads in SQLite so the original API fields remain queryable.

Sources:

- `mosquito_v1_fixtures`: deterministic repo seed records.
- `gbif_api`: GBIF occurrence search records when explicitly fetched. The hosted deep ingest paginates the current `Aedes aegypti` GBIF occurrence set and refreshes only `gbif_api` rows, preserving other hosted lanes. The May 24, 2026 hosted refresh installed 82,237 occurrence records plus the taxonomy row with zero GBIF gaps.
- `inaturalist_api`: bounded iNaturalist observations with licensed photos when explicitly fetched. Local and hosted incremental ingests refresh only `inaturalist_api` rows, preserving literature, genomics, neurobiology, BOLD, and derived facet lanes.
- `mosquito_alert_gbif`: Mosquito Alert Dataset records for `Aedes aegypti`, fetched through GBIF with dataset and taxon pins, preserving expert-validated citizen-science observation fields and still-image metadata.
- `vectornet_aedes_surveillance`: official VectorNet ECDC/EFSA Darwin Core Archive rows where the source row identifies `Aedes aegypti`, preserving row-level surveillance fields and derived regional ecology summaries.
- `aedes_global_compendium_occurrence`: the Kraemer et al. global Aedes occurrence compendium from Zenodo/Dryad, filtered to `Aedes aegypti` rows and indexed with country, coordinates, year, status, source URL, and raw CSV row locator where exposed.
- `aedes_image_atoms`: derived still-image asset, source-label, and gap records from indexed iNaturalist and Mosquito Alert media rows.

The Aedes image-atoms ingest writes derived records under source `aedes_image_atoms`. Image-asset records preserve the source image record ID, source observation record ID, image URL, source URL, license, attribution or creator, rights holder, observed date or event date, place or country, coordinates when supplied, quality grade when supplied, image format when supplied, and exact upstream locator. With `--mirror-images`, the ingest also performs bounded licensed image-byte mirrors, preserving SHA-256 checksum, byte size, detected dimensions, image format, EXIF presence when detectable, and a raw asset path. Image-label records are deterministic source metadata only, such as iNaturalist quality grade and annotations or Mosquito Alert life stage, basis of record, occurrence status, media format, and media type. If source metadata does not provide life stage, sex, anatomy, or body-part labels, or if mirroring is capped, too large, license-unclear, or fails, the ingest writes queryable `image_gap` records instead of inventing labels or pretending bytes were verified.

## Videos And Media

Public moving-image or inspectable media records. V1 reports missing video coverage honestly.

Sources:

- `inaturalist_api`: still-image media URLs from iNaturalist observation photos.
- `pmc_open_access_videos`: curated public PMC article supplementary videos for Aedes behavior, biting, host-seeking, threat avoidance, and photopreference studies.
- `dryad_aedes_behavior_videos`: public Dryad dataset, version, and file manifests for Aedes host-seeking, visual-threat, flight-escape, mating/courtship, male host-attraction, and visual-tracking behavior video archives and source-data files.
- `mendeley_aedes_behavior_media`: public Mendeley Data snapshots, folders, file manifests, and parsed Aedes table rows for mate-recognition, wingbeat, hearing, flight-tone, high-speed video, and locomotory video-analysis datasets.
- `osf_flighttrackai_aedes_videos`: public OSF project `cx762` file manifests for FlightTrackAI `Aedes aegypti` flight-behavior videos, processed/unprocessed video folders, executable bundles, installation instructions, and the trained mosquito model.
- `zenodo_aedes_videos`: bounded Zenodo search/file-manifest records for materially Aedes aegypti video files plus queryable `video_gap` rows for rejected or empty search candidates, preserving download URL, source URL, license, byte size, source-provided hashes, gap reason, and exact raw-search locators.
- `figshare_aedes_videos`: bounded Figshare article-detail/file-manifest records for materially Aedes aegypti video files plus queryable `video_gap` rows for rejected, failed, or empty article candidates, preserving article ID, file ID, DOI, download URL, source URL, license, byte size, source-provided hashes, gap reason, and exact raw-detail locators.
- `aedes_video_atoms`: derived video-asset, artifact, motion-row, and discovery-gap records from indexed Aedes video sources, upstream Zenodo/Figshare manifest gaps, and repository sweeps. Repository search terms do not count as Aedes evidence; title, description, filename, citation, species, or equivalent source metadata must materially name `Aedes aegypti`. License or size gaps preserve source download URL, source URL, byte size, source-provided hashes when available, license text, dataset, repository, original source/reason when promoted from an upstream manifest gap, and locator.

Moving-image video coverage is source-grade for the bounded PMC supplementary-video seed set, Dryad file-manifest layer, Mendeley behavior/media file-manifest plus table layer, OSF FlightTrackAI project file-manifest layer, first-class Zenodo search/file-manifest layer, and first-class Figshare article-detail/file-manifest layer. It is not comprehensive yet; challenge-video datasets and deeper binary/video decoding remain follow-on work.
Deep iNaturalist ingest paginates the public API and saves one raw page artifact per request. Each normalized iNaturalist observation and media row also gets a matching `record_payloads` row with the raw observation and photo payload.
Mosquito Alert ingest saves the GBIF dataset metadata and Aedes occurrence pages under `raw/mosquito_alert/`. It creates one `observations` record per occurrence and one `media` record per still image, with occurrence-level and image-level license fields preserved separately in provenance and payloads.
VectorNet ingest saves the public IPT Darwin Core Archive, metadata XML, Darwin Core meta XML, and a filtered `Aedes aegypti` TSV under `raw/vectornet_surveillance/`. It creates one `observations` record per source row and `ecology` summary records by country and degree of establishment. Records preserve detection versus absence-surveillance status, individual count, life stage, sex, sampling protocol, event-date range, geography, identification method, CC-BY-4.0 license, and exact locators into both the archive row and filtered TSV.
The PMC video ingest saves one raw article HTML artifact per article, extracts downloadable video links, prefers direct NCBI CDN media links when the article exposes both CDN and `/articles/instance/.../bin/...` URLs, stores video records in `media`, stores the raw article/video payload per record, and keeps provenance locators pointing back to the saved HTML.
The Dryad behavior/video ingest saves one raw dataset, version, and file-manifest JSON artifact per DOI under `raw/dryad_behavior_videos/`. It indexes one `behavior` record per dataset, file-level `media` records for video/archive files, and file-level `behavior` records for README or source-data files. It preserves DOI, license, size, checksum, behavior labels, download URL, and raw manifest payloads without mirroring multi-gigabyte binary archives by default.
The Mendeley behavior/media ingest saves one raw snapshot JSON, one folder JSON, one combined folder-file manifest JSON per dataset, and public parsed table files under `raw/mendeley_behavior_media/`. It indexes one `behavior` record per dataset, one `behavior` record per folder, file-level `media` records for video, audio, or archive files, file-level `behavior` records for spreadsheet, source-data, README, and code files, parsed sheet records, and parsed table-row records. It preserves DOI, license, folder path, size, content type, SHA-256 hash, download URL, view URL, behavior labels, headers, row values, and raw locators without mirroring large binaries by default.
The OSF FlightTrackAI ingest saves the OSF project JSON, provider JSON, and recursive `osfstorage` folder/file manifests under `raw/osf_flighttrackai_videos/`. It indexes the project and folders as `behavior`, indexes MP4 files as `media`, indexes software, model, and instruction files as `behavior`, and preserves file size, OSF download URL, API locator, raw item payload, and provenance without mirroring multi-gigabyte binaries by default.
The Zenodo ingest saves bounded search JSON under `raw/zenodo_aedes_videos/`. It indexes source-material Aedes video files as `media` records and preserves Zenodo record ID, file name, download URL, source URL, license, byte size, source-provided hash, raw record/file payload, and search-result locator. It also emits source-specific `video_gap` rows for no-candidate, out-of-scope, or material-record-without-video outcomes. Search terms alone are not species evidence.
The Figshare ingest saves bounded search and article-detail JSON under `raw/figshare_aedes_videos/`. It indexes source-material Aedes video files as `media` records and preserves Figshare article ID, file ID, file name, DOI, download URL, source URL, license, byte size, source-provided hash, raw article/file payload, and article-detail locator. It also emits source-specific `video_gap` rows for no-candidate, fetch-failed, out-of-scope, or material-article-without-video outcomes. Search terms alone are not species evidence. The video-atom discovery sweep uses the broader 100-result Figshare page so more article-detail candidates become queryable asset or gap records.
The Aedes video-atoms ingest writes derived records under source `aedes_video_atoms`. Video-asset records preserve the source paper or dataset, download URL, license, exact locator, checksum, byte size, duration, fps, resolution, and codec when a bounded mirror and probe succeed. Bounded ZIP archives are mirrored, checksummed, expanded into member assets, and indexed as archive manifest/member records; huge, unsupported, unreadable, or license-unclear archives stay explicit `video_gap` records. If mirroring is too large, license status is unclear, a download URL is missing, probing fails, artifact generation fails, a discovery candidate is out of Aedes scope, a repository sweep has no candidates, or a Zenodo/Figshare manifest gap exists upstream, the ingest writes a structured `video_gap` record. Artifact records point to thumbnails, keyframes, preview clips, and frame manifests under `raw/video_atoms/`. Motion-table rows become queryable `behavior` records with behavior type, life stage, sex, assay, stimulus, arena, frame/time range, track ID, coordinates, confidence where supplied, and a source video asset join when the table can be matched to an indexed asset. The default opt-in discovery sweep covers PMC OA, Dryad, Mendeley, OSF, Zenodo, Figshare, institutional Dataverse-style search, and indexed paper-supplement URLs with bounded candidates, queryable gaps, and one queryable `video_sweep` receipt record per repository. The completion gate requires those sweep receipts to preserve coverage method, exact query or local scan label, request URL or raw/local input source, page size, page count, page/cursor completeness, candidate limit, and limit status, so a repository is not treated as covered just because one asset or gap row exists. It also rejects stale unexpanded archive gaps and broken motion/archive asset references. The May 25, 2026 hosted refresh installed 91 video assets, 21 verified mirrored videos, 84 inspectable artifacts, 45,574 motion rows, and 271 video gaps.

## Traits

Trait records preserve individual measured phenotype or life-history rows, especially temperature-dependent measurements useful for behavior, ecology, and vector-competence questions.

Sources:

- `aedes_vectorbyte_traits`: VectorByte/VecTraits public search and dataset JSON rows where source fields identify `Aedes aegypti`, parsed into `traits` records with trait value, unit, temperature, stage, sex, habitat, location, citation, DOI, and raw JSON provenance.

VectorByte trait rows cite saved VBD Hub search JSON and VecTraits dataset JSON under `raw/vectorbyte_traits/`, with locators such as `vectraits_dataset_474.json#results/89092`. Trait questions mentioning VectorByte, VecTraits, fecundity, longevity, development time, body size, thermal response, temperature traits, or transmission potential prefer this lane before adjacent behavior, ecology, vector-competence, or literature records.

## Hosted Boundary

Hosted Ask Insects uses the same source lanes. The difference is location: parsed artifacts live on the Google VM under `/home/josh/ask-insects/artifacts/mosquito-v1/`, and the local CLI asks the hosted API to ingest or query those artifacts.

Hosted GBIF and iNaturalist ingests stage a copy of the active artifact directory, fetch into the staging copy, replace only the matching source rows in SQLite, write receipts, and activate the staged directory only after the refresh succeeds. This keeps the old server database readable during long pulls.

## Genomics

Genome assembly metadata, GFF annotation features, gene rows, transcript rows, and protein FASTA headers.

Sources:

- `ncbi_datasets_genome`: parsed NCBI Datasets package for `Aedes aegypti` assembly `GCF_002204515.2`.
- `ncbi_biosamples`: NCBI BioSample metadata for `Aedes aegypti` samples, strains, isolates, collection dates, geographies, tissues, isolation sources, organizations, and linked SRA identifiers when present, currently complete for the hosted NCBI count of 20,656 fetched and reported records.
- `aedes_ncbi_snp_variation`: NCBI dbSNP organism-query audit for `Aedes aegypti` variation records, indexed as returned `genome_features` records or as an explicit source-gap record when dbSNP returns zero records.
- `aedes_population_genomics`: bounded NCBI BioProject metadata records returned by `Aedes aegypti` population-genomics queries, indexed into `genome_features` with BioProject accession, title, description, data type, target scope, submitter, registration date, and raw ESummary locator.
- `vectorbase_aedes_genomics`: official VectorBase/VEuPathDB `AaegyptiLVP_AGWG` current-release GFF, annotated protein FASTA, annotated CDS FASTA, annotated transcript FASTA, GO GAF, codon usage, identifier event history, NCBI LinkOut downloads, OrthoMCL CURRENT corePairs ortholog, coortholog, and inparalog rows, and OrthoMCL release 6.21 orthogroup rows parsed into genes, transcripts, proteins, CDS sequence summaries, transcript sequence summaries, GO annotation, codon usage, ID history, current-ID resolution, cross-reference records, first-pass pair genome_features records, and orthogroup membership genome_features records.
- `aedes_expression_omics`: bounded, paginated NCBI GEO/SRA expression, RNA-seq, and transcriptome metadata parsed into GEO dataset/sample records, SRA run records, and queryable source-gap records for raw SRA reanalysis, count matrices, normalized expression matrices, and differential-expression outputs not yet indexed.
- `aedes_uniprot_proteins`: bounded UniProtKB protein and UniProt proteome metadata for taxonomy 7159, parsed into function, cross-reference, and proteome records in the `proteins` lane.

The genomics lane indexes useful atoms, not every DNA base. Raw NCBI package files remain the source artifacts. SQLite rows cite locators such as `assembly_data_report.jsonl#line/1`, `genomic.gff#line/42`, or `protein.faa#protein/XP_001`.

NCBI BioSample rows cite saved ESummary batches under `raw/ncbi_biosamples/`. The current hosted receipt is complete for the current NCBI count: 20,656 fetched records out of 20,656 reported, with zero hosted gaps. If a future NCBI count rises beyond a bounded refresh, Ask Insects writes a structured `biosample_limit_applied` source gap.

NCBI dbSNP variation-audit rows cite saved ESearch and ESummary JSON under `raw/ncbi_snp_variation/`. The current `"Aedes aegypti"[Organism]` dbSNP query returns zero records, so source `aedes_ncbi_snp_variation` currently contributes a queryable `genome_features` gap record with reason `ncbi_snp_no_aedes_records`. That gap is the source truth until dbSNP exposes Aedes variation records or another mapped variant source is added.

VectorBase rows cite saved files under `raw/vectorbase_genomics/`, with locators such as `VectorBase-68_AaegyptiLVP_AGWG.gff#line/42`, `VectorBase-68_AaegyptiLVP_AGWG_AnnotatedProteins.fasta#line/12`, `VectorBase-68_AaegyptiLVP_AGWG_AnnotatedCDSs.fasta#line/12`, `VectorBase-68_AaegyptiLVP_AGWG_AnnotatedTranscripts.fasta#line/12`, `VectorBase-CURRENT_AaegyptiLVP_AGWG_GO.gaf.gz#line/200`, `VectorBase-68_AaegyptiLVP_AGWG_CodonUsage.txt#line/2`, `VectorBase-68_AaegyptiLVP_AGWG_ids_events.tab#line/1`, `VectorBase-68_AaegyptiLVP_AGWG_NCBILinkout_Nucleotide.xml#link/1`, `orthologs.txt.gz#line/200`, `coorthologs.txt.gz#line/200`, `inparalogs.txt.gz#line/200`, or `groups_OrthoMCL-6.21.txt.gz#line/200`. OrthoMCL pair rows come from CURRENT `corePairs_OrthoMCL-CURRENT` files and are included only when either side starts with `aaeg-old|AAEL`; they preserve `relationship_type`, `left_id`, `right_id`, `score`, and raw-file line provenance in the old Aedes AAEL namespace. Orthogroup rows come from `groups_OrthoMCL-6.21.txt.gz` and are included when a group member starts with `aaeg|AAEL` or `aaeg-old|AAEL`; they preserve `orthogroup_id`, Aedes member ID, Aedes gene ID, Aedes-member count, group-member count, sample members, and raw-file line provenance. Identifier-history rows preserve every ID event, and current-ID resolution rows are emitted for ID events with a successor identifier. VectorBase-specific questions, AAEL IDs, CDS or transcript sequence questions, GO annotation, codon usage, identifier-history, current-ID resolution, LinkOut questions, first-pass OrthoMCL pair questions, and orthogroup questions prefer this source over generic NCBI genome records.
Expression-omics rows cite saved GEO/SRA ESummary JSON under `raw/expression_omics/`, with locators such as `gds_esummary.json#result/200000001`, `gds_esummary_0002.json#result/200000101`, or `sra_esummary_0003.json#result/44630001/run/1`. ESearch pages and ESummary batches are preserved separately when a bounded refresh spans multiple NCBI requests. The May 25, 2026 hosted refresh installed 420 expression data records: 120 GEO records and 300 SRA run records, with two limit-applied gaps preserving the larger NCBI result frontier. Raw SRA reanalysis, count matrices, normalized expression matrices, and differential-expression outputs are explicit `source_boundary.json` source-gap records. UniProt rows cite saved UniProt REST JSON under `raw/uniprot_proteins/`, with locators such as `uniprotkb_aedes_aegypti.json#results/1` and `uniprot_proteomes_aedes_aegypti.json#results/1`.
Population-genomics rows cite saved NCBI BioProject ESearch and ESummary JSON under `raw/aedes_deep_sources/population_genomics/`, with locators such as `ncbi_bioproject_population_genomics_summary.json#result/PRJNA1090933`. This lane is project metadata and study discovery, not variant-table extraction.

Current genomics lanes:

- `genome_assemblies`
- `genes`
- `transcripts`
- `genome_features`
- `proteins`
- `expression`
- `dna_barcodes`
- `biosamples`

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
- `aedes_olfaction_literature`: a bounded PubMed ESearch/ESummary audit lane for `Aedes aegypti` olfaction, odor, odorant, chemosensory, antenna, antennal, Orco, odorant receptor, and ionotropic receptor papers from 2020 onward. Each PubMed candidate becomes one `literature` record with `coverage_status`, `matched_record_ids`, raw ESummary provenance, and optional legal Unpaywall full-text plus figure-caption units when a direct open XML, PDF, HTML, or text file is available.
- `aedes_crossref_literature_audit`: a bounded Crossref `/works` cursor audit lane for `Aedes aegypti` literature since 2020. Each material Crossref work candidate becomes one `literature` record with DOI, publisher, container title, issued date, Crossref member, reference count, license links when supplied, `coverage_status`, `matched_record_ids`, and raw Crossref page provenance.
- `mosquito_repellent_literature`: a bounded PubMed plus Crossref public-metadata lane for mosquito repellent research since 2020. Each deduped article candidate becomes one `literature` record with PMID or DOI when supplied, candidate source, matched repellent terms, matched mosquito terms, `coverage_status`, `matched_record_ids`, and raw PubMed or Crossref locator provenance.
- `mosquito_repellent_external_discovery`: a bounded external-discovery lane for mosquito repellent research since 2020. It indexes OpenAlex, Europe PMC, AGRICOLA through Europe PMC, Semantic Scholar, Crossref posted-content preprints, DataCite, Zenodo, and Figshare metadata as `literature` or `datasets` records, and indexes explicit source-gap records for native bioRxiv/medRxiv text search, PatentsView/USPTO patent APIs, CABI, and Google Scholar as `literature` or `patents` records.

OpenAlex is the canonical source for discovery and record identity. PubMed E-utilities are enrichment only, used for PMID-backed metadata. Unpaywall is enrichment only, used as the legal open full-text resolver. The lane writes only legal direct XML/PDF/HTML/text chunks and parsed figure captions to `literature_fulltext_units`; it must not use Sci-Hub, private cookies, institutional scraping, or landing pages that are not direct open files.

The olfaction audit lane does not replace the broader OpenAlex lane. It is a source-grade coverage check for a high-value subdomain: PubMed defines the bounded candidate set, Ask Insects compares each PMID against existing literature rows by DOI and normalized title, and any paper not already matched is still queryable as PubMed metadata. Raw PubMed ESearch pages, ESummary batches, Unpaywall payloads, direct full-text files, and `coverage_audit.json` are saved under `artifacts/mosquito-v1/raw/aedes_olfaction_literature/`. Structured gaps preserve PubMed fetch failures, result-limit frontiers with `aedes_olfaction_result_limit_applied`, comparison runs where the artifact has no canonical `aedes_literature_openalex` rows, missing DOI or Unpaywall email, no legal direct full-text URL, and full-text fetch or parse failures. The May 25, 2026 hosted ingest installed 183 PubMed olfaction candidates, matched 156 against canonical OpenAlex literature rows, added 27 PubMed-metadata-only candidates, and recorded zero hosted gaps before full-text enrichment.

The Crossref audit lane complements OpenAlex and PubMed by checking publisher DOI/member metadata. It saves Crossref cursor pages under `artifacts/mosquito-v1/raw/aedes_crossref_literature_audit/`, filters candidates to source-provided material `Aedes aegypti` metadata, and compares each work against existing literature rows by DOI and normalized title. Structured gaps preserve Crossref fetch failures, result-limit frontiers with `aedes_crossref_result_limit_applied`, no material Aedes candidates, and comparison runs where the artifact has no canonical `aedes_literature_openalex` rows.

The mosquito repellent literature lane is broader than the Aedes-only discovery lane. It uses PubMed Title/Abstract terms plus Crossref publisher metadata queries for mosquito repellents, repellency, spatial repellents, topical repellents, DEET, picaridin, icaridin, IR3535, PMD, citronella, essential oils, and plant-extract repellent research. Raw PubMed pages, Crossref pages, and `coverage_audit.json` are saved under `artifacts/mosquito-v1/raw/mosquito_repellent_literature/`. Structured gaps preserve PubMed search/summary failures, PubMed and Crossref result-limit frontiers, no-candidate runs, and comparison runs where the artifact has no canonical `aedes_literature_openalex` rows. This is a source-grade public metadata lane, not a claim that every publisher full text has been parsed.

The external repellent discovery lane adds breadth beyond PubMed and Crossref journal-article metadata. Raw pages are saved under `artifacts/mosquito-v1/raw/mosquito_repellent_external_discovery/`, and each record stores `source_family`, `artifact_type`, DOI or external ID when exposed, source URL, publication date, venue or repository, matched terms, and raw locator provenance. Structured gaps include `semantic_scholar_fetch_failed`, `biorxiv_medrxiv_no_text_search_api`, `patentsview_migrated_or_unavailable_json_api`, `uspto_open_data_portal_requires_api_access`, `cabi_no_public_metadata_api_configured`, and `google_scholar_no_public_api`. Those gap rows are intentionally queryable so Ask Insects can say exactly which high-value source surfaces are still blocked.

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

This lane is source `aedes_literature_facets`. It does not replace dedicated behavior, resistance, vector-competence, ecology, or public-health databases. It creates an immediate source-backed query plane from the indexed Aedes literature while those deeper external lanes are built. The coverage ledger marks these domains as partial source-grade when the facet records are installed and ask-surface wired.

## Pathogen And Vector Competence

Pathogen identity records and vector-competence evidence for `Aedes aegypti`.

Sources:

- `aedes_literature_facets`: literature-derived vector-competence facets while deeper assay extraction is built.
- `aedes_pathogen_taxonomy`: NCBI Taxonomy summary records for dengue, Zika, chikungunya, yellow fever, West Nile, and Mayaro virus as pathogen identity anchors.
- `aedes_vector_competence_assays`: deterministic assay-candidate extraction from indexed Aedes literature records, legal full-text units, and schema-validated parsed `aedes_extracted_facts` supplement table rows.

The pathogen taxonomy lane saves NCBI E-utilities taxonomy summary JSON under `raw/pathogen_taxonomy/`, indexes one `vector_competence` row per configured pathogen, preserves the raw taxonomy summary in `record_payloads`, and cites locators such as `raw/pathogen_taxonomy/aedes_pathogen_taxonomy_esummary.json#taxonomy/64320`. It is an identity layer, not a substitute for structured extraction of infection, dissemination, and transmission assay tables.

The assay-candidate lane reads source-grade `aedes_literature_openalex` records and legal `literature_fulltext_units`, then emits `vector_competence` records when a text unit contains an Aedes-relevant pathogen plus assay context such as infection, dissemination, transmission, dose, temperature, tissue, strain, population, or timepoint. It also reads parsed `aedes_extracted_facts` vector-competence supplement table rows and promotes rows that have a supported pathogen, a non-empty table row, and infection, dissemination, or transmission evidence. Payloads preserve the detected pathogen, matched terms, fields, temperature values, dose values, source paper ID, full-text unit ID, extracted-fact record ID, table headers, table row, row index, and provenance. Promoted table rows are schema-validated parsed atoms, not human-validated assay results.

## Cross-Lane Extracted Facts

`aedes_extracted_facts` is a deterministic derived source over indexed Aedes literature records, `record_payloads`, legal `literature_fulltext_units`, Europe PMC, PMC, and Figshare supplement metadata, and bounded public supplement files. It emits one queryable record per detected candidate fact into `vector_competence`, `resistance`, `behavior`, `ecology`, and `public_health`, one `literature` record per supplement manifest, and one parsed fact per supported supplement table row.

Payloads preserve `fact_type`, schema version, matched fields, source paper ID, full-text unit ID when available, supplement metadata, table row values when parsed, evidence text, confidence, extraction method, and source provenance. Confidence values are intentionally conservative: `candidate` for text-derived facts, `manifest` for supplement pointers, and `parsed` for supported `.csv`, `.tsv`, `.xlsx`, `.docx`, XML table, or simple HTML table rows. The lane makes cross-domain paper facts queryable now, but it is not a claim that every PDF supplement, image table, workbook variant, or archive has been parsed or human validated.

## Insecticide Resistance

Insecticide susceptibility, resistance phenotype, mechanism, mutation, assay protocol, geography, time, and reference records for `Aedes aegypti`.

Sources:

- `irmapper_aedes`: live IR Mapper Aedes JSON endpoint, filtered by default to `Aedes aegypti` and `Ae. aegypti`.
- `who_malaria_threats_resistance_audit`: WHO Malaria Threats Map global insecticide-resistance database audit through the public `FACT_PREVENTION_VIEW` endpoint, indexed as returned Aedes resistance rows or as a queryable Aedes source gap when the public species filter returns no Aedes records.
- `aedes_resistance_markers`: deterministic kdr, VGSC, and metabolic-resistance marker extraction from indexed Aedes literature records and legal full-text units.
- `aedes_resistance_table_rows`: schema-validated promotion of parsed Aedes resistance supplement rows from `aedes_extracted_facts` into table-row resistance records.
- `aedes_who_resistance_guidance`: WHO Aedes insecticide-resistance method and discriminating-concentration pages indexed at guidance-page grain with method terms such as test procedures, filter paper, bottle bioassays, larvae, adults, pyriproxyfen, and Bti when present.
- `aedes_literature_facets`: literature-derived resistance facets while deeper source lanes are built.
- `aedes_extracted_facts`: cross-lane candidate facts and supplement manifests from indexed Aedes literature, payload supplement metadata, and legal full-text units.

The IR Mapper lane indexes one SQLite `resistance` row per matching public API row, stores the raw IR Mapper row in `record_payloads`, and cites a provenance locator such as `raw/irmapper/Aedes_aegypti.json#row/1`. It preserves source fields for country, locality, coordinates, collection year, developmental stage, test method, insecticide class, insecticide, dosage, mode of action, mortality, resistance status, mechanism, mutation frequency, reference, and source URL when present.

The resistance-marker lane indexes one SQLite `resistance` row per marker candidate, stores marker ID, marker class, gene or family, matched aliases, context terms, insecticide terms, source paper ID, and full-text unit ID when present in `record_payloads`, and cites provenance back to `records#<paper_id>` plus `literature_fulltext_units#<unit_id>` when legal full text is available. The May 24, 2026 hosted ingest installed 6,449 marker records with zero marker-source gaps. It covers candidate marker evidence such as kdr/VGSC substitutions and metabolic-resistance genes or families.
The resistance-table lane indexes one SQLite `resistance` row per parsed supported-format table row from `aedes_extracted_facts`, stores insecticide terms, marker or mutation terms, assay terms, metric fields, table headers, table row values, source extracted-fact ID, source paper ID, and validation status in `record_payloads`, and cites provenance back to `aedes_extracted_facts#<record_id>`, `records#<paper_id>`, and the raw supplement row locator. Records are `parsed_table_schema_validated` and `human_validated: false`; if no row passes validation, the lane installs a queryable `source_gap` resistance record. Human-reviewed genotype-frequency and haplotype curation remains follow-on work.
WHO resistance-guidance rows cite saved raw HTML under `raw/aedes_deep_sources/who_resistance_guidance/`. Method questions that mention WHO, bioassays, or discriminating concentrations prefer this lane before general IR Mapper phenotype rows.

## Ecology

Habitat, seasonality, range, and distribution records for `Aedes aegypti`.

Sources:

- `aedes_occurrence_ecology`: derived country, country-month, seasonality, range, and public habitat summaries from indexed GBIF, iNaturalist, and Mosquito Alert observation payloads.
- `aedes_observation_climate_join`: derived WorldClim v2.1 10-minute bioclim raster samples joined to coordinate-bearing GBIF, iNaturalist, and Mosquito Alert Aedes aegypti observations, with annual mean temperature, annual precipitation, raw ZIP locators, and upstream observation provenance.
- `aedes_worldclim_climate`: WorldClim historical and monthly climate source pages plus optional bounded 10-minute bioclim raster samples joined to global-compendium occurrence coordinates.
- `harvard_dataverse_aedes_suitability`: Harvard Dataverse Aedes aegypti dengue-transmission suitability and risk raster file manifests, with dataset DOI, file DOI, file ID, filename, content type, byte size, checksum, scenario terms, license, raw Dataverse JSON locators, and explicit file-download gaps when the binary is not public-downloadable.
- `aedes_global_compendium_occurrence`: global Aedes occurrence compendium rows filtered to `Aedes aegypti`, exposed in the observations lane and preferred for compendium-specific ecology questions.
- `aedes_literature_facets`: literature-derived ecology facets while deeper climate, land-use, suitability, breeding-site, and surveillance lanes are built.

The occurrence ecology lane indexes one SQLite `ecology` row per country summary, country-month summary, and public iNaturalist habitat-field summary. Payloads store aggregation type, country, month when applicable, source counts, observation count, sample input record IDs, sample URLs, coordinate count, bounding box, and observed date range. Provenance points to the derived observation join over `gbif_api`, `inaturalist_api`, and `mosquito_alert_gbif`. The source id is `aedes_occurrence_ecology`, and it is refreshed with `scripts/ingest_occurrence_ecology.py`. The May 24, 2026 hosted ingest installed 1,985 occurrence ecology records from 88,065 Aedes observation inputs. Land-use layers, model outputs, and surveillance completeness remain explicit source gaps.
The observation climate-join lane uses source id `aedes_observation_climate_join` and is refreshed with `scripts/ingest_observation_climate.py` or `python3 -m askinsects ingest-observation-climate-join --limit 1000`. It samples the local WorldClim ZIP at `raw/aedes_deep_sources/worldclim/wc2.1_10m_bio.zip` for bounded coordinate-bearing observation records. Payloads store source observation record ID, source observation source, observed date, country/place, coordinates, `bio1_annual_mean_temperature_c`, `bio12_annual_precipitation_mm`, raw ZIP path, raster URL, and source observation provenance. Missing ZIPs, no coordinate-bearing observations, sampling failures, and applied limits are explicit structured gaps.
WorldClim rows cite saved raw HTML under `raw/aedes_deep_sources/worldclim/`. When `--worldclim-sample-limit` is greater than zero, the ingest also mirrors the WorldClim v2.1 10-minute bioclim ZIP and writes one `ecology` record per sampled compendium occurrence with annual mean temperature and annual precipitation values. If sampling is disabled or fails, that is recorded as a structured WorldClim gap instead of being hidden. The May 25, 2026 hosted refresh installed `500` WorldClim raster-sample rows, bringing `aedes_worldclim_climate` to `502` records and the hosted ecology lane to `9,875` records.
Harvard Dataverse suitability rows cite saved search and dataset-detail JSON under `raw/harvard_dataverse_suitability/`. The ingest indexes file manifests, not raster pixels, so it can preserve suitability model outputs without pretending to have decoded every GeoTIFF. If Dataverse metadata says `canDownloadFile` is false, Ask Insects writes a queryable `dataverse_file_download_not_public` gap while keeping the file DOI, dataset DOI, byte size, checksum, license, and access locator.

## Action Notes

Source-backed next steps for scientists, grounded in indexed observations and literature.

GBIF V1 does not create action notes by itself. It strengthens the observation and taxonomy evidence that action answers can cite.

iNaturalist V1 does not create action notes by itself. It strengthens photo-backed observation evidence that action answers can cite.

## Operational Public Health

Operational guidance, vector-control recommendations, disease-prevention pages, and community action messages connected to `Aedes aegypti`.

Sources:

- `aedes_literature_facets`: literature-derived public-health facets while deeper operational lanes are built.
- `aedes_public_health_guidance`: official WHO, PAHO, CDC, and ECDC guidance pages parsed into `public_health` records with raw HTML receipts and source URLs.
- `aedes_wolbachia_interventions`: World Mosquito Program Wolbachia method, deployment progress, and Yogyakarta trial evidence pages parsed into `public_health` intervention-evidence records with source-mentioned metrics and raw HTML receipts.
- `aedes_paho_dengue_surveillance`: official PAHO dengue situation report, dashboard landing pages, and PAHO/EIH Core Indicators ZIP/CSV parsed at report, subregion, serotype, figure/table, dashboard locator, and annual country/territory dengue-case row grain with raw receipts and PAHO locators.
- `aedes_who_dengue_surveillance`: official WHO dengue surveillance pages, WER global update pages, WPRO situation-update links, archive links, publication download locators, and WHO Western Pacific Health Data Platform dengue dashboard locators parsed at page/report/dashboard-locator grain.
- `aedes_cdc_dengue_surveillance`: official CDC current-year and historic dengue ArboNET pages, CDC WCMS visualization JSON configs, linked CDC CSV datasets, and ArboNET limitations parsed at page, config, CSV-row, and limitation grain.

The guidance lane is source-grade at the guidance-page grain: each page is mapped, fetched, raw-saved, indexed, payload-preserved, and queryable through public-health questions. The default set includes official dengue, Zika, Aedes life-cycle, vector-control, travel-medicine, Wolbachia, community prevention, and ECDC Aedes aegypti species-factsheet pages. The Wolbachia intervention lane is source-grade at the WMP page grain and is preferred for World Mosquito Program, Wolbachia, and Yogyakarta intervention-evidence questions. The PAHO dengue surveillance lane adds report-grain surveillance records for the Region of the Americas, including weekly and year-to-date indicators, subregional case-change notes, serotype circulation notes, figure/table media locators, dashboard page or iframe locator records, and stable machine-readable PAHO/EIH Core Indicators annual country/territory dengue-case CSV rows. The WHO dengue surveillance lane adds WPRO situation-update and archive locators, WER/global-update page records, publication download locators, parsed headline metrics when present in page HTML, and Western Pacific Health Data Platform dashboard locators. The CDC dengue surveillance lane adds U.S. current and historic ArboNET records from CDC-hosted CSVs discovered through the official visualization configs, plus searchable limitation records. PAHO/PLISA and WHO dashboard locator records are queryable, but country/time dashboard cells remain source gaps until a stable weekly unauthenticated CSV, JSON, XLSX, ZIP, or API endpoint is available or explicit authorized access is obtained.
