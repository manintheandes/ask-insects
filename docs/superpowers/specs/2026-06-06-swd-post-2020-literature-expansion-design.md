# SWD Post-2020 Literature Expansion Design

## Goal

Increase the hosted Ask Insects `Drosophila suzukii` paper corpus for papers from 2020 onward. The first hosted expansion reported 1,136 exact OpenAlex SWD paper records, and the next target is at least 2,000 additional OpenAlex search-identified paper candidates across Ask Monarch-related topic areas while preserving an exact-versus-candidate confidence split.

## Boundary

This change expands paper discovery. It does not claim all SWD papers in the world, scrape publisher pages, bypass paywalls, or parse every supplement file format. The canonical answer surface remains hosted Ask Insects. Local code and tests are the implementation surface used to prepare a hosted refresh.

The first expansion target is `drosophila_suzukii_core`, because it owns OpenAlex literature rows. Exact title/abstract matches remain canonical. Broader all-field OpenAlex `search` results are stored as `openalex_search_candidate` records with their search mode, topic group, and candidate status in payloads. The PubMed lane remains an audit and reconciliation lane. It can expose PubMed-only candidates, but it should not silently replace OpenAlex paper records.

## Discovery Terms

The exact OpenAlex query searches the scientific name and common-name aliases in title and abstract:

- `Drosophila suzukii`
- `spotted wing drosophila`
- `spotted-wing drosophila`

The implementation must deduplicate works by OpenAlex work id, DOI, and normalized title when available. Accepted records must preserve which search term found them so later audits can explain why a paper entered the corpus.

The broader OpenAlex search-candidate layer should cover repellency, susceptibility/resistance, assay safety, biocontrol, behavior, omics, monitoring/IPM, crop context, ecology/distribution, and broad SWD search.

## Data Flow

1. `scripts/ingest_drosophila_suzukii.py` calls `fetch_drosophila_suzukii_records`.
2. `fetch_drosophila_suzukii_records` calls the shared OpenAlex literature fetcher with SWD aliases and a higher cap.
3. The shared literature fetcher runs one bounded OpenAlex cursor query per search term.
4. It deduplicates works before writing `EvidenceRecord` rows.
5. `drosophila_suzukii_core` retargets records to SWD provenance and writes source coverage.
6. Follow-on supplement audit lanes can then audit the expanded paper set.

## Acceptance Criteria

- The core SWD ingest can fetch OpenAlex literature using exact title/abstract aliases and broader OpenAlex search candidates from 2020 onward.
- Duplicate OpenAlex works returned by multiple aliases are stored once.
- Record payloads preserve discovery search terms, search mode, topic group, candidate status, and inclusion paths.
- The default SWD literature cap is high enough to exceed the current 1,136 hosted paper boundary by at least 2,000 records when upstream sources expose enough candidates.
- Tests prove multi-term discovery and deduplication without calling the network.
- Docs tell future agents to widen paper discovery before judging supplement coverage and to report exact versus candidate rows separately.

## Verification

Run:

```bash
python3 -m pytest tests/test_drosophila_suzukii_source.py tests/test_ingest_drosophila_suzukii.py tests/test_drosophila_suzukii_pubmed_literature_source.py tests/test_ingest_drosophila_suzukii_pubmed_literature.py -q
python3 scripts/verify_complete.py
```

After deployment or hosted refresh, verify with:

```bash
ask-insects ask --hosted "How many total spotted wing drosophila paper records since 2020 are in Ask Insects?" --json
```
